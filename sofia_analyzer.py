#!/usr/bin/env python3
"""
Sofia Auto-Analyzer v2 — ночной анализ с полным логированием
Первый запуск: 22:00 11.12.2025
"""

import sqlite3
import json
import os
import shutil
from datetime import datetime, timedelta
from openai import OpenAI
import requests

# ══════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # Токен бота Sofia
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "512319063"))  # Твой chat_id

DB_PATH = "/opt/sofia-bot/sofia_conversations.db"
PROMPT_PATH = "/opt/sofia-bot/sofia_prompt.py"
BACKUP_DIR = "/opt/sofia-bot/backups"
LOGS_DIR = "/opt/sofia-bot/analyzer_logs"
LAST_ANALYSIS_FILE = "/opt/sofia-bot/last_analysis_time.txt"

# Минимум оценок для анализа (ставим 1 для первого теста)
MIN_FEEDBACK_COUNT = 1

# Модель для анализа
ANALYZER_MODEL = "gpt-5.2"

# ══════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ══════════════════════════════════════════════════════════════

# Создаём папки
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Уникальный ID запуска
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_DIR = os.path.join(LOGS_DIR, RUN_ID)
os.makedirs(RUN_DIR, exist_ok=True)

client = None


def init_openai():
    """Инициализация OpenAI клиента"""
    global client
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY не установлен!")
    client = OpenAI(api_key=OPENAI_API_KEY)


def log(message, also_print=True):
    """Логирование в файл и консоль"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    
    if also_print:
        print(line)
    
    with open(os.path.join(RUN_DIR, "run.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_to_file(filename, content):
    """Сохраняем контент в файл лога"""
    path = os.path.join(RUN_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"💾 Сохранено: {filename}")
    return path


def send_telegram(message, parse_mode="HTML"):
    """Отправка в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # Telegram лимит 4096 символов
        if len(message) > 4000:
            message = message[:4000] + "\n\n... (обрезано)"
        
        response = requests.post(url, json={
            "chat_id": ADMIN_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode
        }, timeout=30)
        
        if response.status_code == 200:
            log("✅ Telegram: сообщение отправлено")
        else:
            log(f"⚠️ Telegram ошибка: {response.text}")
    except Exception as e:
        log(f"❌ Telegram exception: {e}")


def send_telegram_file(filepath, caption=""):
    """Отправка файла в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filepath, "rb") as f:
            response = requests.post(url, 
                data={"chat_id": ADMIN_CHAT_ID, "caption": caption[:1024]},
                files={"document": f},
                timeout=60
            )
        if response.status_code == 200:
            log(f"✅ Telegram: файл {os.path.basename(filepath)} отправлен")
        else:
            log(f"⚠️ Telegram file ошибка: {response.text}")
    except Exception as e:
        log(f"❌ Telegram file exception: {e}")


# ══════════════════════════════════════════════════════════════
# СБОР ДАННЫХ
# ══════════════════════════════════════════════════════════════

def get_last_analysis_time():
    """Получаем время последнего анализа"""
    try:
        if os.path.exists(LAST_ANALYSIS_FILE):
            with open(LAST_ANALYSIS_FILE, 'r') as f:
                return f.read().strip()
    except:
        pass
    return None


def save_analysis_time():
    """Сохраняем время текущего анализа"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LAST_ANALYSIS_FILE, 'w') as f:
        f.write(timestamp)
    log(f"💾 Время анализа сохранено: {timestamp}")


