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
import random
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
from core.bitrix import (
    create_or_update_lead,
    finalize_lead,
    find_recent_atlantis_lead,
    get_lead_status,
    is_manager_active,
    save_original_assigned,
    set_lead_assigned,
    set_manager_active,
    update_lead,
    SOFIA_AI_USER_ID,
)

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


async def get_or_create_topic(
    phone: str, user_name: str, source_object: str | None = None
) -> int:
    """Получает или создаёт тему для клиента в группе наблюдателей.
    source_object — если задан, добавляется как тег в имя темы:
    "Иван Петров · rizalta" — чтобы наблюдатели визуально различали объекты."""
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
    if source_object:
        topic_name = f"{display_name} · {source_object}"
    else:
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
    channel: str,
    phone: str,
    user_name: str,
    direction: str,
    message: str,
    source_object: str | None = None,
):
    """Отправляет копию сообщения в тему клиента в группе наблюдателей.
    source_object — если задан, при первом сообщении тема создаётся с тегом
    источника (см. get_or_create_topic). На существующую тему не влияет —
    тема создаётся один раз и не переименовывается."""
    if not OBSERVER_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        return

    # Получаем или создаём тему для этого клиента
    topic_key = phone if phone else user_name
    thread_id = await get_or_create_topic(topic_key, user_name, source_object)

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

    # Миграция: tg_username в radist_chats
    try:
        c.execute("ALTER TABLE radist_chats ADD COLUMN tg_username TEXT")
    except sqlite3.OperationalError:
        pass  # уже существует

    # Таблица привязки radist user_id → bitrix lead_id
    c.execute("""CREATE TABLE IF NOT EXISTS radist_leads (
        user_id INTEGER PRIMARY KEY,
        bitrix_lead_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()
    log("📦 БД инициализирована (radist_messages, radist_chats, radist_leads)")


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
        "SELECT role, content FROM radist_messages WHERE channel = ? AND chat_id = ? ORDER BY id DESC LIMIT ?",
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
    tg_username: str = None,
):
    """Сохраняет информацию о чате"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO radist_chats "
        "(channel, connection_id, chat_id, contact_id, phone, user_name, tg_username) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (channel, connection_id, chat_id, contact_id, phone, user_name, tg_username),
    )
    conn.commit()
    conn.close()


def get_tg_username(channel: str, chat_id: int) -> str:
    """Получить tg_username из radist_chats."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT tg_username FROM radist_chats WHERE channel = ? AND chat_id = ?",
        (channel, chat_id),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""


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
# BITRIX — привязка radist user_id к лиду
# ============================================


def get_radist_lead_id(user_id: int) -> int | None:
    """Получить bitrix_lead_id из radist_leads."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bitrix_lead_id FROM radist_leads WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def save_radist_lead_id(user_id: int, lead_id: int):
    """Сохранить bitrix_lead_id в radist_leads."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO radist_leads (user_id, bitrix_lead_id)
           VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET bitrix_lead_id = ?""",
        (user_id, lead_id, lead_id),
    )
    conn.commit()
    conn.close()


def _get_source_object(user_id: int) -> str | None:
    """Читает state.source_object для user_id или None."""
    state = state_manager.get_state(user_id)
    return getattr(state, "source_object", None)


def _is_radist_bitrix_session(user_id: int) -> bool:
    """Битрикс-интеграция включена для сессий с source_object,
    КРОМЕ source_object='rizalta' (для RIZALTA Bitrix отключён by design —
    менеджеры заносят лиды вручную). Возвращает True только если source_object
    задан И не равен 'rizalta'."""
    source = _get_source_object(user_id)
    if source == "rizalta":
        return False
    return bool(source)


