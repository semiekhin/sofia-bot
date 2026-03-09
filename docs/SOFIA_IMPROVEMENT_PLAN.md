# ПЛАН УЛУЧШЕНИЙ SOFIA BOT
## Переход на агентную архитектуру
**Версия:** 1.0  
**Дата:** 10 января 2026  
**Приоритет:** ПЕРВОСТЕПЕННАЯ ЗАДАЧА

---

# СОДЕРЖАНИЕ

1. [Цели и метрики успеха](#1-цели-и-метрики-успеха)
2. [Обзор этапов](#2-обзор-этапов)
3. [Этап 1: WAIT-логика](#3-этап-1-wait-логика)
4. [Этап 2: State Manager](#4-этап-2-state-manager)
5. [Этап 3: Planner Agent](#5-этап-3-planner-agent)
6. [Этап 4: Extractor Agent](#6-этап-4-extractor-agent)
7. [Этап 5: Supervisor Agent](#7-этап-5-supervisor-agent)
8. [Этап 6: RAG Router](#8-этап-6-rag-router)
9. [Этап 7: A/B тестирование моделей](#9-этап-7-ab-тестирование-моделей)
10. [Спецификации и контракты](#10-спецификации-и-контракты)
11. [Риски и митигация](#11-риски-и-митигация)
12. [Чеклист готовности](#12-чеклист-готовности)

---

# 1. ЦЕЛИ И МЕТРИКИ УСПЕХА

## Бизнес-цель

Повысить качество диалогов Sofia Bot для увеличения конверсии в видео-консультации.

## Целевые метрики

| Метрика | Текущее | После этапа 1-2 | После этапа 3-5 | Финальная цель |
|---------|---------|-----------------|-----------------|----------------|
| GOOD rate GPT | 65% | 75% | 85% | 90% |
| GOOD rate Claude | 36% | 55% | 80% | 85% |
| Зацикливания | ~40% BAD | 0% | 0% | 0% |
| Недоквалификация | ~45% BAD | 20% | <5% | <5% |
| Ошибки гендера | ~25% BAD | 25% | <2% | <2% |

## Технические метрики

| Метрика | Текущее | Допустимое | Цель |
|---------|---------|------------|------|
| Latency | ~2 сек | <5 сек | <4 сек |
| Стоимость/сообщение | ~$0.01 | <$0.03 | ~$0.02 |
| Uptime | 99% | >99% | >99.5% |

---

# 2. ОБЗОР ЭТАПОВ

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ROADMAP УЛУЧШЕНИЙ                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Этап 1: WAIT-логика                 ████░░░░░░░░░░░░░░░░  [1-2 часа]
        Убирает: зацикливание                             Эффект: +10% GOOD
        
Этап 2: State Manager               ████████░░░░░░░░░░░░  [3-4 часа]  
        Убирает: потерю контекста                         Эффект: основа для всего
        
Этап 3: Planner Agent               ████████████░░░░░░░░  [4-6 часов]
        Убирает: недоквалификацию, преждевременный созвон Эффект: +15% GOOD
        
Этап 4: Extractor Agent             ████████████████░░░░  [4-6 часов]
        Убирает: ошибки интерпретации                     Эффект: +10% GOOD
        
Этап 5: Supervisor Agent            ██████████████████░░  [3-4 часа]
        Убирает: гендер, ЖК, странные формулировки        Эффект: +5% GOOD
        
Этап 6: RAG Router                  ████████████████████  [2-3 часа]
        Улучшает: релевантность примеров                  Эффект: +5% GOOD
        
Этап 7: A/B тест моделей            ████████████████████  [ongoing]
        Выбор: лучший Generator                           Эффект: оптимизация

ОБЩИЙ СРОК: 2-3 дня активной разработки
ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: GOOD rate 80-90%
```

---

# 3. ЭТАП 1: WAIT-ЛОГИКА

## Цель

Полностью устранить зацикливание после договорённости о созвоне.

## Проблема

После согласования времени созвона бот отвечает на каждое "ок/хорошо/да", повторяя подтверждение 5-7 раз.

## Решение

Детерминированная проверка ПЕРЕД вызовом LLM:

```python
# Добавить в bot_server.py ПЕРЕД вызовом generate_response()

SHORT_CONFIRMATIONS = {
    "ок", "ok", "да", "хорошо", "ладно", "понял", "понятно", 
    "ясно", "угу", "+", "отлично", "супер", "класс", "👍",
    "принял", "принято", "договорились", "ага", "угум"
}

MEETING_MARKERS = [
    "записала", "записал", "созвон", "ссылку пришлю", 
    "видео-встреча", "zoom", "встретимся", "до связи",
    "ждём вас", "жду вас", "буду ждать"
]

def should_skip_response(message: str, last_bot_message: str) -> bool:
    """
    Возвращает True если НЕ нужно отвечать.
    """
    message_lower = message.strip().lower()
    
    # Проверка 1: это короткое подтверждение?
    is_short = message_lower in SHORT_CONFIRMATIONS or len(message_lower) < 15
    
    # Проверка 2: предыдущее сообщение бота содержит маркер договорённости?
    has_meeting_marker = any(marker in last_bot_message.lower() for marker in MEETING_MARKERS)
    
    # Если оба условия — не отвечаем
    if is_short and has_meeting_marker:
        return True
    
    return False


# Использование в handle_message:
async def handle_message(update, context):
    message = update.message.text
    user_id = update.effective_user.id
    
    # Получить последнее сообщение бота
    last_bot_message = get_last_bot_message(user_id)
    
    # WAIT-логика
    if should_skip_response(message, last_bot_message):
        # Сохраняем сообщение в историю, но НЕ отвечаем
        save_message(user_id, "user", message)
        logger.info(f"WAIT: пропускаем ответ на '{message}' после договорённости")
        return  # Выход без ответа
    
    # Обычная обработка
    response = await generate_response(...)
```

## Файлы для изменения

- `/opt/sofia-gpt/bot_server.py`
- `/opt/sofia-claude/bot_server.py`

## Тестирование

```
Сценарий:
1. Бот: "Отлично, записала! Завтра в 18:00. Пришлю ссылку заранее."
2. Клиент: "Ок"
3. Ожидание: бот НЕ отвечает
4. Клиент: "А можно в 19:00?"
5. Ожидание: бот отвечает (это не короткое подтверждение)
```

## Критерии успеха

- [ ] 0 случаев зацикливания на тестовых сценариях
- [ ] Бот отвечает на содержательные сообщения после договорённости
- [ ] Логи показывают срабатывание WAIT

## Оценка времени

**1-2 часа** (включая тестирование)

---

# 4. ЭТАП 2: STATE MANAGER

## Цель

Создать явное хранилище состояния клиента с разделением на подтверждённые факты и упоминания.

## Проблема

Сейчас состояние "размазано" по истории диалога. LLM должен каждый раз заново понимать что уже узнали. Это ненадёжно.

## Решение

### Схема БД

```sql
-- Добавить в sofia_gpt.db / sofia_conversations.db

CREATE TABLE IF NOT EXISTS client_state (
    user_id INTEGER PRIMARY KEY,
    
    -- Подтверждённые факты
    goal TEXT,                  -- 'investment' | 'personal' | null
    goal_confidence TEXT,       -- 'confirmed' | 'mentioned' | null
    
    location TEXT,              -- 'sochi' | 'crimea' | 'altai' | etc | null
    location_confidence TEXT,
    
    budget INTEGER,             -- в рублях | null
    budget_confidence TEXT,
    
    payment_type TEXT,          -- 'full' | 'mortgage' | 'installment' | null
    payment_confidence TEXT,
    
    first_payment INTEGER,      -- в рублях | null
    first_payment_confidence TEXT,
    
    lpr TEXT,                   -- 'alone' | 'with_spouse' | 'with_partner' | null
    lpr_confidence TEXT,
    
    -- Статус диалога
    meeting_agreed BOOLEAN DEFAULT FALSE,
    meeting_datetime TEXT,      -- "завтра 18:00" | null
    materials_sent BOOLEAN DEFAULT FALSE,
    
    -- Временные флаги (сбрасываются после обработки)
    current_question_type TEXT, -- 'price' | 'availability' | 'process' | null
    current_objection TEXT,     -- 'expensive' | 'think' | 'busy' | null
    wants_materials BOOLEAN DEFAULT FALSE,
    
    -- Упоминания (не подтверждённые)
    mentioned_location TEXT,
    mentioned_price INTEGER,
    
    -- Мета
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    qualification_score REAL DEFAULT 0.0  -- 0.0 - 1.0
);

CREATE INDEX idx_client_state_user ON client_state(user_id);
```

### Python модуль state_manager.py

```python
"""
state_manager.py — управление состоянием клиента
"""

import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
from datetime import datetime

ConfidenceLevel = Literal["confirmed", "mentioned", None]

@dataclass
class ClientState:
    user_id: int
    
    # Подтверждённые факты
    goal: Optional[str] = None
    goal_confidence: Optional[ConfidenceLevel] = None
    
    location: Optional[str] = None
    location_confidence: Optional[ConfidenceLevel] = None
    
    budget: Optional[int] = None
    budget_confidence: Optional[ConfidenceLevel] = None
    
    payment_type: Optional[str] = None
    payment_confidence: Optional[ConfidenceLevel] = None
    
    first_payment: Optional[int] = None
    first_payment_confidence: Optional[ConfidenceLevel] = None
    
    lpr: Optional[str] = None
    lpr_confidence: Optional[ConfidenceLevel] = None
    
    # Статус диалога
    meeting_agreed: bool = False
    meeting_datetime: Optional[str] = None
    materials_sent: bool = False
    
    # Временные флаги
    current_question_type: Optional[str] = None
    current_objection: Optional[str] = None
    wants_materials: bool = False
    
    # Упоминания
    mentioned_location: Optional[str] = None
    mentioned_price: Optional[int] = None
    
    # Мета
    updated_at: Optional[datetime] = None
    qualification_score: float = 0.0
    
    def is_qualified(self) -> bool:
        """Проверка полноты квалификации"""
        return all([
            self.goal is not None and self.goal_confidence == "confirmed",
            self.location is not None and self.location_confidence == "confirmed",
            self.budget is not None and self.budget_confidence == "confirmed",
            self.lpr is not None and self.lpr_confidence == "confirmed"
        ])
    
    def get_missing_fields(self) -> list[str]:
        """Возвращает список неподтверждённых полей"""
        missing = []
        if not self.goal or self.goal_confidence != "confirmed":
            missing.append("goal")
        if not self.location or self.location_confidence != "confirmed":
            missing.append("location")
        if not self.budget or self.budget_confidence != "confirmed":
            missing.append("budget")
        if self.payment_type == "mortgage" and not self.first_payment:
            missing.append("first_payment")
        if not self.lpr or self.lpr_confidence != "confirmed":
            missing.append("lpr")
        return missing
    
    def calculate_qualification_score(self) -> float:
        """Расчёт скора квалификации 0.0 - 1.0"""
        fields = ["goal", "location", "budget", "payment_type", "lpr"]
        confirmed = sum(1 for f in fields if getattr(self, f"{f}_confidence", None) == "confirmed")
        mentioned = sum(1 for f in fields if getattr(self, f"{f}_confidence", None) == "mentioned")
        
        score = (confirmed * 1.0 + mentioned * 0.3) / len(fields)
        return min(score, 1.0)


class StateManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Создание таблицы если не существует"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_state (
                user_id INTEGER PRIMARY KEY,
                goal TEXT, goal_confidence TEXT,
                location TEXT, location_confidence TEXT,
                budget INTEGER, budget_confidence TEXT,
                payment_type TEXT, payment_confidence TEXT,
                first_payment INTEGER, first_payment_confidence TEXT,
                lpr TEXT, lpr_confidence TEXT,
                meeting_agreed BOOLEAN DEFAULT FALSE,
                meeting_datetime TEXT,
                materials_sent BOOLEAN DEFAULT FALSE,
                current_question_type TEXT,
                current_objection TEXT,
                wants_materials BOOLEAN DEFAULT FALSE,
                mentioned_location TEXT,
                mentioned_price INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                qualification_score REAL DEFAULT 0.0
            )
        """)
        conn.commit()
        conn.close()
    
    def get_state(self, user_id: int) -> ClientState:
        """Получить состояние клиента"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM client_state WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return ClientState(user_id=user_id)
        
        return ClientState(
            user_id=row["user_id"],
            goal=row["goal"],
            goal_confidence=row["goal_confidence"],
            location=row["location"],
            location_confidence=row["location_confidence"],
            budget=row["budget"],
            budget_confidence=row["budget_confidence"],
            payment_type=row["payment_type"],
            payment_confidence=row["payment_confidence"],
            first_payment=row["first_payment"],
            first_payment_confidence=row["first_payment_confidence"],
            lpr=row["lpr"],
            lpr_confidence=row["lpr_confidence"],
            meeting_agreed=bool(row["meeting_agreed"]),
            meeting_datetime=row["meeting_datetime"],
            materials_sent=bool(row["materials_sent"]),
            current_question_type=row["current_question_type"],
            current_objection=row["current_objection"],
            wants_materials=bool(row["wants_materials"]),
            mentioned_location=row["mentioned_location"],
            mentioned_price=row["mentioned_price"],
            qualification_score=row["qualification_score"] or 0.0
        )
    
    def update_state(self, user_id: int, updates: dict) -> ClientState:
        """Обновить состояние клиента"""
        state = self.get_state(user_id)
        
        # Применяем обновления
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
        
        # Пересчитываем скор
        state.qualification_score = state.calculate_qualification_score()
        state.updated_at = datetime.now()
        
        # Сохраняем
        self._save_state(state)
        return state
    
    def _save_state(self, state: ClientState):
        """Сохранить состояние в БД"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO client_state (
                user_id, goal, goal_confidence, location, location_confidence,
                budget, budget_confidence, payment_type, payment_confidence,
                first_payment, first_payment_confidence, lpr, lpr_confidence,
                meeting_agreed, meeting_datetime, materials_sent,
                current_question_type, current_objection, wants_materials,
                mentioned_location, mentioned_price, updated_at, qualification_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.user_id, state.goal, state.goal_confidence,
            state.location, state.location_confidence,
            state.budget, state.budget_confidence,
            state.payment_type, state.payment_confidence,
            state.first_payment, state.first_payment_confidence,
            state.lpr, state.lpr_confidence,
            state.meeting_agreed, state.meeting_datetime, state.materials_sent,
            state.current_question_type, state.current_objection, state.wants_materials,
            state.mentioned_location, state.mentioned_price,
            state.updated_at, state.qualification_score
        ))
        conn.commit()
        conn.close()
    
    def reset_state(self, user_id: int):
        """Сбросить состояние клиента"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM client_state WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def clear_temporary_flags(self, user_id: int):
        """Очистить временные флаги после обработки сообщения"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE client_state 
            SET current_question_type = NULL,
                current_objection = NULL,
                wants_materials = FALSE
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
```

## Файлы для создания/изменения

- `/opt/sofia-gpt/state_manager.py` (новый)
- `/opt/sofia-claude/state_manager.py` (новый)
- `/opt/sofia-gpt/bot_server.py` (интеграция)
- `/opt/sofia-claude/bot_server.py` (интеграция)

## Критерии успеха

- [ ] Состояние сохраняется между сообщениями
- [ ] Различаются confirmed vs mentioned
- [ ] qualification_score корректно вычисляется
- [ ] Временные флаги сбрасываются после обработки

## Оценка времени

**3-4 часа**

---

# 5. ЭТАП 3: PLANNER AGENT

## Цель

Детерминированная логика выбора следующего действия на основе состояния.

## Проблема

LLM сам решает что делать дальше, опираясь на промпт. Это ненадёжно: перескакивает этапы, предлагает созвон без квалификации.

## Решение

### Модуль planner.py

```python
"""
planner.py — детерминированный планировщик действий
"""

from enum import Enum
from state_manager import ClientState

class Action(Enum):
    # Управление диалогом
    WAIT = "wait"                           # Не отвечать
    GREETING = "greeting"                   # Приветствие
    
    # Квалификация
    ASK_GOAL = "ask_goal"                   # Спросить цель: инвестиция/для себя
    ASK_LOCATION = "ask_location"           # Спросить локацию
    ASK_BUDGET = "ask_budget"               # Спросить бюджет
    ASK_PAYMENT = "ask_payment"             # Спросить способ оплаты
    ASK_FIRST_PAYMENT = "ask_first_payment" # Спросить первый взнос (ипотека)
    ASK_LPR = "ask_lpr"                     # Спросить ЛПР (с кем принимает решение)
    
    # Реактивные действия
    ANSWER_QUESTION = "answer_question"     # Ответить на вопрос клиента
    HANDLE_OBJECTION = "handle_objection"   # Обработать возражение
    CLARIFY_MENTIONED = "clarify_mentioned" # Уточнить упоминание
    
    # Продвижение к цели
    DEFLECT_TO_CALL = "deflect_to_call"     # Перевести на созвон вместо материалов
    PROPOSE_MEETING = "propose_meeting"     # Предложить созвон
    CONFIRM_MEETING = "confirm_meeting"     # Подтвердить время созвона
    SEND_MATERIALS = "send_materials"       # Отправить подборку (если квалифицирован)
    
    # Пост-обработка
    FOLLOW_UP = "follow_up"                 # Напоминание


# Описания действий для промпта Generator
ACTION_DESCRIPTIONS = {
    Action.WAIT: "Не отвечать — клиент просто подтвердил, не нужно реагировать",
    
    Action.ASK_GOAL: "Узнать цель покупки: для инвестиций или для себя/семьи. "
                     "Задай ОДИН вопрос: 'Рассматриваете для себя или как инвестицию?'",
    
    Action.ASK_LOCATION: "Узнать предпочтительную локацию. "
                         "Предложи варианты: побережье (Сочи, Анапа, Крым) или горы (Красная Поляна, Архыз, Алтай). "
                         "Задай ОДИН вопрос.",
    
    Action.ASK_BUDGET: "Узнать бюджет клиента. "
                       "Задай мягко: 'На какой бюджет ориентируетесь?' "
                       "Не спрашивай 'в рублях?' — это странно.",
    
    Action.ASK_PAYMENT: "Узнать способ оплаты: полная оплата, ипотека или рассрочка. "
                        "Задай ОДИН вопрос.",
    
    Action.ASK_FIRST_PAYMENT: "Узнать сумму первого взноса для ипотеки. "
                              "Объясни что обычно от 20%.",
    
    Action.ASK_LPR: "Узнать кто принимает решение: сам или с супругом/партнёром. "
                    "Это важно для планирования созвона.",
    
    Action.ANSWER_QUESTION: "Кратко ответить на вопрос клиента (о ценах, наличии, процессе). "
                            "После ответа задай следующий квалификационный вопрос.",
    
    Action.HANDLE_OBJECTION: "Обработать возражение клиента. "
                             "Проявить понимание, дать аргумент, мягко вернуть к диалогу.",
    
    Action.CLARIFY_MENTIONED: "Уточнить упомянутую информацию. "
                              "Клиент упомянул локацию/цену — уточни, это его выбор или просто вопрос.",
    
    Action.DEFLECT_TO_CALL: "Клиент просит материалы, но не квалифицирован. "
                            "Объясни что на созвоне подберём именно под него, а не 50 вариантов.",
    
    Action.PROPOSE_MEETING: "Предложить видео-созвон. Квалификация завершена. "
                            "Подчеркни выгоду: 15 минут — и покажем подходящие варианты.",
    
    Action.CONFIRM_MEETING: "Подтвердить согласованное время созвона. "
                            "Сказать дату/время и что пришлёшь ссылку. "
                            "НЕ задавать вопросов после.",
    
    Action.SEND_MATERIALS: "Отправить подборку материалов. "
                           "Клиент квалифицирован и настаивает на материалах.",
    
    Action.FOLLOW_UP: "Напомнить о себе, если клиент не отвечал 10+ минут."
}


# Приоритеты возражений
OBJECTION_PRIORITY = {
    "busy": 1,       # "занят" — самый высокий приоритет, уважаем время
    "expensive": 2,  # "дорого" — работаем с возражением
    "think": 3,      # "подумаю" — мягко возвращаем
    "has_realtor": 4 # "есть риелтор" — объясняем нашу ценность
}


SHORT_CONFIRMATIONS = {
    "ок", "ok", "да", "хорошо", "ладно", "понял", "понятно", 
    "ясно", "угу", "+", "отлично", "супер", "класс", "👍",
    "принял", "принято", "договорились", "ага", "угум"
}


def is_short_confirmation(message: str) -> bool:
    """Проверка на короткое подтверждение"""
    msg = message.strip().lower()
    return msg in SHORT_CONFIRMATIONS or len(msg) < 10


def get_next_action(state: ClientState, message: str) -> Action:
    """
    Определяет следующее действие на основе состояния и сообщения.
    
    ПРИОРИТЕТЫ:
    1. WAIT после договорённости
    2. Подтверждение времени созвона
    3. Обработка возражений
    4. Ответ на вопрос клиента
    5. Уточнение упоминаний
    6. Квалификация по порядку
    7. Реакция на запрос материалов
    8. Предложение созвона
    """
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 1: После договорённости — молчим на короткие подтверждения
    # ═══════════════════════════════════════════════════════════════════
    if state.meeting_agreed and is_short_confirmation(message):
        return Action.WAIT
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 2: Подтверждение времени созвона
    # ═══════════════════════════════════════════════════════════════════
    if state.meeting_agreed and state.meeting_datetime:
        # Если клиент что-то написал после договорённости — возможно меняет время
        if not is_short_confirmation(message):
            # Это содержательное сообщение — нужно обработать
            pass  # Переходим к следующим проверкам
        else:
            return Action.CONFIRM_MEETING
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 3: Обработка возражений
    # ═══════════════════════════════════════════════════════════════════
    if state.current_objection:
        return Action.HANDLE_OBJECTION
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 4: Ответ на вопрос клиента
    # ═══════════════════════════════════════════════════════════════════
    if state.current_question_type:
        return Action.ANSWER_QUESTION
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 5: Уточнение упоминаний
    # ═══════════════════════════════════════════════════════════════════
    # Если клиент упомянул локацию/цену, но не подтвердил — уточняем
    if state.mentioned_location and not state.location:
        return Action.CLARIFY_MENTIONED
    if state.mentioned_price and not state.budget:
        return Action.CLARIFY_MENTIONED
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 6: Квалификация по порядку
    # ═══════════════════════════════════════════════════════════════════
    
    # 6.1 Цель покупки
    if not state.goal or state.goal_confidence != "confirmed":
        return Action.ASK_GOAL
    
    # 6.2 Локация
    if not state.location or state.location_confidence != "confirmed":
        return Action.ASK_LOCATION
    
    # 6.3 Бюджет
    if not state.budget or state.budget_confidence != "confirmed":
        return Action.ASK_BUDGET
    
    # 6.4 Способ оплаты
    if not state.payment_type or state.payment_confidence != "confirmed":
        return Action.ASK_PAYMENT
    
    # 6.5 Первый взнос (только для ипотеки)
    if state.payment_type == "mortgage":
        if not state.first_payment or state.first_payment_confidence != "confirmed":
            return Action.ASK_FIRST_PAYMENT
    
    # 6.6 ЛПР (кто принимает решение)
    if not state.lpr or state.lpr_confidence != "confirmed":
        return Action.ASK_LPR
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 7: Реакция на запрос материалов
    # ═══════════════════════════════════════════════════════════════════
    if state.wants_materials:
        if state.is_qualified():
            return Action.SEND_MATERIALS
        else:
            return Action.DEFLECT_TO_CALL
    
    # ═══════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 8: Квалификация завершена — предлагаем созвон
    # ═══════════════════════════════════════════════════════════════════
    return Action.PROPOSE_MEETING


def get_action_context(action: Action, state: ClientState) -> dict:
    """
    Формирует контекст для Generator на основе действия и состояния.
    """
    context = {
        "action": action.value,
        "action_description": ACTION_DESCRIPTIONS[action],
        "known_facts": {},
        "missing_fields": state.get_missing_fields(),
        "qualification_score": state.qualification_score
    }
    
    # Заполняем известные факты
    if state.goal:
        context["known_facts"]["goal"] = {
            "value": state.goal,
            "confidence": state.goal_confidence
        }
    if state.location:
        context["known_facts"]["location"] = {
            "value": state.location,
            "confidence": state.location_confidence
        }
    if state.budget:
        context["known_facts"]["budget"] = {
            "value": state.budget,
            "confidence": state.budget_confidence
        }
    if state.payment_type:
        context["known_facts"]["payment_type"] = {
            "value": state.payment_type,
            "confidence": state.payment_confidence
        }
    if state.lpr:
        context["known_facts"]["lpr"] = {
            "value": state.lpr,
            "confidence": state.lpr_confidence
        }
    
    # Добавляем контекст возражения
    if action == Action.HANDLE_OBJECTION:
        context["objection_type"] = state.current_objection
    
    # Добавляем контекст вопроса
    if action == Action.ANSWER_QUESTION:
        context["question_type"] = state.current_question_type
    
    # Добавляем упоминания для уточнения
    if action == Action.CLARIFY_MENTIONED:
        if state.mentioned_location:
            context["mentioned"] = {"type": "location", "value": state.mentioned_location}
        elif state.mentioned_price:
            context["mentioned"] = {"type": "price", "value": state.mentioned_price}
    
    return context
```

## Интеграция в bot_server.py

```python
from planner import get_next_action, get_action_context, Action

async def handle_message(update, context):
    message = update.message.text
    user_id = update.effective_user.id
    
    # 1. Получаем состояние
    state = state_manager.get_state(user_id)
    
    # 2. Определяем действие
    action = get_next_action(state, message)
    
    # 3. Если WAIT — не отвечаем
    if action == Action.WAIT:
        save_message(user_id, "user", message)
        logger.info(f"WAIT: пропуск ответа для user={user_id}")
        return
    
    # 4. Получаем контекст для генерации
    action_context = get_action_context(action, state)
    
    # 5. Генерируем ответ с учётом action
    response = await generate_response(
        message=message,
        history=get_history(user_id),
        action_context=action_context,  # НОВЫЙ ПАРАМЕТР
        rag_examples=get_rag_examples(action, message)  # RAG по action
    )
    
    # 6. Отправляем
    await send_response(update, response)
```

## Критерии успеха

- [ ] Бот не предлагает созвон без полной квалификации
- [ ] Порядок вопросов соблюдается
- [ ] Возражения обрабатываются приоритетно
- [ ] Вопросы клиента не игнорируются

## Оценка времени

**4-6 часов**

---

# 6. ЭТАП 4: EXTRACTOR AGENT

## Цель

Точное извлечение фактов о клиенте с разделением на подтверждённые, упомянутые и вопросы.

## Проблема

LLM воспринимает любое упоминание как факт: "Говорят в Сочи есть за 10 млн" → location=Сочи, budget=10 млн (НЕПРАВИЛЬНО).

## Решение

### Модуль extractor.py

```python
"""
extractor.py — извлечение структурированных данных из сообщений
"""

import json
import re
from openai import AsyncOpenAI

client = AsyncOpenAI()

EXTRACTOR_SYSTEM_PROMPT = """
Ты — модуль извлечения информации из сообщений клиентов риелторского бота.

ЗАДАЧА: Извлечь информацию из сообщения и вернуть JSON.

═══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНО — РАЗЛИЧАЙ ТРИ ТИПА ИНФОРМАЦИИ:
═══════════════════════════════════════════════════════════════════════════════

1. ПОДТВЕРЖДЁННЫЙ ФАКТ (confidence: "confirmed")
   Клиент ЯВНО говорит о СВОИХ намерениях/параметрах.
   
   Примеры:
   ✓ "Мой бюджет 10 млн" → budget: 10000000, budget_confidence: "confirmed"
   ✓ "Хочу в Сочи" → location: "sochi", location_confidence: "confirmed"
   ✓ "Смотрю для инвестиций" → goal: "investment", goal_confidence: "confirmed"
   ✓ "Буду брать ипотеку" → payment_type: "mortgage", payment_confidence: "confirmed"

2. УПОМИНАНИЕ (confidence: "mentioned" или отдельное поле mentioned_*)
   Клиент упоминает, но НЕ подтверждает как свой выбор.
   
   Примеры:
   ✗ "Говорят в Сочи есть за 10 млн" → mentioned_location: "sochi", mentioned_price: 10000000
   ✗ "Друг купил в Крыму" → mentioned_location: "crimea"
   ✗ "Видел у вас квартиры за 8 млн" → mentioned_price: 8000000
   ✗ "Слышал про Алтай" → mentioned_location: "altai"

3. ВОПРОС (question_type)
   Клиент спрашивает информацию.
   
   Примеры:
   ? "А есть в Сочи до 10?" → question_type: "availability"
   ? "Какие цены в Крыму?" → question_type: "price"
   ? "Как оформляется ипотека?" → question_type: "process"
   ? "Под какой процент ипотека?" → question_type: "mortgage_rate"

═══════════════════════════════════════════════════════════════════════════════
ПРАВИЛА ИЗВЛЕЧЕНИЯ ПОЛЕЙ:
═══════════════════════════════════════════════════════════════════════════════

goal (цель покупки):
• "investment" — инвестиция, вложение, заработать, сдавать, доход
• "personal" — для себя, жить, отдыхать, семья, дети
• null — если неясно

location (локация):
• "sochi" — Сочи, Адлер, Хоста
• "anapa" — Анапа
• "crimea" — Крым, Ялта, Севастополь
• "krasnaya_polyana" — Красная Поляна, Роза Хутор
• "arkhyz" — Архыз
• "altai" — Алтай, Горный Алтай
• "tuapse" — Туапсе
• null — если неясно или несколько без выбора

budget (бюджет в рублях):
• Число в рублях: "10 млн" → 10000000, "15 миллионов" → 15000000
• "до 10" → 10000000 (верхняя граница)
• null — если не указан

payment_type (способ оплаты):
• "full" — полная оплата, 100%, наличные, свои средства
• "mortgage" — ипотека
• "installment" — рассрочка
• null — если не указан

first_payment (первый взнос для ипотеки, в рублях):
• Только если упоминается сумма первого взноса
• null — если не указан

lpr (кто принимает решение):
• "alone" — сам, один
• "with_spouse" — с женой/мужем/супругом
• "with_partner" — с партнёром, другом, родителями
• null — если не указан

═══════════════════════════════════════════════════════════════════════════════
ДОПОЛНИТЕЛЬНЫЕ ПОЛЯ:
═══════════════════════════════════════════════════════════════════════════════

question_type (тип вопроса клиента):
• "price" — спрашивает о ценах
• "availability" — спрашивает о наличии
• "process" — спрашивает о процессе покупки
• "mortgage_rate" — спрашивает о ставках ипотеки
• "location_info" — спрашивает о локации
• null — не задаёт вопрос

objection (возражение):
• "expensive" — дорого, не потяну, много
• "think" — подумаю, посоветуюсь, не сейчас решу
• "busy" — занят, некогда, перезвоните позже
• "has_realtor" — есть риелтор, уже работаю с кем-то
• null — нет возражения

wants_materials (просит материалы):
• true — скиньте, отправьте, покажите варианты, подборку
• false — не просит

meeting_agreed (согласился на созвон):
• true — да, давайте, можно, согласен на созвон
• false — нет явного согласия

meeting_datetime (время созвона):
• Строка: "завтра 18:00", "в понедельник вечером", "сегодня в 15:00"
• null — если не указано

sentiment (настроение):
• "positive" — заинтересован, рад, благодарит
• "neutral" — нейтрально
• "negative" — недоволен, раздражён
• "frustrated" — сильно раздражён, грубит

═══════════════════════════════════════════════════════════════════════════════
ФОРМАТ ОТВЕТА — ТОЛЬКО JSON:
═══════════════════════════════════════════════════════════════════════════════

{
  "goal": "investment" | "personal" | null,
  "goal_confidence": "confirmed" | "mentioned" | null,
  
  "location": "sochi" | "anapa" | "crimea" | "krasnaya_polyana" | "arkhyz" | "altai" | "tuapse" | null,
  "location_confidence": "confirmed" | "mentioned" | null,
  
  "budget": 10000000 | null,
  "budget_confidence": "confirmed" | "mentioned" | null,
  
  "payment_type": "full" | "mortgage" | "installment" | null,
  "payment_confidence": "confirmed" | "mentioned" | null,
  
  "first_payment": 3000000 | null,
  "first_payment_confidence": "confirmed" | "mentioned" | null,
  
  "lpr": "alone" | "with_spouse" | "with_partner" | null,
  "lpr_confidence": "confirmed" | "mentioned" | null,
  
  "question_type": "price" | "availability" | "process" | "mortgage_rate" | "location_info" | null,
  "objection": "expensive" | "think" | "busy" | "has_realtor" | null,
  "wants_materials": true | false,
  
  "meeting_agreed": true | false,
  "meeting_datetime": "завтра 18:00" | null,
  
  "mentioned_location": "sochi" | null,
  "mentioned_price": 10000000 | null,
  
  "sentiment": "positive" | "neutral" | "negative" | "frustrated"
}

ВЕРНИ ТОЛЬКО JSON, БЕЗ КОММЕНТАРИЕВ И ПОЯСНЕНИЙ.
"""


async def extract(message: str, history: list[dict] = None) -> dict:
    """
    Извлекает структурированные данные из сообщения клиента.
    
    Args:
        message: текст сообщения клиента
        history: последние N сообщений диалога (опционально)
    
    Returns:
        dict с извлечёнными данными
    """
    
    # Формируем контекст
    context_parts = []
    if history:
        context_parts.append("ИСТОРИЯ ДИАЛОГА (последние сообщения):")
        for msg in history[-6:]:  # Последние 6 сообщений
            role = "Клиент" if msg["role"] == "user" else "Бот"
            context_parts.append(f"{role}: {msg['content']}")
        context_parts.append("")
    
    context_parts.append(f"НОВОЕ СООБЩЕНИЕ КЛИЕНТА:\n{message}")
    
    user_content = "\n".join(context_parts)
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=500
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        # Fallback при ошибке
        return {
            "goal": None, "goal_confidence": None,
            "location": None, "location_confidence": None,
            "budget": None, "budget_confidence": None,
            "payment_type": None, "payment_confidence": None,
            "first_payment": None, "first_payment_confidence": None,
            "lpr": None, "lpr_confidence": None,
            "question_type": None,
            "objection": None,
            "wants_materials": False,
            "meeting_agreed": False,
            "meeting_datetime": None,
            "mentioned_location": None,
            "mentioned_price": None,
            "sentiment": "neutral",
            "_error": str(e)
        }


def merge_extraction_to_state(current_state: dict, extraction: dict) -> dict:
    """
    Мержит результат extraction в текущее состояние.
    
    Правила:
    - confirmed перезаписывает mentioned
    - mentioned НЕ перезаписывает confirmed
    - Новые значения добавляются
    """
    
    updated = current_state.copy()
    
    # Поля с confidence
    confidence_fields = ["goal", "location", "budget", "payment_type", "first_payment", "lpr"]
    
    for field in confidence_fields:
        new_value = extraction.get(field)
        new_confidence = extraction.get(f"{field}_confidence")
        
        if new_value is None:
            continue
        
        current_confidence = updated.get(f"{field}_confidence")
        
        # confirmed всегда перезаписывает
        if new_confidence == "confirmed":
            updated[field] = new_value
            updated[f"{field}_confidence"] = "confirmed"
        
        # mentioned только если нет confirmed
        elif new_confidence == "mentioned" and current_confidence != "confirmed":
            updated[field] = new_value
            updated[f"{field}_confidence"] = "mentioned"
    
    # Простые поля (перезаписываем если не None)
    simple_fields = [
        "question_type", "objection", "wants_materials",
        "meeting_agreed", "meeting_datetime",
        "mentioned_location", "mentioned_price", "sentiment"
    ]
    
    for field in simple_fields:
        new_value = extraction.get(field)
        if new_value is not None:
            updated[field] = new_value
    
    return updated


# === ТЕСТЫ ===

EXTRACTION_TESTS = [
    {
        "message": "Хочу в Сочи до 10 млн для инвестиций",
        "expected": {
            "goal": "investment", "goal_confidence": "confirmed",
            "location": "sochi", "location_confidence": "confirmed",
            "budget": 10000000, "budget_confidence": "confirmed"
        }
    },
    {
        "message": "Говорят в Сочи есть квартиры за 10 млн",
        "expected": {
            "goal": None,
            "location": None,  # НЕ confirmed!
            "budget": None,    # НЕ confirmed!
            "mentioned_location": "sochi",
            "mentioned_price": 10000000,
            "question_type": "availability"  # или "price"
        }
    },
    {
        "message": "Дорого как-то",
        "expected": {
            "objection": "expensive",
            "sentiment": "negative"
        }
    },
    {
        "message": "Давайте завтра в 18:00",
        "expected": {
            "meeting_agreed": True,
            "meeting_datetime": "завтра в 18:00"
        }
    },
    {
        "message": "Скиньте что есть",
        "expected": {
            "wants_materials": True
        }
    }
]
```

## Интеграция в bot_server.py

```python
from extractor import extract, merge_extraction_to_state

async def handle_message(update, context):
    message = update.message.text
    user_id = update.effective_user.id
    
    # 1. Получаем текущее состояние
    state = state_manager.get_state(user_id)
    history = get_history(user_id)
    
    # 2. Извлекаем данные из нового сообщения
    extraction = await extract(message, history)
    
    # 3. Мержим в состояние
    state_updates = merge_extraction_to_state(state.__dict__, extraction)
    state = state_manager.update_state(user_id, state_updates)
    
    # 4. Определяем действие
    action = get_next_action(state, message)
    
    # ... остальная логика
```

## Критерии успеха

- [ ] "Говорят в Сочи" → mentioned_location, НЕ location
- [ ] "Хочу в Сочи" → location: confirmed
- [ ] "Дорого" → objection: expensive
- [ ] Все тесты проходят

## Оценка времени

**4-6 часов**

---

# 7. ЭТАП 5: SUPERVISOR AGENT

## Цель

Проверка ответа перед отправкой. Отклонение/перегенерация при нарушениях.

## Проблема

Ошибки гендера, упоминание ЖК, странные формулировки проходят напрямую к клиенту.

## Решение

### Модуль supervisor.py

```python
"""
supervisor.py — проверка качества ответов перед отправкой
"""

import json
import re
from openai import AsyncOpenAI
from state_manager import ClientState

client = AsyncOpenAI()

# Паттерны для быстрой проверки (без LLM)
GENDER_ERRORS = [
    r'\bпонял\b', r'\bзаписал\b', r'\bузнал\b', r'\bвзял\b', 
    r'\bполучил\b', r'\bувидел\b', r'\bпонял\b', r'\bсделал\b'
]

SPECIFIC_JK_PATTERNS = [
    r'ЖК\s+[«"]?\w+', r'комплекс\s+[«"]?\w+',
    r'Актёр', r'Гэлакси', r'Сочи Парк', r'Манхэттен',
    r'Имеретинский', r'Бархатные сезоны'
]

EXACT_PRICE_PATTERNS = [
    r'\d{1,3}[\s,.]?\d{3}[\s,.]?\d{3}\s*(руб|₽|р\.)',  # 8 450 000 руб
    r'\d+[.,]\d+\s*млн',  # 8.45 млн (точная цена)
]


def quick_check(response: str) -> list[str]:
    """
    Быстрая проверка без LLM.
    Возвращает список найденных проблем.
    """
    issues = []
    response_lower = response.lower()
    
    # Проверка гендера
    for pattern in GENDER_ERRORS:
        if re.search(pattern, response_lower):
            issues.append("gender_error")
            break
    
    # Проверка конкретных ЖК
    for pattern in SPECIFIC_JK_PATTERNS:
        if re.search(pattern, response, re.IGNORECASE):
            issues.append("specific_jk")
            break
    
    # Проверка точных цен
    for pattern in EXACT_PRICE_PATTERNS:
        if re.search(pattern, response):
            issues.append("exact_price")
            break
    
    # Проверка длины
    sentences = re.split(r'[.!?]+', response)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) > 4:
        issues.append("too_long")
    
    # Проверка количества вопросов
    questions = response.count('?')
    if questions > 1:
        issues.append("multiple_questions")
    
    return issues


SUPERVISOR_SYSTEM_PROMPT = """
Ты — модуль контроля качества ответов бота Sofia (женщина-менеджер по недвижимости).

ЗАДАЧА: Проверить ответ по правилам и вернуть JSON с результатом.

═══════════════════════════════════════════════════════════════════════════════
ПРАВИЛА ПРОВЕРКИ:
═══════════════════════════════════════════════════════════════════════════════

1. ГЕНДЕР (gender_error)
   Sofia — женщина. 
   ✗ ЗАПРЕЩЕНО: "понял", "записал", "узнал", "взял", "получил", "увидел"
   ✓ ПРАВИЛЬНО: "поняла", "записала", "узнала", "увидела"

2. КОНКРЕТНЫЕ ЖК (specific_jk)
   ✗ ЗАПРЕЩЕНО: называть названия комплексов
   ✗ "ЖК Актёр Гэлакси", "Сочи Парк", "Имеретинский"
   ✓ ПРАВИЛЬНО: "у нас есть варианты", "несколько подходящих объектов"

3. ТОЧНЫЕ ЦЕНЫ (exact_price)
   ✗ ЗАПРЕЩЕНО: точные суммы "8,450,000 руб", "12.5 млн рублей"
   ✓ ПРАВИЛЬНО: "от 8 млн", "в районе 12-15 млн", "от 10 млн"

4. ДЛИНА (too_long)
   ✗ ЗАПРЕЩЕНО: больше 3-4 предложений
   ✓ ПРАВИЛЬНО: 1-3 предложения, коротко и по делу

5. КОЛИЧЕСТВО ВОПРОСОВ (multiple_questions)
   ✗ ЗАПРЕЩЕНО: больше 1 вопроса в ответе
   ✓ ПРАВИЛЬНО: максимум 1 вопрос в конце

6. ПОВТОРЫ (repetition)
   ✗ ЗАПРЕЩЕНО: повторять вопрос который уже задавали
   ✗ ЗАПРЕЩЕНО: повторять информацию которую уже говорили

7. ПОСЛЕ ДОГОВОРЁННОСТИ (post_agreement)
   Если meeting_agreed = true:
   ✗ ЗАПРЕЩЕНО: задавать новые вопросы
   ✓ ПРАВИЛЬНО: только подтверждение или ответ на вопрос клиента

8. СТРАННЫЕ ФОРМУЛИРОВКИ (awkward)
   ✗ "В рублях?" — странно
   ✗ "100% оплата" — непонятно клиенту
   ✗ "Капитализация" — непонятно клиенту
   ✓ "Полная оплата", "рост стоимости"

═══════════════════════════════════════════════════════════════════════════════
ФОРМАТ ОТВЕТА:
═══════════════════════════════════════════════════════════════════════════════

{
  "approved": true | false,
  "issues": ["gender_error", "specific_jk", ...],
  "details": "Описание проблемы",
  "suggestion": "Как исправить (если не approved)"
}

ВЕРНИ ТОЛЬКО JSON.
"""


async def supervise(
    response: str, 
    history: list[dict], 
    state: ClientState,
    action: str
) -> dict:
    """
    Проверяет ответ перед отправкой.
    
    Returns:
        {
            "approved": bool,
            "issues": list[str],
            "details": str,
            "suggestion": str
        }
    """
    
    # Шаг 1: быстрая проверка без LLM
    quick_issues = quick_check(response)
    
    # Если есть критические ошибки — сразу отклоняем
    if "gender_error" in quick_issues or "specific_jk" in quick_issues:
        return {
            "approved": False,
            "issues": quick_issues,
            "details": "Найдены критические ошибки при быстрой проверке",
            "suggestion": _get_suggestion(quick_issues, response)
        }
    
    # Шаг 2: LLM проверка (более глубокая)
    context = f"""
СОСТОЯНИЕ КЛИЕНТА:
- meeting_agreed: {state.meeting_agreed}
- Квалификация: {state.qualification_score:.0%}

ДЕЙСТВИЕ БОТА: {action}

ИСТОРИЯ (последние 4 сообщения):
{_format_history(history[-4:])}

ОТВЕТ ДЛЯ ПРОВЕРКИ:
{response}
"""
    
    try:
        result = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=300
        )
        
        check_result = json.loads(result.choices[0].message.content)
        
        # Объединяем с quick_issues
        all_issues = list(set(quick_issues + check_result.get("issues", [])))
        
        return {
            "approved": len(all_issues) == 0,
            "issues": all_issues,
            "details": check_result.get("details", ""),
            "suggestion": check_result.get("suggestion", "")
        }
        
    except Exception as e:
        # При ошибке LLM — используем только quick_check
        return {
            "approved": len(quick_issues) == 0,
            "issues": quick_issues,
            "details": f"LLM error: {e}",
            "suggestion": _get_suggestion(quick_issues, response) if quick_issues else ""
        }


def _format_history(history: list[dict]) -> str:
    """Форматирует историю для промпта"""
    lines = []
    for msg in history:
        role = "Клиент" if msg["role"] == "user" else "Бот"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def _get_suggestion(issues: list[str], response: str) -> str:
    """Генерирует предложение по исправлению"""
    suggestions = []
    
    if "gender_error" in issues:
        suggestions.append("Замени 'понял/записал' на 'поняла/записала'")
    if "specific_jk" in issues:
        suggestions.append("Убери название ЖК, используй 'у нас есть варианты'")
    if "exact_price" in issues:
        suggestions.append("Замени точную цену на 'от X млн'")
    if "too_long" in issues:
        suggestions.append("Сократи до 2-3 предложений")
    if "multiple_questions" in issues:
        suggestions.append("Оставь только один вопрос")
    
    return "; ".join(suggestions)


async def fix_response(response: str, issues: list[str], suggestion: str) -> str:
    """
    Пытается исправить ответ автоматически.
    Для простых случаев — regex замена.
    Для сложных — перегенерация.
    """
    fixed = response
    
    # Простые замены гендера
    if "gender_error" in issues:
        replacements = [
            (r'\bпонял\b', 'поняла'),
            (r'\bзаписал\b', 'записала'),
            (r'\bузнал\b', 'узнала'),
            (r'\bвзял\b', 'взяла'),
            (r'\bполучил\b', 'получила'),
            (r'\bувидел\b', 'увидела'),
            (r'\bсделал\b', 'сделала'),
        ]
        for pattern, replacement in replacements:
            fixed = re.sub(pattern, replacement, fixed, flags=re.IGNORECASE)
    
    return fixed


# === ИСПОЛЬЗОВАНИЕ ===

async def generate_and_validate(
    generator_func,
    message: str,
    history: list[dict],
    state: ClientState,
    action: str,
    max_attempts: int = 2
) -> str:
    """
    Генерирует ответ и валидирует его.
    При ошибках — перегенерирует с фидбеком.
    """
    
    for attempt in range(max_attempts):
        # Генерируем ответ
        response = await generator_func(message, history, state, action)
        
        # Проверяем
        check = await supervise(response, history, state, action)
        
        if check["approved"]:
            return response
        
        # Пытаемся исправить автоматически
        fixed = await fix_response(response, check["issues"], check["suggestion"])
        
        # Проверяем исправленный
        recheck = await supervise(fixed, history, state, action)
        if recheck["approved"]:
            return fixed
        
        # Если не помогло — логируем и на последней попытке возвращаем
        logger.warning(f"Supervisor rejected (attempt {attempt+1}): {check['issues']}")
        
        if attempt == max_attempts - 1:
            # Возвращаем исправленный вариант как есть
            return fixed
    
    return response
```

## Интеграция

```python
from supervisor import generate_and_validate

async def handle_message(update, context):
    # ... извлечение, состояние, планировщик ...
    
    # Генерация + валидация
    response = await generate_and_validate(
        generator_func=generate_response,
        message=message,
        history=history,
        state=state,
        action=action.value
    )
    
    await send_response(update, response)
```

## Критерии успеха

- [ ] 0 ошибок гендера в ответах
- [ ] 0 упоминаний конкретных ЖК
- [ ] Все ответы ≤ 4 предложений
- [ ] ≤ 1 вопрос в ответе

## Оценка времени

**3-4 часа**

---

# 8. ЭТАП 6: RAG ROUTER

## Цель

Подбирать RAG-примеры по action, а не по stage.

## Проблема

Сейчас RAG фильтрует по stage (QUALIFICATION), но внутри stage много разных действий. Примеры "предложи созвон" попадают когда нужно "спроси бюджет".

## Решение

### Маппинг Action → RAG Query

```python
"""
rag_router.py — маршрутизация RAG запросов по действиям
"""

from planner import Action

# Маппинг action → параметры RAG поиска
ACTION_RAG_CONFIG = {
    Action.ASK_GOAL: {
        "query_template": "спросить цель покупки инвестиция для себя",
        "stage_filter": ["GREETING", "QUALIFICATION"],
        "keywords": ["инвестиц", "для себя", "цель", "зачем"],
        "top_k": 3
    },
    
    Action.ASK_LOCATION: {
        "query_template": "спросить локацию регион где хотите",
        "stage_filter": ["QUALIFICATION"],
        "keywords": ["локация", "регион", "где", "море", "горы"],
        "top_k": 3
    },
    
    Action.ASK_BUDGET: {
        "query_template": "спросить бюджет сколько планируете на какую сумму",
        "stage_filter": ["QUALIFICATION"],
        "keywords": ["бюджет", "сумма", "сколько", "стоимость"],
        "top_k": 3
    },
    
    Action.ASK_PAYMENT: {
        "query_template": "спросить способ оплаты ипотека рассрочка",
        "stage_filter": ["QUALIFICATION"],
        "keywords": ["оплата", "ипотека", "рассрочка", "наличные"],
        "top_k": 3
    },
    
    Action.ASK_FIRST_PAYMENT: {
        "query_template": "первый взнос ипотека начальная сумма",
        "stage_filter": ["QUALIFICATION"],
        "keywords": ["взнос", "первоначальный", "20%"],
        "top_k": 2
    },
    
    Action.ASK_LPR: {
        "query_template": "кто принимает решение с супругой вместе",
        "stage_filter": ["QUALIFICATION"],
        "keywords": ["решение", "супруг", "вместе", "один"],
        "top_k": 2
    },
    
    Action.ANSWER_QUESTION: {
        "query_template": "{question_context}",  # Динамически
        "stage_filter": ["PRESENTATION", "QUALIFICATION"],
        "keywords": [],
        "top_k": 3
    },
    
    Action.HANDLE_OBJECTION: {
        "query_template": "{objection_type} возражение работа",
        "stage_filter": ["OBJECTION"],
        "keywords_map": {
            "expensive": ["дорого", "цена", "бюджет"],
            "think": ["подумаю", "время", "не сейчас"],
            "busy": ["занят", "перезвон", "позже"],
            "has_realtor": ["риелтор", "агент", "работаю"]
        },
        "top_k": 3
    },
    
    Action.PROPOSE_MEETING: {
        "query_template": "предложить созвон назначить встречу видео",
        "stage_filter": ["MEETING", "CLOSING"],
        "keywords": ["созвон", "встреча", "видео", "zoom", "покажу"],
        "top_k": 3
    },
    
    Action.CONFIRM_MEETING: {
        "query_template": "подтвердить время созвона записала",
        "stage_filter": ["CLOSING"],
        "keywords": ["записала", "жду", "ссылка", "подтверждаю"],
        "top_k": 2
    },
    
    Action.DEFLECT_TO_CALL: {
        "query_template": "вместо материалов предложить созвон подборка",
        "stage_filter": ["MEETING", "PRESENTATION"],
        "keywords": ["покажу", "созвон", "не 50 вариантов", "именно под вас"],
        "top_k": 3
    },
    
    Action.SEND_MATERIALS: {
        "query_template": "отправить подборку материалы pdf",
        "stage_filter": ["PRESENTATION", "CLOSING"],
        "keywords": ["отправлю", "подборка", "pdf", "варианты"],
        "top_k": 2
    }
}


def get_rag_query(action: Action, context: dict = None) -> dict:
    """
    Формирует параметры запроса к RAG на основе action.
    
    Args:
        action: текущее действие
        context: дополнительный контекст (question_type, objection_type, etc)
    
    Returns:
        {
            "query": str,
            "filters": dict,
            "top_k": int
        }
    """
    
    config = ACTION_RAG_CONFIG.get(action, {
        "query_template": "",
        "stage_filter": [],
        "keywords": [],
        "top_k": 3
    })
    
    query = config["query_template"]
    
    # Динамические подстановки
    if context:
        if action == Action.ANSWER_QUESTION and context.get("question_type"):
            question_contexts = {
                "price": "цены стоимость сколько стоит",
                "availability": "есть в наличии варианты",
                "process": "процесс покупки оформление",
                "mortgage_rate": "ипотека процент ставка",
                "location_info": "локация район инфраструктура"
            }
            query = question_contexts.get(context["question_type"], "ответ на вопрос")
        
        if action == Action.HANDLE_OBJECTION and context.get("objection_type"):
            objection_queries = {
                "expensive": "дорого работа с возражением цена",
                "think": "подумаю работа с возражением",
                "busy": "занят перезвонить позже",
                "has_realtor": "есть риелтор почему мы"
            }
            query = objection_queries.get(context["objection_type"], "работа с возражением")
    
    return {
        "query": query,
        "filters": {
            "stage": {"$in": config["stage_filter"]} if config["stage_filter"] else None,
            "quality": {"$in": ["excellent", "good"]}
        },
        "top_k": config["top_k"]
    }


# Интеграция с существующим rag_module.py

def get_rag_examples_for_action(
    action: Action, 
    message: str, 
    context: dict = None,
    rag_module = None
) -> list[dict]:
    """
    Получает RAG примеры для конкретного action.
    """
    
    rag_params = get_rag_query(action, context)
    
    # Комбинируем query action с сообщением клиента
    combined_query = f"{rag_params['query']} {message}"
    
    # Вызываем существующий RAG
    examples = rag_module.search(
        query=combined_query,
        filters=rag_params["filters"],
        top_k=rag_params["top_k"]
    )
    
    return examples
```

## Критерии успеха

- [ ] ASK_BUDGET → примеры про бюджет, не про созвон
- [ ] HANDLE_OBJECTION:expensive → примеры работы с "дорого"
- [ ] Релевантность примеров выше

## Оценка времени

**2-3 часа**

---

# 9. ЭТАП 7: A/B ТЕСТИРОВАНИЕ МОДЕЛЕЙ

## Цель

Выбрать лучший Generator после внедрения агентной архитектуры.

## Гипотеза

После Planner + Supervisor разница между GPT-5.2 и Claude Sonnet 4.5 уменьшится, т.к. логика теперь в коде, а модель только генерирует текст.

## Методология

### Настройка A/B теста

```python
# В bot_server.py

import random

AB_TEST_CONFIG = {
    "enabled": True,
    "variants": {
        "gpt-5.2": 0.5,       # 50% трафика
        "claude-sonnet": 0.5  # 50% трафика
    }
}

def get_model_for_user(user_id: int) -> str:
    """Детерминированный выбор модели для пользователя"""
    # Один пользователь = одна модель на весь диалог
    random.seed(user_id)
    r = random.random()
    
    cumulative = 0
    for model, weight in AB_TEST_CONFIG["variants"].items():
        cumulative += weight
        if r < cumulative:
            return model
    
    return "gpt-5.2"  # fallback
```

### Метрики для сравнения

| Метрика | Как измерять |
|---------|--------------|
| GOOD rate | Оценки тестировщиков |
| Latency | Время от сообщения до ответа |
| Token usage | Логирование API calls |
| Конверсия в созвон | meeting_agreed = True |
| Полнота квалификации | qualification_score |

### Логирование

```python
def log_ab_metrics(user_id, model, metrics):
    """Сохраняем метрики для анализа"""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO ab_test_log (
            user_id, model, timestamp,
            response_time_ms, tokens_used,
            good_rating, meeting_agreed, qual_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, model, datetime.now(),
        metrics["response_time_ms"],
        metrics["tokens_used"],
        metrics.get("good_rating"),
        metrics.get("meeting_agreed"),
        metrics.get("qual_score")
    ))
    conn.commit()
```

### Анализ результатов

```sql
-- Сравнение моделей
SELECT 
    model,
    COUNT(*) as total_messages,
    AVG(response_time_ms) as avg_latency,
    SUM(tokens_used) as total_tokens,
    AVG(CASE WHEN good_rating = 1 THEN 1.0 ELSE 0.0 END) as good_rate,
    AVG(qual_score) as avg_qualification
FROM ab_test_log
GROUP BY model;
```

## Критерии для выбора модели

1. GOOD rate ≥ 80%
2. Latency < 4 сек
3. Стоимость в пределах бюджета
4. Конверсия в созвон выше

## Оценка времени

**Ongoing** — 1-2 недели сбора данных, 2-3 часа на настройку и анализ.

---

# 10. СПЕЦИФИКАЦИИ И КОНТРАКТЫ

## JSON Schema для State

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "user_id": {"type": "integer"},
    
    "goal": {"enum": ["investment", "personal", null]},
    "goal_confidence": {"enum": ["confirmed", "mentioned", null]},
    
    "location": {"enum": ["sochi", "anapa", "crimea", "krasnaya_polyana", "arkhyz", "altai", "tuapse", null]},
    "location_confidence": {"enum": ["confirmed", "mentioned", null]},
    
    "budget": {"type": ["integer", "null"]},
    "budget_confidence": {"enum": ["confirmed", "mentioned", null]},
    
    "payment_type": {"enum": ["full", "mortgage", "installment", null]},
    "payment_confidence": {"enum": ["confirmed", "mentioned", null]},
    
    "first_payment": {"type": ["integer", "null"]},
    "first_payment_confidence": {"enum": ["confirmed", "mentioned", null]},
    
    "lpr": {"enum": ["alone", "with_spouse", "with_partner", null]},
    "lpr_confidence": {"enum": ["confirmed", "mentioned", null]},
    
    "meeting_agreed": {"type": "boolean"},
    "meeting_datetime": {"type": ["string", "null"]},
    "materials_sent": {"type": "boolean"},
    
    "current_question_type": {"enum": ["price", "availability", "process", "mortgage_rate", "location_info", null]},
    "current_objection": {"enum": ["expensive", "think", "busy", "has_realtor", null]},
    "wants_materials": {"type": "boolean"},
    
    "mentioned_location": {"type": ["string", "null"]},
    "mentioned_price": {"type": ["integer", "null"]},
    
    "qualification_score": {"type": "number", "minimum": 0, "maximum": 1}
  },
  "required": ["user_id"]
}
```

## Таблица: Проблема → Planner → Supervisor

| Проблема | Planner правило | Supervisor проверка |
|----------|-----------------|---------------------|
| Зацикливание | WAIT на короткие подтверждения после meeting_agreed | — |
| Недоквалификация | ASK_* пока все поля не confirmed | — |
| Преждевременный созвон | PROPOSE_MEETING только если is_qualified() | — |
| Ошибки интерпретации | — (решает Extractor) | — |
| Гендер | — | gender_error → отклонить |
| Конкретные ЖК | — | specific_jk → отклонить |
| Точные цены | — | exact_price → отклонить |
| Длина | — | too_long → отклонить |
| Много вопросов | — | multiple_questions → отклонить |
| Повторы | Проверка history в Planner | repetition → отклонить |

---

# 11. РИСКИ И МИТИГАЦИЯ

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Увеличение latency >5 сек | Средняя | Высокое | Параллельные вызовы, кэширование |
| Ошибки Extractor | Средняя | Среднее | Fallback на текущую логику |
| Рост стоимости API | Высокая | Среднее | Мониторинг, бюджет, gpt-4o-mini |
| Сложность отладки | Средняя | Среднее | Подробное логирование каждого агента |
| Regression в качестве | Низкая | Высокое | A/B тест, откат если хуже |

---

# 12. ЧЕКЛИСТ ГОТОВНОСТИ

## Перед началом

- [ ] Бэкап текущего кода
- [ ] Бэкап баз данных
- [ ] Тестовый бот для разработки

## Этап 1: WAIT

- [ ] Код добавлен
- [ ] Тесты пройдены
- [ ] Деплой на прод
- [ ] Мониторинг 24ч

## Этап 2: State Manager

- [ ] Таблица создана
- [ ] Модуль написан
- [ ] Интеграция с bot_server
- [ ] Тесты

## Этап 3: Planner

- [ ] Все Actions определены
- [ ] Приоритеты настроены
- [ ] Интеграция
- [ ] Тесты на сценариях

## Этап 4: Extractor

- [ ] Промпт написан
- [ ] Тесты на примерах
- [ ] Merge логика работает
- [ ] Интеграция

## Этап 5: Supervisor

- [ ] Quick check работает
- [ ] LLM проверка работает
- [ ] Авто-исправление гендера
- [ ] Интеграция

## Этап 6: RAG Router

- [ ] Маппинг Action → Query
- [ ] Интеграция с rag_module
- [ ] Проверка релевантности

## Этап 7: A/B тест

- [ ] Логирование настроено
- [ ] Распределение трафика
- [ ] Дашборд метрик
- [ ] Анализ через неделю

---

**ИТОГО:**
- Время: 2-3 дня активной разработки
- Ожидаемый результат: GOOD rate 80-90%
- Стоимость: +100% к API costs (приемлемо для B2C недвижимости)

---

*Документ подготовлен как руководство к действию*
*Версия 1.0 | 10 января 2026*
