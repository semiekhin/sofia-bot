"""
planner.py — детерминированный планировщик действий
====================================================
Определяет следующее действие на основе состояния клиента.
Логика вынесена из промпта в код = 100% предсказуемость.
"""

from enum import Enum
from typing import Optional
from state_manager import ClientState


class Action(Enum):
    """Возможные действия бота"""
    
    # Управление диалогом
    WAIT = "wait"                           # Не отвечать
    GREETING = "greeting"                   # Приветствие
    
    # Квалификация (в порядке приоритета)
    ASK_GOAL = "ask_goal"                   # Спросить цель: инвестиция/для себя
    ASK_LOCATION = "ask_location"           # Спросить локацию
    ASK_BUDGET = "ask_budget"               # Спросить бюджет
    ASK_PAYMENT = "ask_payment"             # Спросить способ оплаты
    ASK_FIRST_PAYMENT = "ask_first_payment" # Спросить первый взнос (ипотека)
    ASK_LPR = "ask_lpr"                     # Спросить ЛПР (с кем решает)
    
    # Помощь с выбором (после unknown/refusal)
    HELP_GOAL = "help_goal"                 # Помочь определить цель
    HELP_LOCATION = "help_location"         # Помочь с локацией
    HELP_BUDGET = "help_budget"             # Помочь с бюджетом
    HELP_PAYMENT = "help_payment"           # Помочь со способом оплаты
    HELP_LPR = "help_lpr"                   # Помочь с ЛПР
    
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
    
    # NEW v2.0: Дополнительные вопросы
    ASK_STRATEGY = "ask_strategy"           # Стратегия инвестирования (rental/growth)
    ASK_USAGE = "ask_usage"                 # Использование (permanent/vacation)
    ASK_FAMILY = "ask_family"               # Семья, дети
    
    # NEW v2.0: Два предложения созвона
    PROPOSE_MEETING_1 = "propose_meeting_1" # Первое предложение (после базовой квалификации)
    PROPOSE_MEETING_2 = "propose_meeting_2" # Второе предложение (после полной квалификации)
    
    # NEW v2.0: Завершение
    FINISH_WITH_MATERIALS = "finish_with_materials"  # Завершение с подборкой (после 2 отказов)
    
    # NEW v2.2: Управление давлением
    EASE_PRESSURE = "ease_pressure"                 # Снизить давление (friction > 0.7)


