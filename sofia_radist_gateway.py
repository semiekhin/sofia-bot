#!/usr/bin/env python3
"""
Sofia Radist Gateway — мультиканальный шлюз
Версия: 2.0
Каналы: Max, Telegram, WhatsApp (через Radist.Online)
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import logging
from datetime import datetime
import sqlite3
import os
from dotenv import load_dotenv

# Импорт конфига Radist (мультиканальный)
from config.radist_config import (
    RADIST_API,
    CHANNELS,
    CONNECTION_TO_CHANNEL,
    WEBHOOK_CONFIG,
    DEV_MODE,
    get_headers,
    get_base_url,
    get_channel_by_connection_id,
    get_connection_id_by_channel,
)

# Импорт компонентов Sofia
from state_manager import StateManager
from message_processor import process_message
from message_queue import process_with_queue
from core.pipeline import run_pipeline

load_dotenv()

# ============================================
# НАСТРОЙКИ
# ============================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_PATH = "sofia_gpt.db"
LOG_PATH = "sofia_radist.log"


# State Manager
state_manager = StateManager(DB_PATH)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RADIST] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.info

# ============================================
# CHANNEL EMOJI для логов
# ============================================

CHANNEL_EMOJI = {"max": "💬", "telegram": "✈️", "whatsapp": "📱", "unknown": "❓"}
# ============================================
# OBSERVER CHAT — отправка копий диалогов
# ============================================

OBSERVER_CHAT_ID = os.getenv("OBSERVER_CHAT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def get_or_create_topic(phone: str, user_name: str) -> int:
    """Получает или создаёт тему для клиента в группе наблюдателей"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Проверяем есть ли уже тема
    c.execute("SELECT thread_id FROM observer_topics WHERE phone = ?", (phone,))
    row = c.fetchone()
    if row:
        conn.close()
        return row[0]

    # Создаём новую тему
    display_name = user_name if user_name and user_name != phone else phone
    topic_name = f"{display_name}"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createForumTopic"
    payload = {"chat_id": OBSERVER_CHAT_ID, "name": topic_name[:128]}  # Лимит Telegram

    thread_id = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    thread_id = data["result"]["message_thread_id"]
                    log(
                        f"👁️ Observer: создана тема '{topic_name}' (thread_id={thread_id})"
                    )
                else:
                    error = await resp.text()
                    log(f"⚠️ Observer: не удалось создать тему — {error[:100]}")
    except Exception as e:
        log(f"⚠️ Observer createTopic exception: {e}")

    # Сохраняем в БД
    if thread_id:
        c.execute(
            "INSERT OR REPLACE INTO observer_topics (phone, thread_id, user_name) VALUES (?, ?, ?)",
            (phone, thread_id, user_name),
        )
        conn.commit()

    conn.close()
    return thread_id


async def notify_observer(
    channel: str, phone: str, user_name: str, direction: str, message: str
):
    """Отправляет копию сообщения в тему клиента в группе наблюдателей"""
    if not OBSERVER_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        return

    # Получаем или создаём тему для этого клиента
    topic_key = phone if phone else user_name
    thread_id = await get_or_create_topic(topic_key, user_name)

    emoji = CHANNEL_EMOJI.get(channel, "📨")

    if direction == "in":
        text = f"{emoji} <b>Клиент:</b>\n{message}"
    else:
        text = f"↪️ <b>София:</b>\n{message}"

    # Ограничиваем длину
    if len(text) > 4000:
        text = text[:4000] + "..."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": OBSERVER_CHAT_ID, "text": text, "parse_mode": "HTML"}

    if thread_id:
        payload["message_thread_id"] = thread_id

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    log(f"👁️ Observer: отправлено в тему {thread_id}")
                else:
                    error = await resp.text()
                    log(f"⚠️ Observer error: {resp.status} — {error[:100]}")
    except Exception as e:
        log(f"⚠️ Observer exception: {e}")


# ============================================
# DATABASE — универсальная для всех каналов
# ============================================


