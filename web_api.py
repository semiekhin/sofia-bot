"""
Sofia-GPT Web API v2.0
Веб-API для чат-виджета на сайте atlantis-invest.ru

Точка входа для сайта — как bot_server.py для Telegram, как radist_gateway для Max.
Использует тот же пайплайн: process_message() → Analyzer → RAG → Generator.
Никакие существующие файлы не трогает.

Запуск: uvicorn web_api:app --host 0.0.0.0 --port 8080
"""

import os
import sys
import json
import uuid
import re
import sqlite3
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# === Путь к Sofia-GPT ===
SOFIA_PATH = "/opt/sofia-gpt"
sys.path.insert(0, SOFIA_PATH)

# === Загрузка .env ===
from dotenv import load_dotenv
load_dotenv(os.path.join(SOFIA_PATH, ".env"))

# === Импорт модулей Sofia (общие с ботом) ===
from state_manager import StateManager
from message_processor import process_message
from rag_module import search_examples, format_examples_for_prompt
from sofia_prompt_v2 import get_system_prompt_v2, format_state_summary
import aiohttp
from openai import OpenAI

# === Константы ===
DB_PATH = os.path.join(SOFIA_PATH, "sofia_gpt.db")

# Observer (трансляция в Telegram-группу)
OBSERVER_CHAT_ID = os.getenv("OBSERVER_CHAT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Битрикс CRM
BITRIX_WEBHOOK_URL = "https://oazisestate.bitrix24.ru/rest/426/z61dwivdmdy9dk4f/crm.lead.add"
BITRIX_SOURCE_ID = "504"
BITRIX_ASSIGNED_ID = 426  # тест: 426, прод: 24932


def extract_phone_from_history(history):
    """Ищет номер телефона в сообщениях клиента"""
    import re
    phone_pattern = re.compile(r'(?:\+?7|8)[\s\-\(]*(\d{3})[\s\-\)]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})')
    for msg in reversed(history):
        if msg["role"] == "user":
            match = phone_pattern.search(msg["content"])
            if match:
                digits = "7" + match.group(1) + match.group(2) + match.group(3) + match.group(4)
                return digits
    # Fallback: ищем просто 10-11 цифр подряд
    digit_pattern = re.compile(r'(?<!\d)(\d{10,11})(?!\d)')
    for msg in reversed(history):
        if msg["role"] == "user":
            match = digit_pattern.search(msg["content"].replace(" ", "").replace("-", ""))
            if match:
                d = match.group(1)
                if len(d) == 10:
                    return "7" + d
                if len(d) == 11 and d[0] in ("7", "8"):
                    return "7" + d[1:]
    return None


async def send_lead_to_bitrix(user_id, user_name, state, history):
    """Отправляет квалифицированный лид в Битрикс24"""
    phone = extract_phone_from_history(history)
    
    # Собираем данные из state
    goal_map = {"investment": "Инвестиции", "personal": "Для себя", "combined": "Комбинированно"}
    payment_map = {"full": "Полная оплата", "mortgage": "Ипотека", "installment": "Рассрочка"}
    
    goal = goal_map.get(getattr(state, "goal", None) or "", "Не указана")
    budget = getattr(state, "budget", None)
    budget_str = f"{budget / 1_000_000:.1f} млн ₽" if budget else "Не указан"
    payment = payment_map.get(getattr(state, "payment_type", None) or "", "Не указан")
    finish_type = getattr(state, "finish_type", "llm_end")
    
    # Последние сообщения для комментария
    last_msgs = history[-10:] if len(history) > 10 else history
    chat_text = "\n".join([f"{'София' if m['role']=='assistant' else 'Клиент'}: {m['content']}" for m in last_msgs])
    
    comments = f"""Лид от AI-бота София (виджет на сайте)
Цель: {goal}
Бюджет: {budget_str}
Оплата: {payment}
Тип завершения: {"созвон" if "meeting" in str(finish_type) else "подборка/диалог"}

--- Последние сообщения ---
{chat_text}"""
    
    fields = {
        "TITLE": f"AI-бот: {user_name or 'Клиент с сайта'}",
        "NAME": user_name or "Клиент",
        "COMMENTS": comments,
        "SOURCE_ID": BITRIX_SOURCE_ID,
        "ASSIGNED_BY_ID": BITRIX_ASSIGNED_ID,
    }
    
    if phone:
        fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "MOBILE"}]
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(BITRIX_WEBHOOK_URL, json={"fields": fields}) as resp:
                result = await resp.json()
                lead_id = result.get("result")
                if lead_id:
                    log.info(f"✅ [BITRIX] Лид создан #{lead_id}, phone={phone or 'нет'}")
                else:
                    log.warning(f"⚠️ [BITRIX] Ответ без ID: {result}")
    except Exception as e:
        log.error(f"❌ [BITRIX] Ошибка: {e}")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAG_EXAMPLES_COUNT = 10
