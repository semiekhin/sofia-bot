"""
Sofia-GPT Web API v2.0
Веб-API для чат-виджета на сайте atlantis-invest.ru

Точка входа для сайта — как bot_server.py для Telegram, как radist_gateway для Max.
Использует тот же пайплайн: process_message() → Analyzer → RAG → Generator.
Никакие существующие файлы не трогает.

Запуск: uvicorn web_api:app --host 0.0.0.0 --port 8080
"""

import json
import os
import sys
import uuid
import sqlite3
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# === Путь к Sofia-GPT ===
SOFIA_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SOFIA_PATH)

# === Загрузка .env ===
from dotenv import load_dotenv

load_dotenv(os.path.join(SOFIA_PATH, ".env"))

# === Импорт модулей Sofia (общие с ботом) ===
from state_manager import StateManager
from message_processor import process_message
from core.pipeline import run_pipeline
from core.bitrix import (
    create_or_update_lead,
    get_lead_id_by_session,
    save_lead_id_for_session,
    get_session_id_by_user_id,
    find_user_id_by_lead,
    is_manager_active,
    restore_assigned,
    set_lead_assigned,
    set_manager_active,
    BITRIX_BASE_URL,
    SOFIA_AI_USER_ID,
)
import aiohttp
from openai import OpenAI

# === Константы ===
DB_PATH = os.environ.get("DB_PATH", os.path.join(SOFIA_PATH, "sofia_gpt.db"))
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(SOFIA_PATH, DB_PATH)

# Observer (трансляция в Telegram-группу)
OBSERVER_CHAT_ID = os.getenv("OBSERVER_CHAT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Битрикс CRM — логика в core/bitrix.py


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
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ============================================================
# РАБОТА С БД (сообщения) — по образцу bot_server.py
# ============================================================


def save_message(chat_id, user_id, user_name, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (chat_id, user_id, user_name, role, content, processed, stage) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, user_name, role, content, 1, None),
    )
    conn.commit()
    conn.close()