# Описания действий для промпта Generator
ACTION_DESCRIPTIONS = {
    Action.WAIT: "Не отвечать — клиент просто подтвердил, не нужно реагировать.",
    
    Action.ASK_GOAL: """Узнать цель покупки: для инвестиций или для себя/семьи.
Задай ОДИН вопрос: 'Рассматриваете для себя или как инвестицию?'
Не объясняй зачем спрашиваешь.""",
    
    Action.ASK_LOCATION: """Узнать предпочтительную локацию.
Предложи варианты: побережье (Сочи, Анапа, Крым) или горы (Красная Поляна, Архыз, Алтай).
Задай ОДИН вопрос.""",
    
    Action.ASK_BUDGET: """Узнать бюджет клиента.
Задай мягко: 'На какой бюджет ориентируетесь?'
НЕ спрашивай 'в рублях?' — это странно.""",
    
    Action.ASK_PAYMENT: """Узнать способ оплаты: полная оплата, ипотека или рассрочка.
Задай ОДИН вопрос.""",
    
    Action.ASK_FIRST_PAYMENT: """Узнать сумму первого взноса для ипотеки.
Объясни что обычно от 20%.""",
    
    Action.ASK_LPR: """Узнать кто принимает решение: сам или с супругом/партнёром.
Это важно для планирования созвона.""",
    
    Action.ANSWER_QUESTION: """Кратко ответить на вопрос клиента (о ценах, наличии, процессе).
После ответа задай следующий квалификационный вопрос.""",
    
    Action.HANDLE_OBJECTION: """Обработать возражение клиента.
Проявить понимание, дать аргумент, мягко вернуть к диалогу.""",
    
    Action.CLARIFY_MENTIONED: """Уточнить упомянутую информацию.
Клиент упомянул локацию/цену — уточни, это его выбор или просто вопрос.""",
    
    Action.DEFLECT_TO_CALL: """Клиент просит материалы, но не квалифицирован.
Объясни что на созвоне подберём именно под него, а не 50 вариантов.""",
    
    Action.PROPOSE_MEETING: """Предложить видео-созвон. Квалификация завершена.
Подчеркни выгоду: 15 минут — и покажем подходящие варианты.
Спроси когда удобно.""",
    
    Action.CONFIRM_MEETING: """Подтвердить согласованное время созвона.
Сказать дату/время и что пришлёшь ссылку.
НЕ задавать вопросов после.""",
    
    Action.SEND_MATERIALS: """Отправить подборку материалов.
Клиент квалифицирован и настаивает на материалах.""",
    
    Action.FOLLOW_UP: """Напомнить о себе, если клиент не отвечал 10+ минут.""",
    
    # HELP_* actions (упрощённый выбор после "не знаю")
    Action.HELP_GOAL: """Клиент не знает цель. Объясни зачем важно и упрости:
'Просто под инвестиции и для себя подбираем разные объекты. Что ближе: доход с аренды или для своего отдыха?'
Если снова 'не знаю' — прими и иди дальше.""",
    
    Action.HELP_LOCATION: """Клиент не знает локацию. Предложи простой выбор:
'Что ближе по духу — море или горы?'""",
    
    Action.HELP_BUDGET: """Клиент не знает бюджет. Объясни зачем важно и дай диапазоны:
'В разных сегментах разные объекты — до 10 млн студии, 10-15 апартаменты, 15+ премиум. Что комфортнее?'
Если снова 'не знаю' — прими и иди дальше.""",
    
    Action.HELP_PAYMENT: """Клиент не определился со способом оплаты. Объясни важность и упрости выбор:
'Поняла. От способа оплаты сильно зависит выбор — есть варианты только за наличные, есть что под ипотеку не проходит. Как у вас: есть сумма на полную оплату, или смотрим с финансированием?'
Если снова 'не знаю' — НЕ переспрашивай, прими и иди дальше.""",
    
    Action.HELP_LPR: """Клиент не ответил про ЛПР. Объясни зачем и спроси мягко:
'Чтобы на созвон сразу всех позвать. Решение за вами одним, или с кем-то согласовать нужно?'
Если уходит от ответа — не настаивай, иди дальше.""",

    # NEW v2.0: Дополнительные вопросы
    Action.ASK_STRATEGY: """Спросить стратегию инвестирования.
'Что важнее: доход с аренды или рост стоимости при перепродаже?'
Если 'не знаю' или 'и то и другое' — принять, идти дальше.""",
    
    Action.ASK_USAGE: """Спросить как будет использоваться.
'Для постоянного проживания или как дача для отдыха?'
Если 'не знаю' — принять, идти дальше.""",
    
    Action.ASK_FAMILY: """Спросить про семью.
'С семьёй планируете? Дети есть?'
Если 'не знаю' или не хочет отвечать — принять, идти дальше.""",
    
    # NEW v2.0: Два предложения созвона
    Action.PROPOSE_MEETING_1: """Первое предложение созвона (после базовой квалификации).
Короткая формулировка, акцент на экономии времени.
'Давайте созвонимся на 15 минут — покажу 2-3 варианта под ваш запрос. Когда удобно?'
Использовать примеры из RAG.""",
    
    Action.PROPOSE_MEETING_2: """Второе предложение созвона (после первого отказа, полная квалификация).
Развёрнутая формулировка из работы с возражениями.
Показать ценность: экспертиза, закрытые лоты, экономия времени.
'За 15 минут покажу варианты, которых нет в открытом доступе. Когда удобнее?'
Использовать примеры из RAG.""",
    
    # NEW v2.0: Завершение
    Action.FINISH_WITH_MATERIALS: """Завершение диалога с обещанием подборки.
Клиент дважды отказался от созвона — не настаиваем.
'Хорошо, вижу вашу занятость) В ближайшее время отправлю варианты которые подобрала.
Если будут вопросы — пишите!'
После этого НЕ задавать вопросов, замолчать.""",

    # NEW v2.2: Управление давлением
    Action.EASE_PRESSURE: """Клиент напряжён (friction > 0.7). Снизить давление.
Не задавай новых вопросов. Прояви понимание, покажи что не давишь.
'Понимаю, много вопросов сразу) Давайте без спешки — расскажите что для вас сейчас важнее всего?'
Или просто ответь на то, что волнует клиента, без перехода к следующему слоту."""
}


