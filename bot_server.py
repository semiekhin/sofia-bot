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
from datetime import datetime
from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

import os
from dotenv import load_dotenv
from sofia_prompt import get_system_prompt, BOT_NAME

# NEW: RAG модули
from stage_detector import detect_stage, get_stage_context
from rag_module import search_examples, format_examples_for_prompt, init_vector_store, get_collection_stats

# NEW: Agent Architecture
from state_manager import StateManager, ClientState
from extractor import extract_sync, merge_extraction_to_state
from planner import get_next_action, get_action_context, format_action_for_prompt, Action, increment_slot_attempt

# Детекторы отключены — управление через промпт + RAG
# from detectors import ...

load_dotenv()

# ============================================
# НАСТРОЙКИ
# ============================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "512319063"))

# Модель OpenAI
MODEL_MODE = os.getenv("MODEL_MODE", "gpt-5.2")

MODEL_CONFIGS = {
    "gpt-4o": {"model": "gpt-4o", "use_responses_api": False, "temperature": 0.4, "max_tokens": 200},
    "gpt-5.2": {"model": "gpt-5.2", "use_responses_api": True, "max_tokens": 400, "reasoning": None},
    "gpt-5.2-reasoning": {"model": "gpt-5.2", "use_responses_api": True, "max_tokens": 400, "reasoning": {"effort": "xhigh"}}
}

def get_model_config():
    return MODEL_CONFIGS.get(MODEL_MODE, MODEL_CONFIGS["gpt-5.2"])

DB_PATH = "sofia_gpt.db"

# NEW: State Manager для агентной архитектуры
state_manager = StateManager(DB_PATH)
LOG_PATH = "sofia_bot.log"
ANTIFLOOD_DELAY = 3
CONTEXT_SIZE = 8  # Последние 8 сообщений

ADMIN_IDS = [5186134824, 512319063]

# RAG настройки
RAG_EXAMPLES_COUNT = 10  # Сколько примеров добавлять в промпт
RAG_ENABLED = True      # Включить/выключить RAG

# Маппинг Action → Stage для RAG (чтобы RAG искал по действию Planner, а не Stage Detector)
ACTION_TO_RAG_STAGE = {
    "ask_goal": "QUALIFICATION",
    "ask_location": "QUALIFICATION",
    "ask_budget": "QUALIFICATION",
    "ask_strategy": "QUALIFICATION",
    "ask_usage": "QUALIFICATION",
    "ask_family": "QUALIFICATION",
    "ask_payment": "QUALIFICATION",
    "ask_first_payment": "QUALIFICATION",
    "ask_lpr": "QUALIFICATION",
    "help_goal": "QUALIFICATION",
    "help_location": "QUALIFICATION",
    "help_budget": "QUALIFICATION",
    "help_payment": "QUALIFICATION",
    "help_lpr": "QUALIFICATION",
    "answer_question": "PRESENTATION",
    "handle_objection": "OBJECTION",
    "clarify_mentioned": "QUALIFICATION",
    "propose_meeting": "MEETING",
    "propose_meeting_1": "MEETING",
    "propose_meeting_2": "MEETING",
    "confirm_meeting": "CLOSING",
    "finish_with_materials": "CLOSING",
    "send_materials": "PRESENTATION",
    "greeting": "GREETING",
}

# ============================================
# WAIT-ЛОГИКА: не отвечать после договорённости
# ============================================

SHORT_CONFIRMATIONS = {
    "ок", "ok", "да", "хорошо", "ладно", "понял", "понятно", 
    "ясно", "угу", "+", "отлично", "супер", "класс", "👍",
    "принял", "принято", "договорились", "ага", "угум", "ок!",
    "хор", "да!", "ок.", "good", "yes", "ясненько", "понятненько"
}

MEETING_MARKERS = [
    "созвон", "ссылку пришлю", 
    "пришлю ссылку", "видео-встреча", "zoom", "встретимся", 
    "до связи", "ждём вас", "жду вас", "буду ждать",
    "ссылку на созвон", "по мск", "заранее"
]

