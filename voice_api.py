"""
voice_api.py — WebSocket адаптер для Retell AI Custom LLM

Принимает WebSocket-соединение от Retell, обрабатывает через тот же пайплайн
что web_api.py: process_message() → Analyzer → RAG → Generator.

Endpoint: ws://.../llm-websocket/{call_id}
"""

import hashlib
import json
import logging
import os
import re

from fastapi import WebSocket, WebSocketDisconnect

from state_manager import StateManager
from core.pipeline import stream_voice_response
from web_api import save_message, get_history

# TODO: вернуть когда voice latency позволит
# from message_processor import process_message

log = logging.getLogger("sofia.voice")

SOFIA_PATH = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(SOFIA_PATH, "sofia_gpt.db"))
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(SOFIA_PATH, DB_PATH)
state_manager = StateManager(DB_PATH)

VOICE_USER_ID_OFFSET = 7_000_000


def call_id_to_user_id(call_id: str) -> int:
    """Стабильный user_id из call_id: 7_000_000 + (md5[:8] as int % 1_000_000)"""
    h = hashlib.md5(call_id.encode()).hexdigest()[:8]
    return VOICE_USER_ID_OFFSET + (int(h, 16) % 1_000_000)


def clean_for_voice(text: str) -> str:
    """Убираем markdown и маркеры — голос не читает форматирование."""
    text = text.replace("[END]", "").replace("[end]", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"^[\-\•]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


async def handle_voice_ws(websocket: WebSocket, call_id: str):
    """Основной обработчик WebSocket для Retell AI."""
    await websocket.accept()

    user_id = call_id_to_user_id(call_id)
    user_name = f"voice_{call_id[:8]}"
    response_id = 0

    log.info(f"[VOICE] WS connected: call_id={call_id}, user_id={user_id}")

    try:
        # === Приветствие — фиксированное, нейтральное (без LLM) ===
        greeting_text = (
            "Добрый день! Это София из Oazis Estate. "
            "Вы оставляли заявку на сайте по недвижимости. "
            "Вам удобно сейчас пообщаться?"
        )
        has_end = False

        save_message(
            chat_id=user_id,
            user_id=user_id,
            user_name=user_name,
            role="assistant",
            content=greeting_text,
        )

        greeting_response = {
            "response_type": "response",
            "response_id": response_id,
            "content": greeting_text,
            "content_complete": True,
            "end_call": has_end,
        }
        await websocket.send_text(json.dumps(greeting_response))
        log.info(f"[VOICE] Greeting sent: {greeting_text[:60]}...")

        # === Цикл обработки сообщений от Retell ===
        is_responding = False  # флаг: pipeline стримит ответ
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                log.warning(f"[VOICE] Invalid JSON: {raw[:100]}")
                continue

            interaction_type = data.get("interaction_type", "")

            if interaction_type == "update_only":
                continue

            if interaction_type not in ("response_required", "reminder_required"):
                log.debug(f"[VOICE] Unknown interaction_type: {interaction_type}")
                continue

            # Извлекаем последнее сообщение пользователя из transcript
            transcript = data.get("transcript", [])
            user_text = ""
            for entry in reversed(transcript):
                if entry.get("role") == "user":
                    user_text = entry.get("content", "").strip()
                    break

            # Reminder без текста — фиксированный nudge, НЕ ходим в пайплайн
            if not user_text and interaction_type == "reminder_required":
                response_id += 1
                nudge = "Алло, вы меня слышите? Вам удобно сейчас говорить?"
                nudge_msg = {
                    "response_type": "response",
                    "response_id": response_id,
                    "content": nudge,
                    "content_complete": True,
                    "end_call": False,
                }
                await websocket.send_text(json.dumps(nudge_msg))
                log.info("[VOICE] Reminder nudge sent (no user text)")
                continue

            if not user_text:
                continue

            # Если pipeline ещё стримит предыдущий ответ — пропускаем
            if is_responding:
                log.info(f"[VOICE] Skipping response_required — still responding (text: {user_text[:50]})")
                continue

            response_id += 1

            # Сохраняем сообщение пользователя
            save_message(
                chat_id=user_id,
                user_id=user_id,
                user_name=user_name,
                role="user",
                content=user_text,
            )

            # Обрабатываем через единый пайплайн
            history = get_history(user_id, limit=20)

            # Extractor пропускаем для голоса — экономим ~1-2с
            # TODO: вернуть когда латенси будет приемлемым
            # await process_message(
            #     user_id=user_id,
            #     user_name=user_name,
            #     message=user_text,
            #     history=history,
            #     state_manager=state_manager,
            #     channel="voice",
            # )

            # Стриминг ответа Generator → Retell (с буферизацией)
            FLUSH_CHARS = ".!?,"
            MIN_BUF_LEN = 20

            full_text = ""
            buf = ""
            chunk_count = 0

            async def _flush_buf():
                nonlocal buf, chunk_count
                if not buf:
                    return
                chunk_count += 1
                await websocket.send_text(
                    json.dumps(
                        {
                            "response_type": "response",
                            "response_id": response_id,
                            "content": buf,
                            "content_complete": False,
                            "end_call": False,
                        }
                    )
                )
                buf = ""

            is_responding = True
            async for chunk in stream_voice_response(
                user_id=user_id,
                user_message=user_text,
                user_name=user_name,
                history=history,
                state_manager=state_manager,
                channel="voice",
            ):
                if not chunk:
                    continue
                full_text += chunk
                buf += chunk

                # Flush по знаку препинания или по длине + пробел
                if buf[-1] in FLUSH_CHARS:
                    await _flush_buf()
                elif len(buf) >= MIN_BUF_LEN and buf[-1] == " ":
                    await _flush_buf()

            # Остаток буфера
            await _flush_buf()

            # Очистка полного текста от markdown для сохранения
            full_text = clean_for_voice(full_text)

            # [END] check
            end_call = "[END]" in full_text or "[end]" in full_text
            full_text = full_text.replace("[END]", "").replace("[end]", "").strip()
            if end_call:
                state_manager.update_state(
                    user_id,
                    {"dialog_finished": True, "finish_type": "llm_end"},
                )

            # Финальное сообщение — content_complete: true
            await websocket.send_text(
                json.dumps(
                    {
                        "response_type": "response",
                        "response_id": response_id,
                        "content": "",
                        "content_complete": True,
                        "end_call": end_call,
                    }
                )
            )

            is_responding = False

            # Сохраняем полный очищенный ответ
            reply_text = full_text or "Повторите, пожалуйста?"
            save_message(
                chat_id=user_id,
                user_id=user_id,
                user_name=user_name,
                role="assistant",
                content=reply_text,
            )

            log.info(
                f"[VOICE] Reply #{response_id}: "
                f"chunks={chunk_count}, end_call={end_call}, "
                f"len={len(reply_text)}"
            )

    except WebSocketDisconnect:
        log.info(f"[VOICE] WS disconnected: call_id={call_id}")
    except Exception as e:
        log.error(f"[VOICE] WS error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass
