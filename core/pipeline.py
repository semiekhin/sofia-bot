"""
core/pipeline.py — единый пайплайн Sofia-GPT v3.0
Analyzer → RAG → Generator

НЕ делает: process_message(), save_message(), Observer, Bitrix, send.
Эти обязанности остаются в транспортах.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

import os

from openai import OpenAI

from rag_module import search_examples, format_examples_for_prompt
from sofia_prompt_v2 import get_system_prompt_v2, format_state_summary
from config.source_objects import load_object_context, get_object_by_key

log = logging.getLogger("sofia.pipeline")
vd = logging.getLogger("VOICE_DIAG")
vd.setLevel(logging.DEBUG)

RAG_EXAMPLES_COUNT = 10

# Voice LLM config — Groq primary, OpenAI fallback
VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "groq")
VOICE_MODEL_GROQ = os.getenv(
    "VOICE_MODEL_GROQ", "meta-llama/llama-4-scout-17b-16e-instruct"
)
VOICE_MODEL_OPENAI = os.getenv("VOICE_MODEL_OPENAI", "gpt-5.4-mini")

# Groq client (OpenAI-compatible)
_groq_client: Optional[OpenAI] = None


def _get_groq_client() -> Optional[OpenAI]:
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            _groq_client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )
    return _groq_client


VOICE_PROMPT_ADDON = """
Ты сейчас разговариваешь ГОЛОСОМ по телефону. Строгие правила:
- Отвечай 1-2 предложениями максимум
- Если клиент задаёт прямой вопрос — СНАЧАЛА ответь на него, потом можешь задать уточняющий вопрос
- Не уворачивайся от вопросов контрвопросами — это раздражает
- Никаких списков, буллетов, markdown, ссылок
- Не перечисляй больше 2 вариантов за раз
- Используй разговорный русский, короткие фразы
- Подтверждай что услышал: "Понял, значит вас интересует..."
- НИКОГДА не используй латиницу, URL, email, @юзернеймы — клиент слушает голосом и не видит текст
- Пиши "Оазис Эстэйт" вместо "Oazis Estate", "наш сайт" вместо URL, "наш эксперт" вместо @username
"""

ANALYZER_PROMPT = """Ты — аналитик диалогов продаж недвижимости.

Прочитай диалог и последнее сообщение клиента. Определи:
1. На какой вопрос/тему отвечает клиент?
2. Какой сейчас этап продажи?
3. Какие примеры из базы помогут менеджеру ответить?

ЭТАПЫ:
- GREETING — приветствие, начало диалога
- ACTUALIZATION — актуализация интереса холодного лида (не помнит заявку, давно оставлял, спрашивает "кто вы?", "какой сайт?")
- QUALIFICATION — выясняем цель, бюджет, сроки, способ оплаты
- MEETING — предлагаем созвон
- OBJECTION — клиент возражает (дорого, подумаю, не сейчас, пришлите материалы)
- CLOSING — завершение (договорились о созвоне, отправляем подборку, прощаемся)