def should_skip_response(message: str, last_bot_message: str) -> bool:
    """
    WAIT-логика: не отвечать на короткие подтверждения после договорённости.
    Возвращает True если НЕ нужно отвечать.
    """
    if not last_bot_message:
        return False
    
    msg_lower = message.strip().lower().rstrip('!.,')
    
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
        (chat_id,)
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER, user_id INTEGER, user_name TEXT,
        role TEXT, content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        processed INTEGER DEFAULT 0,
        stage TEXT DEFAULT NULL
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, chat_id INTEGER, user_name TEXT,
        first_contact DATETIME, last_message DATETIME,
        messages_count INTEGER DEFAULT 0,
        current_stage TEXT DEFAULT 'GREETING'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS feedback_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user_id INTEGER,
        expert_name TEXT,
        context TEXT,
        rating TEXT,
        comment TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # NEW: Таблица для логов RAG
    c.execute('''CREATE TABLE IF NOT EXISTS rag_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        user_message TEXT,
        detected_stage TEXT,
        confidence REAL,
        examples_used TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    
    # Инициализируем векторный RAG при старте
    if RAG_ENABLED:
        rag_ok = init_vector_store()
        if not rag_ok:
            log("⚠️ Векторный RAG не инициализирован!")
    
    log(f"📦 База данных инициализирована (GPT: {MODEL_MODE}, RAG: {'ON' if RAG_ENABLED else 'OFF'})")

def save_message(chat_id, user_id, user_name, role, content, processed=0, stage=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (chat_id, user_id, user_name, role, content, processed, stage) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (chat_id, user_id, user_name, role, content, processed, stage))
    message_id = c.lastrowid
    conn.commit()
    conn.close()
    return message_id

def save_rag_log(chat_id, user_message, stage, confidence, examples):
    """Сохраняет лог RAG для анализа."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    examples_json = json.dumps([ex.get("id", "") for ex in examples], ensure_ascii=False)
    c.execute('INSERT INTO rag_logs (chat_id, user_message, detected_stage, confidence, examples_used) VALUES (?, ?, ?, ?, ?)',
              (chat_id, user_message, stage, confidence, examples_json))
    conn.commit()
    conn.close()

def get_conversation_history(chat_id, limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

def get_context_for_feedback(chat_id, limit=CONTEXT_SIZE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1], "time": row[2]} for row in reversed(rows)]

def get_unprocessed_messages(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, content, timestamp FROM messages WHERE chat_id = ? AND role = "user" AND processed = 0 ORDER BY timestamp ASC', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_messages_processed(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET processed = 1 WHERE chat_id = ? AND role = "user" AND processed = 0', (chat_id,))
    conn.commit()
    conn.close()

def clear_chat_history(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()
    
    # Сбрасываем этап
    if chat_id in user_stages:
        del user_stages[chat_id]
    
    log(f"🗑️ История чата {chat_id} очищена")

def reset_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET messages_count = 0, current_stage = "GREETING" WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def update_user(user_id, chat_id, user_name, stage=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if stage:
        c.execute('''INSERT INTO users (user_id, chat_id, user_name, first_contact, last_message, messages_count, current_stage)
                     VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, ?)
                     ON CONFLICT(user_id) DO UPDATE SET last_message = CURRENT_TIMESTAMP, messages_count = messages_count + 1, current_stage = ?''',
                  (user_id, chat_id, user_name, stage, stage))
    else:
        c.execute('''INSERT INTO users (user_id, chat_id, user_name, first_contact, last_message, messages_count)
                     VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                     ON CONFLICT(user_id) DO UPDATE SET last_message = CURRENT_TIMESTAMP, messages_count = messages_count + 1''',
                  (user_id, chat_id, user_name))
    
    conn.commit()
    conn.close()

def is_new_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT messages_count FROM users WHERE user_id = ?', (user_id,))
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
        budget_text = f"{client_state.budget/1_000_000:.1f} млн" if client_state.budget else "не указан"
        
        if finish_type == "meeting":
            emoji = "📞"
            type_text = "Созвон"
            meeting_line = f"\n⏰ Время: {client_state.meeting_datetime or 'уточняется'}"
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
    c.execute('''INSERT INTO feedback_v2 (chat_id, user_id, expert_name, context, rating, comment)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (chat_id, user_id, expert_name, context_json, rating, comment))
    conn.commit()
    conn.close()
    log(f"📊 Feedback: {rating} от {expert_name}")

def export_feedback_json():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT context, rating, comment, expert_name, timestamp FROM feedback_v2 ORDER BY timestamp')
    rows = c.fetchall()
    conn.close()
    
    data = []
    for r in rows:
        data.append({
            "context": json.loads(r[0]),
            "rating": r[1],
            "comment": r[2],
            "expert_name": r[3],
            "timestamp": r[4]
        })
    
    filepath = "training_data.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath, len(data)