def get_new_data():
    """Получаем только НОВЫЕ данные после последнего анализа"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    last_time = get_last_analysis_time()
    
    if last_time:
        log(f"📅 Последний анализ: {last_time}")
        log(f"📥 Берём данные ПОСЛЕ {last_time}")
        
        # Сообщения после последнего анализа
        c.execute('''
            SELECT chat_id, user_name, role, content, timestamp 
            FROM messages 
            WHERE timestamp > ?
            ORDER BY chat_id, timestamp
        ''', (last_time,))
        messages = c.fetchall()
        
        # Feedback после последнего анализа
        c.execute('''
            SELECT expert_name, rating, comment, context, timestamp 
            FROM feedback_v2 
            WHERE timestamp > ?
            ORDER BY timestamp
        ''', (last_time,))
        feedback = c.fetchall()
    else:
        log("📅 Первый запуск — берём ВСЕ данные")
        
        # Все сообщения
        c.execute('''
            SELECT chat_id, user_name, role, content, timestamp 
            FROM messages 
            ORDER BY chat_id, timestamp
        ''')
        messages = c.fetchall()
        
        # Все feedback
        c.execute('''
            SELECT expert_name, rating, comment, context, timestamp 
            FROM feedback_v2 
            ORDER BY timestamp
        ''')
        feedback = c.fetchall()
    
    conn.close()
    
    log(f"📊 Загружено: {len(messages)} сообщений, {len(feedback)} оценок")
    return messages, feedback


def format_dialogs(messages):
    """Форматируем диалоги"""
    if not messages:
        return "Нет диалогов."
    
    dialogs = {}
    for chat_id, user_name, role, content, timestamp in messages:
        if chat_id not in dialogs:
            dialogs[chat_id] = {"user": user_name or "Unknown", "messages": []}
        dialogs[chat_id]["messages"].append({
            "role": role,
            "content": content,
            "time": timestamp
        })
    
    result = []
    for chat_id, data in dialogs.items():
        result.append(f"\n{'='*50}")
        result.append(f"ДИАЛОГ С: {data['user']} (chat_id: {chat_id})")
        result.append('='*50)
        for m in data["messages"]:
            role = "🤖 СОФИЯ" if m["role"] == "assistant" else "👤 КЛИЕНТ"
            result.append(f"[{m['time']}] {role}:")
            result.append(f"   {m['content']}")
            result.append("")
    
    return "\n".join(result)


def format_feedback(feedback):
    """Форматируем оценки"""
    if not feedback:
        return "Нет оценок экспертов."
    
    result = []
    for expert, rating, comment, context, timestamp in feedback:
        emoji = "✅ GOOD" if rating == "good" else "❌ BAD"
        result.append(f"\n{'─'*50}")
        result.append(f"{emoji} | Эксперт: {expert} | {timestamp}")
        result.append('─'*50)
        
        if comment:
            result.append(f"💬 КОММЕНТАРИЙ: {comment}")
        
        # Контекст диалога
        try:
            ctx = json.loads(context)
            result.append("\n📝 Контекст диалога:")
            for m in ctx:
                role = "София" if m["role"] == "assistant" else "Клиент"
                content = m["content"][:150] + "..." if len(m["content"]) > 150 else m["content"]
                result.append(f"   {role}: {content}")
        except:
            pass
        
        result.append("")
    
    return "\n".join(result)


def get_current_prompt():
    """Читаем текущий промпт"""
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ══════════════════════════════════════════════════════════════
# АНАЛИЗ GPT
# ══════════════════════════════════════════════════════════════

def build_analysis_prompt(dialogs_text, feedback_text, current_prompt):
    """Собираем промпт для анализа"""
    
    return f"""Ты — эксперт по продажам недвижимости и промпт-инженер.

Твоя задача: проанализировать диалоги AI-продажника "София" и предложить улучшения в промпт.

══════════════════════════════════════════════════════════════
ДИАЛОГИ
══════════════════════════════════════════════════════════════
{dialogs_text}

══════════════════════════════════════════════════════════════
ОЦЕНКИ ЭКСПЕРТОВ (менеджеров по продажам)
══════════════════════════════════════════════════════════════
{feedback_text}

══════════════════════════════════════════════════════════════
ТЕКУЩИЙ ПРОМПТ СОФИИ
══════════════════════════════════════════════════════════════
```python
{current_prompt}
```

══════════════════════════════════════════════════════════════
ТВОЯ ЗАДАЧА
══════════════════════════════════════════════════════════════

1. **СТАТИСТИКА**: Сколько GOOD, сколько BAD, процент успеха

2. **ЧТО РАБОТАЕТ**: Выдели паттерны которые получили GOOD оценки

3. **ПРОБЛЕМЫ**: Выдели 2-3 главные проблемы из BAD оценок. Процитируй конкретные комментарии экспертов.

4. **РЕШЕНИЯ**: Для каждой проблемы предложи конкретное решение:
   - Какую фразу/правило добавить
   - В какую секцию промпта
   - Пример как это должно работать

5. **НОВЫЙ ПРОМПТ**: Выдай ПОЛНЫЙ обновлённый файл sofia_prompt.py
   - Добавь в начало комментарий: # Обновлено: {datetime.now().strftime("%Y-%m-%d")} автоанализом
   - Сохрани ВСЮ структуру и функции
   - Внеси ТОЛЬКО необходимые улучшения для исправления BAD кейсов
   - НЕ удаляй то что работает (GOOD)

ВАЖНО: 
- Минимальные точечные изменения
- Каждое изменение должно решать конкретную проблему из BAD
- Сохрани весь рабочий код

══════════════════════════════════════════════════════════════
ФОРМАТ ОТВЕТА
══════════════════════════════════════════════════════════════

## 📊 СТАТИСТИКА
(цифры)

## ✅ ЧТО РАБОТАЕТ
(список)

## ❌ ПРОБЛЕМЫ
(список с цитатами экспертов)

## 💡 РЕШЕНИЯ
(конкретные изменения)

## 📝 НОВЫЙ ПРОМПТ
```python
(полный код файла sofia_prompt.py)
```
"""


def call_gpt_analysis(analysis_prompt):
    """Отправляем на анализ"""
    log(f"🧠 Отправляем в {ANALYZER_MODEL}...")
    log(f"   Размер запроса: ~{len(analysis_prompt)} символов")
    
    try:
        response = client.responses.create(
            model=ANALYZER_MODEL,
            input=analysis_prompt,
            
        )
        
        result = response.output_text
        log(f"✅ Ответ получен: ~{len(result)} символов")
        return result
        
    except Exception as e:
        log(f"❌ Ошибка API: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# ОБРАБОТКА РЕЗУЛЬТАТА
# ══════════════════════════════════════════════════════════════

def extract_new_prompt(analysis_result):
    """Извлекаем новый промпт из ответа"""
    if not analysis_result:
        return None
    
    import re
    
    # Ищем код между ```python и ```
    matches = re.findall(r'```python\n(.*?)```', analysis_result, re.DOTALL)
    
    if matches:
        # Ищем тот который содержит нужные функции
        for match in reversed(matches):
            if "def get_system_prompt" in match and "def get_time_context" in match:
                log(f"✅ Найден валидный промпт: {len(match)} символов")
                return match
    
    log("⚠️ Не удалось извлечь промпт из ответа")
    return None


def extract_analysis_summary(analysis_result):
    """Извлекаем краткую сводку для Telegram"""
    if not analysis_result:
        return "Анализ не выполнен"
    
    # Берём всё до "## 📝 НОВЫЙ ПРОМПТ"
    parts = analysis_result.split("## 📝 НОВЫЙ ПРОМПТ")
    if len(parts) > 1:
        return parts[0].strip()
    
    # Или первые 2000 символов
    return analysis_result[:2000]


def validate_prompt(new_prompt):
    """Проверяем валидность Python"""
    try:
        compile(new_prompt, '<string>', 'exec')
        
        if "def get_system_prompt" not in new_prompt:
            return False, "Нет функции get_system_prompt"
        if "def get_time_context" not in new_prompt:
            return False, "Нет функции get_time_context"
        if "COMPANY" not in new_prompt:
            return False, "Нет переменной COMPANY"
            
        return True, "OK"
    except SyntaxError as e:
        return False, f"Синтаксическая ошибка: {e}"


def backup_current_prompt():
    """Бэкап текущего промпта"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"sofia_prompt_{timestamp}.py")
    shutil.copy(PROMPT_PATH, backup_path)
    log(f"💾 Бэкап создан: {backup_path}")
    
    # Удаляем старые (храним 7)
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')])
    while len(backups) > 7:
        old = backups.pop(0)
        os.remove(os.path.join(BACKUP_DIR, old))
        log(f"🗑️ Удалён старый бэкап: {old}")
    
    return backup_path