Ответь СТРОГО в формате JSON:
{
  "client_intent": "краткое описание что имеет в виду клиент",
  "stage": "ОДИН ИЗ ЭТАПОВ",
  "rag_query": "что искать в базе примеров (на русском, 3-7 слов)"
}"""


@dataclass
class PipelineResult:
    answer: Optional[str]
    stage: str
    dialog_finished: bool = False
    analysis: Optional[dict] = field(default=None)


# OpenAI client — инициализируется лениво
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        import os

        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


async def run_pipeline(
    *,
    user_id: int,
    user_message: str,
    user_name: str,
    history: list,
    state_manager,
    channel: str,
    was_offline: bool = False,
    voice_mode: bool = False,
) -> PipelineResult:
    """
    Единый пайплайн: Analyzer → RAG → Generator.

    Args:
        user_id: ID пользователя (формула зависит от канала)
        user_message: Текст сообщения (или склеенные сообщения)
        user_name: Имя для логов
        history: [{"role": "user"/"assistant", "content": "..."}]
        state_manager: StateManager instance
        channel: "telegram" | "web" | "max" | "whatsapp"
        was_offline: True если сообщения были склеены (bot_server)

    Returns:
        PipelineResult с ответом, stage, флагом dialog_finished
    """
    client = _get_client()
    tag = channel.upper()

    state = state_manager.get_state(user_id)
    history_text = "\n".join(
        f"{'София' if m['role'] == 'assistant' else 'Клиент'}: {m['content']}"
        for m in history[-20:]
    )
    state_summary = format_state_summary(state) if state else "Новый клиент"

    # ═══════════════════════════════════════════════════════════════
    # Source routing: skip analyzer при source_object + ≤2 сообщений
    # ═══════════════════════════════════════════════════════════════
    user_msg_count = sum(1 for m in history if m["role"] == "user")
    skip_analyzer = False

    if state and state.source_object and user_msg_count <= 2:
        rag_stage = "GREETING"
        rag_query = "приветствие клиент с сайта интерес к объекту"
        skip_analyzer = True
        log.info(
            f"🏷️ [{tag}] Source routing: force stage=GREETING "
            f"(user_msgs={user_msg_count}, object={state.source_object})"
        )

    # ═══════════════════════════════════════════════════════════════
    # ШАГ 1: LLM-Analyzer
    # ═══════════════════════════════════════════════════════════════
    analysis = None

    analyzer_input = f"""ИСТОРИЯ ДИАЛОГА:
{history_text if history_text else "Диалог только начался"}

НОВОЕ СООБЩЕНИЕ КЛИЕНТА:
{user_message}