def get_history(chat_id, limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (chat_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


# ============================================================
# СЕССИИ: session_id (UUID) → user_id (int)
# ============================================================

_session_to_uid = {}
_uid_counter_lock = __import__("threading").Lock()


def _get_next_web_uid():
    """Стабильный автоинкремент вместо hash()"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(MAX(user_id), ?) FROM web_sessions", (WEB_USER_ID_OFFSET,)
    )
    max_uid = c.fetchone()[0]
    conn.close()
    return max_uid + 1


def get_web_user_id(session_id):
    # 1. Кэш в памяти (быстрый путь)
    if session_id in _session_to_uid:
        return _session_to_uid[session_id]
    # 2. SQLite (переживает рестарт)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM web_sessions WHERE session_id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    if row:
        _session_to_uid[session_id] = row[0]
        return row[0]
    # 3. Новая сессия — стабильный ID
    with _uid_counter_lock:
        uid = _get_next_web_uid()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO web_sessions (session_id, user_id) VALUES (?, ?)",
            (session_id, uid),
        )
        conn.commit()
        conn.close()
    _session_to_uid[session_id] = uid
    log.info(f"Новая сессия: {session_id[:8]}... -> user_id={uid}")
    return uid


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

    display_name = (
        f"\U0001f310 {user_name}" if user_name else f"\U0001f310 Web {session_id[:8]}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createForumTopic"
    payload = {"chat_id": OBSERVER_CHAT_ID, "name": display_name[:128]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if data.get("ok"):
                    thread_id = data["result"]["message_thread_id"]
                    c.execute(
                        "INSERT OR REPLACE INTO observer_topics (phone, thread_id, user_name) VALUES (?, ?, ?)",
                        (topic_key, thread_id, display_name),
                    )
                    conn.commit()
                    conn.close()
                    return thread_id
    except Exception as e:
        log.warning(f"\u26a0\ufe0f [WEB] Observer topic error: {e}")

    conn.close()
    return None


async def notify_web_observer(
    session_id: str, user_name: str, direction: str, message: str
):
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
    payload = {"chat_id": OBSERVER_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if thread_id:
        payload["message_thread_id"] = thread_id

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                pass
    except Exception as e:
        log.warning(f"\u26a0\ufe0f [WEB] Observer send error: {e}")


async def generate_response(user_id, user_message, user_name, channel="web"):
    """Генерирует ответ через core/pipeline.py."""
    history = get_history(user_id, limit=100)

    result = await run_pipeline(
        user_id=user_id,
        user_message=user_message,
        user_name=user_name,
        history=history,
        state_manager=state_manager,
        channel=channel,
    )

    # Финализация при [END]
    if result.dialog_finished:
        session_id = get_session_id_by_user_id(DB_PATH, user_id)
        if session_id:
            try:
                state_fresh = state_manager.get_state(user_id)
                history_fresh = get_history(user_id, limit=100)
                lead_id = get_lead_id_by_session(DB_PATH, session_id)
                await create_or_update_lead(
                    lead_id,
                    user_name,
                    state_fresh,
                    history_fresh,
                    is_final=True,
                    channel="web",
                )
                # Вернуть ответственного после завершения
                if lead_id:
                    await restore_assigned(DB_PATH, lead_id)
            except Exception as e:
                log.error(f"❌ [BITRIX] final update error: {e}")

    return (
        result.answer
        or "Подскажите, что для вас сейчас важнее — посмотреть варианты или обсудить условия?"
    )


# ============================================================
# ОБРАБОТКА СООБЩЕНИЯ — полный цикл
# ============================================================


async def handle_web_message(user_id, user_name, message, session_id=None):
    # Проверяем перехват менеджером
    if is_manager_active(DB_PATH, user_id):
        log.info(f"🛑 [WEB] manager_active=1 для user_id={user_id}, Sofia молчит")
        save_message(
            chat_id=user_id,
            user_id=user_id,
            user_name=user_name,
            role="user",
            content=message,
        )
        return None

    save_message(
        chat_id=user_id,
        user_id=user_id,
        user_name=user_name,
        role="user",
        content=message,
    )

    history = get_history(user_id, limit=100)
    await process_message(
        user_id=user_id,
        user_name=user_name,
        message=message,
        history=history,
        state_manager=state_manager,
        channel="web",
    )

    await notify_web_observer(str(user_id), user_name, "in", message)

    reply = await generate_response(user_id, message, user_name)

    if reply:
        await notify_web_observer(str(user_id), user_name, "out", reply)
    save_message(
        chat_id=user_id,
        user_id=user_id,
        user_name=user_name,
        role="assistant",
        content=reply,
    )

    # Создаём/обновляем лид в Битриксе при каждом сообщении
    if session_id:
        try:
            state = state_manager.get_state(user_id)
            fresh_history = get_history(user_id, limit=100)
            lead_id = get_lead_id_by_session(DB_PATH, session_id)
            new_lead_id = await create_or_update_lead(
                lead_id,
                user_name,
                state,
                fresh_history,
                channel="web",
            )
            if new_lead_id and not lead_id:
                save_lead_id_for_session(DB_PATH, session_id, new_lead_id)
        except Exception as e:
            log.error(f"❌ [BITRIX] handle_web_message error: {e}")

    return reply


# ============================================================
# FASTAPI APP
# ============================================================


def _migrate_db():
    """Миграция БД: добавляет новые колонки если их нет."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for sql in [
        "ALTER TABLE web_sessions ADD COLUMN bitrix_lead_id INTEGER DEFAULT NULL",
        "ALTER TABLE client_state ADD COLUMN manager_active INTEGER DEFAULT 0",
    ]:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass  # уже существует
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🌐 Sofia Web API v2.1 starting...")
    log.info(f"   Sofia path: {SOFIA_PATH}")
    log.info(f"   DB: {DB_PATH}")
    _migrate_db()
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


@app.get("/api/docs/file")
async def docs_file(path: str = ""):
    from pathlib import Path

    BASE_DIR = Path(SOFIA_PATH)
    if not path:
        # Без параметра — список файлов
        files = sorted(
            [
                f.name
                for f in BASE_DIR.iterdir()
                if f.is_file() and f.suffix in {".py", ".md", ".json", ".txt", ".sh"}
            ]
        )
        docs = sorted(
            [f"docs/{f.name}" for f in (BASE_DIR / "docs").iterdir() if f.is_file()]
            if (BASE_DIR / "docs").exists()
            else []
        )
        return {"files": files, "docs": docs}
    resolved = (BASE_DIR / path).resolve()
    if not str(resolved).startswith(str(BASE_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"{path} not found")
    ALLOWED_EXT = {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".js",
        ".html",
        ".css",
        ".toml",
        ".yaml",
        ".yml",
        ".cfg",
        ".ini",
        ".sh",
    }
    if resolved.suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(
            status_code=403, detail=f"Extension {resolved.suffix} not allowed"
        )
    from fastapi.responses import Response

    text = resolved.read_text(encoding="utf-8")
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


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
    save_message(
        chat_id=user_id,
        user_id=user_id,
        user_name="Sofia",
        role="assistant",
        content=greeting,
    )

    # Сохраняем page_url в web_sessions
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE web_sessions SET page_url = ? WHERE session_id = ?",
            (req.page_url, session_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"web_sessions update error: {e}")

    return {"session_id": session_id, "greeting": greeting}


@app.post("/api/session/resume")
async def resume_session(req: ChatRequest):
    """Восстановить сессию по session_id из localStorage"""
    # Проверяем есть ли сессия в БД
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT user_id FROM web_sessions WHERE session_id = ?", (req.session_id,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = row[0]
    _session_to_uid[req.session_id] = user_id  # восстанавливаем кэш

    # Возвращаем историю переписки
    history = get_history(user_id, limit=50)

    # Обновляем last_active
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE web_sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?",
            (req.session_id,),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    log.info(
        f"♻️ Сессия восстановлена: {req.session_id[:8]}... user_id={user_id}, msgs={len(history)}"
    )
    return {"session_id": req.session_id, "history": history}


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
        message=req.message,
        session_id=req.session_id,
    )
    if reply is None:
        # manager_active — София молчит
        return ChatResponse(
            session_id=req.session_id,
            reply="Менеджер подключился к диалогу. Ожидайте ответа.",
            timestamp=datetime.now().isoformat(),
        )
    return ChatResponse(
        session_id=req.session_id, reply=reply, timestamp=datetime.now().isoformat()
    )


@app.get("/api/history/{session_id}")
async def get_session_history(session_id: str, limit: int = 50):
    user_id = get_web_user_id(session_id)
    messages = get_history(user_id, limit=limit)
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": "bot" if m["role"] == "assistant" else "user",
                "content": m["content"],
            }
            for m in messages
        ],
    }


