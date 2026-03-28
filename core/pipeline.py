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

from openai import OpenAI

from rag_module import search_examples, format_examples_for_prompt
from sofia_prompt_v2 import get_system_prompt_v2, format_state_summary
from config.source_objects import load_object_context, get_object_by_key

log = logging.getLogger("sofia.pipeline")
vd = logging.getLogger("VOICE_DIAG")
vd.setLevel(logging.DEBUG)

RAG_EXAMPLES_COUNT = 10
VOICE_MODEL = "gpt-4.1-mini"

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


def _parse_voice_state(full_text: str) -> tuple:
    """Разделяет ответ на текст клиенту и state-обновления."""
    if "###STATE###" in full_text:
        parts = full_text.split("###STATE###", 1)
        answer_text = parts[0].strip()
        try:
            state_json = json.loads(parts[1].strip())
            return answer_text, state_json
        except json.JSONDecodeError:
            return answer_text, {}
    return full_text.strip(), {}


VOICE_SYSTEM_PROMPT = """Ты — София, менеджер компании Оазис Эстэйт, курортная недвижимость. Голосовой звонок. Женский род.

ЦЕЛЬ: квалифицировать клиента → договориться о созвоне с экспертом (15 минут).
Созвон = успех. Подборка без созвона = запасной вариант после двух отказов.

ЭТАП: {stage}
КЛИЕНТ: {state_summary}

СКРИПТ (иди по этапам, но подстраивайся если клиент перескакивает):

1. GREETING → Представься коротко, спроси цель.
2. GOAL → Для себя или инвестиция? Если "не знаю" — объясни зачем: "Просто под инвестиции и для жизни подбираем разные объекты — локация, планировки отличаются. Что ближе: доход с аренды или для отдыха?"
3. BUDGET → Примерный бюджет? Если "не знаю" — дай ориентир: "До десяти — это студии под аренду, десять-пятнадцать — полноценные апартаменты, выше пятнадцати — премиум. Что комфортнее?"
4. PAYMENT → Полная оплата, ипотека или рассрочка? Если "не знаю" — объясни: "От способа оплаты зависит выбор — есть варианты только за наличные, а в рассрочку можно без банка на шесть-двенадцать месяцев."
5. MEETING_1 → Предложи созвон: "Давайте наш эксперт за пятнадцать минут покажет два-три варианта под ваш запрос. Когда удобно?"
6. MEETING_2 (после отказа) → Задай доп. вопросы (локация — море или горы? стадия — готовое или стройка?), потом повторно: "За пятнадцать минут покажем варианты, которых нет в открытом доступе. Когда удобнее?"
7. CLOSING → Согласился — уточни время. Второй отказ — "Хорошо, эксперт подготовит подборку и пришлёт вам. Если появятся вопросы — звоните." Добавь [END].

ПРАВИЛА:
- Одно-два предложения. Это телефон.
- НЕ оценивай слова клиента. Никаких "хороший выбор", "отличный бюджет", "правильное решение". Просто прими и двигайся дальше.
- НЕ начинай каждый ответ одинаково. Чередуй: ответ на вопрос, уточнение, переход к делу. Слово "Поняла" — максимум один раз за весь разговор.
- Если клиент задал вопрос — СНАЧАЛА ответь коротко (одно предложение), потом задай свой.
- Если клиент дважды уклонился — прими и иди дальше, не переспрашивай.
- Говори "скажите", "расскажите", не "напишите".
- Без латиницы, без ссылок, без email.

ЦЕНЫ (когда спросят, не раньше):
Море: Туапсе от 5, Сочи от 8, Анапа от 9, Крым от 9.5 миллионов.
Горы: Алтай от 9, Архыз от 15, Красная Поляна от 19 миллионов.
Доходность аренды: 8-15% годовых. Рост на стройке: 15-30%.
Рассрочка от застройщика: 6-12 месяцев, без процентов.
{object_context}

ФОРМАТ:
Текст ответа (1-2 предложения).
Затем:
###STATE###
{{"stage": "текущий_этап", "goal": "investment/personal/null", "budget": число_или_null, "payment_type": "full/mortgage/installment/null", "meeting_agreed": true/false}}"""


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
    Голосовой пайплайн v2 — компактный промпт, без RAG, без Extractor.

    Модель: gpt-4.1-mini (быстрая, без reasoning).
    Промпт: ~1100 токенов (VOICE_SYSTEM_PROMPT).
    State: извлекается из ответа LLM (JSON-блок ###STATE###).
    Ответ: целиком (один yield), не стримингом — для правильных ударений TTS.
    """
    client = _get_client()
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

    # 2. Собрать промпт (компактный, без RAG)
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
    vd.info(
        f"[{cid}] PROMPT_BUILT | elapsed={timings['prompt']:.0f}ms "
        f"| prompt_len={len(system_prompt)} chars "
        f"| no_rag=yes | messages={len(messages)}"
    )

    # 3. Один вызов LLM — БЕЗ стриминга (ждём полный ответ)
    try:
        t_llm_start = time.monotonic()
        vd.info(
            f"[{cid}] LLM_REQUEST_START | model={VOICE_MODEL} "
            f"| max_tokens=300 | messages={len(messages)} | stream=false"
        )
        log.info(
            f"🔄 [{tag}] Generator запрос для {user_name} "
            f"(model={VOICE_MODEL}, stage={stage})..."
        )

        response = await asyncio.to_thread(
            client.responses.create,
            model=VOICE_MODEL,
            instructions=system_prompt,
            input=messages,
            max_output_tokens=300,
        )
        full_text = response.output_text or ""

        t_llm_done = time.monotonic()
        timings["llm_full"] = (t_llm_done - t_llm_start) * 1000
        vd.info(
            f"[{cid}] LLM_COMPLETE | elapsed={timings['llm_full']:.0f}ms "
            f"| len={len(full_text)} chars "
            f'| text="{full_text[:120]}"'
        )
        log.info(f"✅ [{tag}] Generator ответ получен")

    except Exception as e:
        log.error(f"❌ [{tag}] Generator error: {e}")
        vd.error(f"[{cid}] LLM_ERROR | error={e}")
        yield "Простите, связь подвисла. Повторите?"
        return

    # 4. Парсить ###STATE### из ответа
    answer_text, state_updates = _parse_voice_state(full_text)

    if state_updates:
        vd.info(f"[{cid}] STATE_PARSED | raw={state_updates}")

    # 5. Обновить state из JSON
    update_dict = {}
    if state_updates:
        goal = state_updates.get("goal")
        if goal and goal != "null":
            update_dict["goal"] = goal
            update_dict["goal_confidence"] = "confirmed"
        budget = state_updates.get("budget")
        if budget and budget != "null":
            try:
                update_dict["budget"] = int(budget)
                update_dict["budget_confidence"] = "confirmed"
            except (ValueError, TypeError):
                pass
        payment = state_updates.get("payment_type")
        if payment and payment != "null":
            update_dict["payment_type"] = payment
            update_dict["payment_type_confidence"] = "confirmed"
        if state_updates.get("meeting_agreed") is True:
            update_dict["meeting_agreed"] = True

    if update_dict:
        state_manager.update_state(user_id, update_dict)
        vd.info(f"[{cid}] STATE_UPDATED | updates={update_dict}")

    # 6. [END] check
    if "[END]" in answer_text or "[end]" in answer_text:
        answer_text = answer_text.replace("[END]", "").replace("[end]", "").strip()
        state_manager.update_state(
            user_id, {"dialog_finished": True, "finish_type": "llm_end"}
        )
        log.info(f"🏁 [{tag}] Voice: диалог завершён [END]")

    # 7. Sanitize for TTS
    t_san_start = time.monotonic()
    answer_text = sanitize_for_tts(answer_text)
    t_san_done = time.monotonic()
    timings["sanitize"] = (t_san_done - t_san_start) * 1000

    if not answer_text:
        answer_text = "Повторите, пожалуйста?"

    # 8. Отдать ВЕСЬ ответ одним куском
    yield answer_text

    # 9. Pipeline summary
    t_end = time.monotonic()
    total_pipeline = (t_end - t0) * 1000
    vd.info(
        f"[{cid}] PIPELINE_SUMMARY | total={total_pipeline:.0f}ms "
        f"| prompt={timings.get('prompt', 0):.0f}ms "
        f"| llm={timings.get('llm_full', 0):.0f}ms "
        f"| sanitize={timings.get('sanitize', 0):.0f}ms "
        f"| stage={stage} | answer_len={len(answer_text)}"
    )