ЧТО ИЗВЕСТНО О КЛИЕНТЕ:
{state_summary}"""

    # Дефолты (используются если Analyzer пропущен)
    rag_stage = "QUALIFICATION"
    rag_query = user_message

    if not skip_analyzer and not voice_mode:

        if state and state.source_object:
            analyzer_input += (
                "\n\nВАЖНО: Клиент пришёл с сайта объекта ("
                + state.source_object
                + "). Первые сообщения — НЕ возражения, а начало диалога."
            )

        try:
            log.info(f"🧠 [{tag}] Analyzer запрос...")
            analyzer_response = await asyncio.to_thread(
                client.responses.create,
                model="gpt-5.2",
                instructions=ANALYZER_PROMPT,
                input=analyzer_input,
                **({"reasoning": {"effort": "medium"}} if not voice_mode else {}),
                max_output_tokens=1000,
            )
            analyzer_text = analyzer_response.output_text or ""
            json_match = re.search(r"\{[^}]+\}", analyzer_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                rag_stage = analysis.get("stage", "QUALIFICATION")
                rag_query = analysis.get("rag_query", user_message)
                log.info(
                    f"🧠 [{tag}] Analyzer: stage={rag_stage}, "
                    f"query='{rag_query[:40]}...'"
                )
            else:
                log.warning(f"⚠️ [{tag}] Analyzer: JSON не найден, fallback")
        except Exception as e:
            log.warning(f"⚠️ [{tag}] Analyzer error: {e}, fallback")

    # ═══════════════════════════════════════════════════════════════
    # ШАГ 2: RAG
    # ═══════════════════════════════════════════════════════════════
    examples_prompt = ""
    rag_limit = RAG_EXAMPLES_COUNT
    examples = search_examples(rag_stage, rag_query, limit=rag_limit)
    if examples:
        examples_prompt = format_examples_for_prompt(examples)
        log.info(f"📚 [{tag}] RAG [{rag_stage}]: {len(examples)} примеров")

    # ═══════════════════════════════════════════════════════════════
    # ШАГ 3: LLM-Generator
    # ═══════════════════════════════════════════════════════════════
    system_prompt = get_system_prompt_v2(state_summary, examples_prompt)

    if voice_mode:
        system_prompt += VOICE_PROMPT_ADDON

    # Source routing: инъекция контекста объекта
    state = state_manager.get_state(user_id)
    if state and state.source_object:
        obj_config = get_object_by_key(state.source_object)
        if obj_config:
            object_context = load_object_context(obj_config)
            system_prompt += (
                f"\n\n═══ ТВОЙ ОБЪЕКТ: {obj_config['short_name']} ═══\n"
                f"{object_context}\n\n"
                f"Ссылка на презентацию: {obj_config['presentation_url']}\n"
                f"При запросе презентации — отправь эту ссылку клиенту."
            )
            if obj_config.get("prompt_addon"):
                system_prompt += f"\n\n{obj_config['prompt_addon']}"

    # was_offline: оборачиваем сообщение
    generator_message = user_message
    if was_offline:
        generator_message = (
            f"[Клиент написал несколько сообщений пока меня не было:\n"
            f"{user_message}\n]\n"
            f"Ответь на актуальный вопрос, можешь мягко извиниться "
            f"что ненадолго отходила."
        )

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": generator_message})

    try:
        log.info(f"🔄 [{tag}] Generator запрос для {user_name}...")
        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5.2",
            instructions=system_prompt,
            input=messages,
            **({"reasoning": {"effort": "high"}} if not voice_mode else {}),
            max_output_tokens=4000,
        )
        answer = response.output_text or ""

        log.info(
            f"📏 [{tag}] Generator: len={len(answer)}, "
            f"output_tokens={getattr(response.usage, 'output_tokens', '?')}"
        )

        # Проверка обрезки (пропускаем для voice — короткие ответы ложно срабатывают)
        if not voice_mode:
            try:
                stop_reason = (
                    getattr(response.output[-1], "stop_reason", None)
                    if response.output
                    else None
                )
                if stop_reason == "max_tokens" or (
                    len(answer) > 50
                    and not answer.rstrip().endswith(("?", "!", ".", ")", "»", '"'))
                ):
                    log.warning(
                        f"⚠️ [{tag}] ОБРЕЗКА! stop={stop_reason}, len={len(answer)}"
                    )
            except Exception as e:
                log.warning(f"⚠️ [{tag}] stop_reason check error: {e}")

        # [END] check
        dialog_finished = False
        if "[END]" in answer or "[end]" in answer:
            answer = answer.replace("[END]", "").replace("[end]", "").strip()
            state_manager.update_state(
                user_id, {"dialog_finished": True, "finish_type": "llm_end"}
            )
            dialog_finished = True
            log.info(f"🏁 [{tag}] LLM завершил диалог [END]")

        # Пустой ответ
        if not answer.strip():
            state = state_manager.get_state(user_id)
            if state and getattr(state, "dialog_finished", False):
                log.info(f"🔇 [{tag}] Диалог завершён, пустой ответ — молчим")
                return PipelineResult(
                    answer=None,
                    stage=rag_stage,
                    dialog_finished=True,
                    analysis=analysis,
                )
            answer = (
                "Подскажите, что для вас сейчас важнее — "
                "посмотреть варианты или обсудить условия?"
            )

        log.info(f"✅ [{tag}] Generator ответил")
        return PipelineResult(
            answer=answer,
            stage=rag_stage,
            dialog_finished=dialog_finished,
            analysis=analysis,
        )

    except Exception as e:
        log.error(f"❌ [{tag}] Generator error: {e}")
        return PipelineResult(
            answer="Простите, связь подвисла. Напишите ещё раз?",
            stage=rag_stage,
            dialog_finished=False,
            analysis=analysis,
        )


def sanitize_for_tts(text: str) -> str:
    """Убирает латиницу, URL, email — чтобы TTS не спотыкался."""
    text = text.replace("Oazis Estate", "Оазис Эстэйт")
    text = text.replace("oazis estate", "Оазис Эстэйт")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\S+@\S+\.\S+", "", text)
    text = re.sub(r"\S+\.ru\b", "", text)
    text = text.replace("@oazis_expert", "наш эксперт")
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"  +", " ", text).strip()
    return text


def _determine_voice_stage(state) -> str:
    """Определяет текущий этап скрипта по state."""
    if not state:
        return "GREETING"
    if getattr(state, "meeting_agreed", False):
        return "CLOSING"
    if getattr(state, "dialog_finished", False):
        return "CLOSING"
    if not getattr(state, "goal", None):
        return "GOAL"
    if not getattr(state, "budget", None):
        return "BUDGET"
    if not getattr(state, "payment_type", None):
        return "PAYMENT"
    # Все обязательные поля собраны — предлагаем созвон
    call_refused = getattr(state, "call_refused", False)
    if call_refused:
        return "MEETING_2"
    return "MEETING_1"


def _format_voice_state(state) -> str:
    """Компактная сводка state для голосового промпта."""
    if not state:
        return "Новый клиент, ничего не известно."
    parts = []
    if getattr(state, "goal", None):
        parts.append(
            f"Цель: {'инвестиция' if state.goal == 'investment' else 'для себя'}"
        )
    budget = getattr(state, "budget", None)
    if budget:
        try:
            parts.append(f"Бюджет: {int(budget) / 1_000_000:.0f} млн")
        except (ValueError, TypeError):
            parts.append(f"Бюджет: {budget}")
    if getattr(state, "payment_type", None):
        m = {"full": "полная", "mortgage": "ипотека", "installment": "рассрочка"}
        parts.append(f"Оплата: {m.get(state.payment_type, state.payment_type)}")
    if getattr(state, "location", None):
        parts.append(f"Локация: {state.location}")
    if getattr(state, "meeting_agreed", False):
        parts.append("Согласился на созвон")
    return ", ".join(parts) if parts else "Ничего не известно пока."


def _get_object_context(state) -> str:
    """Компактный контекст объекта для голоса."""
    if not state or not getattr(state, "source_object", None):
        return ""
    obj_config = get_object_by_key(state.source_object)
    if not obj_config:
        return ""
    if state.source_object == "atlantis":
        return (
            "\nОБЪЕКТ КЛИЕНТА: АК Атлантис, Крым, Новофёдоровка.\n"
            "Всесезонный wellness-курорт, термальный комплекс, собственный пляж, "
            "управление Космос Хотел Груп.\n"
            "Студии от 16.8 млн, однокомнатные от 20.7, двухкомнатные от 22.8 миллионов.\n"
            "Рассрочка и ипотека. Эскроу через Сбербанк. Доходность 5-17% годовых.\n"
            "Контакт клиента уже получен — НЕ спрашивай телефон. "
            "Предлагай время созвона."
        )
    full_context = load_object_context(obj_config)
    return "\nОБЪЕКТ КЛИЕНТА:\n" + full_context[:500]


# Текстовые числа → цифры (longest match first)
_NUMBER_WORDS = [
    ("двадцать пять", 25),
    ("пятьдесят", 50),
    ("сорок", 40),
    ("тридцать", 30),
    ("двадцать", 20),
    ("девятнадцать", 19),
    ("восемнадцать", 18),
    ("семнадцать", 17),
    ("шестнадцать", 16),
    ("пятнадцать", 15),
    ("четырнадцать", 14),
    ("тринадцать", 13),
    ("двенадцать", 12),
    ("одиннадцать", 11),
    ("десять", 10),
    ("девять", 9),
    ("восемь", 8),
    ("семь", 7),
    ("шесть", 6),
    ("пять", 5),
    ("четыре", 4),
    ("три", 3),
    ("два", 2),
]


def _parse_budget_from_text(text, budget_context=False):
    """
    Parse budget from text. Returns value in millions or None.

    Handles: "десять-пятнадцать миллионов", "10-15", "от 8 до 12",
    "десять пятнадцать", "около 10 миллионов", text numbers without
    "миллион" in budget context.
    """
    has_million = bool(re.search(r"миллион|млн", text))

    # Replace text numbers with digits (operates on a copy for number extraction)
    normalized = text
    for word, val in _NUMBER_WORDS:
        normalized = normalized.replace(word, str(val))

    # Extract all numbers (including hyphenated ranges like "10-15")
    # Pattern: digit-digit range or standalone digit
    range_match = re.search(r"(\d+)\s*[-–—]\s*(\d+)", normalized)
    if range_match:
        a, b = int(range_match.group(1)), int(range_match.group(2))
        if 1 <= max(a, b) <= 200:
            return max(a, b)

    # "от X до Y"
    from_to = re.search(r"от\s+(\d+)\s+до\s+(\d+)", normalized)
    if from_to:
        a, b = int(from_to.group(1)), int(from_to.group(2))
        if 1 <= max(a, b) <= 200:
            return max(a, b)

    # Standalone numbers
    nums = re.findall(r"\b(\d+)\b", normalized)
    nums = [int(n) for n in nums if 1 <= int(n) <= 200]

    if not nums:
        return None

    # With "миллион" — confident
    if has_million:
        return max(nums)

    # Without "миллион" — only in budget context
    if budget_context:
        return max(nums)

    # Two numbers close together (e.g. "десять пятнадцать") — likely a range
    if len(nums) >= 2 and all(3 <= n <= 100 for n in nums):
        return max(nums)

    return None


def _extract_state_from_context(user_message, history, current_state):
    """Rule-based извлечение state из сообщения клиента."""
    updates = {}
    text = user_message.lower()

    # Контекст из последнего сообщения бота
    last_bot_msg = ""
    for m in reversed(history):
        if m["role"] == "assistant":
            last_bot_msg = m["content"].lower()
            break
    budget_context = any(
        w in last_bot_msg for w in ["бюджет", "сумм", "рассматриваете"]
    )

    # Goal
    if not getattr(current_state, "goal", None):
        if any(w in text for w in ["инвестиц", "сдавать", "доход", "аренд", "вложен"]):
            updates["goal"] = "investment"
            updates["goal_confidence"] = "confirmed"
        elif any(w in text for w in ["для себя", "жить", "отдых", "семь"]):
            updates["goal"] = "personal"
            updates["goal_confidence"] = "confirmed"

    # Budget
    if not getattr(current_state, "budget", None):
        budget_val = _parse_budget_from_text(text, budget_context)
        if budget_val:
            updates["budget"] = budget_val * 1_000_000
            updates["budget_confidence"] = "confirmed"

    # Payment type
    if not getattr(current_state, "payment_type", None):
        if any(w in text for w in ["ипотек", "ипотеку"]):
            updates["payment_type"] = "mortgage"
            updates["payment_type_confidence"] = "confirmed"
        elif "рассрочк" in text:
            updates["payment_type"] = "installment"
            updates["payment_type_confidence"] = "confirmed"
        elif any(w in text for w in ["полн", "наличн", "сразу", "целиком"]):
            updates["payment_type"] = "full"
            updates["payment_type_confidence"] = "confirmed"

    # Meeting — только если София предлагала созвон в предыдущем сообщении
    meeting_context = any(
        w in last_bot_msg
        for w in ["созвон", "эксперт", "позвон", "встреч", "пятнадцать минут"]
    )
    if meeting_context and any(
        w in text for w in ["давайте созвон", "да, давайте", "давай", "созвонимся"]
    ):
        updates["meeting_agreed"] = True
    elif "созвонимся" in text:
        updates["meeting_agreed"] = True

    return updates


VOICE_SYSTEM_PROMPT = """Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. Ты уверенная, дружелюбная, с юмором и говоришь кратко — это телефонный звонок. Твоя цель — узнать что нужно клиенту и предложить пятнадцатиминутный созвон с экспертом. Если клиент не готов к созвону, то допускается договоренность на отправку подборки Говори в женском роде.

