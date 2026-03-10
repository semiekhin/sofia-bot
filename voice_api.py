"""
voice_api.py — WebSocket адаптер для Retell AI Custom LLM

Принимает WebSocket-соединение от Retell, обрабатывает через тот же пайплайн
что web_api.py: process_message() → Analyzer → RAG → Generator.

Endpoint: ws://.../llm-websocket/{call_id}
"""

import hashlib
import json
import logging
import re

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger("sofia.voice")

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
    # Импорт здесь чтобы избежать circular imports при подключении из web_api
    from web_api import (
        state_manager,
        save_message,
        get_history,
        generate_response,
    )
    from message_processor import process_message

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
                log.info(f"[VOICE] Reminder nudge sent (no user text)")
                continue

            if not user_text:
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

            # Обрабатываем через пайплайн (как в web_api.handle_web_message)
            history = get_history(user_id, limit=100)
            await process_message(
                user_id=user_id,
                user_name=user_name,
                message=user_text,
                history=history,
                state_manager=state_manager,
                channel="voice",
            )

            reply_raw = await generate_response(user_id, user_text, user_name)
            end_call = "[END]" in (reply_raw or "") or "[end]" in (reply_raw or "")
            reply_clean = clean_for_voice(reply_raw or "Повторите, пожалуйста?")

            save_message(
                chat_id=user_id,
                user_id=user_id,
                user_name=user_name,
                role="assistant",
                content=reply_clean,
            )

            response_msg = {
                "response_type": "response",
                "response_id": response_id,
                "content": reply_clean,
                "content_complete": True,
                "end_call": end_call,
            }
            await websocket.send_text(json.dumps(response_msg))
            log.info(
                f"[VOICE] Reply #{response_id}: "
                f"end_call={end_call}, len={len(reply_clean)}"
            )

    except WebSocketDisconnect:
        log.info(f"[VOICE] WS disconnected: call_id={call_id}")
    except Exception as e:
        log.error(f"[VOICE] WS error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass
