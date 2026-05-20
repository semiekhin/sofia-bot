"""
Очередь сообщений Sofia-GPT — cancel-and-restart.

Если во время обработки сообщения приходит новое — текущий pipeline
отменяется и перезапускается с объединённым (combined) текстом.
Результат: один pipeline и один ответ на залп сообщений.

Версия: 2.0
Дата: 2026-05-20
"""

import asyncio
from datetime import datetime
from typing import Dict, Callable

# user_key → {"task": asyncio.Task|None, "pending": list[str], "context": dict|None}
_user_data: Dict[str, dict] = {}


def _log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [QUEUE] {message}")


def _get_user_data(user_key: str) -> dict:
    """Получает или создаёт структуру данных для пользователя."""
    if user_key not in _user_data:
        _user_data[user_key] = {"task": None, "pending": [], "context": None}
    return _user_data[user_key]


async def process_with_queue(
    user_key: str,
    message: str,
    context: dict,
    processor: Callable,
) -> None:
    """
    Cancel-and-restart обработка.

    Накапливает сообщение в pending. Если pipeline уже работает —
    отменяет его и перезапускает на объединённом тексте. Если нет —
    запускает новый task.
    """
    data = _get_user_data(user_key)
    data["pending"].append(message)
    data["context"] = context

    running = data["task"] and not data["task"].done()
    if running:
        _log(
            f"♻️ {user_key}: новое сообщение во время обработки — "
            f"отмена pipeline, рестарт с combined ({len(data['pending'])} сообщ.)"
        )
        data["task"].cancel()
    else:
        _log(f"🔄 {user_key}: старт обработки")

    data["task"] = asyncio.create_task(_run(user_key, processor))


async def _run(user_key: str, processor: Callable) -> None:
    """
    Один прогон pipeline на combined из накопленного pending.

    Ответ отправляется только если за время обработки не пришло новое
    сообщение (иначе нас вытеснил новый task — отправит он).
    """
    data = _get_user_data(user_key)
    me = asyncio.current_task()

    combined = "\n".join(data["pending"])
    context = data["context"]

    try:
        result = await processor(combined, context)
    except asyncio.CancelledError:
        # Пришло новое сообщение → pending сохранён, его обработает новый task
        _log(f"⏹️ {user_key}: pipeline отменён, перезапуск с combined")
        return
    except Exception as e:
        _log(f"❌ {user_key}: ошибка обработки: {e}")
        if data["task"] is me:
            data["pending"] = []
            data["task"] = None
        return

    # Вытеснены новым сообщением под конец обработки — не отправляем,
    # combined целиком обработает новый task.
    if data["task"] is not me:
        _log(f"🚫 {user_key}: вытеснен новым сообщением, ответ не отправляем")
        return

    # Очередь спокойна — отправляем единственный ответ.
    # send_callback защищён shield: это точка невозврата (БД + Bitrix + send),
    # отменять её нельзя даже если прямо сейчас придёт новое сообщение.
    data["pending"] = []
    _log(f"✅ {user_key}: очередь пуста, отправляем ответ")
    try:
        if result.get("send_callback"):
            await asyncio.shield(result["send_callback"]())
    except asyncio.CancelledError:
        _log(f"⏹️ {user_key}: отмена во время отправки — ответ доставлен (shield)")
    except Exception as e:
        _log(f"❌ {user_key}: ошибка отправки: {e}")
    finally:
        if data["task"] is me:
            data["task"] = None


def get_queue_stats() -> dict:
    """Статистика очередей (для отладки)."""
    return {
        user_key: {
            "pending": len(d["pending"]),
            "running": bool(d["task"] and not d["task"].done()),
        }
        for user_key, d in _user_data.items()
    }