# ============================================================
# BITRIX WEBHOOK
# ============================================================


@app.post("/api/bitrix/webhook")
async def bitrix_webhook(request: Request):
    """Принимает исходящий вебхук от Битрикса.
    При смене статуса лида ставит manager_active=1.
    """
    try:
        content_type = request.headers.get("content-type", "")
        if "json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        log.info(
            f"📩 [BITRIX WEBHOOK] Получен: {json.dumps(data, ensure_ascii=False, default=str)[:500]}"
        )

        # Битрикс шлёт event=ONCRMLEADUPDATE + data[FIELDS][ID]=lead_id
        lead_id = None
        if "data[FIELDS][ID]" in data:
            lead_id = data["data[FIELDS][ID]"]
        elif isinstance(data.get("data"), dict):
            fields = data["data"].get("FIELDS", {})
            lead_id = fields.get("ID")

        if not lead_id:
            log.warning("⚠️ [BITRIX WEBHOOK] lead_id не найден в данных")
            return {"status": "ok", "action": "ignored", "reason": "no lead_id"}

        lead_id = int(lead_id)
        user_id = find_user_id_by_lead(DB_PATH, lead_id)
        if not user_id:
            log.warning(f"⚠️ [BITRIX WEBHOOK] lead #{lead_id} не найден в web_sessions")
            return {"status": "ok", "action": "ignored", "reason": "lead not found"}

        # Проверяем кто сейчас ответственный за лид
        # Если ASSIGNED_BY_ID != Sofia AI (428) → менеджер перехватил
        manager_id = None
        try:
            async with aiohttp.ClientSession() as sess:
                get_url = BITRIX_BASE_URL + "crm.lead.get"
                async with sess.get(get_url, params={"id": lead_id}) as resp:
                    result = await resp.json()
                    lead_data = result.get("result", {})
                    current_assigned = int(lead_data.get("ASSIGNED_BY_ID", 0))
                    if current_assigned and current_assigned != SOFIA_AI_USER_ID:
                        manager_id = current_assigned
        except Exception as e:
            log.warning(f"⚠️ [BITRIX WEBHOOK] не удалось получить лид: {e}")

        if not manager_id:
            # ASSIGNED_BY_ID == Sofia AI → это наше собственное обновление, игнорируем
            log.info(
                f"ℹ️ [BITRIX WEBHOOK] lead #{lead_id} — assigned=Sofia AI, "
                f"игнорируем (наше обновление)"
            )
            return {"status": "ok", "action": "ignored", "reason": "self_update"}

        # Менеджер перехватил лид → ставим его ответственным и manager_active
        set_manager_active(DB_PATH, user_id, active=True)
        await set_lead_assigned(lead_id, manager_id)
        log.info(
            f"✅ [BITRIX WEBHOOK] manager_active=1, ASSIGNED_BY_ID={manager_id} "
            f"для user_id={user_id}, lead #{lead_id}"
        )
        return {
            "status": "ok",
            "action": "manager_activated",
            "user_id": user_id,
            "lead_id": lead_id,
            "manager_id": manager_id,
        }

    except Exception as e:
        log.error(f"❌ [BITRIX WEBHOOK] Error: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================
# VOICE: Retell AI WebSocket
# ============================================================


@app.websocket("/llm-websocket/{call_id}")
async def voice_ws(websocket: WebSocket, call_id: str):
    from voice_api import handle_voice_ws

    await handle_voice_ws(websocket, call_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8081)