def _get_radist_user_name(user_id: int) -> str:
    """Получить user_name из radist_chats по user_id."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # user_id = -(offset + chat_id), chat_id нужен для поиска
    # Ищем по всем radist_chats
    channel_offset = {"max": 1000000, "telegram": 2000000, "whatsapp": 3000000}
    for ch, offset in channel_offset.items():
        chat_id = -(user_id) - offset
        if chat_id > 0:
            c.execute(
                "SELECT user_name FROM radist_chats WHERE channel = ? AND chat_id = ?",
                (ch, chat_id),
            )
            row = c.fetchone()
            if row:
                conn.close()
                return row[0] or "Клиент"
    conn.close()
    return "Клиент"


def _get_radist_history_for_bitrix(channel: str, chat_id: int, limit: int = 100):
    """Получить историю из radist_messages в формате для Bitrix."""
    return get_history(channel, chat_id, limit)


# ============================================
# ТАЙМАУТЫ (15/60/15 минут) — аналог bot_server.py
# ============================================

radist_reminder_tasks = {}  # {user_key: asyncio.Task}
radist_reminder_sent = {}  # {user_key: True}

REMINDER_PHRASES = [
    "{name}, продолжим общение?",
    "{name}, не забыли про меня?",
]

TIMEOUT_NO_RESPONSE = 15 * 60  # Сценарий А: 15 мин без ответа после первого сообщения
TIMEOUT_REMINDER = int(os.getenv("REMINDER_TIMEOUT_MIN", "15")) * 60  # Сценарий Б (env)
TIMEOUT_AFTER_REMINDER = 15 * 60  # Сценарий Б: +15 мин после напоминания → финализация


def _get_radist_last_message_time(channel: str, chat_id: int) -> float | None:
    """Время последнего сообщения в radist-диалоге."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp FROM radist_messages WHERE channel = ? AND chat_id = ? "
        "ORDER BY timestamp DESC LIMIT 1",
        (channel, chat_id),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    ts = row[0]
    if isinstance(ts, str):
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            return None
    return float(ts)


