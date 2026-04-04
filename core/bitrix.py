"""
core/bitrix.py — Битрикс CRM интеграция для Sofia-GPT.
Единый модуль для всех транспортов.

Функции:
- create_or_update_lead() — создать или обновить лид
- build_lead_comments() — собрать COMMENTS для лида
- extract_phone_from_history() — найти телефон в истории
- extract_telegram_from_history() — найти @username
- is_manager_active() / set_manager_active() — перехват менеджером
- get_lead_id_by_session() / save_lead_id_for_session() — привязка лида к сессии
"""

import logging
import os
import re
import sqlite3

import aiohttp

log = logging.getLogger("sofia.bitrix")

# === Константы ===
BITRIX_BASE_URL = os.getenv(
    "BITRIX_BASE_URL",
    "https://oazisestate.bitrix24.ru/rest/426/z61dwivdmdy9dk4f/",
)
if not BITRIX_BASE_URL.endswith("/"):
    BITRIX_BASE_URL += "/"

BITRIX_CREATE_URL = BITRIX_BASE_URL + "crm.lead.add"
BITRIX_UPDATE_URL = BITRIX_BASE_URL + "crm.lead.update"
BITRIX_LIST_URL = BITRIX_BASE_URL + "crm.lead.list"
BITRIX_SOURCE_ID = os.getenv("BITRIX_SOURCE_ID", "504")
BITRIX_ASSIGNED_ID = int(os.getenv("BITRIX_ASSIGNED_ID", "426"))
BITRIX_ATLANTIS_SOURCE_ID = "397"  # Источник Тильда/Атлантис
SOFIA_AI_USER_ID = 428  # Сотрудник "Sofia AI" — ответственный на время квалификации
BITRIX_BP_ASSIGNED_ID = int(
    os.getenv("BITRIX_BP_ASSIGNED_ID", "24932")
)  # Ответственный перед запуском БП


# ============================================================
# Извлечение контактных данных из истории
# ============================================================

_PHONE_RE = re.compile(
    r"(?:\+?7|8)[\s\-\(]*(\d{3})[\s\-\)]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})"
)
_DIGITS_RE = re.compile(r"(?<!\d)(\d{10,11})(?!\d)")
_TG_RE = re.compile(r"@([A-Za-z0-9_]{5,32})")


def extract_phone_from_history(history: list) -> str | None:
    """Ищет номер телефона в сообщениях клиента (с конца)."""
    for msg in reversed(history):
        if msg["role"] == "user":
            match = _PHONE_RE.search(msg["content"])
            if match:
                return (
                    "7"
                    + match.group(1)
                    + match.group(2)
                    + match.group(3)
                    + match.group(4)
                )
    # Fallback: 10-11 цифр подряд
    for msg in reversed(history):
        if msg["role"] == "user":
            clean = msg["content"].replace(" ", "").replace("-", "")
            match = _DIGITS_RE.search(clean)
            if match:
                d = match.group(1)
                if len(d) == 10:
                    return "7" + d
                if len(d) == 11 and d[0] in ("7", "8"):
                    return "7" + d[1:]
    return None


def extract_telegram_from_history(history: list) -> str | None:
    """Ищет @username в сообщениях клиента."""
    for msg in reversed(history):
        if msg["role"] == "user":
            match = _TG_RE.search(msg["content"])
            if match:
                return "@" + match.group(1)
    return None


# ============================================================
# Форматирование данных для Битрикс
# ============================================================

_GOAL_MAP = {
    "investment": "Инвестиции",
    "personal": "Для себя",
    "combined": "Комбинированно",
}
_PAYMENT_MAP = {
    "full": "Полная оплата",
    "mortgage": "Ипотека",
    "installment": "Рассрочка",
}


def _format_dialog(history: list) -> str:
    """Форматирует полный диалог для COMMENTS."""
    return "\n".join(
        f"{'София' if m['role'] == 'assistant' else 'Клиент'}: {m['content']}"
        for m in history
    )


