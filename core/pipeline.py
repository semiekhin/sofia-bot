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
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

from openai import OpenAI

from rag_module import search_examples, format_examples_for_prompt
from sofia_prompt_v2 import get_system_prompt_v2, format_state_summary
from config.source_objects import load_object_context, get_object_by_key

log = logging.getLogger("sofia.pipeline")

RAG_EXAMPLES_COUNT = 10

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
    rag_limit = 3 if voice_mode else RAG_EXAMPLES_COUNT
    examples = search_examples(rag_stage, rag_query, limit=rag_limit)
    if examples:
        examples_prompt = format_examples_for_prompt(examples)
        log.info(f"📚 [{tag}] RAG [{rag_stage}]: {len(examples)} примеров")

    # ═══════════════════════════════════════════════════════════════
    # ШАГ 3: LLM-Generator
    # ═══════════════════════════════════════════════════════════════
    system_prompt = get_system_prompt_v2(state_summary, examples_prompt)

    if voice_mode:
        system_prompt += (
            "\n\nВАЖНО: Это голосовой звонок. Отвечай ОЧЕНЬ коротко — "
            "максимум 2 предложения. Без списков, без форматирования."
        )

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


async def stream_voice_response(
    *,
    user_id: int,
    user_message: str,
    user_name: str,
    history: list,
    state_manager,
    channel: str = "voice",
) -> AsyncGenerator[str, None]:
    """
    Стриминг ответа Generator для голосового канала.

    Analyzer и Extractor пропущены (как voice_mode=True в run_pipeline).
    Yield'ит текстовые чанки по мере получения от OpenAI.
    После завершения стрима — проверяет [END] и обновляет state.
    """
    client = _get_client()
    tag = channel.upper()

    state = state_manager.get_state(user_id)
    state_summary = format_state_summary(state) if state else "Новый клиент"

    # Source routing
    user_msg_count = sum(1 for m in history if m["role"] == "user")
    rag_stage = "QUALIFICATION"
    rag_query = user_message

    if state and state.source_object and user_msg_count <= 2:
        rag_stage = "GREETING"
        rag_query = "приветствие клиент с сайта интерес к объекту"
        log.info(
            f"🏷️ [{tag}] Source routing: force stage=GREETING "
            f"(user_msgs={user_msg_count}, object={state.source_object})"
        )

    # RAG (3 примера для voice)
    examples_prompt = ""
    examples = search_examples(rag_stage, rag_query, limit=3)
    if examples:
        examples_prompt = format_examples_for_prompt(examples)
        log.info(f"📚 [{tag}] RAG [{rag_stage}]: {len(examples)} примеров")

    # System prompt
    system_prompt = get_system_prompt_v2(state_summary, examples_prompt)
    system_prompt += (
        "\n\nВАЖНО: Это голосовой звонок. Отвечай ОЧЕНЬ коротко — "
        "максимум 2 предложения. Без списков, без форматирования."
    )

    # Source routing: контекст объекта
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

    # Messages
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    try:
        log.info(f"🔄 [{tag}] Generator STREAM запрос для {user_name}...")

        # stream=True возвращает синхронный итератор —
        # создаём его в thread, затем итерируем через queue
        queue: asyncio.Queue = asyncio.Queue()

        async def _run_stream():
            def _sync_stream():
                stream = client.responses.create(
                    model="gpt-5.2",
                    instructions=system_prompt,
                    input=messages,
                    max_output_tokens=4000,
                    stream=True,
                )
                for event in stream:
                    if event.type == "response.output_text.delta":
                        delta = event.delta
                        if delta:
                            queue.put_nowait(delta)
                queue.put_nowait(None)  # sentinel

            await asyncio.to_thread(_sync_stream)

        stream_task = asyncio.create_task(_run_stream())

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

        await stream_task  # убедимся что завершился без ошибок

        log.info(f"✅ [{tag}] Generator stream завершён")

    except Exception as e:
        log.error(f"❌ [{tag}] Generator stream error: {e}")
        yield "Простите, связь подвисла. Повторите?"