ЭТАП: {stage}
КЛИЕНТ: {state_summary}

ТВОИ ЗНАНИЯ (используй в ответах, не молчи):
- Доходность аренды: 8-15% годовых
- Покупка на стадии строительства: прирост 18-30%
- Цены от: Туапсе от 5 млн, Сочи и Крым от 9 млн, горный кластер (Архыз, Алтай) от 9 млн
- Оплата: рассрочка без банка 6-12 месяцев, ипотека, полная оплата
- Локации: у моря (Сочи, Туапсе, Анапа, Крым), горы (Архыз, Алтай, Красная Поляна)
Конкретные ЖК, точные цены квартир и расписание экспертов тебе неизвестны.

СКРИПТ: цель → бюджет → оплата → созвон с экспертом → уточни время.
Если клиент уже назвал цель, бюджет или оплату — двигайся дальше, не переспрашивай.
Если предлагала созвон и клиент не согласился — ответь на его вопрос, вернись к созвону через 2-3 хода другими словами.

ПРИМЕРЫ:

Клиент: "Здравствуйте, да, удобно"
София: "Отлично! Подскажите, что вас интересует — покупка для себя или инвестиции?"

Клиент: "Не очень удобно, давайте позже"
София: "Хорошо, перезвоним в удобное время. Когда лучше — сегодня вечером или завтра?"