# Короткие подтверждения для WAIT-логики
SHORT_CONFIRMATIONS = {
    "ок", "ok", "да", "хорошо", "ладно", "понял", "понятно", 
    "ясно", "угу", "+", "отлично", "супер", "класс", "👍",
    "принял", "принято", "договорились", "ага", "угум", "ок!",
    "хор", "да!", "ок.", "good", "yes", "ясненько", "понятненько"
}


# Порядок слотов для квалификации
SLOT_ORDER = ["goal", "location", "budget", "payment_type", "first_payment", "lpr"]

# Маппинг слот → ASK action
SLOT_TO_ASK = {
    "goal": Action.ASK_GOAL,
    "location": Action.ASK_LOCATION,
    "budget": Action.ASK_BUDGET,
    "payment_type": Action.ASK_PAYMENT,
    "first_payment": Action.ASK_FIRST_PAYMENT,
    "lpr": Action.ASK_LPR,
    "strategy": Action.ASK_STRATEGY,
    "usage": Action.ASK_USAGE,
    "family": Action.ASK_FAMILY,
}

# Маппинг слот → HELP action
SLOT_TO_HELP = {
    "goal": Action.HELP_GOAL,
    "location": Action.HELP_LOCATION,
    "budget": Action.HELP_BUDGET,
    "payment_type": Action.HELP_PAYMENT,
    "lpr": Action.HELP_LPR,
}


def is_short_confirmation(message: str) -> bool:
    """Проверка на короткое подтверждение"""
    msg = message.strip().lower().rstrip('!.,')
    return msg in SHORT_CONFIRMATIONS or len(msg) < 8


def get_next_action(state: ClientState, message: str, extraction: dict = None) -> Action:
    """
    Определяет следующее действие на основе состояния и сообщения.
    
    v2.0 ЛОГИКА:
    - Две ветки: INVESTMENT и PERSONAL
    - Два предложения созвона: после базовой и полной квалификации  
    - Счётчик отказов: при 2 отказах → FINISH_WITH_MATERIALS
    """
    
    extraction = extraction or {}
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 0: Диалог завершён — молчим
    # ═══════════════════════════════════════════════════════════════════════
    if getattr(state, 'dialog_finished', False):
        return Action.WAIT
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 1: Клиент согласился на созвон — подтверждаем
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("meeting_agreed") and extraction.get("meeting_datetime"):
        return Action.CONFIRM_MEETING
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 1.5 (NEW v2.2): Высокий friction — снижаем давление
    # ═══════════════════════════════════════════════════════════════════════
    signals = extraction.get("signals", {})
    friction = signals.get("friction", 0.3)
    call_readiness = signals.get("call_readiness", 0.5)
    
    if friction > 0.7:
        return Action.EASE_PRESSURE
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 2: Счётчик отказов (wants_materials или no_call)
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("wants_materials") or extraction.get("objection") == "no_call":
        # Увеличиваем счётчик в state (будет сохранён в bot_server.py)
        state.materials_request_count = getattr(state, 'materials_request_count', 0) + 1
        
        if state.materials_request_count >= 2:
            return Action.FINISH_WITH_MATERIALS
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 3: Обработка возражений (кроме no_call после первого отказа)
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("objection"):
        obj = extraction.get("objection")
        # no_call обрабатываем через счётчик выше, не через HANDLE_OBJECTION
        if obj != "no_call":
            return Action.HANDLE_OBJECTION
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 4: Ответ на вопрос клиента
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("question_type"):
        return Action.ANSWER_QUESTION
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 5: Уточнение упоминаний
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("mentioned_location") and not state.location:
        return Action.CLARIFY_MENTIONED
    if extraction.get("mentioned_price") and not state.budget:
        return Action.CLARIFY_MENTIONED
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 6: Определяем ветку диалога
    # ═══════════════════════════════════════════════════════════════════════
    if not getattr(state, 'branch', None):
        if state.goal == "investment":
            state.branch = "investment"
        elif state.goal == "personal":
            state.branch = "personal"
        else:
            # Цель не определена — спрашиваем
            return _ask_slot_with_limit(state, "goal")
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 7: Квалификация по ветке
    # ═══════════════════════════════════════════════════════════════════════
    if state.branch == "investment":
        return _qualify_investment(state, extraction)
    else:
        return _qualify_personal(state, extraction)


