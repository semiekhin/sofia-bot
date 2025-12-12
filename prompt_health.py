#!/usr/bin/env python3
"""Проверка здоровья промпта Sofia"""

import sqlite3
import requests
import os

DB_PATH = "/opt/sofia-bot/sofia_conversations.db"
PROMPT_PATH = "/opt/sofia-bot/sofia_prompt.py"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "512319063"))

def get_health_report():
    """Собираем отчёт о здоровье"""
    # Размер промпта
    with open(PROMPT_PATH, "r") as f:
        prompt = f.read()
    
    tokens_est = len(prompt) // 4
    lines = len(prompt.split('\n'))
    
    # Статистика оценок
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating, COUNT(*) FROM feedback_v2 GROUP BY rating")
    ratings = dict(c.fetchall())
    c.execute("SELECT COUNT(DISTINCT chat_id) FROM messages")
    dialogs = c.fetchone()[0]
    conn.close()
    
    good = ratings.get('good', 0)
    bad = ratings.get('bad', 0)
    total = good + bad
    rate = (good / total * 100) if total > 0 else 0
    
    # Статусы
    token_status = "🟢" if tokens_est < 8000 else ("🟡" if tokens_est < 15000 else "🔴")
    rate_status = "🟢" if rate > 80 else ("🟡" if rate > 65 else "🔴")
    
    report = f"""📊 <b>ЗДОРОВЬЕ ПРОМПТА</b>

{token_status} Токены: ~{tokens_est:,} (строк: {lines})
{rate_status} GOOD rate: {rate:.0f}% ({good}/{total})
📈 Диалогов: {dialogs}
🎯 До fine-tuning: {good}/500 GOOD

"""
    
    if tokens_est > 15000:
        report += "⚠️ Промпт большой — рассмотри RAG\n"
    if rate < 65:
        report += "⚠️ Много BAD — система анализирует\n"
    if rate >= 65 and tokens_est < 15000:
        report += "✅ Всё в норме\n"
    
    return report

def send_telegram(message):
    """Отправка в Telegram"""
    if not TELEGRAM_TOKEN:
        print("⚠️ TELEGRAM_TOKEN не установлен")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": ADMIN_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def check_health(send_to_telegram=False):
    report = get_health_report()
    print(report)
    
    if send_to_telegram:
        send_telegram(report)
        print("📤 Отправлено в Telegram")

if __name__ == "__main__":
    import sys
    send_tg = "--telegram" in sys.argv
    check_health(send_to_telegram=send_tg)