Клиент: "Хочу инвестировать"
София: "Отличный выбор. Какой бюджет рассматриваете?"

Клиент: "Какие цены есть?"
София: "Зависит от локации — Туапсе от пяти миллионов, Сочи и Крым от девяти. Скажите примерный бюджет — подберём варианты."

Клиент: "Какая доходность?"
София: "Аренда приносит 8-15% годовых, а на этапе строительства прирост 18-30%. Это намного выгоднее чем банковский депозит, особенно в условиях падающей ставки. Хотите, эксперт подберёт лучший вариант?"

Клиент: "Десять-пятнадцать миллионов"
София: "Хороший диапазон, есть варианты и у моря, и в горах. Как планируете оплачивать — рассрочка, ипотека или полная сумма?"

Клиент: "Это дорого"
София: "Есть варианты в разных диапазонах и с рассрочкой. Давайте эксперт за пятнадцать минут покажет что вписывается в ваш бюджет?"

Клиент: "Давайте созвонимся"
София: "Отлично! Когда вам удобнее — завтра или в другой день?"

Клиент: "Отправьте варианты"
София: "Конечно, эксперт подготовит подборку. Куда удобнее — в мессенджер или на почту?"

Клиент: (непонятно / тишина)
София: "Извините, не расслышала. Можете повторить?"