def _ask_slot_with_limit(state: ClientState, slot: str) -> Action:
    """Спрашивает слот с учётом лимита попыток"""
    # Инициализируем slot_attempts если нет
    if not hasattr(state, 'slot_attempts') or not state.slot_attempts:
        state.slot_attempts = {}
    
    if slot not in state.slot_attempts:
        state.slot_attempts[slot] = {"ask": 0, "help": 0}
    
    attempts = state.slot_attempts[slot]
    
    if attempts["ask"] == 0:
        return SLOT_TO_ASK[slot]
    elif attempts["ask"] >= 1 and attempts["help"] == 0 and slot in SLOT_TO_HELP:
        return SLOT_TO_HELP[slot]
    else:
        return None  # Исчерпали попытки


def _qualify_investment(state: ClientState, extraction: dict) -> Action:
    """
    Квалификация для ИНВЕСТОРА.
    Порядок: goal → strategy → budget → MEETING_1 → payment → location → lpr → MEETING_2
    """
    
    # 1. strategy (необязательно)
    if not getattr(state, 'strategy', None):
        action = _ask_slot_with_limit(state, "strategy")
        if action:
            return action
    
    # 2. budget (обязательно)
    if not state.budget or state.budget_confidence != "confirmed":
        action = _ask_slot_with_limit(state, "budget")
        if action:
            return action
    
    # ★ PROPOSE_MEETING_1 (после базовой квалификации: goal + budget)
    # NEW v2.2: Проверяем готовность к созвону
    friction = getattr(state, 'friction', 0.3)
    call_readiness = getattr(state, 'call_readiness', 0.5)
    
    if getattr(state, 'call_proposal_count', 0) == 0:
        # Если клиент не готов (friction >= 0.5 или call_readiness < 0.4) — продолжаем квалификацию
        if friction >= 0.5 or call_readiness < 0.4:
            pass  # Пропускаем MEETING_1, идём дальше по квалификации
        else:
            state.call_proposal_count = 1
            return Action.PROPOSE_MEETING_1
    
    # 3. payment_type (необязательно)
    if not state.payment_type:
        action = _ask_slot_with_limit(state, "payment_type")
        if action:
            return action
    
    # 4. location (обязательно, но "море/горы" достаточно)
    if not state.location or state.location_confidence != "confirmed":
        action = _ask_slot_with_limit(state, "location")
        if action:
            return action
    
    # 5. lpr (необязательно)
    if not state.lpr:
        action = _ask_slot_with_limit(state, "lpr")
        if action:
            return action
    
    # ★ PROPOSE_MEETING_2 (после полной квалификации)
    if getattr(state, 'call_proposal_count', 0) == 1:
        state.call_proposal_count = 2
        return Action.PROPOSE_MEETING_2
    
    # После второго отказа → FINISH_WITH_MATERIALS
    return Action.FINISH_WITH_MATERIALS


def _qualify_personal(state: ClientState, extraction: dict) -> Action:
    """
    Квалификация для 'ДЛЯ СЕБЯ'.
    Порядок: goal → usage → location → budget → MEETING_1 → family → payment → lpr → MEETING_2
    """
    
    # 1. usage (необязательно)
    if not getattr(state, 'usage', None):
        action = _ask_slot_with_limit(state, "usage")
        if action:
            return action
    
    # 2. location (обязательно)
    if not state.location or state.location_confidence != "confirmed":
        action = _ask_slot_with_limit(state, "location")
        if action:
            return action
    
    # 3. budget (обязательно)
    if not state.budget or state.budget_confidence != "confirmed":
        action = _ask_slot_with_limit(state, "budget")
        if action:
            return action
    
    # ★ PROPOSE_MEETING_1 (после базовой квалификации: goal + location + budget)
    # NEW v2.2: Проверяем готовность к созвону
    friction = getattr(state, 'friction', 0.3)
    call_readiness = getattr(state, 'call_readiness', 0.5)
    
    if getattr(state, 'call_proposal_count', 0) == 0:
        # Если клиент не готов (friction >= 0.5 или call_readiness < 0.4) — продолжаем квалификацию
        if friction >= 0.5 or call_readiness < 0.4:
            pass  # Пропускаем MEETING_1, идём дальше по квалификации
        else:
            state.call_proposal_count = 1
            return Action.PROPOSE_MEETING_1
    
    # 4. family (необязательно)
    if not getattr(state, 'family', None):
        action = _ask_slot_with_limit(state, "family")
        if action:
            return action
    
    # 5. payment_type (необязательно)
    if not state.payment_type:
        action = _ask_slot_with_limit(state, "payment_type")
        if action:
            return action
    
    # 6. lpr (необязательно)
    if not state.lpr:
        action = _ask_slot_with_limit(state, "lpr")
        if action:
            return action
    
    # ★ PROPOSE_MEETING_2 (после полной квалификации)
    if getattr(state, 'call_proposal_count', 0) == 1:
        state.call_proposal_count = 2
        return Action.PROPOSE_MEETING_2
    
    # После второго отказа → FINISH_WITH_MATERIALS
    return Action.FINISH_WITH_MATERIALS


