#!/usr/bin/env python3
"""
Sofia Radist Gateway — шлюз для Max мессенджера через Radist.Online
Версия: 1.0
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

# Импорт конфига Radist
from config.radist_config import RADIST_CONFIG, get_headers, get_base_url

# Импорт компонентов Sofia
from state_manager import StateManager, ClientState
from extractor import extract_sync, merge_extraction_to_state
from planner import get_next_action, get_allowed_actions, get_action_context, Action, increment_slot_attempt
from sofia_prompt import get_system_prompt, BOT_NAME
from rag_module import search_examples, format_examples_for_prompt
from stage_detector import detect_stage

load_dotenv()

# ============================================
# НАСТРОЙКИ
# ============================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_MODE = os.getenv("MODEL_MODE", "gpt-5.2")
USE_LLM_PLANNER = os.getenv("USE_LLM_PLANNER", "false").lower() == "true"
DB_PATH = "sofia_gpt.db"
LOG_PATH = "sofia_radist.log"

# RAG настройки
RAG_EXAMPLES_COUNT = 10
RAG_ENABLED = True

# Маппинг Action → Stage для RAG
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
    "ease_pressure": "OBJECTION",
    "send_materials": "PRESENTATION",
    "greeting": "GREETING",
}

# OpenAI client
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# State Manager
state_manager = StateManager(DB_PATH)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [MAX] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
log = logging.info

# ============================================
# DATABASE для Max сообщений
# ============================================

def init_max_db():
    """Инициализация таблицы для Max сообщений"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS max_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        contact_id INTEGER,
        phone TEXT,
        role TEXT,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS max_chats (
        chat_id INTEGER PRIMARY KEY,
        contact_id INTEGER,
        phone TEXT,
        user_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def save_max_message(chat_id: int, contact_id: int, phone: str, role: str, content: str):
    """Сохраняет сообщение Max в БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO max_messages (chat_id, contact_id, phone, role, content) VALUES (?, ?, ?, ?, ?)",
        (chat_id, contact_id, phone, role, content)
    )
    conn.commit()
    conn.close()

def get_max_history(chat_id: int, limit: int = 8) -> list:
    """Получает историю сообщений Max"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM max_messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (chat_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def save_max_chat(chat_id: int, contact_id: int, phone: str, user_name: str = None):
    """Сохраняет информацию о чате Max"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO max_chats (chat_id, contact_id, phone, user_name) VALUES (?, ?, ?, ?)",
        (chat_id, contact_id, phone, user_name)
    )
    conn.commit()
    conn.close()

# ============================================
# RADIST API
# ============================================

async def send_message_to_max(chat_id: int, text: str) -> bool:
    """Отправляет сообщение в Max через Radist API"""
    url = f"{get_base_url()}/messaging/messages/"
    payload = {
        "connection_id": RADIST_CONFIG["connection_id"],
        "chat_id": chat_id,
        "message_type": "text",
        "text": {"text": text}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=get_headers(), json=payload) as resp:
                if resp.status == 200:
                    log(f"📤 Отправлено в Max (chat_id={chat_id}): {text[:50]}...")
                    return True
                else:
                    error = await resp.text()
                    log(f"❌ Ошибка отправки в Max: {resp.status} — {error}")
                    return False
    except Exception as e:
        log(f"❌ Исключение при отправке в Max: {e}")
        return False

# ============================================
# ОБРАБОТКА СООБЩЕНИЙ (аналог delayed_response)
# ============================================

async def process_max_message(chat_id: int, contact_id: int, phone: str, user_message: str, user_name: str = None):
    """
    Обрабатывает входящее сообщение из Max.
    Логика аналогична delayed_response из bot_server.py
    """
    # Уникальный user_id для Max (чтобы не пересекался с Telegram)
    # Используем отрицательный chat_id или префикс
    user_id = -chat_id  # Отрицательный ID для Max клиентов
    
    if not user_name:
        user_name = phone
    
    log(f"📥 Max [{phone}]: {user_message}")
    
    # Сохраняем входящее сообщение
    save_max_message(chat_id, contact_id, phone, "user", user_message)
    
    # ════════════════════════════════════════════════════════════════════════
    # Агентная архитектура — Extractor → State → Planner
    # ════════════════════════════════════════════════════════════════════════
    
    # 1. Получаем текущее состояние клиента
    client_state = state_manager.get_state(user_id)
    
    # 2. Получаем историю для Extractor
    history = get_max_history(chat_id, limit=6)
    history_for_extractor = [{"role": m["role"], "content": m["content"]} for m in history]
    
    # 3. Извлекаем данные из сообщения (NLU)
    extraction = extract_sync(user_message, history_for_extractor)
    log(f"🔍 Extractor: {extraction}")
    
    # 4. Обновляем состояние клиента
    state_updates = merge_extraction_to_state(client_state.to_dict(), extraction)
    client_state = state_manager.update_state(user_id, state_updates)
    log(f"📊 State: {client_state.summary()}")
    
    # 5. Определяем следующее действие (Planner)
    micro_goal = None
    tone = "warm"
    
    if USE_LLM_PLANNER:
        try:
            from llm_planner import llm_select_action
            allowed_actions = get_allowed_actions(client_state, user_message, extraction)
            log(f"🔀 Allowed actions: {[a.value for a in allowed_actions]}")
            
            if len(allowed_actions) > 1:
                llm_result = llm_select_action(allowed_actions, client_state, user_message, history, extraction)
                action = llm_result["action"]
                micro_goal = llm_result.get("micro_goal")
                tone = llm_result.get("tone", "warm")
                log(f"🤖 LLM Planner: {action.value} | micro_goal: {micro_goal} | tone: {tone}")
            else:
                action = allowed_actions[0]
                log(f"🎯 Single action: {action.value}")
        except Exception as e:
            log(f"⚠️ LLM Planner error: {e}, fallback to deterministic")
            action = get_next_action(client_state, user_message, extraction)
    else:
        action = get_next_action(client_state, user_message, extraction)
    
    action_context = get_action_context(action, client_state, extraction)
    if micro_goal:
        action_context["micro_goal"] = micro_goal
    action_context["tone"] = tone
    log(f"🎯 Planner: {action.value}")
    
    # 5.1 Увеличиваем счётчики
    ACTION_TO_SLOT = {"payment": "payment_type"}
    if action.value.startswith("ask_"):
        slot = action.value.replace("ask_", "")
        slot = ACTION_TO_SLOT.get(slot, slot)
        increment_slot_attempt(client_state, slot, "ask")
        state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
    elif action.value.startswith("help_"):
        slot = action.value.replace("help_", "")
        slot = ACTION_TO_SLOT.get(slot, slot)
        increment_slot_attempt(client_state, slot, "help")
        state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
    
    # 5.1.2 Увеличиваем счётчик запросов материалов
    if extraction.get("wants_materials") or extraction.get("objection") == "no_call":
        client_state.materials_request_count = getattr(client_state, "materials_request_count", 0) + 1
    
    if action in [Action.PROPOSE_MEETING_1, Action.PROPOSE_MEETING_2]:
        client_state.call_proposal_count = getattr(client_state, 'call_proposal_count', 0) + 1
    
    # 5.2 Сохраняем обновления состояния
    v2_updates = {
        "branch": client_state.branch,
        "call_proposal_count": client_state.call_proposal_count,
        "materials_request_count": client_state.materials_request_count,
    }
    
    signals = extraction.get("signals", {})
    if signals:
        v2_updates["friction"] = signals.get("friction", 0.3)
        v2_updates["call_readiness"] = signals.get("call_readiness", 0.5)
        v2_updates["engagement"] = signals.get("engagement", "medium")
        v2_updates["urgency"] = signals.get("urgency", "unclear")
    
    if action == Action.FINISH_WITH_MATERIALS:
        v2_updates["dialog_finished"] = True
        v2_updates["finish_type"] = "materials"
    elif action == Action.CONFIRM_MEETING:
        v2_updates["dialog_finished"] = True
        v2_updates["finish_type"] = "meeting"
    
    state_manager.update_state(user_id, v2_updates)
    
    # 6. Проверка WAIT
    if action == Action.WAIT:
        log(f"⏸️ WAIT: пропускаем ответ")
        return
    
    # 7. Очищаем временные флаги
    state_manager.clear_temporary_flags(user_id)
    
    # ════════════════════════════════════════════════════════════════════════
    # Генерация ответа
    # ════════════════════════════════════════════════════════════════════════
    
    response = await generate_response_max(chat_id, user_id, user_message, user_name, action_context)
    
    # Сохраняем ответ
    save_max_message(chat_id, contact_id, phone, "assistant", response)
    
    # Отправляем в Max
    await send_message_to_max(chat_id, response)


async def generate_response_max(chat_id: int, user_id: int, user_message: str, user_name: str, action_context: dict) -> str:
    """Генерирует ответ для Max с использованием RAG"""
    
    history = get_max_history(chat_id)
    
    # Определяем этап для RAG
    stage_result = detect_stage(user_message, history, "QUALIFICATION")
    current_stage = stage_result["stage"]
    
    # RAG примеры
    examples_prompt = ""
    if RAG_ENABLED and action_context:
        action = action_context.get("action", "")
        rag_stage = ACTION_TO_RAG_STAGE.get(action, current_stage)
        examples = search_examples(rag_stage, user_message, limit=RAG_EXAMPLES_COUNT)
        if examples:
            examples_prompt = format_examples_for_prompt(examples)
            log(f"📚 RAG: {len(examples)} примеров для {rag_stage}")
    
    # System prompt
    system_prompt = get_system_prompt(user_name, action_context)
    
    if examples_prompt:
        system_prompt += f"""

════════════════════════════════════════════════════════════════════════════════
ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ (RAG)
════════════════════════════════════════════════════════════════════════════════
{examples_prompt}
"""
    
    # Формируем сообщения
    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    
    # Вызов OpenAI
    try:
        log(f"🔄 GPT запрос для Max [{user_name}]...")
        
        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5.2",
            instructions=system_prompt,
            input=messages,
            text={"verbosity": "low"}
        )
        
        assistant_message = response.output_text
        if not assistant_message or assistant_message.strip() == "":
            assistant_message = "Вы на связи? 😊"
        
        log(f"✅ GPT ответил")
        return assistant_message
        
    except Exception as e:
        log(f"❌ Ошибка GPT: {e}")
        return "Простите, связь подвисла. Напишите ещё раз?"


# ============================================
# WEBHOOK HANDLER
# ============================================

async def handle_webhook(request):
    """Обработчик webhook от Radist"""
    try:
        data = await request.json()
        log(f"🔔 Webhook: {json.dumps(data, ensure_ascii=False)[:500]}")
        
        event_type = data.get("event_type")
        
        if event_type == "messages.create":
            event_data = data.get("event", {})
            message = event_data.get("message", {})
            chat = event_data.get("chat", {})
            
            # Проверяем что это наше подключение
            connection_id = event_data.get("connection_id")
            if connection_id != RADIST_CONFIG["connection_id"]:
                log(f"⚠️ Чужой connection_id: {connection_id}")
                return web.json_response({"status": "ignored"})
            
            # Извлекаем данные
            chat_id = event_data.get("chat_id")
            contact_id = event_data.get("contact_id")
            phone = chat.get("phone", "")
            user_name = phone  # Имя из Max некорректное, используем телефон
            
            # Текст сообщения
            # Игнорируем исходящие сообщения (от бота)
            direction = message.get("direction")
            if direction == "outbound":
                log(f"⏭️ Пропускаем outbound сообщение")
                return web.json_response({"status": "ignored_outbound"})
            
            message_type = message.get("message_type")
            if message_type == "text":
                text_data = message.get("text", {})
                user_message = text_data.get("text", "")
            else:
                user_message = f"[{message_type}]"
                log(f"⚠️ Неподдерживаемый тип: {message_type}")
            
            if user_message and chat_id:
                # Сохраняем информацию о чате
                save_max_chat(chat_id, contact_id, phone, user_name)
                
                # Обрабатываем асинхронно
                asyncio.create_task(
                    process_max_message(chat_id, contact_id, phone, user_message, user_name)
                )
        
        return web.json_response({"status": "ok"})
        
    except Exception as e:
        log(f"❌ Webhook error: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def health_check(request):
    """Health check endpoint"""
    return web.json_response({
        "status": "ok",
        "service": "sofia-radist-gateway",
        "timestamp": datetime.now().isoformat()
    })


# ============================================
# MAIN
# ============================================

def main():
    """Запуск gateway"""
    init_max_db()
    
    app = web.Application()
    app.router.add_post(RADIST_CONFIG["webhook_path"], handle_webhook)
    app.router.add_get("/health", health_check)
    
    port = RADIST_CONFIG["webhook_port"]
    log(f"🚀 Sofia Radist Gateway запущен на порту {port}")
    log(f"📡 Webhook: http://0.0.0.0:{port}{RADIST_CONFIG['webhook_path']}")
    
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