def export_feedback_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT context, rating, comment, expert_name, timestamp FROM feedback_v2 ORDER BY timestamp')
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
    c.execute('SELECT rating, COUNT(*) FROM feedback_v2 GROUP BY rating')
    rows = c.fetchall()
    c.execute('SELECT COUNT(DISTINCT user_id) FROM feedback_v2')
    users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM feedback_v2 WHERE comment != ""')
    with_comments = c.fetchone()[0]
    conn.close()
    
    stats = {"good": 0, "bad": 0, "total": 0, "users": users, "with_comments": with_comments}
    for row in rows:
        stats[row[0]] = row[1]
        stats["total"] += row[1]
    return stats

# ============================================
# КНОПКИ ОЦЕНКИ
# ============================================

def get_rating_keyboard(message_id):
    keyboard = [[
        InlineKeyboardButton("❌ Нет", callback_data=f"rate_bad_{message_id}"),
        InlineKeyboardButton("✅ Да", callback_data=f"rate_good_{message_id}"),
    ]]
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
        "expert_name": user_name
    }
    
    await query.edit_message_reply_markup(reply_markup=None)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{emoji} Оценка принята!\n\n💬 Напишите комментарий (почему {rating == 'good' and 'хорошо' or 'плохо'}?)\n\nИли /skip чтобы пропустить"
    )
    
    log(f"👍 {user_name} оценил: {rating}, ждём комментарий")

# ============================================
# АНТИФЛУД
# ============================================

pending_responses = {}
reminder_tasks = {}  # Таймеры напоминания (10 мин)
REMINDER_DELAY = 600  # 10 минут в секундах

async def send_reminder(chat_id, user_name, context):
    """Отправляет напоминание если клиент не ответил 10 минут"""
    await asyncio.sleep(REMINDER_DELAY)
    
    # Проверяем meeting_agreed в состоянии клиента
    state = state_manager.get_state(chat_id)
    if state and state.meeting_agreed:
        return  # Уже договорились о созвоне — не напоминаем
    
    # Проверяем что диалог не завершён
    history = get_conversation_history(chat_id)
    if not history:
        return
    
    last_msg = history[-1]
    if last_msg.get("role") != "assistant":
        return  # Последнее сообщение от клиента — не напоминаем
    
    last_text = last_msg.get("content", "").lower()
    
    # Признаки завершения — не напоминаем
    finish_markers = ["записала", "договорились", "пришлю ссылку", "до связи", "хорошего дня", "будем на связи"]
    if any(marker in last_text for marker in finish_markers):
        return
    
    # Отправляем напоминание
    reminder_text = f"{user_name}, на связи? 🙂"
    await context.bot.send_message(chat_id=chat_id, text=reminder_text)
    log(f"⏰ Напоминание → {user_name}")
    
    # Удаляем задачу
    if chat_id in reminder_tasks:
        del reminder_tasks[chat_id]


async def delayed_response(chat_id, user_id, user_name, context):
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