def get_action_context(action: Action, state: ClientState, extraction: dict = None) -> dict:
    """
    Формирует контекст для Generator на основе действия и состояния.
    """
    extraction = extraction or {}
    
    context = {
        "action": action.value,
        "action_description": ACTION_DESCRIPTIONS.get(action, ""),
        "known_facts": {},
        "missing_fields": state.get_missing_fields(),
        "qualification_score": state.qualification_score,
        "is_qualified": state.is_qualified(),
        # NEW: поля из Extractor v2.0
        "answered_last_bot_question": extraction.get("answered_last_bot_question"),
        "answer_mode": extraction.get("answer_mode"),
        "target_slot": extraction.get("target_slot"),
        "conversation_complete": extraction.get("conversation_complete", False)
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
            "value": f"{state.budget/1_000_000:.1f} млн",
            "confidence": state.budget_confidence
        }
    if state.payment_type:
        context["known_facts"]["payment_type"] = {
            "value": state.payment_type,
            "confidence": state.payment_type_confidence
        }
    if state.lpr:
        context["known_facts"]["lpr"] = {
            "value": state.lpr,
            "confidence": state.lpr_confidence
        }
    
    # Добавляем контекст возражения
    if action == Action.HANDLE_OBJECTION:
        context["objection_type"] = extraction.get("objection")
    
    # Добавляем контекст вопроса
    if action == Action.ANSWER_QUESTION:
        context["question_type"] = extraction.get("question_type")
    
    # Добавляем упоминания для уточнения
    if action == Action.CLARIFY_MENTIONED:
        if extraction.get("mentioned_location"):
            context["mentioned"] = {"type": "location", "value": extraction["mentioned_location"]}
        elif extraction.get("mentioned_price"):
            context["mentioned"] = {"type": "price", "value": extraction["mentioned_price"]}
    
    # Добавляем время созвона для подтверждения
    if action == Action.CONFIRM_MEETING:
        context["meeting_datetime"] = extraction.get("meeting_datetime") or state.meeting_datetime
    
    # ════════════════════════════════════════════════════════════════════════
    # NEW: Ситуативный контекст для живости диалога
    # ════════════════════════════════════════════════════════════════════════
    
    # NEW v2.2: Получаем signals
    signals = extraction.get("signals", {})
    
    context["situation"] = {
        "client_mood": extraction.get("sentiment", "neutral"),
        "answer_mode": extraction.get("answer_mode"),
        "is_off_topic": extraction.get("answer_mode") == "off_topic",
        "is_joking": extraction.get("sentiment") == "positive" and extraction.get("answer_mode") == "off_topic",
        "is_frustrated": extraction.get("sentiment") == "negative",
        "dialog_stage": "early" if state.qualification_score < 0.3 else ("middle" if state.qualification_score < 0.7 else "late"),
        "rapport_built": state.qualification_score > 0.5,  # уже поговорили, можно расслабиться
        # NEW v2.2: Латентные метрики
        "friction": signals.get("friction", 0.3),
        "call_readiness": signals.get("call_readiness", 0.5),
        "engagement": signals.get("engagement", "medium"),
        "urgency": signals.get("urgency", "unclear"),
    }
    
    # Опциональные подсказки для Generator (может использовать, может нет)
    optional_hints = []
    
    # Позитивный клиент — можно пошутить
    if extraction.get("sentiment") == "positive":
        optional_hints.append("Клиент в хорошем настроении — можешь поддержать лёгкий тон, пошутить")
    
    # Клиент нервничает — сначала успокоить
    if extraction.get("sentiment") == "negative" or extraction.get("objection"):
        optional_hints.append("Клиент напряжён — сначала прояви понимание, потом к делу")
    
    # Off-topic — поболтать, но вернуться
    if extraction.get("answer_mode") == "off_topic":
        optional_hints.append("Клиент ушёл от темы — ответь по-человечески (1-2 предложения), потом мягко вернись к делу")
    
    # Уже хорошо поговорили — можно быть теплее
    if state.qualification_score > 0.5:
        optional_hints.append("Вы уже неплохо пообщались — можно быть теплее и менее формальной")
    
    # Начало диалога — быть дружелюбной но профессиональной
    if state.qualification_score < 0.2:
        optional_hints.append("Начало диалога — будь дружелюбной, но не панибратствуй")
    
    context["optional_hints"] = optional_hints
    
    return context


