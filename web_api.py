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
from openai import OpenAI

# === Константы ===
DB_PATH = os.path.join(SOFIA_PATH, "sofia_gpt.db")
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

async def generate_response(user_id, user_message, user_name):
    history = get_history(user_id, limit=100)
    state = state_manager.get_state(user_id)

    history_text = "\n".join([
        f"{'София' if m['role']=='assistant' else 'Клиент'}: {m['content']}"
        for m in history[-20:]
    ])

    state_summary = format_state_summary(state) if state else "Новый клиент"

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

    reply = await generate_response(user_id, message, user_name)
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
    return {
        "session_id": session_id,
        "greeting": "Здравствуйте! 😊 Я София, эксперт Oazis Estate по курортной недвижимости. Чем могу помочь?"
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
