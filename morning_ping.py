#!/usr/bin/env python3
"""Утреннее напоминание экспертам"""

import sqlite3
import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DB_PATH = "/opt/sofia-bot/sofia_conversations.db"

def get_active_users():
    """Получаем всех кто общался с ботом"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT DISTINCT chat_id, user_name 
        FROM messages 
        WHERE user_name IS NOT NULL
        GROUP BY chat_id
    ''')
    users = c.fetchall()
    conn.close()
    return users

def save_message(chat_id, role, content, user_name=None):
    """Сохраняем сообщение в базу"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (chat_id, user_name, role, content, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, user_name, role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def send_morning_ping():
    """Отправляем утреннее сообщение"""
    users = get_active_users()
    
    for chat_id, user_name in users:
        name = user_name.split()[0] if user_name else "друг"
        message = f"{name}, доброе утро! ☀️ Я готова учиться дальше)) Пообщаемся?"
        
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            response = requests.post(url, json={
                "chat_id": chat_id,
                "text": message
            }, timeout=10)
            
            if response.status_code == 200:
                # Сохраняем в базу как сообщение от ассистента
                save_message(chat_id, "assistant", message, user_name)
                print(f"✅ {user_name}: отправлено и сохранено")
            else:
                print(f"❌ {user_name}: {response.text}")
        except Exception as e:
            print(f"❌ {user_name}: {e}")

if __name__ == "__main__":
    print(f"🌅 Утренний пинг: {datetime.now()}")
    send_morning_ping()