def format_action_for_prompt(action: Action, context: dict) -> str:
    """
    Форматирует действие и контекст для добавления в промпт Generator.
    """
    lines = [
        "═══════════════════════════════════════════════════════════════",
        f"ТВОЁ ДЕЙСТВИЕ: {action.value.upper()}",
        "═══════════════════════════════════════════════════════════════",
        "",
        context.get("action_description", ""),
        ""
    ]
    
    # Известные факты
    if context.get("known_facts"):
        lines.append("ИЗВЕСТНО О КЛИЕНТЕ:")
        for field, data in context["known_facts"].items():
            lines.append(f"  • {field}: {data['value']} ({data['confidence']})")
        lines.append("")
    
    # Чего не хватает
    if context.get("missing_fields"):
        lines.append(f"НЕ ХВАТАЕТ: {', '.join(context['missing_fields'])}")
        lines.append("")
    
    # Специфичный контекст
    if context.get("objection_type"):
        lines.append(f"ВОЗРАЖЕНИЕ: {context['objection_type']}")
    if context.get("question_type"):
        lines.append(f"ВОПРОС КЛИЕНТА: {context['question_type']}")
    if context.get("mentioned"):
        lines.append(f"УПОМЯНУТО: {context['mentioned']['type']} = {context['mentioned']['value']}")
    if context.get("meeting_datetime"):
        lines.append(f"ВРЕМЯ СОЗВОНА: {context['meeting_datetime']}")
    
    return "\n".join(lines)


def increment_slot_attempt(state, slot: str, attempt_type: str = "ask"):
    """
    Увеличивает счётчик попыток для слота.
    Вызывать из bot_server.py ПОСЛЕ выбора действия ASK_* или HELP_*.
    """
    if not hasattr(state, 'slot_attempts') or not state.slot_attempts:
        state.slot_attempts = {s: {"ask": 0, "help": 0} for s in SLOT_ORDER}
    
    if slot in state.slot_attempts:
        state.slot_attempts[slot][attempt_type] += 1


# === ТЕСТЫ ===