def _count_radist_user_messages(channel: str, chat_id: int) -> int:
    """Количество сообщений от клиента в radist-диалоге."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM radist_messages WHERE channel = ? AND chat_id = ? "
        "AND role = 'user'",
        (channel, chat_id),
    )
    count = c.fetchone()[0]
    conn.close()
    return count


def _is_radist_dialog_active(user_id: int) -> bool:
    """Проверяет что диалог не завершён и менеджер не перехватил."""
    state = state_manager.get_state(user_id)
    if state and getattr(state, "dialog_finished", False):
        return False
    if is_manager_active(DB_PATH, user_id):
        return False
    return True


async def _radist_finalize_timeout(
    user_key: str,
    user_id: int,
    channel: str,
    chat_id: int,
    connection_id: int,
    phone: str,
    user_name: str,
    finish_type: str,
):
    """Финализирует radist-диалог по таймауту. Битрикс — только для source-сессий."""
    state_manager.update_state(
        user_id, {"dialog_finished": True, "finish_type": finish_type}
    )

    if _is_radist_bitrix_session(user_id):
        try:
            state_fresh = state_manager.get_state(user_id)
            history = get_history(channel, chat_id, limit=100)
            lead_id = get_radist_lead_id(user_id)

            # Stage guard: если менеджер уже взял лид (не NEW) — заглушаем
            # Sofia для этого user и не трогаем Bitrix совсем.
            if lead_id:
                status = await get_lead_status(lead_id)
                if status != "NEW":
                    set_manager_active(DB_PATH, user_id, True)
                    log(
                        f"⚠️ [TIMEOUT_SKIP] lead #{lead_id} in stage={status} "
                        f"(not NEW), user {user_id} muted"
                    )
                    radist_reminder_tasks.pop(user_key, None)
                    radist_reminder_sent.pop(user_key, None)
                    return

            # Получаем сохранённый TG username для передачи в Bitrix
            stored_tg = get_tg_username(channel, chat_id)
            tg_url = f"https://t.me/{stored_tg}" if stored_tg else ""

            new_lead_id = await create_or_update_lead(
                lead_id,
                user_name,
                state_fresh,
                history,
                is_final=True,
                channel="radist_telegram",
                telegram_username=f"@{stored_tg}" if stored_tg else None,
                telegram_url=tg_url,
            )
            if new_lead_id and not lead_id:
                save_radist_lead_id(user_id, new_lead_id)

            final_lead_id = new_lead_id or lead_id
            if final_lead_id:
                await finalize_lead(DB_PATH, final_lead_id)
        except Exception as e:
            logging.warning(f"⚠️ [RADIST BITRIX] finalize_timeout error: {e}")
    elif _get_source_object(user_id) == "rizalta":
        log(
            f"🚫 [BITRIX_SKIP] source=rizalta function=radist_finalize_timeout "
            f"user_id={user_id}"
        )

    log(f"⏱️ [TIMEOUT] {finish_type} для user_key={user_key}, user_id={user_id}")

    radist_reminder_tasks.pop(user_key, None)
    radist_reminder_sent.pop(user_key, None)


async def radist_send_reminder(
    user_key: str,
    user_id: int,
    channel: str,
    chat_id: int,
    connection_id: int,
    phone: str,
    user_name: str,
):
    """Отправляет напоминание через 60 мин (сценарий Б)."""
    log(
        f"⏳ [TIMEOUT-Б] Запущен для {user_name}, "
        f"user_key={user_key}, ждём {TIMEOUT_REMINDER}с"
    )
    try:
        await asyncio.sleep(TIMEOUT_REMINDER)

        if not _is_radist_dialog_active(user_id):
            return

        state = state_manager.get_state(user_id)
        if state and state.meeting_agreed:
            return

        history = get_history(channel, chat_id)
        if not history:
            return

        last_msg = history[-1]
        if last_msg.get("role") != "assistant":
            return

        # Stage guard перед отправкой напоминания: если менеджер взял лид,
        # Sofia молчит (manager_active=True → Sofia отключена во всех каналах).
        lead_id = get_radist_lead_id(user_id)
        if lead_id:
            status = await get_lead_status(lead_id)
            if status != "NEW":
                set_manager_active(DB_PATH, user_id, True)
                log(
                    f"⚠️ [REMINDER_SKIP] lead #{lead_id} in stage={status} "
                    f"(not NEW), user {user_id} muted"
                )
                return

        # Отправляем напоминание через Radist
        reminder_text = random.choice(REMINDER_PHRASES).format(name=user_name)
        success = await send_message(connection_id, chat_id, reminder_text)
        if success:
            contact_id = 0  # Не критично для напоминания
            save_message(
                channel,
                connection_id,
                chat_id,
                contact_id,
                phone,
                "assistant",
                reminder_text,
            )
            log(f"⏰ [RADIST] Напоминание → {user_name}")
            await notify_observer(
                channel,
                phone,
                user_name,
                "out",
                reminder_text,
                source_object=_get_source_object(user_id),
            )

        radist_reminder_sent[user_key] = True

        # Ждём ещё 15 мин
        await asyncio.sleep(TIMEOUT_AFTER_REMINDER)

        if not _is_radist_dialog_active(user_id):
            return

        last_time = _get_radist_last_message_time(channel, chat_id)
        if (
            last_time
            and (datetime.now().timestamp() - last_time) >= TIMEOUT_AFTER_REMINDER - 30
        ):
            # Свежий stage-check перед финализацией (стадия могла поменяться
            # за 15 мин sleep после первой проверки перед отправкой напоминания).
            lead_id = get_radist_lead_id(user_id)
            if lead_id:
                status = await get_lead_status(lead_id)
                if status != "NEW":
                    set_manager_active(DB_PATH, user_id, True)
                    log(
                        f"⚠️ [REMINDER_SKIP] lead #{lead_id} in stage={status} "
                        f"(not NEW) before finalize, user {user_id} muted"
                    )
                    return

            await _radist_finalize_timeout(
                user_key,
                user_id,
                channel,
                chat_id,
                connection_id,
                phone,
                user_name,
                "no_response_after_reminder",
            )
    except asyncio.CancelledError:
        log(f"⏳ [TIMEOUT-Б] Отменён для {user_key}")
    except Exception as e:
        log(f"❌ [TIMEOUT-Б] Ошибка для {user_key}: {e}")


async def radist_timeout_no_response(
    user_key: str,
    user_id: int,
    channel: str,
    chat_id: int,
    connection_id: int,
    phone: str,
    user_name: str,
):
    """Сценарий А: 0 сообщений от клиента → 15 мин → финализация."""
    log(
        f"⏳ [TIMEOUT-A] Запущен для {user_name}, "
        f"user_key={user_key}, ждём {TIMEOUT_NO_RESPONSE}с"
    )
    try:
        await asyncio.sleep(TIMEOUT_NO_RESPONSE)

        if not _is_radist_dialog_active(user_id):
            log(f"⏳ [TIMEOUT-A] Диалог не активен для {user_key}, пропускаем")
            return

        user_count = _count_radist_user_messages(channel, chat_id)
        if user_count > 1:
            # >1 потому что первое сообщение — триггер, ответ клиента = 2+
            log(f"⏳ [TIMEOUT-A] Клиент ответил ({user_count} msgs), пропускаем")
            return

        log(f"⏳ [TIMEOUT-A] Финализируем — 0 ответов для {user_key}")
        await _radist_finalize_timeout(
            user_key,
            user_id,
            channel,
            chat_id,
            connection_id,
            phone,
            user_name,
            "no_response",
        )
    except asyncio.CancelledError:
        log(f"⏳ [TIMEOUT-A] Отменён для {user_key}")
    except Exception as e:
        log(f"❌ [TIMEOUT-A] Ошибка для {user_key}: {e}")


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
    await notify_observer(
        channel,
        phone,
        user_name,
        "in",
        user_message,
        source_object=_get_source_object(user_id),
    )

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
        await notify_observer(
            channel,
            phone,
            user_name,
            "out",
            response,
            source_object=_get_source_object(user_id),
        )


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
    tg_username = context.get("tg_username", "")
    tg_profile_link = context.get("tg_profile_link", "")

    channel_offset = {"max": 1000000, "telegram": 2000000, "whatsapp": 3000000}
    offset = channel_offset.get(channel, 9000000)
    user_id = -(offset + chat_id)
    user_key = f"{channel}:{chat_id}"

    if not user_name:
        user_name = phone

    emoji = CHANNEL_EMOJI.get(channel, "📨")
    log(f"{emoji} [{channel.upper()}] {phone}: {combined_message}")

    # Отмена предыдущих таймеров при новом сообщении
    if user_key in radist_reminder_tasks:
        radist_reminder_tasks[user_key].cancel()
    radist_reminder_sent.pop(user_key, None)

    # ════════════════════════════════════════════════════════════════════════
    # Source routing: распознаём объект из первого сообщения
    # ════════════════════════════════════════════════════════════════════════
    from config.source_objects import detect_source

    obj_config, clean_text = detect_source(combined_message)
    is_first_atl = False
    if obj_config:
        state_manager.update_state(user_id, {"source_object": obj_config["key"]})
        log(
            f"🏷️ [{channel.upper()}] Объект распознан: "
            f"{obj_config['short_name']} → source_object={obj_config['key']}"
        )
        combined_message = clean_text
        is_first_atl = obj_config.get("key") == "atlantis"

    # ════════════════════════════════════════════════════════════════════════
    # Bitrix: привязка к лиду при первом ATL-сообщении
    # ════════════════════════════════════════════════════════════════════════
    # Telegram URL для Bitrix (нормализация)
    telegram_url = ""
    if tg_username:
        telegram_url = f"https://t.me/{tg_username}"
    elif tg_profile_link and tg_profile_link.startswith("https://t.me/"):
        telegram_url = tg_profile_link

    if is_first_atl:
        try:
            lead_data = await find_recent_atlantis_lead()
            if lead_data:
                existing_lead_id = lead_data["id"]
                save_radist_lead_id(user_id, existing_lead_id)

                orig_assigned = lead_data.get("assigned_by_id")
                if orig_assigned:
                    save_original_assigned(DB_PATH, existing_lead_id, orig_assigned)

                await set_lead_assigned(existing_lead_id, SOFIA_AI_USER_ID)

                radist_info = f"Radist {channel}: {phone or user_name}"
                await update_lead(
                    existing_lead_id,
                    comments=(f"{radist_info}\n" f"София подключена к диалогу."),
                    telegram_url=telegram_url,
                )
                log(
                    f"🔗 [BITRIX] Привязан к лиду Тильды #{existing_lead_id} "
                    f"для radist user {user_id}, original_assigned={orig_assigned}"
                )
        except Exception as e:
            logging.warning(f"⚠️ [RADIST BITRIX] find_recent_atlantis_lead error: {e}")

    # Сохранение клиентского сообщения — вызывается один раз после
    # опустошения очереди (внутри send_callback), а не на каждой итерации
    async def save_user_and_notify():
        save_message(
            channel, connection_id, chat_id, contact_id, phone, "user", combined_message
        )
        await notify_observer(
            channel,
            phone,
            user_name,
            "in",
            combined_message,
            source_object=_get_source_object(user_id),
        )

    # ════════════════════════════════════════════════════════════════════════
    # Guard: manager_active — София молчит
    # ════════════════════════════════════════════════════════════════════════
    if is_manager_active(DB_PATH, user_id):
        log(f"🛑 [{channel.upper()}] manager_active=1 для user_id={user_id}, молчим")
        return {"response": None, "send_callback": save_user_and_notify}

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
        return {"response": None, "send_callback": save_user_and_notify}

    # Генерация ответа
    response = await generate_response(
        channel, chat_id, user_id, combined_message, user_name
    )

    if response is None:
        log(f"🔇 [{channel.upper()}] Ответ не требуется — молчим")
        return {"response": None, "send_callback": save_user_and_notify}

    # Callback для отправки (вызывается после проверки очереди)
    async def send_callback():
        await save_user_and_notify()
        save_message(
            channel, connection_id, chat_id, contact_id, phone, "assistant", response
        )
        success = await send_message(connection_id, chat_id, response)
        if success:
            log(f"{emoji} [{channel.upper()}] → {user_name}: {response[:50]}...")
            await notify_observer(
                channel,
                phone,
                user_name,
                "out",
                response,
                source_object=_get_source_object(user_id),
            )

        # ════════════════════════════════════════════════════════════════
        # Bitrix: meeting_agreed → финализация
        # ════════════════════════════════════════════════════════════════
        state_fresh = state_manager.get_state(user_id)
        meeting_ok = bool(getattr(state_fresh, "meeting_agreed", False))
        if meeting_ok and not getattr(state_fresh, "dialog_finished", False):
            state_manager.update_state(
                user_id, {"dialog_finished": True, "finish_type": "meeting"}
            )
            state_fresh = state_manager.get_state(user_id)
            log(f"✅ [RADIST] meeting_agreed → финализация для user {user_id}")

        is_final = bool(getattr(state_fresh, "dialog_finished", False))

        # ════════════════════════════════════════════════════════════════
        # Bitrix CRM: только для source-сессий (ATL и др.)
        # ════════════════════════════════════════════════════════════════
        if _is_radist_bitrix_session(user_id):
            try:
                history_fresh = get_history(channel, chat_id, limit=100)
                lead_id = get_radist_lead_id(user_id)

                new_lead_id = await create_or_update_lead(
                    lead_id,
                    user_name,
                    state_fresh,
                    history_fresh,
                    is_final=is_final,
                    channel="radist_telegram",
                    telegram_username=f"@{tg_username}" if tg_username else None,
                    telegram_url=telegram_url,
                )
                if new_lead_id and not lead_id:
                    save_radist_lead_id(user_id, new_lead_id)
                    log(
                        f"🏷️ [BITRIX] Лид #{new_lead_id} создан "
                        f"для radist user {user_id}"
                    )
                elif lead_id:
                    log(
                        f"🔄 [BITRIX] Лид #{lead_id} обновлён "
                        f"для radist user {user_id}"
                    )

                if is_final:
                    final_lead_id = new_lead_id or lead_id
                    if final_lead_id:
                        await finalize_lead(DB_PATH, final_lead_id)
            except Exception as e:
                logging.warning(f"⚠️ [RADIST BITRIX] create_or_update error: {e}")
        elif _get_source_object(user_id) == "rizalta":
            log(
                f"🚫 [BITRIX_SKIP] source=rizalta function=radist_callback "
                f"user_id={user_id}"
            )

        # ════════════════════════════════════════════════════════════════
        # Таймеры (если диалог не финализирован)
        # ════════════════════════════════════════════════════════════════
        if not is_final:
            if user_key in radist_reminder_tasks:
                radist_reminder_tasks[user_key].cancel()
            radist_reminder_sent.pop(user_key, None)

            if is_first_atl:
                # Сценарий А: первый ATL-контакт → 15 мин без ответа → finalize
                radist_reminder_tasks[user_key] = asyncio.create_task(
                    radist_timeout_no_response(
                        user_key,
                        user_id,
                        channel,
                        chat_id,
                        connection_id,
                        phone,
                        user_name,
                    )
                )
            else:
                # Сценарий Б: диалог идёт → 60 мин → reminder → 15 мин → finalize
                radist_reminder_tasks[user_key] = asyncio.create_task(
                    radist_send_reminder(
                        user_key,
                        user_id,
                        channel,
                        chat_id,
                        connection_id,
                        phone,
                        user_name,
                    )
                )

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
            tg_username = chat.get("username") or ""
            tg_profile_link = chat.get("profile_link") or ""

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
                save_chat(
                    channel,
                    connection_id,
                    chat_id,
                    contact_id,
                    phone,
                    user_name,
                    tg_username=tg_username,
                )

                # Обрабатываем через очередь (защита от race condition)
                user_key = f"{channel}:{chat_id}"
                context = {
                    "channel": channel,
                    "connection_id": connection_id,
                    "chat_id": chat_id,
                    "contact_id": contact_id,
                    "phone": phone,
                    "user_name": user_name,
                    "tg_username": tg_username,
                    "tg_profile_link": tg_profile_link,
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