def init_radist_db():
    """Инициализация таблиц для Radist сообщений (все каналы)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Универсальная таблица сообщений
    c.execute("""CREATE TABLE IF NOT EXISTS radist_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT,
        connection_id INTEGER,
        chat_id INTEGER,
        contact_id INTEGER,
        phone TEXT,
        role TEXT,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    # Универсальная таблица чатов
    c.execute("""CREATE TABLE IF NOT EXISTS radist_chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT,
        connection_id INTEGER,
        chat_id INTEGER,
        contact_id INTEGER,
        phone TEXT,
        user_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(channel, chat_id)
    )""")

    # Индексы
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_radist_messages_chat ON radist_messages(channel, chat_id)"
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_radist_chats_channel ON radist_chats(channel)"
    )

    # Таблица для топиков наблюдателя (каждый клиент = отдельная тема)
    c.execute("""CREATE TABLE IF NOT EXISTS observer_topics (
        phone TEXT PRIMARY KEY,
        thread_id INTEGER,
        user_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()
    log("📦 БД инициализирована (radist_messages, radist_chats)")


def save_message(
    channel: str,
    connection_id: int,
    chat_id: int,
    contact_id: int,
    phone: str,
    role: str,
    content: str,
):
    """Сохраняет сообщение в БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO radist_messages (channel, connection_id, chat_id, contact_id, phone, role, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (channel, connection_id, chat_id, contact_id, phone, role, content),
    )
    conn.commit()
    conn.close()


def get_history(channel: str, chat_id: int, limit: int = 100) -> list:
    """Получает историю сообщений"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM radist_messages WHERE channel = ? AND chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (channel, chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def save_chat(
    channel: str,
    connection_id: int,
    chat_id: int,
    contact_id: int,
    phone: str,
    user_name: str = None,
):
    """Сохраняет информацию о чате"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO radist_chats (channel, connection_id, chat_id, contact_id, phone, user_name) VALUES (?, ?, ?, ?, ?, ?)",
        (channel, connection_id, chat_id, contact_id, phone, user_name),
    )
    conn.commit()
    conn.close()


# ============================================
# RADIST API — отправка сообщений
# ============================================


async def send_message(connection_id: int, chat_id: int, text: str) -> bool:
    """Отправляет сообщение через Radist API (любой канал)"""
    if DEV_MODE:
        channel = get_channel_by_connection_id(connection_id)
        log(
            f"🔇 [DEV] [{channel.upper()}] НЕ отправлено (chat_id={chat_id}): {text[:80]}..."
        )
        return True

    url = f"{get_base_url()}/messaging/messages/"
    payload = {
        "connection_id": connection_id,
        "chat_id": chat_id,
        "message_type": "text",
        "text": {"text": text},
    }

    channel = get_channel_by_connection_id(connection_id)
    emoji = CHANNEL_EMOJI.get(channel, "📤")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=get_headers(), json=payload) as resp:
                if resp.status == 200:
                    log(
                        f"{emoji} [{channel.upper()}] Отправлено (chat_id={chat_id}): {text[:50]}..."
                    )
                    return True
                else:
                    error = await resp.text()
                    log(
                        f"❌ [{channel.upper()}] Ошибка отправки: {resp.status} — {error}"
                    )
                    return False
    except Exception as e:
        log(f"❌ [{channel.upper()}] Исключение при отправке: {e}")
        return False


# ============================================
# ОБРАБОТКА СООБЩЕНИЙ
# ============================================


