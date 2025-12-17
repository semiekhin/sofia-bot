#!/usr/bin/env python3
"""
Sofia Bot — с экспертной системой обучения
==========================================
- Контекст диалога (последние 8 сообщений)
- Комментарии экспертов
- Экспорт для анализа
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

load_dotenv()

# НАСТРОЙКИ
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DB_PATH = "sofia_conversations.db"
LOG_PATH = "sofia_bot.log"
ANTIFLOOD_DELAY = 3
CONTEXT_SIZE = 8  # Последние 8 сообщений (4 вопроса + 4 ответа)

ADMIN_IDS = [5186134824]

client = OpenAI(api_key=OPENAI_API_KEY)

# Состояния пользователей (ожидание комментария)
waiting_for_comment = {}  # chat_id -> {"rating": "good/bad", "context": [...]}

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
        processed INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, chat_id INTEGER, user_name TEXT,
        first_contact DATETIME, last_message DATETIME,
        messages_count INTEGER DEFAULT 0
    )''')
    
    # Обновлённая таблица feedback с контекстом и комментарием
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
    
    conn.commit()
    conn.close()
    log("📦 База данных инициализирована (feedback_v2)")

def save_message(chat_id, user_id, user_name, role, content, processed=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (chat_id, user_id, user_name, role, content, processed) VALUES (?, ?, ?, ?, ?, ?)',
              (chat_id, user_id, user_name, role, content, processed))
    message_id = c.lastrowid
    conn.commit()
    conn.close()
    return message_id

def get_conversation_history(chat_id, limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

def get_context_for_feedback(chat_id, limit=CONTEXT_SIZE):
    """Получаем последние N сообщений для feedback"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    # Возвращаем в хронологическом порядке
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
    log(f"🗑️ История чата {chat_id} очищена")

