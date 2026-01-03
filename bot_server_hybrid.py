# bot_server_hybrid.py — Telegram бот на гибридной системе
# Версия: 2.0
# Обновлено: 2025-12-28

import asyncio
import json
import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from sofia_hybrid import process_message, analyze_history, get_current_model_info, MODEL_CONFIGS

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
DB_PATH = os.getenv("DB_PATH", "sofia_hybrid.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS chat_meta (
        chat_id INTEGER PRIMARY KEY,
        client_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS debug_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_message TEXT,
        bot_response TEXT,
        action TEXT,
        reason TEXT,
        model_mode TEXT,
        stats TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


def get_setting(key: str, default: str = None) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)', (key, value))
    conn.commit()
    conn.close()


def get_history(chat_id: int, limit: int = 50) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content FROM conversations WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


def save_message(chat_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO conversations (chat_id, role, content) VALUES (?, ?, ?)', (chat_id, role, content))
    c.execute('UPDATE chat_meta SET updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()


def save_debug(chat_id: int, user_message: str, bot_response: str, debug: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO debug_logs (chat_id, user_message, bot_response, action, reason, model_mode, stats)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (chat_id, user_message, bot_response, debug.get("action"), debug.get("reason"),
         debug.get("model_mode"), json.dumps(debug.get("stats", {}), ensure_ascii=False)))
    conn.commit()
    conn.close()


def get_client_name(chat_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT client_name FROM chat_meta WHERE chat_id = ?', (chat_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Клиент"


def save_client_name(chat_id: int, name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO chat_meta (chat_id, client_name, created_at, updated_at)
        VALUES (?, ?, COALESCE((SELECT created_at FROM chat_meta WHERE chat_id = ?), CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)''',
        (chat_id, name, chat_id))
    conn.commit()
    conn.close()


def clear_history(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM conversations WHERE chat_id = ?', (chat_id,))
    c.execute('DELETE FROM debug_logs WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()


def get_model_mode() -> str:
    return get_setting("model_mode", "gpt-5.2")


def set_model_mode(mode: str) -> bool:
    if mode in MODEL_CONFIGS:
        set_setting("model_mode", mode)
        os.environ["MODEL_MODE"] = mode
        import sofia_hybrid
        sofia_hybrid.MODEL_MODE = mode
        return True
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name or "Клиент"
    
    clear_history(chat_id)
    save_client_name(chat_id, user_name)
    
    greeting = f"{user_name}, здравствуйте! Вы оставляли у нас на сайте свой контакт. По недвижимости. Меня зовут София. Удобно сейчас пообщаться?"
    save_message(chat_id, "assistant", greeting)
    
    logger.info(f"[{chat_id}] New conversation started for {user_name}")
    await update.message.reply_text(greeting)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    user_name = update.effective_user.first_name or "Клиент"
    
    client_name = get_client_name(chat_id)
    history = get_history(chat_id)
    
    if not history:
        save_client_name(chat_id, user_name)
        client_name = user_name
        greeting = f"{client_name}, здравствуйте! Вы оставляли у нас на сайте свой контакт. По недвижимости. Меня зовут София. Удобно сейчас пообщаться?"
        save_message(chat_id, "assistant", greeting)
        history = [{"role": "assistant", "content": greeting}]
    
    save_message(chat_id, "user", user_message)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        current_mode = get_model_mode()
        os.environ["MODEL_MODE"] = current_mode
        import sofia_hybrid
        sofia_hybrid.MODEL_MODE = current_mode
        
        response, debug = process_message(history, user_message, client_name)
        
        save_message(chat_id, "assistant", response)
        save_debug(chat_id, user_message, response, debug)
        
        logger.info(f"[{chat_id}] {user_name}: {user_message[:50]}...")
        logger.info(f"[{chat_id}] → {debug['action']} ({debug['reason']}) | Model: {debug.get('model_mode')} | Q: {debug['allow_questions']} → {debug['response_has_question']}")
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"[{chat_id}] Error: {e}", exc_info=True)
        await update.message.reply_text("Простите, связь подвисла. Напишите ещё раз?")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history = get_history(chat_id)
    current_mode = get_model_mode()
    
    if not history:
        await update.message.reply_text(f"Нет активного диалога.\n\n🤖 Модель: {current_mode}\n\nНапишите /start")
        return
    
    stats = analyze_history(history)
    status = f"""📊 Состояние диалога:

📝 Сообщений: {stats['total_messages']}
👤 От клиента: {stats['user_messages']}
🤖 От бота: {stats['bot_messages']}

📊 Счётчики:
- "Скинь": {stats['send_requests']}
- Отказов от созвона: {stats['call_rejections']}
- "Без разницы": {stats['neutral_answers']}
- Раздражение: {'🔴 Да' if stats['irritation_detected'] else '🟢 Нет'}

🤖 Модель: {current_mode}"""
    
    await update.message.reply_text(status)


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if ADMIN_CHAT_ID and str(chat_id) != str(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ Только администратор может переключать модели")
        return
    
    args = context.args
    current_mode = get_model_mode()
    
    if not args:
        modes_list = "\n".join([f"• {m}" for m in MODEL_CONFIGS.keys()])
        await update.message.reply_text(f"🤖 Текущая модель: {current_mode}\n\nДоступные:\n{modes_list}\n\nДля переключения: /model <режим>")
        return
    
    new_mode = args[0]
    
    if new_mode not in MODEL_CONFIGS:
        await update.message.reply_text(f"❌ Неизвестный режим: {new_mode}\n\nДоступные: {', '.join(MODEL_CONFIGS.keys())}")
        return
    
    if set_model_mode(new_mode):
        config = MODEL_CONFIGS[new_mode]
        reasoning_str = "✅ reasoning xhigh" if config.get("reasoning") else "❌ без reasoning"
        await update.message.reply_text(f"✅ Переключено на: {new_mode}\n\n• Model: {config['model']}\n• {reasoning_str}\n• Temp: {config['temperature']}")
        logger.info(f"Model switched to {new_mode} by chat_id={chat_id}")
    else:
        await update.message.reply_text("❌ Ошибка переключения")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    clear_history(chat_id)
    logger.info(f"[{chat_id}] Conversation reset")
    await update.message.reply_text("Диалог сброшен. Напишите /start чтобы начать заново.")


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_message, action, reason, model_mode FROM debug_logs WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 5', (chat_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("Нет debug записей")
        return
    
    lines = ["🔍 Последние решения:\n"]
    for row in rows:
        msg = row[0][:30] if row[0] else "?"
        lines.append(f"📩 {msg}...\n   → {row[1]} ({row[2]})\n   🤖 {row[3] or '?'}\n")
    
    await update.message.reply_text("\n".join(lines))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 Sofia Hybrid v2.0

/start — Начать диалог
/reset — Сбросить
/status — Состояние
/debug — Последние решения
/model — Текущая модель
/model <режим> — Переключить

Режимы: gpt-4o, gpt-5.2, gpt-5.2-reasoning"""
    await update.message.reply_text(help_text)


def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    init_db()
    
    saved_mode = get_setting("model_mode", "gpt-5.2")
    os.environ["MODEL_MODE"] = saved_mode
    
    logger.info(f"🚀 Sofia Hybrid Bot v2.0 starting...")
    logger.info(f"🤖 Model mode: {saved_mode}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ Bot ready")
    app.run_polling()


if __name__ == "__main__":
    main()