#     # WAIT-логика: не отвечать на короткие подтверждения после договорённости
#     last_bot_msg = get_last_bot_message(chat_id)
#     if should_skip_response(combined_message, last_bot_msg):
#         log(f"⏸️ WAIT: пропускаем ответ на '{combined_message}' после договорённости")
#         return
#     
    # ════════════════════════════════════════════════════════════════════════
    # NEW: Агентная архитектура — Extractor → State → Planner
    # ════════════════════════════════════════════════════════════════════════
    
    # 1. Получаем текущее состояние клиента
    client_state = state_manager.get_state(user_id)
    
    # 2. Получаем историю для Extractor
    history = get_conversation_history(chat_id, limit=6)
    history_for_extractor = [{"role": m["role"], "content": m["content"]} for m in history]
    
    # 3. Извлекаем данные из сообщения (NLU)
    extraction = extract_sync(combined_message, history_for_extractor)
    log(f"🔍 Extractor: {extraction}")
    
    # 4. Обновляем состояние клиента
    state_updates = merge_extraction_to_state(client_state.to_dict(), extraction)
    client_state = state_manager.update_state(user_id, state_updates)
    log(f"📊 State: {client_state.summary()}")
    
    # 5. Определяем следующее действие (Planner)
    action = get_next_action(client_state, combined_message, extraction)
    action_context = get_action_context(action, client_state, extraction)
    log(f"🎯 Planner: {action.value} → {action_context.get('action_description', '')[:50]}...")
    
    # 5.0.1 Обогащение финансовым расчётом (если спрашивают про доходность)
    if action == Action.ANSWER_QUESTION and extraction.get("question_type") == "profitability":
        if client_state.budget and client_state.budget > 0:
            try:
                from finance_calculator import compare_investments, format_short_comparison
                fin_result = compare_investments(amount=client_state.budget, construction_years=2, total_years=5)
                action_context["finance_calculation"] = format_short_comparison(fin_result)
                log(f"💰 Finance: расчёт для {client_state.budget/1_000_000:.1f} млн")
            except Exception as e:
                log(f"⚠️ Finance error: {e}")
        else:
            # Бюджет неизвестен — дадим общую информацию
            action_context["finance_calculation"] = "Бюджет пока не известен — дай общие цифры (8-12% аренда, 20-30% рост на стройке)"
    
    # 5.1 Увеличиваем счётчик попыток для слота
    # Маппинг: action name → slot name (для несовпадающих имён)
    ACTION_TO_SLOT = {"payment": "payment_type"}
    if action.value.startswith("ask_"):
        slot = action.value.replace("ask_", "")
        slot = ACTION_TO_SLOT.get(slot, slot)  # payment → payment_type
        increment_slot_attempt(client_state, slot, "ask")
        state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
    elif action.value.startswith("help_"):
        slot = action.value.replace("help_", "")
        slot = ACTION_TO_SLOT.get(slot, slot)  # payment → payment_type
        increment_slot_attempt(client_state, slot, "help")
        state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
    
    # 5.2 NEW v2.0: Сохраняем поля изменённые в Planner
    v2_updates = {
        "branch": client_state.branch,
        "call_proposal_count": client_state.call_proposal_count,
        "materials_request_count": client_state.materials_request_count,
    }
    
    # При завершении диалога
    if action == Action.FINISH_WITH_MATERIALS:
        v2_updates["dialog_finished"] = True
        v2_updates["finish_type"] = "materials"
    elif action == Action.CONFIRM_MEETING:
        v2_updates["dialog_finished"] = True
        v2_updates["finish_type"] = "meeting"
    
    state_manager.update_state(user_id, v2_updates)
    
    # 5.3 Уведомление менеджеру при завершении диалога
    if v2_updates.get("dialog_finished"):
        await notify_manager_deal(context.bot, client_state, user_name, v2_updates["finish_type"])
    
    # 6. Проверка WAIT от Planner
    if action == Action.WAIT:
        log(f"⏸️ WAIT (Planner): пропускаем ответ")
        return
    
    # 7. Очищаем временные флаги после обработки
    state_manager.clear_temporary_flags(user_id)
    
    # ════════════════════════════════════════════════════════════════════════
    
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(chat_id, context.bot, stop_typing))
    
    try:
        response, stage = await generate_response_with_rag(chat_id, user_id, combined_message, user_name, was_offline, action_context)
    finally:
        stop_typing.set()
        await typing_task
    
    msg_id = save_message(chat_id, 0, BOT_NAME, "assistant", response, processed=1, stage=stage)
    
    await context.bot.send_message(chat_id=chat_id, text=response, reply_markup=get_rating_keyboard(msg_id))
    log(f"📤 София → {user_name}: {response[:100]}...")
    
    if chat_id in pending_responses:
        del pending_responses[chat_id]
    
    # Запускаем таймер напоминания (10 мин)
    if chat_id in reminder_tasks:
        reminder_tasks[chat_id].cancel()
    reminder_tasks[chat_id] = asyncio.create_task(send_reminder(chat_id, user_name, context))

# ============================================
# CLAUDE API с RAG
# ============================================


def _format_known_facts(facts: dict) -> str:
    """Форматирует известные факты для промпта"""
    if not facts:
        return "- пока ничего не известно"
    
    lines = []
    translations = {
        'goal': 'Цель',
        'location': 'Локация', 
        'budget': 'Бюджет',
        'payment_type': 'Оплата',
        'first_payment': 'Первый взнос',
        'lpr': 'ЛПР'
    }
    
    for key, data in facts.items():
        name = translations.get(key, key)
        value = data.get('value', '?')
        conf = data.get('confidence', '?')
        
        # Форматируем бюджет
        if key in ['budget', 'first_payment'] and isinstance(value, int):
            value = f"{value/1_000_000:.1f} млн ₽"
        
        lines.append(f"- {name}: {value} ({conf})")
    
    return '\n'.join(lines) if lines else "- пока ничего не известно"