def apply_new_prompt(new_prompt):
    """Применяем новый промпт"""
    with open(PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(new_prompt)
    log("✅ Новый промпт записан")


def restart_bot():
    """Перезапуск бота"""
    log("🔄 Перезапускаем sofia-bot...")
    result = os.system("systemctl restart sofia-bot")
    if result == 0:
        log("✅ Бот перезапущен")
    else:
        log(f"⚠️ Ошибка перезапуска: код {result}")
    return result == 0


# ══════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ══════════════════════════════════════════════════════════════

def main():
    log("=" * 60)
    log("🚀 SOFIA AUTO-ANALYZER ЗАПУЩЕН")
    log(f"   Run ID: {RUN_ID}")
    log(f"   Логи: {RUN_DIR}")
    log("=" * 60)
    
    send_telegram(f"🚀 <b>Автоанализ запущен</b>\n\nRun ID: {RUN_ID}")
    
    try:
        # 1. Инициализация
        log("\n[1/8] Инициализация OpenAI...")
        init_openai()
        log("✅ OpenAI клиент готов")
        
        # 2. Сбор данных
        log("\n[2/8] Сбор данных из базы...")
        messages, feedback = get_new_data()
        
        if len(feedback) < MIN_FEEDBACK_COUNT:
            msg = f"⏸️ Недостаточно оценок: {len(feedback)} < {MIN_FEEDBACK_COUNT}"
            log(msg)
            send_telegram(msg)
            return
        
        # 3. Форматирование
        log("\n[3/8] Форматирование данных...")
        dialogs_text = format_dialogs(messages)
        feedback_text = format_feedback(feedback)
        current_prompt = get_current_prompt()
        
        # Сохраняем входные данные
        save_to_file("01_dialogs.txt", dialogs_text)
        save_to_file("02_feedback.txt", feedback_text)
        save_to_file("03_current_prompt.py", current_prompt)
        
        # 4. Сборка промпта для GPT
        log("\n[4/8] Сборка промпта для анализа...")
        analysis_prompt = build_analysis_prompt(dialogs_text, feedback_text, current_prompt)
        save_to_file("04_gpt_input.txt", analysis_prompt)
        log(f"   Размер: {len(analysis_prompt)} символов (~{len(analysis_prompt)//4} токенов)")
        
        # 5. Отправка в GPT
        log("\n[5/8] Отправка в GPT-5.1...")
        analysis_result = call_gpt_analysis(analysis_prompt)
        
        if not analysis_result:
            send_telegram("❌ <b>Ошибка</b>: GPT не вернул ответ")
            return
        
        save_to_file("05_gpt_output.txt", analysis_result)
        
        # 6. Извлечение нового промпта
        log("\n[6/8] Извлечение нового промпта...")
        new_prompt = extract_new_prompt(analysis_result)
        analysis_summary = extract_analysis_summary(analysis_result)
        
        if not new_prompt:
            log("⚠️ Промпт не извлечён — сохраняем анализ для ручного просмотра")
            send_telegram(f"⚠️ <b>Анализ завершён, но промпт не извлечён</b>\n\nСмотри логи: {RUN_DIR}")
            send_telegram_file(os.path.join(RUN_DIR, "05_gpt_output.txt"), "Ответ GPT")
            return
        
        save_to_file("06_new_prompt.py", new_prompt)
        
        # 7. Валидация
        log("\n[7/8] Валидация нового промпта...")
        valid, error = validate_prompt(new_prompt)
        
        if not valid:
            log(f"❌ Промпт невалидный: {error}")
            send_telegram(f"❌ <b>Промпт невалидный</b>\n\nОшибка: {error}\n\nСмотри логи: {RUN_DIR}")
            send_telegram_file(os.path.join(RUN_DIR, "06_new_prompt.py"), "Невалидный промпт")
            return
        
        log("✅ Промпт валидный")
        
        # 8. Применение
        log("\n[8/8] Применение изменений...")
        backup_path = backup_current_prompt()
        apply_new_prompt(new_prompt)
        bot_restarted = restart_bot()
        
        # Финальное уведомление
        log("\n" + "=" * 60)
        log("✅ АВТОАНАЛИЗ ЗАВЕРШЁН УСПЕШНО")
        log("=" * 60)
        
        # Отправляем сводку
        final_message = f"""✅ <b>АВТОАНАЛИЗ ЗАВЕРШЁН</b>

📊 <b>Данные:</b>
• Диалогов: {len(set(m[0] for m in messages))}
• Сообщений: {len(messages)}
• Оценок: {len(feedback)}

💾 <b>Файлы:</b>
• Бэкап: создан
• Новый промпт: применён
• Бот: {'✅ перезапущен' if bot_restarted else '⚠️ требует ручного перезапуска'}

📁 <b>Логи:</b> {RUN_DIR}

{'─'*30}
{analysis_summary[:1500]}..."""
        
        send_telegram(final_message)
        
        # Отправляем файлы
        send_telegram_file(os.path.join(RUN_DIR, "05_gpt_output.txt"), "📄 Полный ответ GPT")
        send_telegram_file(os.path.join(RUN_DIR, "06_new_prompt.py"), "📄 Новый промпт")
        
    except Exception as e:
        error_msg = f"❌ <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n\n{type(e).__name__}: {e}"
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        send_telegram(error_msg)
        
        import traceback
        save_to_file("ERROR.txt", traceback.format_exc())


if __name__ == "__main__":
    main()
