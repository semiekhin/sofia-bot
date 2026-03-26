#!/usr/bin/env python3
"""
Sofia Bot (GPT) — AI-продажник недвижимости
==============================================
Версия: 2.0 с Stage-Aware RAG
Oazis Estate
"""

import asyncio
import sqlite3
import json
import csv
from datetime import datetime, timedelta
import random
from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import os
from dotenv import load_dotenv
from sofia_prompt_v2 import BOT_NAME

try:
    from stage_detector import get_stage_context  # только для /stage команды
except ImportError:

    def get_stage_context(s):
        return {"goal": "N/A", "next_step": "N/A"}


from rag_module import init_vector_store, get_collection_stats
from state_manager import StateManager
from message_processor import process_message
from core.pipeline import run_pipeline
from core.bitrix import (
    create_or_update_lead,
    find_recent_atlantis_lead,
    is_manager_active,
    restore_assigned,
    save_original_assigned,
    set_lead_assigned,
    update_lead,
    SOFIA_AI_USER_ID,
)

# Детекторы отключены — управление через промпт + RAG
# from detectors import ...

load_dotenv()

# ============================================
# НАСТРОЙКИ
# ============================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "512319063"))
OBSERVER_CHAT_ID = int(os.getenv("OBSERVER_CHAT_ID", "-5206139579"))

# Модель OpenAI
MODEL_MODE = os.getenv("MODEL_MODE", "gpt-5.2")
# v3.0: LLM-Planner
USE_LLM_PLANNER = os.getenv("USE_LLM_PLANNER", "false").lower() == "true"

MODEL_CONFIGS = {
    "gpt-4o": {
        "model": "gpt-4o",
        "use_responses_api": False,
        "temperature": 0.4,
        "max_tokens": 200,
    },
    "gpt-5.2": {
        "model": "gpt-5.2",
        "use_responses_api": True,
        "max_tokens": 400,
        "reasoning": None,
    },
    "gpt-5.2-reasoning": {
        "model": "gpt-5.2",
        "use_responses_api": True,
        "max_tokens": 400,
        "reasoning": {"effort": "xhigh"},
    },
}


def get_model_config():
    return MODEL_CONFIGS.get(MODEL_MODE, MODEL_CONFIGS["gpt-5.2"])


SOFIA_PATH = os.getenv("SOFIA_PATH", "/opt/sofia-gpt-dev")
DB_PATH = os.path.join(SOFIA_PATH, os.getenv("DB_PATH", "sofia_gpt.db"))

# NEW: State Manager для агентной архитектуры
state_manager = StateManager(DB_PATH)


# ============================================
# BITRIX: хелперы для lead_id (отдельная таблица)
# ============================================
# НЕ храним в client_state — state_manager делает INSERT OR REPLACE
# без bitrix_lead_id, что стирает значение при каждом save_state().


def _migrate_bitrix_tables():
    """Создаёт таблицу telegram_leads если её нет."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telegram_leads (
            user_id INTEGER PRIMARY KEY,
            bitrix_lead_id INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_bitrix_lead_id(user_id: int) -> int | None:
    """Получить bitrix_lead_id из telegram_leads."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bitrix_lead_id FROM telegram_leads WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def save_bitrix_lead_id(user_id: int, lead_id: int):
    """Сохранить bitrix_lead_id в telegram_leads."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO telegram_leads (user_id, bitrix_lead_id)
           VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET bitrix_lead_id = ?""",
        (user_id, lead_id, lead_id),
    )
    conn.commit()
    conn.close()


def clear_bitrix_lead_id(user_id: int):
    """Сбросить lead_id при /start (новый диалог → новый лид)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM telegram_leads WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


LOG_PATH = "sofia_bot.log"
ANTIFLOOD_DELAY = 3
CONTEXT_SIZE = 8  # Последние 8 сообщений

ADMIN_IDS = [5186134824, 512319063]

# RAG настройки
RAG_EXAMPLES_COUNT = 10  # Сколько примеров добавлять в промпт
RAG_ENABLED = True  # Включить/выключить RAG

# Маппинг Action → Stage для RAG (чтобы RAG искал по действию Planner, а не Stage Detector)

# ============================================
# WAIT-ЛОГИКА: не отвечать после договорённости
# ============================================

SHORT_CONFIRMATIONS = {
    "ок",
    "ok",
    "да",
    "хорошо",
    "ладно",
    "понял",
    "понятно",
    "ясно",
    "угу",
    "+",
    "отлично",
    "супер",
    "класс",
    "👍",
    "принял",
    "принято",
    "договорились",
    "ага",
    "угум",
    "ок!",
    "хор",
    "да!",
    "ок.",
    "good",
    "yes",
    "ясненько",
    "понятненько",
}

MEETING_MARKERS = [
    "созвон",
    "ссылку пришлю",
    "пришлю ссылку",
    "видео-встреча",
    "zoom",
    "встретимся",
    "до связи",
    "ждём вас",
    "жду вас",
    "буду ждать",
    "ссылку на созвон",
    "по мск",
    "заранее",
]


def should_skip_response(message: str, last_bot_message: str) -> bool:
    """
    WAIT-логика: не отвечать на короткие подтверждения после договорённости.
    Возвращает True если НЕ нужно отвечать.
    """
    if not last_bot_message:
        return False

    msg_lower = message.strip().lower().rstrip("!.,")

    # Проверка 1: это короткое подтверждение?
    is_short = msg_lower in SHORT_CONFIRMATIONS or len(msg_lower) < 8

    # Проверка 2: предыдущее сообщение бота содержит маркер договорённости?
    bot_msg_lower = last_bot_message.lower()
    has_meeting_marker = any(marker in bot_msg_lower for marker in MEETING_MARKERS)

    return is_short and has_meeting_marker


def get_last_bot_message(chat_id) -> str:
    """Получить последнее сообщение бота для chat_id"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT content FROM messages WHERE chat_id = ? AND role = "assistant" ORDER BY timestamp DESC LIMIT 1',
        (chat_id,),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""