async def generate_response_with_rag(chat_id, user_id, user_message, user_name, was_offline=False, action_context=None):
    """
    Генерирует ответ с использованием Stage-Aware RAG + детекторов.
    
    Returns:
        (response_text, detected_stage)
    """
    history = get_conversation_history(chat_id)
    last_stage = get_user_stage(chat_id)
    
    # Детекторы отключены — RAG + промпт управляют диалогом
    
    # NEW: Определяем этап
    stage_result = detect_stage(user_message, history, last_stage)
    current_stage = stage_result["stage"]
    confidence = stage_result["confidence"]
    substage = stage_result["substage"]
    
    # Обновляем этап пользователя
    set_user_stage(chat_id, current_stage)
    
    log(f"🎯 Stage: {current_stage} ({confidence}) [{substage}]")
    
    # NEW: Ищем примеры из RAG
    examples = []
    examples_prompt = ""
    
    if RAG_ENABLED:
        # Определяем stage для RAG по action от Planner
        rag_stage = current_stage  # fallback
        if action_context:
            action = action_context.get("action", "")
            rag_stage = ACTION_TO_RAG_STAGE.get(action, current_stage)
        examples = search_examples(rag_stage, user_message, limit=RAG_EXAMPLES_COUNT)
        if examples:
            examples_prompt = format_examples_for_prompt(examples)
            log(f"📚 RAG: {len(examples)} примеров для {rag_stage}")
        
        # Сохраняем лог RAG
        save_rag_log(chat_id, user_message, current_stage, confidence, examples)
    
    # Формируем system prompt (унифицировано с userbot)
    system_prompt = get_system_prompt(user_name, action_context)
    
    # Добавляем RAG примеры
    if examples_prompt:
        system_prompt += f"""

════════════════════════════════════════════════════════════════════════════════
ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ (RAG)
════════════════════════════════════════════════════════════════════════════════
{examples_prompt}
"""
    
    if was_offline:
        user_message = f"[Клиент написал несколько сообщений пока меня не было:\n{user_message}\n]\nОтветь на актуальный вопрос, можешь мягко извиниться что ненадолго отходила."
    
    # Формируем сообщения для GPT
    messages = []
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    messages.append({"role": "user", "content": user_message})
    
    config = get_model_config()
    
    def call_openai():
        if config["use_responses_api"]:
            # GPT-5.2 responses API
            params = {
                "model": config["model"],
                "instructions": system_prompt,
                "input": messages,
                "text": {"verbosity": "low"},
            }
            if config.get("reasoning"):
                params["reasoning"] = config["reasoning"]
            return client.responses.create(**params)
        else:
            # GPT-4o chat completions API
            chat_msgs = [{"role": "system", "content": system_prompt}] + messages
            return client.chat.completions.create(
                model=config["model"],
                messages=chat_msgs,
                temperature=config.get("temperature", 0.4),
                max_tokens=config["max_tokens"]
            )
    
    try:
        log(f"🔄 GPT запрос ({MODEL_MODE}) для {user_name} (stage: {current_stage})...")
        response = await asyncio.to_thread(call_openai)
        log(f"✅ GPT ответил ({MODEL_MODE})")
        
        if config["use_responses_api"]:
            assistant_message = response.output_text
        else:
            assistant_message = response.choices[0].message.content
        if not assistant_message or assistant_message.strip() == "":
            assistant_message = "Вы на связи? 😊"
        

        return assistant_message, current_stage
        
    except Exception as e:
        log(f"❌ Ошибка GPT: {e}")
        return "Простите, связь подвисла. Напишите ещё раз?", current_stage

# Legacy wrapper
async def generate_response(chat_id, user_id, user_message, user_name, was_offline=False):
    response, _ = await generate_response_with_rag(chat_id, user_id, user_message, user_name, was_offline)
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