def build_lead_comments(
    state,
    history: list,
    is_final: bool = False,
    channel: str = "web",
    telegram_username: str = None,
) -> tuple:
    """
    Собирает COMMENTS для Битрикс лида.
    Возвращает (comments_text, phone, telegram).
    """
    phone = extract_phone_from_history(history)
    telegram = extract_telegram_from_history(history) or telegram_username

    goal = _GOAL_MAP.get(getattr(state, "goal", None) or "", "Не указана")
    budget = getattr(state, "budget", None)
    budget_str = f"{budget / 1_000_000:.1f} млн ₽" if budget else "Не указан"
    payment = _PAYMENT_MAP.get(getattr(state, "payment_type", None) or "", "Не указан")
    finish_type = getattr(state, "finish_type", None)

    phone_str = phone or "Не указан"
    tg_str = telegram or "Не указан"
    if is_final and finish_type == "meeting":
        status = "Квалифицирован, созвон согласован"
    elif is_final and finish_type == "no_response":
        status = "Нет ответа"
    elif is_final and finish_type == "no_response_after_reminder":
        status = "Нет ответа после напоминания"
    elif is_final:
        status = "ЗАВЕРШЁН"
    else:
        status = "В ПРОЦЕССЕ"

    channel_map = {
        "web": "виджет на сайте",
        "telegram": "Telegram бот",
        "radist": "Radist мессенджер",
    }
    channel_label = channel_map.get(channel, channel)

    chat_text = _format_dialog(history)

    comments = f"""Лид от AI-бота София ({channel_label})
Статус диалога: {status}
Телефон: {phone_str}
Telegram: {tg_str}
Цель: {goal}
Бюджет: {budget_str}
Оплата: {payment}"""

    if is_final and finish_type:
        comments += f"\nТип завершения: {'созвон' if 'meeting' in str(finish_type) else 'подборка/диалог'}"

    if is_final:
        summary = build_qualification_summary(state, finish_type)
        comments += f"\n\n{summary}"

    comments += f"\n\n--- Полный диалог ({len(history)} сообщений) ---\n{chat_text}"

    return comments, phone, telegram


# ============================================================
# API: поиск существующих лидов
# ============================================================


async def find_lead_by_phone(phone: str) -> int | None:
    """Поиск существующего лида по телефону через crm.lead.list.
    Возвращает lead_id или None.
    """
    if not phone:
        return None
    # Битрикс хранит телефон в разных форматах — ищем по последним 10 цифрам
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 10:
        search_phone = digits[-10:]
    else:
        search_phone = digits
    params = {
        "filter[PHONE]": search_phone,
        "filter[STATUS_ID]": "NEW",
        "order[DATE_CREATE]": "DESC",
        "select[]": ["ID", "TITLE", "DATE_CREATE"],
        "start": 0,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BITRIX_LIST_URL, params=params) as resp:
                result = await resp.json()
                leads = result.get("result", [])
                if leads:
                    lead_id = int(leads[0]["ID"])
                    log.info(
                        f"🔍 [BITRIX] Найден лид #{lead_id} по телефону "
                        f"{search_phone} ({leads[0].get('TITLE', '?')})"
                    )
                    return lead_id
                return None
    except Exception as e:
        log.error(f"❌ [BITRIX] find_lead_by_phone error: {e}")
        return None


async def find_recent_atlantis_lead() -> dict | None:
    """Найти последний лид с SOURCE_ID=397 (Тильда/Атлантис).
    Возвращает dict с ID и ASSIGNED_BY_ID или None.
    """
    params = {
        "filter[SOURCE_ID]": BITRIX_ATLANTIS_SOURCE_ID,
        "order[DATE_CREATE]": "DESC",
        "select[]": ["ID", "TITLE", "DATE_CREATE", "ASSIGNED_BY_ID"],
        "start": 0,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BITRIX_LIST_URL, params=params) as resp:
                result = await resp.json()
                leads = result.get("result", [])
                if leads:
                    lead = leads[0]
                    lead_id = int(lead["ID"])
                    assigned = lead.get("ASSIGNED_BY_ID")
                    log.info(
                        f"🔗 [BITRIX] Найден лид Тильды #{lead_id} "
                        f"({lead.get('TITLE', '?')}), "
                        f"assigned={assigned}"
                    )
                    return {
                        "id": lead_id,
                        "assigned_by_id": int(assigned) if assigned else None,
                    }
                log.info("🔗 [BITRIX] Лидов Тильды не найдено")
                return None
    except Exception as e:
        log.error(f"❌ [BITRIX] find_recent_atlantis_lead error: {e}")
        return None


async def restore_assigned(db_path: str, lead_id: int) -> bool:
    """Вернуть ответственного за лид после завершения диалога.
    Порядок: original из lead_assigned → fallback BITRIX_ASSIGNED_ID (426).
    """
    original = get_original_assigned(db_path, lead_id)
    restore_to = original or BITRIX_ASSIGNED_ID
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BITRIX_UPDATE_URL,
                json={"id": lead_id, "fields": {"ASSIGNED_BY_ID": restore_to}},
            ) as resp:
                result = await resp.json()
                if result.get("result"):
                    log.info(
                        f"🔄 [BITRIX] Лид #{lead_id}: ASSIGNED_BY_ID "
                        f"восстановлен → {restore_to} "
                        f"({'original' if original else 'fallback'})"
                    )
                    return True
                log.warning(f"⚠️ [BITRIX] restore_assigned ошибка: {result}")
                return False
    except Exception as e:
        log.error(f"❌ [BITRIX] restore_assigned error: {e}")
        return False