# Инициализация GPT
client = OpenAI(api_key=OPENAI_API_KEY)

# Состояния пользователей
waiting_for_comment = {}
user_stages = {}  # Отслеживание этапа для каждого пользователя


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================
# БАЗА ДАННЫХ
# ============================================


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER, user_id INTEGER, user_name TEXT,
        role TEXT, content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        processed INTEGER DEFAULT 0,
        stage TEXT DEFAULT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, chat_id INTEGER, user_name TEXT,
        first_contact DATETIME, last_message DATETIME,
        messages_count INTEGER DEFAULT 0,
        current_stage TEXT DEFAULT 'GREETING'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS feedback_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user_id INTEGER,
        expert_name TEXT,
        context TEXT,
        rating TEXT,
        comment TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    # NEW: Таблица для логов RAG
    c.execute("""CREATE TABLE IF NOT EXISTS rag_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user_message TEXT,
        detected_stage TEXT,
        confidence REAL,
        examples_used TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()

    # Инициализируем векторный RAG при старте
    if RAG_ENABLED:
        rag_ok = init_vector_store()
        if not rag_ok:
            log("⚠️ Векторный RAG не инициализирован!")

    _migrate_bitrix_tables()

    log(
        f"📦 База данных инициализирована (GPT: {MODEL_MODE}, RAG: {'ON' if RAG_ENABLED else 'OFF'})"
    )


def save_message(chat_id, user_id, user_name, role, content, processed=0, stage=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (chat_id, user_id, user_name, role, content, processed, stage) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, user_name, role, content, processed, stage),
    )
    message_id = c.lastrowid
    conn.commit()
    conn.close()
    return message_id


def save_rag_log(chat_id, user_message, stage, confidence, examples):
    """Сохраняет лог RAG для анализа."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    examples_json = json.dumps(
        [ex.get("id", "") for ex in examples], ensure_ascii=False
    )
    c.execute(
        "INSERT INTO rag_logs (chat_id, user_message, detected_stage, confidence, examples_used) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_message, stage, confidence, examples_json),
    )
    conn.commit()
    conn.close()


def get_conversation_history(chat_id, limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


def get_context_for_feedback(chat_id, limit=CONTEXT_SIZE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"role": row[0], "content": row[1], "time": row[2]} for row in reversed(rows)
    ]