RAG_ENABLED = True
WEB_USER_ID_OFFSET = 9_000_000

# === OpenAI Client ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === State Manager (общая БД с ботом) ===
state_manager = StateManager(DB_PATH)

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WEB-API] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(SOFIA_PATH, "web_api.log")),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ============================================================
# РАБОТА С БД (сообщения) — по образцу bot_server.py
# ============================================================

def save_message(chat_id, user_id, user_name, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO messages (chat_id, user_id, user_name, role, content, processed, stage) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (chat_id, user_id, user_name, role, content, 1, None)
    )
    conn.commit()
    conn.close()


def get_history(chat_id, limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?',
        (chat_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


# ============================================================
# СЕССИИ: session_id (UUID) → user_id (int)
# ============================================================

_session_to_uid = {}


def get_web_user_id(session_id):
    if session_id not in _session_to_uid:
        uid = WEB_USER_ID_OFFSET + (hash(session_id) % 1_000_000)
        _session_to_uid[session_id] = uid
        log.info(f"Новая сессия: {session_id[:8]}... -> user_id={uid}")
    return _session_to_uid[session_id]


# ============================================================
# ГЕНЕРАЦИЯ ОТВЕТА — Analyzer → RAG → Generator
# ============================================================

async def get_or_create_web_topic(session_id: str, user_name: str) -> int:
    """Получает или создаёт тему для веб-клиента в группе наблюдателей"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    topic_key = f"web_{session_id[:8]}"
    c.execute("SELECT thread_id FROM observer_topics WHERE phone = ?", (topic_key,))
    row = c.fetchone()
    if row:
        conn.close()
        return row[0]
    
    display_name = f"\U0001f310 {user_name}" if user_name else f"\U0001f310 Web {session_id[:8]}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createForumTopic"
    payload = {"chat_id": OBSERVER_CHAT_ID, "name": display_name[:128]}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if data.get("ok"):
                    thread_id = data["result"]["message_thread_id"]
                    c.execute("INSERT OR REPLACE INTO observer_topics (phone, thread_id, user_name) VALUES (?, ?, ?)",
                              (topic_key, thread_id, display_name))
                    conn.commit()
                    conn.close()
                    return thread_id
    except Exception as e:
        log.warning(f"\u26a0\ufe0f [WEB] Observer topic error: {e}")
    
    conn.close()
    return None


async def notify_web_observer(session_id: str, user_name: str, direction: str, message: str):
    """Отправляет копию сообщения из веб-виджета в группу наблюдателей"""
    if not OBSERVER_CHAT_ID or not TELEGRAM_BOT_TOKEN:
        return
    
    thread_id = await get_or_create_web_topic(session_id, user_name)
    
    if direction == "in":
        text = f"\U0001f310 <b>Клиент:</b>\n{message}"
    else:
        text = f"\u21a9\ufe0f <b>София:</b>\n{message}"
    
    if len(text) > 4000:
        text = text[:4000] + "..."
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": OBSERVER_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                pass
    except Exception as e:
        log.warning(f"\u26a0\ufe0f [WEB] Observer send error: {e}")


async def generate_response(user_id, user_message, user_name):
    history = get_history(user_id, limit=100)
    state = state_manager.get_state(user_id)

    history_text = "\n".join([
        f"{'София' if m['role']=='assistant' else 'Клиент'}: {m['content']}"
        for m in history[-20:]
    ])

    state_summary = format_state_summary(state) if state else "Новый клиент"
    
    # Контекст источника: клиент пришёл с сайта ЖК Атлантис
    state_summary += """

КОНТЕКСТ ИСТОЧНИКА:
Клиент пришёл с сайта atlantis-invest.ru — это сайт апарт-отеля «Атлантис» в Крыму.
- Объект: первая береговая линия Крыма, wellness-курорт, управление Cosmos Hotel Group
- Планировки и цены (актуальные, февраль 2026):
  · Студия 35-40 м² — от 16.8 млн ₽ (470-480 тыс/м²)
  · 1-спальня 47 м² — от 20.7 млн ₽ (440-480 тыс/м²)
  · 2-спальня 57-65 м² — от 22.8 млн ₽ (400-410 тыс/м²)
  · 3-комнатная 66-80 м² — от 26.5 млн ₽ (400-410 тыс/м²)
  · Премиум 117+ м² — от 45 млн ₽
  · Черновая отделка дешевле, с ремонтом — дороже
- Рассрочка/ипотека доступны, сделка по ФЗ-214 через эскроу-счета
- НЕ спрашивай про локацию — клиент уже выбрал Крым и этот объект
- Фокусируйся на Атлантисе

СТРАТЕГИЯ ВЕБ-ЧАТА (ты общаешься через виджет на сайте):
Клиент анонимный, вовлечённость низкая — может закрыть вкладку в любой момент.

ПРИНЦИП: давай ценность, спрашивай мало.
- Отвечай полноценно и интересно: конкретные цифры доходности, планировки, преимущества объекта
- НЕ говори «подробнее расскажу на созвоне» — дай информацию ЗДЕСЬ, этим ты вовлекаешь
- Будь экспертом который делится знаниями, а не анкетой которая допрашивает

КВАЛИФИКАЦИЯ — максимум 3 вопроса за весь диалог:
1. Цель (уже спросила в приветствии: отдых / доход / комбинированно)
2. Бюджет (естественно: «В каком бюджете смотрите?»)
3. Способ оплаты (рассрочка / ипотека / полная)
Всё. Никаких дополнительных вопросов (ЛПР, сроки, локация и т.д.)

СБОР КОНТАКТА (ОБЯЗАТЕЛЬНО):
- Контакт клиента НЕ ИЗВЕСТЕН — без номера договорённость бесполезна
- Когда клиент согласился на созвон или подборку → спроси: «Куда удобнее — WhatsApp, Telegram? Напишите номер»
- Пока не дал номер → НЕ ставь [END], мягко повтори просьбу
- Получила номер → «Спасибо! Специалист перезвонит/отправит подборку в ближайшее время 😊» → [END]"""
    

    # ШАГ 1: LLM-Аналитик
    analyzer_prompt = """Ты — аналитик диалогов продаж недвижимости.

Прочитай диалог и последнее сообщение клиента. Определи:
1. На какой вопрос/тему отвечает клиент?
2. Какой сейчас этап продажи?
3. Какие примеры из базы помогут менеджеру ответить?

ЭТАПЫ:
- GREETING — приветствие, начало диалога
- ACTUALIZATION — актуализация интереса холодного лида (не помнит заявку, давно оставлял, спрашивает "кто вы?", "какой сайт?")
- QUALIFICATION — выясняем цель, бюджет, сроки, способ оплаты
- MEETING — предлагаем созвон
- OBJECTION — клиент возражает (дорого, подумаю, не сейчас, пришлите материалы)
- CLOSING — завершение (договорились о созвоне, отправляем подборку, прощаемся)

Ответь СТРОГО в формате JSON:
{
  "client_intent": "краткое описание что имеет в виду клиент",
  "stage": "ОДИН ИЗ ЭТАПОВ",
  "rag_query": "что искать в базе примеров (на русском, 3-7 слов)"
}"""

    analyzer_input = f"""ИСТОРИЯ ДИАЛОГА:
{history_text if history_text else "Диалог только начался"}

НОВОЕ СООБЩЕНИЕ КЛИЕНТА:
{user_message}

ЧТО ИЗВЕСТНО О КЛИЕНТЕ:
{state_summary}"""

    rag_stage = "QUALIFICATION"
    rag_query = user_message

    try:
        log.info(f"🧠 [WEB] Analyzer запрос...")
        analyzer_response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5.2",
            instructions=analyzer_prompt,
            input=analyzer_input,
            reasoning={"effort": "medium"}
        )
        analyzer_text = analyzer_response.output_text or ""
        json_match = re.search(r'\{[^}]+\}', analyzer_text, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            rag_stage = analysis.get("stage", "QUALIFICATION")
            rag_query = analysis.get("rag_query", user_message)
            log.info(f"🧠 [WEB] Analyzer: stage={rag_stage}, query='{rag_query[:30]}...'")
        else:
            log.warning(f"⚠️ [WEB] Analyzer: JSON не найден, fallback")
    except Exception as e:
        log.warning(f"⚠️ [WEB] Analyzer error: {e}, fallback")

    # ШАГ 2: RAG
    examples_prompt = ""
    if RAG_ENABLED:
        examples = search_examples(rag_stage, rag_query, limit=RAG_EXAMPLES_COUNT)
        if examples:
            examples_prompt = format_examples_for_prompt(examples)
            log.info(f"📚 [WEB] RAG [{rag_stage}]: {len(examples)} примеров")

    # ШАГ 3: LLM-Генератор
    system_prompt = get_system_prompt_v2(state_summary, examples_prompt)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    try:
        log.info(f"🔄 [WEB] Generator запрос для {user_name}...")
        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5.2",
            instructions=system_prompt,
            input=messages,
            reasoning={"effort": "high"},
            max_output_tokens=4000
        )
        answer = response.output_text or ""

        log.info(f"📏 [WEB] Generator: len={len(answer)}, output_tokens={getattr(response.usage, 'output_tokens', '?')}")
        try:
            stop_reason = getattr(response.output[-1], 'stop_reason', None) if response.output else None
            if stop_reason == "max_tokens" or (len(answer) > 50 and not answer.rstrip().endswith(("?", "!", ".", ")", "»", '"'))):
                log.warning(f"⚠️ [WEB] ОБРЕЗКА! stop={stop_reason}, len={len(answer)}")
        except Exception as e:
            log.warning(f"⚠️ stop_reason check error: {e}")

        if "[END]" in answer or "[end]" in answer:
            answer = answer.replace("[END]", "").replace("[end]", "").strip()
            state_manager.update_state(user_id, {"dialog_finished": True, "finish_type": "llm_end"})
            log.info(f"🏁 [WEB] LLM завершил диалог [END]")
            
            # Отправляем лид в Битрикс
            try:
                state_fresh = state_manager.get_state(user_id)
                history_fresh = get_history(user_id, limit=100)
                await send_lead_to_bitrix(user_id, user_name, state_fresh, history_fresh)
            except Exception as e:
                log.error(f"❌ [BITRIX] send error: {e}")

        if not answer.strip():
            answer = "Подскажите, что для вас сейчас важнее — посмотреть варианты или обсудить условия?"

        log.info(f"✅ [WEB] Generator ответил")
        return answer

    except Exception as e:
        log.error(f"❌ [WEB] Generator error: {e}")
        return "Простите, связь подвисла. Напишите ещё раз?"


# ============================================================
# ОБРАБОТКА СООБЩЕНИЯ — полный цикл
# ============================================================

async def handle_web_message(user_id, user_name, message):
    save_message(chat_id=user_id, user_id=user_id, user_name=user_name, role="user", content=message)

    history = get_history(user_id, limit=100)
    await process_message(
        user_id=user_id,
        user_name=user_name,
        message=message,
        history=history,
        state_manager=state_manager,
        channel="web"
    )

    await notify_web_observer(str(user_id), user_name, "in", message)
    
    reply = await generate_response(user_id, message, user_name)
    
    if reply:
        await notify_web_observer(str(user_id), user_name, "out", reply)
    save_message(chat_id=user_id, user_id=user_id, user_name=user_name, role="assistant", content=reply)

    return reply


# ============================================================
# FASTAPI APP
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🌐 Sofia Web API v2.0 starting...")
    log.info(f"   Sofia path: {SOFIA_PATH}")
    log.info(f"   DB: {DB_PATH}")
    yield
    log.info("Sofia Web API shutting down...")

app = FastAPI(title="Sofia-GPT Web API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://atlantis-invest.ru",
        "http://atlantis-invest.ru",
        "https://www.atlantis-invest.ru",
        "http://www.atlantis-invest.ru",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
        "https://sochiremstroy.tilda.ws",
        "http://sochiremstroy.tilda.ws",
        "https://invest-apartmens.online",
        "http://invest-apartmens.online",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class SessionRequest(BaseModel):
    referrer: Optional[str] = None
    page_url: Optional[str] = None

class ChatRequest(BaseModel):
    session_id: str
    message: str
    page_url: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    timestamp: str


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0", "timestamp": datetime.now().isoformat()}


@app.post("/api/session")
async def create_session(req: SessionRequest):
    session_id = str(uuid.uuid4())
    user_id = get_web_user_id(session_id)
    log.info(f"📱 Новая сессия: {session_id[:8]}... from {req.page_url or 'unknown'}")
    # Приветствие зависит от источника
    if req.page_url and "atlantis" in req.page_url.lower():
        greeting = "Здравствуйте! 😊 Я София, менеджер отдела продаж. Помогу подобрать варианты. Какая цель: отдых / доход / комбинированно?"
    else:
        greeting = "Здравствуйте! 😊 Я София, эксперт Oazis Estate по курортной недвижимости. Чем могу помочь?"
    
    # BUG-005 fix: сохраняем greeting в историю чтобы LLM видел свой вопрос
    save_message(chat_id=user_id, user_id=user_id, user_name="Sofia", role="assistant", content=greeting)
    
    return {
        "session_id": session_id,
        "greeting": greeting
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    if len(req.message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")

    user_id = get_web_user_id(req.session_id)
    reply = await handle_web_message(
        user_id=user_id,
        user_name=f"web_{req.session_id[:8]}",
        message=req.message
    )
    return ChatResponse(session_id=req.session_id, reply=reply, timestamp=datetime.now().isoformat())


@app.get("/api/history/{session_id}")
async def get_session_history(session_id: str, limit: int = 50):
    user_id = get_web_user_id(session_id)
    messages = get_history(user_id, limit=limit)
    return {
        "session_id": session_id,
        "messages": [{"role": "bot" if m["role"] == "assistant" else "user", "content": m["content"]} for m in messages]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