async def set_lead_assigned(lead_id: int, assigned_id: int) -> bool:
    """Поставить конкретного ответственного на лид."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BITRIX_UPDATE_URL,
                json={"id": lead_id, "fields": {"ASSIGNED_BY_ID": assigned_id}},
            ) as resp:
                result = await resp.json()
                if result.get("result"):
                    log.info(
                        f"✅ [BITRIX] Лид #{lead_id}: ASSIGNED_BY_ID → {assigned_id}"
                    )
                    return True
                log.warning(f"⚠️ [BITRIX] set_lead_assigned ошибка: {result}")
                return False
    except Exception as e:
        log.error(f"❌ [BITRIX] set_lead_assigned error: {e}")
        return False


# ============================================================
# API: создание и обновление лидов
# ============================================================


async def create_lead(
    name: str,
    comments: str,
    phone: str = None,
    source_id: str = None,
    assigned_id: int = None,
) -> int | None:
    """Создать новый лид. Возвращает lead_id или None.
    По умолчанию ответственный = Sofia AI (428) на время квалификации.
    """
    fields = {
        "TITLE": f"AI-бот: {name}",
        "NAME": name,
        "COMMENTS": comments,
        "SOURCE_ID": source_id or BITRIX_SOURCE_ID,
        "ASSIGNED_BY_ID": assigned_id or SOFIA_AI_USER_ID,
    }
    if phone:
        fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "MOBILE"}]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(BITRIX_CREATE_URL, json={"fields": fields}) as resp:
                result = await resp.json()
                lead_id = result.get("result")
                if lead_id:
                    log.info(f"✅ [BITRIX] Лид создан #{lead_id}")
                    return int(lead_id)
                else:
                    log.warning(f"⚠️ [BITRIX] Ответ без ID: {result}")
                    return None
    except Exception as e:
        log.error(f"❌ [BITRIX] Create error: {e}")
        return None


async def update_lead(
    lead_id: int,
    comments: str,
    phone: str = None,
    name: str = None,
    is_final: bool = False,
    assigned_id: int = None,
) -> bool:
    """Обновить существующий лид. Возвращает True при успехе."""
    fields = {"COMMENTS": comments}
    if assigned_id:
        fields["ASSIGNED_BY_ID"] = assigned_id
    if is_final:
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "MOBILE"}]
        if name:
            fields["NAME"] = name

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BITRIX_UPDATE_URL, json={"id": lead_id, "fields": fields}
            ) as resp:
                result = await resp.json()
                if result.get("result"):
                    log.info(f"✅ [BITRIX] Лид #{lead_id} обновлён, final={is_final}")
                    return True
                else:
                    log.warning(f"⚠️ [BITRIX] Update ошибка: {result}")
                    return False
    except Exception as e:
        log.error(f"❌ [BITRIX] Update error: {e}")
        return False


async def create_or_update_lead(
    lead_id: int | None,
    user_name: str,
    state,
    history: list,
    is_final: bool = False,
    channel: str = "web",
    telegram_username: str = None,
) -> int | None:
    """
    Если lead_id есть → update, иначе → create.
    Возвращает lead_id (существующий или новый).
    """
    comments, phone, telegram = build_lead_comments(
        state, history, is_final, channel, telegram_username=telegram_username
    )
    name = user_name or "Клиент"
    if name.startswith("web_"):
        name = "Клиент с сайта"

    if lead_id:
        await update_lead(lead_id, comments, phone=phone, name=name, is_final=is_final)
        return lead_id

    # Дедупликация: ищем существующий лид по телефону перед созданием
    if phone:
        existing_id = await find_lead_by_phone(phone)
        if existing_id:
            log.info(
                f"🔗 [BITRIX] Дедупликация: найден лид #{existing_id} "
                f"по телефону, обновляем вместо создания нового"
            )
            await update_lead(
                existing_id, comments, phone=phone, name=name, is_final=is_final
            )
            return existing_id

    return await create_lead(name, comments, phone=phone)


# ============================================================
# DB helpers: привязка lead_id к web-сессии
# ============================================================


def get_lead_id_by_session(db_path: str, session_id: str) -> int | None:
    """Получить bitrix_lead_id по session_id (web_sessions)."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "SELECT bitrix_lead_id FROM web_sessions WHERE session_id = ?", (session_id,)
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def save_lead_id_for_session(db_path: str, session_id: str, lead_id: int):
    """Сохранить bitrix_lead_id в web_sessions."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE web_sessions SET bitrix_lead_id = ? WHERE session_id = ?",
        (lead_id, session_id),
    )
    conn.commit()
    conn.close()


def get_session_id_by_user_id(db_path: str, user_id: int) -> str | None:
    """Найти session_id по user_id (web_sessions)."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT session_id FROM web_sessions WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def find_user_id_by_lead(db_path: str, lead_id: int) -> int | None:
    """Найти user_id по bitrix_lead_id (web_sessions)."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT user_id FROM web_sessions WHERE bitrix_lead_id = ?", (lead_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


# ============================================================
# Manager active: перехват диалога менеджером
# ============================================================


def is_manager_active(db_path: str, user_id: int) -> bool:
    """Проверить флаг manager_active для клиента."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT manager_active FROM client_state WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])