async def process_incoming_message(
    channel: str,
    connection_id: int,
    chat_id: int,
    contact_id: int,
    phone: str,
    user_message: str,
    user_name: str = None,
):
    """
    Обрабатывает входящее сообщение из любого канала Radist.
    """
    # Уникальный user_id: отрицательный для Radist каналов, разные диапазоны для разных каналов
    channel_offset = {
        "max": 1000000,
        "telegram": 2000000,
        "whatsapp": 3000000,
    }
    offset = channel_offset.get(channel, 9000000)
    user_id = -(offset + chat_id)

    if not user_name:
        user_name = phone

    emoji = CHANNEL_EMOJI.get(channel, "📨")
    log(f"{emoji} [{channel.upper()}] {phone}: {user_message}")

    # ════════════════════════════════════════════════════════════════════════
    # Source routing: парсим маркер объекта из первого сообщения
    # ════════════════════════════════════════════════════════════════════════
    log(f"🔍 [{channel.upper()}] Source routing check: {user_message[:50]}")
    from config.source_objects import detect_source

    obj_config, clean_text = detect_source(user_message)
    if obj_config:
        state_manager.update_state(user_id, {"source_object": obj_config["key"]})
        log(
            f"🏷️ [{channel.upper()}] Объект распознан: {obj_config['short_name']} → source_object={obj_config['key']}"
        )
        user_message = clean_text

    # Сохраняем входящее сообщение
    save_message(
        channel, connection_id, chat_id, contact_id, phone, "user", user_message
    )

    # Отправляем в Observer (входящее)
    await notify_observer(channel, phone, user_name, "in", user_message)

    # Получаем историю
    history = get_history(channel, chat_id, limit=100)

    # ════════════════════════════════════════════════════════════════════════
    # Единая обработка через message_processor
    # ════════════════════════════════════════════════════════════════════════

    result = await process_message(
        user_id=user_id,
        user_name=user_name,
        message=user_message,
        history=history,
        state_manager=state_manager,
        channel=channel,
    )

    # Если WAIT — не отвечаем
    if result["skip_response"]:
        log(f"⏸️ [{channel.upper()}] WAIT: пропускаем ответ")
        return

    # ════════════════════════════════════════════════════════════════════════
    # Генерация ответа
    # ════════════════════════════════════════════════════════════════════════

    response = await generate_response(
        channel, chat_id, user_id, user_message, user_name
    )

    if response is None:
        log(f"🔇 [{channel.upper()}] Ответ не требуется — молчим")
        return

    # Сохраняем ответ
    save_message(
        channel, connection_id, chat_id, contact_id, phone, "assistant", response
    )

    # Отправляем через Radist
    success = await send_message(connection_id, chat_id, response)
    if success:
        log(f"{emoji} [{channel.upper()}] → {user_name}: {response[:50]}...")

        # Отправляем в Observer (исходящее)
        await notify_observer(channel, phone, user_name, "out", response)


async def generate_response(
    channel: str, chat_id: int, user_id: int, user_message: str, user_name: str
) -> str:
    """Генерирует ответ через core/pipeline.py."""
    history = get_history(channel, chat_id)

    result = await run_pipeline(
        user_id=user_id,
        user_message=user_message,
        user_name=user_name,
        history=history,
        state_manager=state_manager,
        channel=channel,
    )

    return result.answer


# ============================================

# ============================================
# WRAPPER ДЛЯ ОЧЕРЕДИ СООБЩЕНИЙ
# ============================================


async def process_message_wrapper(combined_message: str, context: dict) -> dict:
    """
    Wrapper для обработки сообщений с поддержкой очереди.
    Генерирует ответ, но НЕ отправляет — возвращает callback для отправки.
    """
    channel = context["channel"]
    connection_id = context["connection_id"]
    chat_id = context["chat_id"]
    contact_id = context["contact_id"]
    phone = context["phone"]
    user_name = context["user_name"]

    channel_offset = {"max": 1000000, "telegram": 2000000, "whatsapp": 3000000}
    offset = channel_offset.get(channel, 9000000)
    user_id = -(offset + chat_id)

    if not user_name:
        user_name = phone

    emoji = CHANNEL_EMOJI.get(channel, "📨")
    log(f"{emoji} [{channel.upper()}] {phone}: {combined_message}")

    # ════════════════════════════════════════════════════════════════════════
    # Source routing: распознаём объект из первого сообщения
    # ════════════════════════════════════════════════════════════════════════
    from config.source_objects import detect_source

    obj_config, clean_text = detect_source(combined_message)
    if obj_config:
        state_manager.update_state(user_id, {"source_object": obj_config["key"]})
        log(
            f"🏷️ [{channel.upper()}] Объект распознан: {obj_config['short_name']} → source_object={obj_config['key']}"
        )
        combined_message = clean_text
    # Сохраняем входящее сообщение
    save_message(
        channel, connection_id, chat_id, contact_id, phone, "user", combined_message
    )

    # Отправляем в Observer
    await notify_observer(channel, phone, user_name, "in", combined_message)

    # Получаем историю
    history = get_history(channel, chat_id, limit=100)

    # Обработка через message_processor
    result = await process_message(
        user_id=user_id,
        user_name=user_name,
        message=combined_message,
        history=history,
        state_manager=state_manager,
        channel=channel,
    )

    # Если WAIT — не отвечаем
    if result["skip_response"]:
        log(f"⏸️ [{channel.upper()}] WAIT: пропускаем ответ")
        return {"response": None, "send_callback": None}

    # Генерация ответа
    response = await generate_response(
        channel, chat_id, user_id, combined_message, user_name
    )

    if response is None:
        log(f"🔇 [{channel.upper()}] Ответ не требуется — молчим")
        return

    # Callback для отправки (вызывается после проверки очереди)
    async def send_callback():
        save_message(
            channel, connection_id, chat_id, contact_id, phone, "assistant", response
        )
        success = await send_message(connection_id, chat_id, response)
        if success:
            log(f"{emoji} [{channel.upper()}] → {user_name}: {response[:50]}...")
            await notify_observer(channel, phone, user_name, "out", response)

    return {"response": response, "send_callback": send_callback}