async def send_greeting(chat_id, user_id, user_name, context):
    greeting_msg = f"{user_name}, добрый день! Это София, по недвижимости. Вы оставляли заявку на сайте — удобно сейчас пообщаться?"
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    await asyncio.sleep(2)
    await context.bot.send_message(chat_id=chat_id, text=greeting_msg)
    
    log(f"📤 София: {greeting_msg}")
    save_message(chat_id, user_id, user_name, "user", "/start", processed=1, stage="GREETING")
    save_message(chat_id, 0, BOT_NAME, "assistant", greeting_msg, processed=1, stage="GREETING")
    
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
    
    await send_greeting(chat_id, user_id, user_name, context)

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
        comment=""
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
        reasoning = "✅ reasoning xhigh" if config.get("reasoning") else "❌ без reasoning"
        modes = "\n".join([f"• {m}" for m in MODEL_CONFIGS.keys()])
        await update.message.reply_text(f"🤖 Текущая модель: {MODEL_MODE}\n{reasoning}\n\nДоступные:\n{modes}\n\n/model <режим>")
        return
    
    new_mode = args[0]
    if new_mode not in MODEL_CONFIGS:
        await update.message.reply_text(f"❌ Неизвестный режим: {new_mode}")
        return
    
    MODEL_MODE = new_mode
    config = MODEL_CONFIGS[new_mode]
    reasoning = "✅ reasoning xhigh" if config.get("reasoning") else "❌ без reasoning"
    api = "responses API" if config.get("use_responses_api") else "chat completions"
    
    await update.message.reply_text(f"✅ Переключено: {new_mode}\n\n• API: {api}\n• {reasoning}")
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
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        
        # Удаляем временный файл
        import os as os_module
        os_module.remove(audio_path)
        
        user_message = transcript.text.strip()
        
        if not user_message:
            await update.message.reply_text("Не удалось распознать. Попробуйте ещё раз или напишите текстом.")
            return
        
        log(f"🎤→📝 {user_name}: {user_message}")
        
        # Обрабатываем как обычное сообщение
        update_user(user_id, chat_id, user_name)
        save_message(chat_id, user_id, user_name, "user", user_message, processed=0)
        
        if chat_id in pending_responses:
            pending_responses[chat_id].cancel()
        
        task = asyncio.create_task(delayed_response(chat_id, user_id, user_name, context))
        pending_responses[chat_id] = task
        
    except Exception as e:
        log(f"❌ Ошибка распознавания: {e}")
        await update.message.reply_text("Не удалось распознать голос. Попробуйте ещё раз или напишите текстом.")

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id
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
            comment=user_message
        )
        
        del waiting_for_comment[chat_id]
        
        await update.message.reply_text("✅ Спасибо за комментарий! Продолжайте диалог.")
        log(f"📊 Feedback сохранён с комментарием: {user_message[:50]}...")
        return
    
    log(f"📩 {user_name}: {user_message}")
    
    # Приветствия
    is_greeting = user_message.lower().strip() in ["привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро", "хай", "hi", "hello"]
    new_user = is_new_user(user_id)
    
    if is_greeting and new_user:
        update_user(user_id, chat_id, user_name, stage="GREETING")
        await send_greeting(chat_id, user_id, user_name, context)
        return
    
    update_user(user_id, chat_id, user_name)
    save_message(chat_id, user_id, user_name, "user", user_message, processed=0)
    
    if chat_id in pending_responses:
        pending_responses[chat_id].cancel()
    
    # Отменяем напоминание если клиент ответил
    if chat_id in reminder_tasks:
        reminder_tasks[chat_id].cancel()
        del reminder_tasks[chat_id]
    
    task = asyncio.create_task(delayed_response(chat_id, user_id, user_name, context))
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
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename="training_data_claude.json")
        with open(csv_path, "rb") as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename="training_data_claude.csv")
    
    log(f"📤 Экспорт: {count} записей")

async def cmd_stats(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return
    
    stats = get_feedback_stats()
    if stats['total'] == 0:
        await update.message.reply_text(f"📊 Пока нет оценок\n\n🤖 Модель: {MODEL_MODE}\n📚 RAG: {'ON' if RAG_ENABLED else 'OFF'}")
        return
    
    good_pct = (stats['good'] / stats['total'] * 100) if stats['total'] > 0 else 0
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
    for stage, count in stats.get('stages', {}).items():
        msg += f"  {stage}: {count}\n"
    
    await update.message.reply_text(msg)

# ============================================
# ЗАПУСК
# ============================================

async def main():
    log(f"🚀 Запуск Sofia Bot (GPT: {MODEL_MODE}, RAG: {'ON' if RAG_ENABLED else 'OFF'})")
    
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