def get_unprocessed_messages(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, content, timestamp FROM messages WHERE chat_id = ? AND role = "user" AND processed = 0 ORDER BY timestamp ASC',
        (chat_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def mark_messages_processed(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'UPDATE messages SET processed = 1 WHERE chat_id = ? AND role = "user" AND processed = 0',
        (chat_id,),
    )
    conn.commit()
    conn.close()


def clear_chat_history(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

    # Сбрасываем этап
    if chat_id in user_stages:
        del user_stages[chat_id]

    log(f"🗑️ История чата {chat_id} очищена")


def reset_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'UPDATE users SET messages_count = 0, current_stage = "GREETING" WHERE user_id = ?',
        (user_id,),
    )
    conn.commit()
    conn.close()


def update_user(user_id, chat_id, user_name, stage=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if stage:
        c.execute(
            """INSERT INTO users (user_id, chat_id, user_name, first_contact, last_message, messages_count, current_stage)
                     VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, ?)
                     ON CONFLICT(user_id) DO UPDATE SET last_message = CURRENT_TIMESTAMP, messages_count = messages_count + 1, current_stage = ?""",
            (user_id, chat_id, user_name, stage, stage),
        )
    else:
        c.execute(
            """INSERT INTO users (user_id, chat_id, user_name, first_contact, last_message, messages_count)
                     VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                     ON CONFLICT(user_id) DO UPDATE SET last_message = CURRENT_TIMESTAMP, messages_count = messages_count + 1""",
            (user_id, chat_id, user_name),
        )

    conn.commit()
    conn.close()


def is_new_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT messages_count FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is None or row[0] == 0


def get_user_stage(chat_id):
    """Получает текущий этап пользователя."""
    return user_stages.get(chat_id, "GREETING")


def set_user_stage(chat_id, stage):
    """Устанавливает текущий этап пользователя."""
    user_stages[chat_id] = stage


# ============================================
# УВЕДОМЛЕНИЯ МЕНЕДЖЕРУ
# ============================================


async def notify_manager_deal(bot, client_state, user_name: str, finish_type: str):
    """
    Отправляет уведомление менеджеру о новой договорённости.
    finish_type: 'meeting' или 'materials'
    """
    try:
        # Формируем информацию о клиенте
        goal_map = {"investment": "инвестиция", "personal": "для себя"}
        goal_text = goal_map.get(client_state.goal, client_state.goal or "не указана")

        location_text = client_state.location or "не указана"
        budget_text = (
            f"{client_state.budget/1_000_000:.1f} млн"
            if client_state.budget
            else "не указан"
        )

        if finish_type == "meeting":
            emoji = "📞"
            type_text = "Созвон"
            meeting_line = (
                f"\n⏰ Время: {client_state.meeting_datetime or 'уточняется'}"
            )
        else:
            emoji = "📋"
            type_text = "Подборка материалов"
            meeting_line = ""

        message = f"""🏁 Новая договорённость

{emoji} Тип: {type_text}
👤 Клиент: {user_name}
🎯 Цель: {goal_text}
📍 Локация: {location_text}
💰 Бюджет: {budget_text}{meeting_line}
"""

        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        log(f"📨 Уведомление менеджеру: {finish_type} для {user_name}")

    except Exception as e:
        log(f"❌ Ошибка уведомления: {e}")


# ============================================
# FEEDBACK
# ============================================


def save_feedback_v2(chat_id, user_id, expert_name, context, rating, comment=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    context_json = json.dumps(context, ensure_ascii=False)
    c.execute(
        """INSERT INTO feedback_v2 (chat_id, user_id, expert_name, context, rating, comment)
                 VALUES (?, ?, ?, ?, ?, ?)""",
        (chat_id, user_id, expert_name, context_json, rating, comment),
    )
    conn.commit()
    conn.close()
    log(f"📊 Feedback: {rating} от {expert_name}")


def export_feedback_json():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT context, rating, comment, expert_name, timestamp FROM feedback_v2 ORDER BY timestamp"
    )
    rows = c.fetchall()
    conn.close()

    data = []
    for r in rows:
        data.append(
            {
                "context": json.loads(r[0]),
                "rating": r[1],
                "comment": r[2],
                "expert_name": r[3],
                "timestamp": r[4],
            }
        )

    filepath = "training_data.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath, len(data)


def export_feedback_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT context, rating, comment, expert_name, timestamp FROM feedback_v2 ORDER BY timestamp"
    )
    rows = c.fetchall()
    conn.close()

    filepath = "training_data.csv"
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["context", "rating", "comment", "expert_name", "timestamp"])
        writer.writerows(rows)
    return filepath, len(rows)


def get_feedback_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating, COUNT(*) FROM feedback_v2 GROUP BY rating")
    rows = c.fetchall()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM feedback_v2")
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM feedback_v2 WHERE comment != ""')
    with_comments = c.fetchone()[0]
    conn.close()

    stats = {
        "good": 0,
        "bad": 0,
        "total": 0,
        "users": users,
        "with_comments": with_comments,
    }
    for row in rows:
        stats[row[0]] = row[1]
        stats["total"] += row[1]
    return stats


# ============================================
# КНОПКИ ОЦЕНКИ
# ============================================


def get_rating_keyboard(message_id):
    keyboard = [
        [
            InlineKeyboardButton("❌ Нет", callback_data=f"rate_bad_{message_id}"),
            InlineKeyboardButton("✅ Да", callback_data=f"rate_good_{message_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_rating(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    user_name = query.from_user.first_name or "эксперт"
    chat_id = query.message.chat_id

    if data.startswith("rate_good_"):
        rating = "good"
        emoji = "✅"
    elif data.startswith("rate_bad_"):
        rating = "bad"
        emoji = "❌"
    else:
        return

    ctx = get_context_for_feedback(chat_id, CONTEXT_SIZE)

    waiting_for_comment[chat_id] = {
        "rating": rating,
        "context": ctx,
        "user_id": user_id,
        "expert_name": user_name,
    }

    await query.edit_message_reply_markup(reply_markup=None)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{emoji} Оценка принята!\n\n💬 Напишите комментарий (почему {rating == 'good' and 'хорошо' or 'плохо'}?)\n\nИли /skip чтобы пропустить",
    )

    log(f"👍 {user_name} оценил: {rating}, ждём комментарий")


# ============================================
# АНТИФЛУД
# ============================================

pending_responses = {}
reminder_tasks = {}  # Таймеры напоминания
# {chat_id: True} — напоминание уже отправлено, ждём финализации
reminder_sent = {}

REMINDER_PHRASES = [
    "{name}, продолжим общение?",
    "{name}, не забыли про меня?",
]

# Таймауты (секунды)
TIMEOUT_NO_RESPONSE = 15 * 60  # Сценарий А: 15 мин без ответа
TIMEOUT_REMINDER = 60 * 60  # Сценарий Б: 60 мин → напоминание
TIMEOUT_AFTER_REMINDER = 15 * 60  # Сценарий Б: +15 мин после напоминания → финализация


def _get_last_message_time(chat_id: int) -> float | None:
    """Время последнего сообщения в диалоге (unix timestamp)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1",
        (chat_id,),
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


def _count_user_messages(chat_id: int) -> int:
    """Количество сообщений от клиента (role=user) в диалоге."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND role = 'user' "
        "AND content NOT LIKE '/start%'",
        (chat_id,),
    )
    count = c.fetchone()[0]
    conn.close()
    return count


def _get_user_id_for_chat(chat_id: int) -> int | None:
    """Получить user_id по chat_id из messages."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT user_id FROM messages WHERE chat_id = ? AND role = 'user' LIMIT 1",
        (chat_id,),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else chat_id


def _get_user_name_for_chat(chat_id: int) -> str:
    """Получить user_name по chat_id из messages (любая роль)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT user_name FROM messages WHERE chat_id = ? AND user_name != '' "
        "AND user_name IS NOT NULL LIMIT 1",
        (chat_id,),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Клиент"


def _is_dialog_active(chat_id: int) -> bool:
    """Проверяет что диалог не завершён и менеджер не перехватил."""
    user_id = _get_user_id_for_chat(chat_id)
    state = state_manager.get_state(user_id)
    if state and getattr(state, "dialog_finished", False):
        return False
    if is_manager_active(DB_PATH, user_id):
        return False
    return True


async def _finalize_timeout(chat_id: int, finish_type: str, bot):
    """Финализирует лид в Битрикс по таймауту."""
    user_id = _get_user_id_for_chat(chat_id)
    user_name = _get_user_name_for_chat(chat_id)

    state_manager.update_state(
        user_id, {"dialog_finished": True, "finish_type": finish_type}
    )
    state_fresh = state_manager.get_state(user_id)
    history = get_conversation_history(chat_id, limit=100)
    lead_id = get_bitrix_lead_id(user_id)

    new_lead_id = await create_or_update_lead(
        lead_id,
        user_name,
        state_fresh,
        history,
        is_final=True,
        channel="telegram",
    )
    if new_lead_id and not lead_id:
        save_bitrix_lead_id(user_id, new_lead_id)

    # Вернуть ответственного после завершения
    final_lead_id = new_lead_id or lead_id
    if final_lead_id:
        await restore_assigned(DB_PATH, final_lead_id)

    log(f"⏱️ [TIMEOUT] {finish_type} для chat {chat_id}, user {user_id}")

    # Убираем из отслеживания
    reminder_tasks.pop(chat_id, None)
    reminder_sent.pop(chat_id, None)


async def send_reminder(chat_id, user_name, context):
    """Отправляет напоминание через 60 мин (сценарий Б)."""
    log(
        f"⏳ [TIMEOUT-Б] Запущен для {user_name}, chat {chat_id}, ждём {TIMEOUT_REMINDER}с"
    )
    await asyncio.sleep(TIMEOUT_REMINDER)

    if not _is_dialog_active(chat_id):
        return

    # Проверяем meeting_agreed
    user_id = _get_user_id_for_chat(chat_id)
    state = state_manager.get_state(user_id)
    if state and state.meeting_agreed:
        return

    history = get_conversation_history(chat_id)
    if not history:
        return

    last_msg = history[-1]
    if last_msg.get("role") != "assistant":
        return  # Последнее сообщение от клиента — не напоминаем

    # Отправляем напоминание
    reminder_text = random.choice(REMINDER_PHRASES).format(name=user_name)
    await context.bot.send_message(chat_id=chat_id, text=reminder_text)
    save_message(chat_id, 0, BOT_NAME, "assistant", reminder_text, processed=1)
    log(f"⏰ Напоминание → {user_name}")
    reminder_sent[chat_id] = True

    # Ждём ещё 15 мин — если нет ответа, финализируем
    await asyncio.sleep(TIMEOUT_AFTER_REMINDER)

    if not _is_dialog_active(chat_id):
        return

    # Проверяем что клиент не ответил за 15 мин после напоминания
    last_time = _get_last_message_time(chat_id)
    if (
        last_time
        and (datetime.now().timestamp() - last_time) >= TIMEOUT_AFTER_REMINDER - 30
    ):
        await _finalize_timeout(chat_id, "no_response_after_reminder", context.bot)


async def timeout_checker_no_response(chat_id, user_name, context):
    """Сценарий А: 0 сообщений от клиента → 15 мин → финализация без напоминания."""
    log(
        f"⏳ [TIMEOUT-A] Запущен для {user_name}, chat {chat_id}, ждём {TIMEOUT_NO_RESPONSE}с"
    )
    try:
        await asyncio.sleep(TIMEOUT_NO_RESPONSE)

        if not _is_dialog_active(chat_id):
            log(f"⏳ [TIMEOUT-A] Диалог не активен для chat {chat_id}, пропускаем")
            return

        # Перепроверяем: клиент так и не ответил?
        user_count = _count_user_messages(chat_id)
        if user_count > 0:
            log(f"⏳ [TIMEOUT-A] Клиент ответил ({user_count} msgs), пропускаем")
            return

        log(f"⏳ [TIMEOUT-A] Финализируем — 0 ответов для chat {chat_id}")
        await _finalize_timeout(chat_id, "no_response", context.bot)
    except asyncio.CancelledError:
        log(f"⏳ [TIMEOUT-A] Отменён для chat {chat_id}")
    except Exception as e:
        log(f"❌ [TIMEOUT-A] Ошибка для chat {chat_id}: {e}")


async def delayed_response(chat_id, user_id, user_name, context, tg_user=None):
    await asyncio.sleep(ANTIFLOOD_DELAY)
    unprocessed = get_unprocessed_messages(chat_id)
    if not unprocessed:
        return

    if len(unprocessed) == 1:
        combined_message = unprocessed[0][1]
        was_offline = False
    else:
        messages = [msg[1] for msg in unprocessed]
        combined_message = "\n".join(messages)
        was_offline = True
        log(f"⚠️ Накопилось {len(unprocessed)} сообщений от {user_name}")

    mark_messages_processed(chat_id)

    # ════════════════════════════════════════════════════════════════════════
    # Унифицированная обработка через message_processor
    # ════════════════════════════════════════════════════════════════════════

    history = get_conversation_history(chat_id, limit=100)
    result = await process_message(
        state_manager=state_manager,
        user_id=user_id,
        user_name=user_name,
        message=combined_message,
        history=history,
        channel="telegram",
    )

    # Если WAIT — не отвечаем
    if result["skip_response"]:
        return

    action_context = result.get("action_context")
    client_state = result["client_state"]

    # Уведомление менеджеру при завершении диалога
    if result.get("should_notify"):
        await notify_manager_deal(
            context.bot,
            client_state,
            user_name,
            result.get("notification_type", "unknown"),
        )

    # ════════════════════════════════════════════════════════════════════════

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(chat_id, context.bot, stop_typing))

    try:
        response, stage = await generate_response_with_rag(
            chat_id, user_id, combined_message, user_name, was_offline, action_context
        )
    finally:
        stop_typing.set()
        await typing_task

    if response is None:
        log(f"🔇 Ответ не требуется — молчим")
        return

    msg_id = save_message(
        chat_id, 0, BOT_NAME, "assistant", response, processed=1, stage=stage
    )

    await context.bot.send_message(chat_id=chat_id, text=response)
    log(f"📤 София → {user_name}: {response[:100]}...")

    # ── Bitrix CRM: создаём/обновляем лид ──
    try:
        state_fresh = state_manager.get_state(user_id)
        history_fresh = get_conversation_history(chat_id, limit=100)
        lead_id = get_bitrix_lead_id(user_id)

        # meeting_agreed → финализация (квалифицирован, созвон согласован)
        meeting_ok = bool(getattr(state_fresh, "meeting_agreed", False))
        if meeting_ok and not getattr(state_fresh, "dialog_finished", False):
            state_manager.update_state(
                user_id, {"dialog_finished": True, "finish_type": "meeting"}
            )
            state_fresh = state_manager.get_state(user_id)
            log(f"✅ [BITRIX] meeting_agreed → финализация для user {user_id}")

        is_final = bool(getattr(state_fresh, "dialog_finished", False))

        # Имя для Битрикса: first_name + @username если есть
        bitrix_name = user_name
        tg_username = None
        if tg_user and tg_user.username:
            bitrix_name = f"{user_name} (@{tg_user.username})"
            tg_username = f"@{tg_user.username}"

        new_lead_id = await create_or_update_lead(
            lead_id,
            bitrix_name,
            state_fresh,
            history_fresh,
            is_final=is_final,
            channel="telegram",
            telegram_username=tg_username,
        )
        if new_lead_id and not lead_id:
            save_bitrix_lead_id(user_id, new_lead_id)
            log(f"🏷️ [BITRIX] Лид #{new_lead_id} создан для TG user {user_id}")
        elif lead_id:
            log(f"🔄 [BITRIX] Лид #{lead_id} обновлён для TG user {user_id}")

        # Вернуть ответственного при финализации
        if is_final:
            final_lead_id = new_lead_id or lead_id
            if final_lead_id:
                await restore_assigned(DB_PATH, final_lead_id)
    except Exception as e:
        log(f"❌ [BITRIX] delayed_response error: {e}")

    if chat_id in pending_responses:
        del pending_responses[chat_id]

    # Не запускаем таймер если диалог финализирован
    if not is_final:
        if chat_id in reminder_tasks:
            reminder_tasks[chat_id].cancel()
        reminder_sent.pop(chat_id, None)
        reminder_tasks[chat_id] = asyncio.create_task(
            send_reminder(chat_id, user_name, context)
        )


# ============================================
# CLAUDE API с RAG
# ============================================


def _format_known_facts(facts: dict) -> str:
    """Форматирует известные факты для промпта"""
    if not facts:
        return "- пока ничего не известно"

    lines = []
    translations = {
        "goal": "Цель",
        "location": "Локация",
        "budget": "Бюджет",
        "payment_type": "Оплата",
        "first_payment": "Первый взнос",
        "lpr": "ЛПР",
    }

    for key, data in facts.items():
        name = translations.get(key, key)
        value = data.get("value", "?")
        conf = data.get("confidence", "?")

        # Форматируем бюджет
        if key in ["budget", "first_payment"] and isinstance(value, int):
            value = f"{value/1_000_000:.1f} млн ₽"

        lines.append(f"- {name}: {value} ({conf})")

    return "\n".join(lines) if lines else "- пока ничего не известно"


async def generate_response_with_rag(
    chat_id, user_id, user_message, user_name, was_offline=False, action_context=None
):
    """
    Генерирует ответ v3.0 через core/pipeline.py.
    Обёртка сохраняет совместимость: set_user_stage, save_rag_log.
    """
    history = get_conversation_history(chat_id)

    result = await run_pipeline(
        user_id=user_id,
        user_message=user_message,
        user_name=user_name,
        history=history,
        state_manager=state_manager,
        channel="telegram",
        was_offline=was_offline,
    )

    # Совместимость: set_user_stage + save_rag_log
    set_user_stage(chat_id, result.stage)
    if RAG_ENABLED:
        save_rag_log(chat_id, user_message, result.stage, 0.0, [])

    return result.answer, result.stage


# Legacy wrapper
async def generate_response(
    chat_id, user_id, user_message, user_name, was_offline=False
):
    response, _ = await generate_response_with_rag(
        chat_id, user_id, user_message, user_name, was_offline
    )
    return response


async def keep_typing(chat_id, bot, stop_event):
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
        except:
            break


# ============================================
# ПРИВЕТСТВИЕ
# ============================================


async def send_greeting(chat_id, user_id, user_name, context, source_object=None):
    if source_object:
        # Сообщение 1: приветствие + ссылка на презентацию
        msg1 = f"{user_name}, добрый день! {source_object['greeting']}"
        msg2_link = source_object["presentation_url"]
        # Сообщение 2: квалификационный вопрос
        msg3 = "Для себя смотрите или как инвестицию?"

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(2)
        await context.bot.send_message(chat_id=chat_id, text=f"{msg1}\n{msg2_link}")
        await asyncio.sleep(5)
        await context.bot.send_message(chat_id=chat_id, text=msg3)

        full_greeting = f"{msg1}\n{msg2_link}\n{msg3}"
        log(f"📤 София: {full_greeting}")
        save_message(
            chat_id, user_id, user_name, "user", "/start", processed=1, stage="GREETING"
        )
        save_message(
            chat_id,
            0,
            BOT_NAME,
            "assistant",
            full_greeting,
            processed=1,
            stage="GREETING",
        )
    else:
        greeting_msg = f"{user_name}, добрый день! Это София, по недвижимости. Вы оставляли заявку на сайте — удобно сейчас пообщаться?"

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        await asyncio.sleep(2)
        await context.bot.send_message(chat_id=chat_id, text=greeting_msg)

        log(f"📤 София: {greeting_msg}")
        save_message(
            chat_id, user_id, user_name, "user", "/start", processed=1, stage="GREETING"
        )
        save_message(
            chat_id,
            0,
            BOT_NAME,
            "assistant",
            greeting_msg,
            processed=1,
            stage="GREETING",
        )

    # Устанавливаем начальный этап
    set_user_stage(chat_id, "GREETING")


# ============================================
# ОБРАБОТЧИКИ
# ============================================


async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id

    log(f"📩 {user_name}: /start")

    if chat_id in waiting_for_comment:
        del waiting_for_comment[chat_id]

    clear_chat_history(chat_id)
    reset_user(user_id)
    state_manager.reset_state(user_id)  # Сброс агентного состояния
    update_user(user_id, chat_id, user_name, stage="GREETING")

    # Source routing: парсинг параметра /start ATL
    source_object = None
    if context.args:
        from config.source_objects import SOURCE_OBJECTS

        param = context.args[0].upper()
        for obj_id, config in SOURCE_OBJECTS.items():
            if param in [k.upper().replace("#", "") for k in config["keywords"]]:
                source_object = config
                state_manager.update_state(user_id, {"source_object": config["key"]})
                log(f"🏷️ /start с объектом: {config['short_name']}")
                break

    await send_greeting(
        chat_id, user_id, user_name, context, source_object=source_object
    )

    # Сбрасываем старый lead_id — новый диалог получит новый лид
    clear_bitrix_lead_id(user_id)

    # Привязка к существующему лиду из Тильды (только для Атлантиса)
    if source_object and source_object.get("key") == "atlantis":
        try:
            lead_data = await find_recent_atlantis_lead()
            if lead_data:
                existing_lead_id = lead_data["id"]
                save_bitrix_lead_id(user_id, existing_lead_id)

                # Сохраняем оригинального ответственного (Тильда/робот)
                orig_assigned = lead_data.get("assigned_by_id")
                if orig_assigned:
                    save_original_assigned(DB_PATH, existing_lead_id, orig_assigned)

                # Ставим Sofia AI ответственной на время квалификации
                await set_lead_assigned(existing_lead_id, SOFIA_AI_USER_ID)

                # Дописываем Telegram username в существующий лид
                tg_info = ""
                if update.effective_user.username:
                    tg_info = f"@{update.effective_user.username}"
                await update_lead(
                    existing_lead_id,
                    comments=(
                        f"Telegram: {tg_info or user_name}\n"
                        f"София подключена к диалогу."
                    ),
                )
                log(
                    f"🔗 [BITRIX] Привязан к лиду Тильды #{existing_lead_id} "
                    f"для user {user_id}, original_assigned={orig_assigned}"
                )
        except Exception as e:
            log(f"❌ [BITRIX] find_recent_atlantis_lead error: {e}")

    # Сценарий А: 15 мин таймаут если клиент не ответит
    if chat_id in reminder_tasks:
        reminder_tasks[chat_id].cancel()
    reminder_sent.pop(chat_id, None)
    reminder_tasks[chat_id] = asyncio.create_task(
        timeout_checker_no_response(chat_id, user_name, context)
    )


async def cmd_reset(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id

    log(f"🔄 {user_name}: /reset")

    if chat_id in waiting_for_comment:
        del waiting_for_comment[chat_id]

    clear_chat_history(chat_id)
    reset_user(user_id)
    state_manager.reset_state(user_id)  # Сброс агентного состояния
    update_user(user_id, chat_id, user_name, stage="GREETING")

    await send_greeting(chat_id, user_id, user_name, context)


async def cmd_skip(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in waiting_for_comment:
        await update.message.reply_text("Нечего пропускать 🤷")
        return

    data = waiting_for_comment[chat_id]

    save_feedback_v2(
        chat_id=chat_id,
        user_id=data["user_id"],
        expert_name=data["expert_name"],
        context=data["context"],
        rating=data["rating"],
        comment="",
    )

    del waiting_for_comment[chat_id]

    await update.message.reply_text("✅ Сохранено без комментария. Продолжайте диалог!")
    log(f"📊 Feedback сохранён без комментария")


async def cmd_stage(update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий этап пользователя."""
    chat_id = update.effective_chat.id
    stage = get_user_stage(chat_id)
    stage_ctx = get_stage_context(stage)

    await update.message.reply_text(
        f"📍 Текущий этап: {stage}\n\n"
        f"🎯 Цель: {stage_ctx['goal']}\n"
        f"➡️ Следующий шаг: {stage_ctx['next_step']}"
    )


async def cmd_model(update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение модели GPT."""
    global MODEL_MODE
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Только админ может переключать модели")
        return

    args = context.args

    if not args:
        config = get_model_config()
        reasoning = (
            "✅ reasoning xhigh" if config.get("reasoning") else "❌ без reasoning"
        )
        modes = "\n".join([f"• {m}" for m in MODEL_CONFIGS.keys()])
        await update.message.reply_text(
            f"🤖 Текущая модель: {MODEL_MODE}\n{reasoning}\n\nДоступные:\n{modes}\n\n/model <режим>"
        )
        return

    new_mode = args[0]
    if new_mode not in MODEL_CONFIGS:
        await update.message.reply_text(f"❌ Неизвестный режим: {new_mode}")
        return

    MODEL_MODE = new_mode
    config = MODEL_CONFIGS[new_mode]
    reasoning = "✅ reasoning xhigh" if config.get("reasoning") else "❌ без reasoning"
    api = "responses API" if config.get("use_responses_api") else "chat completions"

    await update.message.reply_text(
        f"✅ Переключено: {new_mode}\n\n• API: {api}\n• {reasoning}"
    )
    log(f"🔄 Модель → {new_mode}")


async def handle_voice(update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений через Whisper."""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id

    log(f"🎤 {user_name}: голосовое сообщение")

    try:
        # Скачиваем аудио
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        audio_path = f"/tmp/voice_{chat_id}_{voice.file_id}.ogg"
        await file.download_to_drive(audio_path)

        # Транскрибируем через Whisper
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, language="ru"
            )

        # Удаляем временный файл
        import os as os_module

        os_module.remove(audio_path)

        user_message = transcript.text.strip()

        if not user_message:
            await update.message.reply_text(
                "Не удалось распознать. Попробуйте ещё раз или напишите текстом."
            )
            return

        log(f"🎤→📝 {user_name}: {user_message}")

        # Обрабатываем как обычное сообщение
        update_user(user_id, chat_id, user_name)
        save_message(chat_id, user_id, user_name, "user", user_message, processed=0)

        if chat_id in pending_responses:
            pending_responses[chat_id].cancel()

        task = asyncio.create_task(
            delayed_response(
                chat_id, user_id, user_name, context, tg_user=update.effective_user
            )
        )
        pending_responses[chat_id] = task

    except Exception as e:
        log(f"❌ Ошибка распознавания: {e}")
        await update.message.reply_text(
            "Не удалось распознать голос. Попробуйте ещё раз или напишите текстом."
        )


async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id

    # Игнорируем сообщения из групп (включая Observer)
    if update.effective_chat.type in ["group", "supergroup"]:
        return
    user_message = update.message.text

    # Комментарий к оценке?
    if chat_id in waiting_for_comment:
        data = waiting_for_comment[chat_id]

        save_feedback_v2(
            chat_id=chat_id,
            user_id=data["user_id"],
            expert_name=data["expert_name"],
            context=data["context"],
            rating=data["rating"],
            comment=user_message,
        )

        del waiting_for_comment[chat_id]

        await update.message.reply_text(
            "✅ Спасибо за комментарий! Продолжайте диалог."
        )
        log(f"📊 Feedback сохранён с комментарием: {user_message[:50]}...")
        return

    log(f"📩 {user_name}: {user_message}")

    # Проверка перехвата менеджером — София молчит
    if is_manager_active(DB_PATH, user_id):
        log(f"🛑 [TG] manager_active=1 для user_id={user_id}, София молчит")
        save_message(chat_id, user_id, user_name, "user", user_message, processed=1)
        return

    # Приветствия
    is_greeting = user_message.lower().strip() in [
        "привет",
        "здравствуйте",
        "добрый день",
        "добрый вечер",
        "доброе утро",
        "хай",
        "hi",
        "hello",
    ]
    new_user = is_new_user(user_id)

    if is_greeting and new_user:
        update_user(user_id, chat_id, user_name, stage="GREETING")
        await send_greeting(chat_id, user_id, user_name, context)
        return

    update_user(user_id, chat_id, user_name)
    save_message(chat_id, user_id, user_name, "user", user_message, processed=0)

    if chat_id in pending_responses:
        pending_responses[chat_id].cancel()

    # Отменяем таймер если клиент ответил
    if chat_id in reminder_tasks:
        reminder_tasks[chat_id].cancel()
        del reminder_tasks[chat_id]
    reminder_sent.pop(chat_id, None)

    task = asyncio.create_task(
        delayed_response(
            chat_id, user_id, user_name, context, tg_user=update.effective_user
        )
    )
    pending_responses[chat_id] = task


# ============================================
# КОМАНДЫ АДМИНА
# ============================================


async def cmd_export(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    json_path, count = export_feedback_json()
    csv_path, _ = export_feedback_csv()
    stats = get_feedback_stats()

    msg = f"""📊 Экспорт данных (GPT + RAG)

Всего оценок: {stats['total']}
✅ Хорошо: {stats['good']}
❌ Плохо: {stats['bad']}
💬 С комментариями: {stats['with_comments']}
👥 Экспертов: {stats['users']}

🤖 RAG: {'Включен' if RAG_ENABLED else 'Выключен'}"""

    await update.message.reply_text(msg)

    if count > 0:
        with open(json_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename="training_data_claude.json",
            )
        with open(csv_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename="training_data_claude.csv",
            )

    log(f"📤 Экспорт: {count} записей")


async def cmd_stats(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    stats = get_feedback_stats()
    if stats["total"] == 0:
        await update.message.reply_text(
            f"📊 Пока нет оценок\n\n🤖 Модель: {MODEL_MODE}\n📚 RAG: {'ON' if RAG_ENABLED else 'OFF'}"
        )
        return

    good_pct = (stats["good"] / stats["total"] * 100) if stats["total"] > 0 else 0
    msg = f"""📊 Статистика (GPT + RAG)

🤖 Модель: {MODEL_MODE}
📚 RAG: {'Включен' if RAG_ENABLED else 'Выключен'}

Всего оценок: {stats['total']}
✅ Хорошо: {stats['good']} ({good_pct:.1f}%)
❌ Плохо: {stats['bad']} ({100-good_pct:.1f}%)
💬 С комментариями: {stats['with_comments']}
👥 Экспертов: {stats['users']}"""

    await update.message.reply_text(msg)


async def cmd_myid(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Твой user_id: {user_id}")


async def cmd_rag(update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус RAG."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return

    stats = get_collection_stats()

    if stats.get("status") == "not_initialized":
        await update.message.reply_text("❌ Векторный RAG не инициализирован")
        return

    if stats.get("status") == "error":
        await update.message.reply_text(f"❌ Ошибка RAG: {stats.get('error')}")
        return

    msg = f"""📚 Векторный RAG

Статус: ✅ Готов
Примеров всего: {stats.get('count', 0)}
Примеров на запрос: {RAG_EXAMPLES_COUNT}
Модель: text-embedding-3-small

По этапам:
"""
    for stage, count in stats.get("stages", {}).items():
        msg += f"  {stage}: {count}\n"

    await update.message.reply_text(msg)


# ============================================
# ЗАПУСК
# ============================================


async def main():
    log(
        f"🚀 Запуск Sofia Bot (GPT: {MODEL_MODE}, RAG: {'ON' if RAG_ENABLED else 'OFF'})"
    )

    if not OPENAI_API_KEY:
        log("❌ OPENAI_API_KEY не установлен!")
        return

    if not TELEGRAM_TOKEN:
        log("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return

    init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("stage", cmd_stage))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("rag", cmd_rag))

    app.add_handler(CallbackQueryHandler(handle_rating, pattern="^rate_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    log("🔗 @humanAINeural_bot")
    log(f"✅ Бот запущен (GPT: {MODEL_MODE}, RAG: {'ON' if RAG_ENABLED else 'OFF'})")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        log("🛑 Остановка...")

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