# WEBHOOK HANDLER
# ============================================


async def handle_webhook(request):
    """Обработчик webhook от Radist (все каналы)"""
    try:
        data = await request.json()
        log(f"🔔 Webhook: {json.dumps(data, ensure_ascii=False)[:500]}")

        event_type = data.get("event_type")

        if event_type == "messages.create":
            event_data = data.get("event", {})
            message = event_data.get("message", {})
            chat = event_data.get("chat", {})

            # Определяем канал по connection_id
            connection_id = event_data.get("connection_id")
            channel = get_channel_by_connection_id(connection_id)

            if channel == "unknown":
                log(f"⚠️ Неизвестный connection_id: {connection_id}")
                return web.json_response(
                    {"status": "ignored", "reason": "unknown_connection"}
                )

            # Проверяем что канал включён
            if not CHANNELS.get(channel, {}).get("enabled", False):
                log(f"⚠️ Канал {channel} отключён")
                return web.json_response(
                    {"status": "ignored", "reason": "channel_disabled"}
                )

            # Извлекаем данные
            chat_id = event_data.get("chat_id")
            contact_id = event_data.get("contact_id")
            phone = chat.get("phone", "")
            user_name = chat.get("name", phone)

            # Игнорируем исходящие сообщения (от бота)
            direction = message.get("direction")
            if direction == "outbound":
                log(f"⏭️ [{channel.upper()}] Пропускаем outbound")
                return web.json_response({"status": "ignored_outbound"})

            # Текст сообщения
            message_type = message.get("message_type")
            if message_type == "text":
                text_data = message.get("text", {})
                user_message = text_data.get("text", "")
            else:
                user_message = f"[{message_type}]"
                log(f"⚠️ [{channel.upper()}] Неподдерживаемый тип: {message_type}")

            if user_message and chat_id:
                # Сохраняем информацию о чате
                save_chat(channel, connection_id, chat_id, contact_id, phone, user_name)

                # Обрабатываем через очередь (защита от race condition)
                user_key = f"{channel}:{chat_id}"
                context = {
                    "channel": channel,
                    "connection_id": connection_id,
                    "chat_id": chat_id,
                    "contact_id": contact_id,
                    "phone": phone,
                    "user_name": user_name,
                }
                asyncio.create_task(
                    process_with_queue(
                        user_key, user_message, context, process_message_wrapper
                    )
                )

        return web.json_response({"status": "ok"})

    except Exception as e:
        log(f"❌ Webhook error: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def health_check(request):
    """Health check endpoint"""
    channels_status = {name: cfg["enabled"] for name, cfg in CHANNELS.items()}
    return web.json_response(
        {
            "status": "ok",
            "service": "sofia-radist-gateway",
            "version": "2.0",
            "channels": channels_status,
            "timestamp": datetime.now().isoformat(),
        }
    )


# ============================================
# MAIN
# ============================================


def main():
    """Запуск мультиканального gateway"""
    init_radist_db()

    app = web.Application()
    app.router.add_post(WEBHOOK_CONFIG["path"], handle_webhook)
    app.router.add_get("/health", health_check)

    port = WEBHOOK_CONFIG["port"]

    # Логируем активные каналы
    active_channels = [name for name, cfg in CHANNELS.items() if cfg["enabled"]]
    mode = "DEV (send disabled)" if DEV_MODE else "PROD"
    log(f"🚀 Sofia Radist Gateway v2.0 [{mode}]")
    log(f"📡 Webhook: http://0.0.0.0:{port}{WEBHOOK_CONFIG['path']}")
    log(f"📢 Активные каналы: {', '.join(active_channels)}")

    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
# ============================================
