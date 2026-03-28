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
            _groq_client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
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
        # Паттерн 1: число + млн/миллион
        patterns = [r"(\d+)\s*(?:млн|миллион)", r"(?:миллион\w*)\s*(\d+)"]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = int(m.group(1))
                if val < 100:
                    updates["budget"] = val * 1_000_000
                    updates["budget_confidence"] = "confirmed"
                break

        # Паттерн 2: числительные + млн/миллион
        if "budget" not in updates:
            number_words = {
                "двадцать пять": 25,
                "пять": 5,
                "шесть": 6,
                "семь": 7,
                "восемь": 8,
                "девять": 9,
                "десять": 10,
                "одиннадцать": 11,
                "двенадцать": 12,
                "тринадцать": 13,
                "четырнадцать": 14,
                "пятнадцать": 15,
                "двадцать": 20,
                "тридцать": 30,
                "сорок": 40,
                "пятьдесят": 50,
            }
            for word, val in number_words.items():
                if word in text and ("млн" in text or "миллион" in text):
                    updates["budget"] = val * 1_000_000
                    updates["budget_confidence"] = "confirmed"
                    break

        # Паттерн 3: числительные БЕЗ "миллион" в контексте бюджета
        if "budget" not in updates and budget_context:
            # Сначала двухсловные
            context_number_words = {
                "двадцать пять": 25,
                "пять": 5,
                "шесть": 6,
                "семь": 7,
                "восемь": 8,
                "девять": 9,
                "десять": 10,
                "одиннадцать": 11,
                "двенадцать": 12,
                "тринадцать": 13,
                "четырнадцать": 14,
                "пятнадцать": 15,
                "двадцать": 20,
                "тридцать": 30,
                "сорок": 40,
                "пятьдесят": 50,
            }
            for word, val in sorted(
                context_number_words.items(), key=lambda x: -len(x[0])
            ):
                if word in text:
                    updates["budget"] = val * 1_000_000
                    updates["budget_confidence"] = "confirmed"
                    break

            # Цифры в контексте бюджета: "10", "15", "10-15"
            if "budget" not in updates:
                nums = re.findall(r"\b(\d{1,3})\b", text)
                if nums:
                    max_num = max(int(n) for n in nums)
                    if 3 <= max_num <= 200:
                        updates["budget"] = max_num * 1_000_000
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

    # Meeting
    if any(w in text for w in ["давайте созвон", "да, давайте", "созвонимся"]):
        updates["meeting_agreed"] = True

    return updates


VOICE_SYSTEM_PROMPT = """\
Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. \
Голосовой звонок. Женский род.

ЦЕЛЬ: квалифицировать клиента → договориться о созвоне с экспертом (15 минут).
Созвон = успех. Подборка без созвона = запасной вариант после двух отказов.

ЭТАП: {stage}
КЛИЕНТ: {state_summary}

СТРОГИЕ ЗАПРЕТЫ (нарушение = критическая ошибка):
- НИКОГДА не начинай ответ словами: "Поняла", "Понял", "Понятно", "Ясно".
- НИКОГДА не предлагай конкретное время, дату, адрес — только уточняй у клиента. \
Ты НЕ ЗНАЕШЬ расписание эксперта. Можешь только спросить удобное время.
- НИКОГДА не выдумывай факты: проценты доходности, конкретные объекты, условия. \
Если не знаешь — предложи уточнить у эксперта.
- НИКОГДА не повторяй формулировку из предыдущего ответа дословно. \
Если уже предлагал созвон — скажи по-другому.
- Вместо "Поняла" начни с парафраза или сразу переходи к вопросу.

СКРИПТ (иди по этапам, подстраивайся если клиент перескакивает):

1. GREETING → Представься коротко, спроси цель.
2. GOAL → Для себя или инвестиция? Если "не знаю" — объясни зачем: \
"Просто под инвестиции и для жизни подбираем разные объекты — \
локация, планировки отличаются. Что ближе: доход с аренды или для отдыха?" \
После ответа — сразу к бюджету, без уточнений про стратегию.
3. BUDGET → Примерный бюджет? Если "не знаю" — дай ориентир: \
"До десяти — это студии под аренду, десять-пятнадцать — полноценные апартаменты, \
выше пятнадцати — премиум. Что комфортнее?"
4. PAYMENT → Полная оплата, ипотека или рассрочка? Если "не знаю" — объясни: \
"От способа оплаты зависит выбор — есть варианты только за наличные, \
а в рассрочку можно без банка на шесть-двенадцать месяцев."
5. MEETING_1 → Предложи созвон: \
"Давайте наш эксперт за пятнадцать минут покажет два-три варианта. Когда удобно?"
6. MEETING_2 (после отказа) → Задай доп. вопросы \
(локация — море или горы? стадия — готовое или стройка?), потом повторно: \
"За пятнадцать минут покажем варианты, которых нет в открытом доступе. \
Когда удобнее?"
7. CLOSING → Согласился — уточни время. Второй отказ — \
"Хорошо, эксперт подготовит подборку и пришлёт вам. \
Если появятся вопросы — звоните." Добавь [END].

ПРАВИЛА:
- Одно-два предложения. Это телефон.
- СТРОГО один вопрос за ответ. Уточнение тоже считается вопросом.
- НЕ оценивай слова клиента. Никаких "хороший выбор", "отличный бюджет".
- НЕ пугай ограничениями.
- Если клиент задал вопрос — СНАЧАЛА ответь коротко, потом задай свой.
- Если клиент дважды уклонился — прими и иди дальше, не переспрашивай.
- Говори "скажите", "расскажите", не "напишите".
- Без латиницы, без ссылок, без email.

ЦЕНЫ (когда спросят, не раньше):
Море: Туапсе от 5, Сочи от 8, Анапа от 9, Крым от 9.5 миллионов.
Горы: Алтай от 9, Архыз от 15, Красная Поляна от 19 миллионов.
Говори "от", никогда не говори "до" — верхней границы нет.
{object_context}

ФОРМАТ: Только текст ответа клиенту (1-2 предложения). Ничего больше."""


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
    try:
        if use_groq:
            # Groq — Chat Completions API (OpenAI-compatible)
            groq_messages = [{"role": "system", "content": system_prompt}] + messages
            resp = await asyncio.to_thread(
                groq.chat.completions.create,
                model=voice_model,
                messages=groq_messages,
                max_tokens=300,
                temperature=0.7,
            )
            full_text = resp.choices[0].message.content or ""
        else:
            # OpenAI — Responses API
            resp = await asyncio.to_thread(
                openai_client.responses.create,
                model=voice_model,
                instructions=system_prompt,
                input=messages,
                max_output_tokens=300,
            )
            full_text = resp.output_text or ""

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
                    max_output_tokens=300,
                )
                full_text = resp.output_text or ""
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
        f'| text="{full_text[:120]}"'
    )
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