def test_planner():
    """Тест Planner v2.0"""
    from state_manager import ClientState
    
    print("=== ТЕСТ PLANNER v2.0 ===\n")
    
    # Тест 1: Новый клиент → ASK_GOAL
    state = ClientState(user_id=1)
    action = get_next_action(state, "Привет", {})
    assert action == Action.ASK_GOAL, f"Ожидалось ASK_GOAL, получено {action}"
    print("✅ Тест 1: новый клиент → ASK_GOAL")
    
    # Тест 2: INVESTMENT ветка: goal → ASK_STRATEGY
    state.goal = "investment"
    state.goal_confidence = "confirmed"
    action = get_next_action(state, "ок", {})
    assert action == Action.ASK_STRATEGY, f"Ожидалось ASK_STRATEGY, получено {action}"
    print("✅ Тест 2: investment → ASK_STRATEGY")
    
    # Тест 3: После strategy → ASK_BUDGET
    state.branch = "investment"
    state.strategy = "rental"
    state.slot_attempts = {"strategy": {"ask": 1, "help": 0}}
    action = get_next_action(state, "ок", {})
    assert action == Action.ASK_BUDGET, f"Ожидалось ASK_BUDGET, получено {action}"
    print("✅ Тест 3: после strategy → ASK_BUDGET")
    
    # Тест 4: После budget → PROPOSE_MEETING_1
    state.budget = 10000000
    state.budget_confidence = "confirmed"
    state.slot_attempts["budget"] = {"ask": 1, "help": 0}
    action = get_next_action(state, "ок", {})
    assert action == Action.PROPOSE_MEETING_1, f"Ожидалось PROPOSE_MEETING_1, получено {action}"
    print("✅ Тест 4: после budget → PROPOSE_MEETING_1")
    
    # Тест 5: Возражение → HANDLE_OBJECTION (приоритет)
    extraction = {"objection": "expensive"}
    action = get_next_action(state, "дорого", extraction)
    assert action == Action.HANDLE_OBJECTION, f"Ожидалось HANDLE_OBJECTION, получено {action}"
    print("✅ Тест 5: возражение → HANDLE_OBJECTION")
    
    # Тест 6: Вопрос → ANSWER_QUESTION (приоритет)
    extraction = {"question_type": "price"}
    action = get_next_action(state, "какие цены?", extraction)
    assert action == Action.ANSWER_QUESTION, f"Ожидалось ANSWER_QUESTION, получено {action}"
    print("✅ Тест 6: вопрос → ANSWER_QUESTION")
    
    # Тест 7: Согласие на созвон → CONFIRM_MEETING
    extraction = {"meeting_agreed": True, "meeting_datetime": "завтра 18:00"}
    action = get_next_action(state, "давайте завтра в 18", extraction)
    assert action == Action.CONFIRM_MEETING, f"Ожидалось CONFIRM_MEETING, получено {action}"
    print("✅ Тест 7: согласие на созвон → CONFIRM_MEETING")
    
    # Тест 8: dialog_finished=True → WAIT
    state3 = ClientState(user_id=3)
    state3.dialog_finished = True
    action = get_next_action(state3, "привет", {})
    assert action == Action.WAIT, f"Ожидалось WAIT, получено {action}"
    print("✅ Тест 8: dialog_finished=True → WAIT")
    
    # Тест 9: Два отказа → FINISH_WITH_MATERIALS
    state4 = ClientState(user_id=4)
    state4.goal = "investment"
    state4.goal_confidence = "confirmed"
    state4.branch = "investment"
    state4.materials_request_count = 1  # Уже 1 отказ
    extraction = {"wants_materials": True}  # Второй отказ
    action = get_next_action(state4, "скиньте варианты", extraction)
    assert action == Action.FINISH_WITH_MATERIALS, f"Ожидалось FINISH_WITH_MATERIALS, получено {action}"
    print("✅ Тест 9: два отказа → FINISH_WITH_MATERIALS")
    
    # Тест 10: PERSONAL ветка: goal → ASK_USAGE
    state5 = ClientState(user_id=5)
    state5.goal = "personal"
    state5.goal_confidence = "confirmed"
    action = get_next_action(state5, "ок", {})
    assert action == Action.ASK_USAGE, f"Ожидалось ASK_USAGE, получено {action}"
    print("✅ Тест 10: personal → ASK_USAGE")
    
    # Тест 11: PERSONAL полная квалификация → PROPOSE_MEETING_2
    state6 = ClientState(user_id=6)
    state6.goal = "personal"
    state6.goal_confidence = "confirmed"
    state6.branch = "personal"
    state6.usage = "vacation"
    state6.location = "sochi"
    state6.location_confidence = "confirmed"
    state6.budget = 15000000
    state6.budget_confidence = "confirmed"
    state6.call_proposal_count = 1  # Уже было первое предложение
    state6.family = "с женой и детьми"
    state6.payment_type = "mortgage"
    state6.lpr = "with_spouse"
    state6.slot_attempts = {
        "usage": {"ask": 1, "help": 0},
        "location": {"ask": 1, "help": 0},
        "budget": {"ask": 1, "help": 0},
        "family": {"ask": 1, "help": 0},
        "payment_type": {"ask": 1, "help": 0},
        "lpr": {"ask": 1, "help": 0},
    }
    action = get_next_action(state6, "ок", {})
    assert action == Action.PROPOSE_MEETING_2, f"Ожидалось PROPOSE_MEETING_2, получено {action}"
    print("✅ Тест 11: personal полная квалификация → PROPOSE_MEETING_2")
    
    print("\n✅ Все тесты v2.0 пройдены!")


if __name__ == "__main__":
    test_planner()