def set_manager_active(db_path: str, user_id: int, active: bool = True):
    """Установить флаг manager_active."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE client_state SET manager_active = ? WHERE user_id = ?",
        (1 if active else 0, user_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# Lead assigned: сохранение оригинального ответственного
# ============================================================


def _migrate_lead_assigned(db_path: str):
    """Создаёт таблицу lead_assigned если её нет."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lead_assigned (
            lead_id INTEGER PRIMARY KEY,
            original_assigned_by_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_original_assigned(db_path: str, lead_id: int, assigned_id: int):
    """Сохранить оригинального ответственного для лида."""
    _migrate_lead_assigned(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO lead_assigned (lead_id, original_assigned_by_id)
           VALUES (?, ?)
           ON CONFLICT(lead_id) DO UPDATE SET original_assigned_by_id = ?""",
        (lead_id, assigned_id, assigned_id),
    )
    conn.commit()
    conn.close()
    log.info(
        f"💾 [BITRIX] Сохранён original_assigned={assigned_id} для лида #{lead_id}"
    )


def get_original_assigned(db_path: str, lead_id: int) -> int | None:
    """Получить оригинального ответственного для лида."""
    _migrate_lead_assigned(db_path)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "SELECT original_assigned_by_id FROM lead_assigned WHERE lead_id = ?",
        (lead_id,),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


# ============================================================
# Запуск бизнес-процесса раздачи лидов
# ============================================================

_GOAL_LABEL = {
    "investment": "Инвестиции",
    "personal": "Для себя",
    "combined": "Комбинированно",
}
_PAYMENT_LABEL = {
    "full": "Полная оплата",
    "mortgage": "Ипотека",
    "installment": "Рассрочка",
}


def build_qualification_summary(state, finish_type: str | None = None) -> str:
    """Формирует блок итога квалификации для COMMENTS."""
    ft = finish_type or getattr(state, "finish_type", None)
    lines = ["[София AI — итог квалификации]"]
    if ft:
        lines.append(f"Результат: {ft}")
    goal = getattr(state, "goal", None)
    if goal:
        lines.append(f"Цель: {_GOAL_LABEL.get(goal, goal)}")
    location = getattr(state, "location", None)
    if location:
        lines.append(f"Локация: {location}")
    budget = getattr(state, "budget", None)
    if budget:
        lines.append(f"Бюджет: {budget / 1_000_000:.1f} млн ₽")
    payment = getattr(state, "payment_type", None)
    if payment:
        lines.append(f"Оплата: {_PAYMENT_LABEL.get(payment, payment)}")
    if getattr(state, "meeting_agreed", False):
        lines.append("Созвон: согласился")
    return "\n".join(lines)


async def start_distribution_bp(lead_id: int) -> bool:
    """
    Запускает БП раздачи лидов (проверка дублей → раздача/контроль качества).
    Вызывать ПОСЛЕ restore_assigned().
    Возвращает True если БП запущен, False при ошибке.
    """
    template_id = os.getenv("BITRIX_BP_TEMPLATE_ID")
    if not template_id:
        log.warning(
            f"[BITRIX] BP template ID not configured, skipping for lead {lead_id}"
        )
        return False

    try:
        url = f"{BITRIX_BASE_URL}bizproc.workflow.start"
        payload = {
            "TEMPLATE_ID": int(template_id),
            "DOCUMENT_ID": ["crm", "CCrmDocumentLead", f"LEAD_{lead_id}"],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                result = await resp.json()

        if result.get("result"):
            log.info(
                f"[BITRIX] BP {template_id} started for lead {lead_id}, "
                f"workflow_id={result['result']}"
            )
            return True
        else:
            error = result.get("error_description", result.get("error", "unknown"))
            log.warning(f"[BITRIX] BP start failed for lead {lead_id}: {error}")
            return False

    except Exception as e:
        log.warning(f"[BITRIX] BP start exception for lead {lead_id}: {e}")
        return False


async def finalize_lead(db_path: str, lead_id: int) -> None:
    """Завершение работы с лидом: сменить ответственного на BP-assigned + запустить БП."""
    log.info(f"[BITRIX] Финализация лида #{lead_id}")
    await set_lead_assigned(lead_id, BITRIX_BP_ASSIGNED_ID)
    await start_distribution_bp(lead_id)