def reset_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET messages_count = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def update_user(user_id, chat_id, user_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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

# ============================================
# FEEDBACK V2 (с контекстом и комментарием)
# ============================================

def save_feedback_v2(chat_id, user_id, expert_name, context, rating, comment=""):
    """Сохраняем оценку с контекстом и комментарием"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    context_json = json.dumps(context, ensure_ascii=False)
    c.execute('''INSERT INTO feedback_v2 (chat_id, user_id, expert_name, context, rating, comment)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (chat_id, user_id, expert_name, context_json, rating, comment))
    conn.commit()
    conn.close()
    log(f"📊 Feedback: {rating} от {expert_name} (комментарий: {len(comment)} симв.)")

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
    
    filepath = "/opt/sofia-bot/training_data.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath, len(data)

def export_feedback_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT context, rating, comment, expert_name, timestamp FROM feedback_v2 ORDER BY timestamp')
    rows = c.fetchall()
    conn.close()
    
    filepath = "/opt/sofia-bot/training_data.csv"
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
    
    # Получаем контекст (последние 8 сообщений)
    ctx = get_context_for_feedback(chat_id, CONTEXT_SIZE)
    
    # Сохраняем состояние — ждём комментарий
    waiting_for_comment[chat_id] = {
        "rating": rating,
        "context": ctx,
        "user_id": user_id,
        "expert_name": user_name
    }
    
    # Убираем кнопки
    await query.edit_message_reply_markup(reply_markup=None)
    
    # Просим комментарий
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{emoji} Оценка принята!\n\n💬 Напишите комментарий (почему {rating == 'good' and 'хорошо' or 'плохо'}?)\n\nИли /skip чтобы пропустить"
    )
    
    log(f"👍 {user_name} оценил: {rating}, ждём комментарий")

# ============================================
# АНТИФЛУД
# ============================================

pending_responses = {}

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
    
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(chat_id, context.bot, stop_typing))
    
    try:
        response = await generate_response(chat_id, user_id, combined_message, user_name, was_offline)
    finally:
        stop_typing.set()
        await typing_task
    
    msg_id = save_message(chat_id, 0, BOT_NAME, "assistant", response, processed=1)
    
    await context.bot.send_message(chat_id=chat_id, text=response, reply_markup=get_rating_keyboard(msg_id))
    log(f"📤 София → {user_name}: {response[:100]}...")
    
    if chat_id in pending_responses:
        del pending_responses[chat_id]

# ============================================
# GPT
# ============================================

async def generate_response(chat_id, user_id, user_message, user_name, was_offline=False):
    history = get_conversation_history(chat_id)
    
    if was_offline:
        user_message = f"[Клиент написал несколько сообщений пока меня не было:\n{user_message}\n]\nОтветь на актуальный вопрос, можешь мягко извиниться что ненадолго отходила."
    
    messages = history + [{"role": "user", "content": user_message}]
    
    def call_openai():
        return client.responses.create(
            model="gpt-5.2",
            instructions=get_system_prompt(user_name),
            input=messages,
            reasoning={"effort": "xhigh"},
            text={"verbosity": "low"},
        )
    
    try:
        log(f"🔄 GPT запрос для {user_name}...")
        response = await asyncio.to_thread(call_openai)
        log(f"✅ GPT ответил")
        assistant_message = response.output_text
        if not assistant_message or assistant_message.strip() == "":
            assistant_message = "Вы на связи? 😊"
        return assistant_message
    except Exception as e:
        log(f"❌ Ошибка GPT: {e}")
        return "Простите, связь подвисла. Напишите ещё раз?"

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
    greeting_msg = f"{user_name}, здравствуйте! Вы оставляли у нас на сайте свой контакт. По недвижимости. Меня зовут София. Удобно сейчас пообщаться?"
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    await asyncio.sleep(2)
    await context.bot.send_message(chat_id=chat_id, text=greeting_msg)
    
    log(f"📤 София: {greeting_msg}")
    save_message(chat_id, user_id, user_name, "user", "/start", processed=1)
    save_message(chat_id, 0, BOT_NAME, "assistant", greeting_msg, processed=1)

# ============================================
# ОБРАБОТЧИКИ
# ============================================

async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id
    
    log(f"📩 {user_name}: /start")
    
    # Очищаем состояние ожидания комментария
    if chat_id in waiting_for_comment:
        del waiting_for_comment[chat_id]
    
    clear_chat_history(chat_id)
    reset_user(user_id)
    update_user(user_id, chat_id, user_name)
    
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
    update_user(user_id, chat_id, user_name)
    
    await send_greeting(chat_id, user_id, user_name, context)

async def cmd_skip(update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить комментарий"""
    chat_id = update.effective_chat.id
    
    if chat_id not in waiting_for_comment:
        await update.message.reply_text("Нечего пропускать 🤷")
        return
    
    data = waiting_for_comment[chat_id]
    
    # Сохраняем без комментария
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

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    # Проверяем — может это комментарий к оценке?
    if chat_id in waiting_for_comment:
        data = waiting_for_comment[chat_id]
        
        # Сохраняем с комментарием
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
    
    # Проверяем приветствия
    is_greeting = user_message.lower().strip() in ["привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро", "хай", "hi", "hello"]
    new_user = is_new_user(user_id)
    
    if is_greeting and new_user:
        update_user(user_id, chat_id, user_name)
        await send_greeting(chat_id, user_id, user_name, context)
        return
    
    update_user(user_id, chat_id, user_name)
    save_message(chat_id, user_id, user_name, "user", user_message, processed=0)
    
    if chat_id in pending_responses:
        pending_responses[chat_id].cancel()
    
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
    
    msg = f"""📊 Экспорт данных

Всего оценок: {stats['total']}
✅ Хорошо: {stats['good']}
❌ Плохо: {stats['bad']}
💬 С комментариями: {stats['with_comments']}
👥 Экспертов: {stats['users']}"""
    
    await update.message.reply_text(msg)
    
    if count > 0:
        with open(json_path, "rb") as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename="training_data.json")
        with open(csv_path, "rb") as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename="training_data.csv")
    
    log(f"📤 Экспорт: {count} записей")

async def cmd_stats(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа")
        return
    
    stats = get_feedback_stats()
    if stats['total'] == 0:
        await update.message.reply_text("📊 Пока нет оценок")
        return
    
    good_pct = (stats['good'] / stats['total'] * 100) if stats['total'] > 0 else 0
    msg = f"""📊 Статистика обучения

Всего оценок: {stats['total']}
✅ Хорошо: {stats['good']} ({good_pct:.1f}%)
❌ Плохо: {stats['bad']} ({100-good_pct:.1f}%)
💬 С комментариями: {stats['with_comments']}
👥 Экспертов: {stats['users']}"""
    
    await update.message.reply_text(msg)

async def cmd_myid(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Твой user_id: {user_id}")

# ============================================
# ЗАПУСК
# ============================================

async def main():
    log("🚀 Запуск Sofia Bot (экспертная система обучения)")
    init_db()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("myid", cmd_myid))
    
    app.add_handler(CallbackQueryHandler(handle_rating, pattern="^rate_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    log("🔗 t.me/humanAINeural_bot")
    log("✅ Бот запущен с экспертной системой обучения")
    
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