Клиент: "Ты робот?"
София: "Скажем так — я не пью кофе, но в недвижимости разбираюсь. Так на чём мы остановились?"

СТИЛЬ: 1-2 предложения. Один вопрос за ответ. Сначала ответь на вопрос клиента, потом задай свой. Говори "скажите", не "напишите". Без латиницы и ссылок. Варьируй формулировки. Никогда не указывай клиенту на ошибки, повторения или странности в его речи — просто ответь по существу.

[END] ставь только когда клиент согласился на созвон и назвал время или ориентир (завтра после обеда), или дважды чётко отказался. "Отправьте варианты" — это интерес.
{object_context}"""


async def stream_voice_response(
    *,
    user_id: int,
    user_message: str,
    user_name: str,
    history: list,
    state_manager,
    channel: str = "voice",
    call_id: str = "",
) -> AsyncGenerator[str, None]:
    """
    Голосовой пайплайн v4 — Groq llama-4-scout primary, OpenAI fallback.

    Промпт V3: строгие запреты + анти-looping.
    State: rule-based извлечение из сообщения клиента.
    Ответ: целиком одним yield — Retell TTS получает полную фразу.
    """
    # Выбор провайдера: Groq primary, OpenAI fallback
    groq = _get_groq_client()
    use_groq = VOICE_PROVIDER == "groq" and groq is not None
    voice_model = VOICE_MODEL_GROQ if use_groq else VOICE_MODEL_OPENAI
    openai_client = _get_client()
    tag = channel.upper()
    cid = call_id or "no_id"
    t0 = time.monotonic()
    timings = {}

    # 1. Определить stage и state
    state = state_manager.get_state(user_id)
    stage = _determine_voice_stage(state)
    state_summary = _format_voice_state(state)

    # Log pipeline start with state snapshot
    collected = []
    if state:
        for fld in ("goal", "location", "budget", "payment_type"):
            val = getattr(state, fld, None)
            if val:
                collected.append(f"{fld}={str(val)[:25]}")
    vd.info(
        f'[{cid}] PIPELINE_START | text="{user_message[:80]}" '
        f"| stage={stage} "
        f"| finished={getattr(state, 'dialog_finished', False) if state else False} "
        f"| fields=[{', '.join(collected)}]"
    )

    # History loaded
    vd.info(f"[{cid}] HISTORY_LOADED | messages={len(history)}")

    # 2. Rule-based state extraction (ДО LLM — обновляем stage)
    state_updates = _extract_state_from_context(user_message, history, state)
    if state_updates:
        state_manager.update_state(user_id, state_updates)
        vd.info(f"[{cid}] STATE_EXTRACTED | updates={state_updates}")
        # Пересчитать stage после обновления
        state = state_manager.get_state(user_id)
        stage = _determine_voice_stage(state)
        state_summary = _format_voice_state(state)
        vd.info(f"[{cid}] STAGE_UPDATED | new_stage={stage}")

    # 2b. Detect MEETING from assistant history
    # If model already proposed a meeting (last assistant msg has meeting keywords)
    # and stage is still BUDGET/PAYMENT — advance to MEETING
    if stage in ("BUDGET", "PAYMENT") and history:
        last_assistant_msgs = [
            m["content"] for m in history if m["role"] == "assistant"
        ]
        if last_assistant_msgs:
            last_a = last_assistant_msgs[-1].lower()
            meeting_kw = ["созвон", "эксперт покажет", "когда удобно", "когда вам"]
            if any(kw in last_a for kw in meeting_kw):
                stage = "MEETING"
                vd.info(f"[{cid}] STAGE_OVERRIDE | to=MEETING (from assistant history)")

    # 3. Собрать промпт (компактный, без RAG)
    t_prompt_start = time.monotonic()
    object_context = _get_object_context(state)
    system_prompt = VOICE_SYSTEM_PROMPT.format(
        stage=stage,
        state_summary=state_summary,
        object_context=object_context,
    )

    # Messages
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    t_prompt_done = time.monotonic()
    timings["prompt"] = (t_prompt_done - t_prompt_start) * 1000
    est_tokens = len(system_prompt) // 4
    vd.info(
        f"[{cid}] PROMPT_BUILT | elapsed={timings['prompt']:.0f}ms "
        f"| prompt_len={len(system_prompt)} chars "
        f"| est_tokens={est_tokens} | messages={len(messages)}"
    )

    # 4. Вызов LLM — Groq primary, OpenAI fallback
    provider_used = "groq" if use_groq else "openai"
    t_llm_start = time.monotonic()
    vd.info(
        f"[{cid}] LLM_REQUEST_START | provider={provider_used} "
        f"| model={voice_model} | messages={len(messages)}"
    )
    log.info(
        f"🔄 [{tag}] Generator запрос для {user_name} "
        f"(provider={provider_used}, model={voice_model}, stage={stage})..."
    )

    full_text = None
    finish_reason = None
    try:
        if use_groq:
            # Groq — Chat Completions API (OpenAI-compatible)
            groq_messages = [{"role": "system", "content": system_prompt}] + messages
            resp = await asyncio.to_thread(
                groq.chat.completions.create,
                model=voice_model,
                messages=groq_messages,
                max_tokens=400,
                temperature=0.7,
            )
            full_text = resp.choices[0].message.content or ""
            finish_reason = resp.choices[0].finish_reason
        else:
            # OpenAI — Responses API
            resp = await asyncio.to_thread(
                openai_client.responses.create,
                model=voice_model,
                instructions=system_prompt,
                input=messages,
                max_output_tokens=400,
            )
            full_text = resp.output_text or ""
            finish_reason = resp.status

    except Exception as e:
        log.error(f"❌ [{tag}] {provider_used} error: {e}")
        vd.error(f"[{cid}] LLM_ERROR | provider={provider_used} | error={e}")

        # Fallback на OpenAI если Groq сломался
        if use_groq:
            provider_used = "openai_fallback"
            log.info(f"🔄 [{tag}] Fallback → OpenAI {VOICE_MODEL_OPENAI}")
            vd.info(f"[{cid}] LLM_FALLBACK | to=openai")
            try:
                resp = await asyncio.to_thread(
                    openai_client.responses.create,
                    model=VOICE_MODEL_OPENAI,
                    instructions=system_prompt,
                    input=messages,
                    max_output_tokens=400,
                )
                full_text = resp.output_text or ""
                finish_reason = resp.status
            except Exception as e2:
                log.error(f"❌ [{tag}] Fallback also failed: {e2}")
                vd.error(f"[{cid}] LLM_FALLBACK_ERROR | error={e2}")

    if not full_text:
        yield "Простите, связь подвисла. Повторите?"
        return

    t_llm_done = time.monotonic()
    timings["llm_full"] = (t_llm_done - t_llm_start) * 1000
    vd.info(
        f"[{cid}] LLM_COMPLETE | provider={provider_used} "
        f"| elapsed={timings['llm_full']:.0f}ms "
        f"| len={len(full_text)} chars "
        f"| finish={finish_reason} "
        f'| text="{full_text[:120]}"'
    )
    if finish_reason and finish_reason not in ("stop", "completed"):
        vd.warning(f"[{cid}] LLM_TRUNCATED | finish_reason={finish_reason}")
    log.info(
        f"✅ [{tag}] Generator ответ получен "
        f"({provider_used}, {timings['llm_full']:.0f}ms)"
    )

    # Strip <think> тегов (safety net)
    if "<think>" in full_text:
        full_text = re.sub(
            r"<think>.*?</think>", "", full_text, flags=re.DOTALL
        ).strip()

    # 5. [END] check
    answer_text = full_text.strip()
    if "[END]" in answer_text or "[end]" in answer_text:
        answer_text = answer_text.replace("[END]", "").replace("[end]", "").strip()
        state_manager.update_state(
            user_id, {"dialog_finished": True, "finish_type": "llm_end"}
        )
        log.info(f"🏁 [{tag}] Voice: диалог завершён [END]")

    # 6. Sanitize for TTS
    answer_text = sanitize_for_tts(answer_text)
    if not answer_text:
        answer_text = "Повторите, пожалуйста?"

    # 7. Отдать ВЕСЬ ответ одним куском
    yield answer_text

    # 8. Pipeline summary
    t_end = time.monotonic()
    total_pipeline = (t_end - t0) * 1000
    vd.info(
        f"[{cid}] PIPELINE_SUMMARY | total={total_pipeline:.0f}ms "
        f"| prompt={timings.get('prompt', 0):.0f}ms "
        f"| llm={timings.get('llm_full', 0):.0f}ms "
        f"| stage={stage}"
    )
