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
    
    Action.FOLLOW_UP: """Напомнить о себе, если клиент не отвечал 10+ минут."""
}


# Короткие подтверждения для WAIT-логики
SHORT_CONFIRMATIONS = {
    "ок", "ok", "да", "хорошо", "ладно", "понял", "понятно", 
    "ясно", "угу", "+", "отлично", "супер", "класс", "👍",
    "принял", "принято", "договорились", "ага", "угум", "ок!",
    "хор", "да!", "ок.", "good", "yes", "ясненько", "понятненько"
}


def is_short_confirmation(message: str) -> bool:
    """Проверка на короткое подтверждение"""
    msg = message.strip().lower().rstrip('!.,')
    return msg in SHORT_CONFIRMATIONS or len(msg) < 8


def get_next_action(state: ClientState, message: str, extraction: dict = None) -> Action:
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
    
    extraction = extraction or {}
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 1: После договорённости — молчим на короткие подтверждения
    # ═══════════════════════════════════════════════════════════════════════
#     if state.meeting_agreed and is_short_confirmation(message):
#         return Action.WAIT
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 2: Клиент согласился на созвон — подтверждаем
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("meeting_agreed") and extraction.get("meeting_datetime"):
        return Action.CONFIRM_MEETING
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 3: Обработка возражений
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("objection"):
        return Action.HANDLE_OBJECTION
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 4: Ответ на вопрос клиента
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("question_type"):
        return Action.ANSWER_QUESTION
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 5: Уточнение упоминаний
    # ═══════════════════════════════════════════════════════════════════════
    # Если клиент упомянул локацию/цену, но не подтвердил — уточняем
    if extraction.get("mentioned_location") and not state.location:
        return Action.CLARIFY_MENTIONED
    if extraction.get("mentioned_price") and not state.budget:
        return Action.CLARIFY_MENTIONED
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 6: Реакция на запрос материалов (ПЕРЕД квалификацией!)
    # ═══════════════════════════════════════════════════════════════════════
    if extraction.get("wants_materials"):
        if state.is_qualified():
            return Action.SEND_MATERIALS
        else:
            return Action.DEFLECT_TO_CALL
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 7: Квалификация по порядку
    # ═══════════════════════════════════════════════════════════════════════
    
    # 7.1 Цель покупки
    if not state.goal or state.goal_confidence != "confirmed":
        return Action.ASK_GOAL
    
    # 7.2 Локация
    if not state.location or state.location_confidence != "confirmed":
        return Action.ASK_LOCATION
    
    # 7.3 Бюджет
    if not state.budget or state.budget_confidence != "confirmed":
        return Action.ASK_BUDGET
    
    # 7.4 Способ оплаты
    if not state.payment_type or state.payment_type_confidence != "confirmed":
        return Action.ASK_PAYMENT
    
    # 7.5 Первый взнос (только для ипотеки)
    if state.payment_type == "mortgage":
        if not state.first_payment or state.first_payment_confidence != "confirmed":
            return Action.ASK_FIRST_PAYMENT
    
    # 7.6 ЛПР (кто принимает решение)
    if not state.lpr or state.lpr_confidence != "confirmed":
        return Action.ASK_LPR
    
    # ═══════════════════════════════════════════════════════════════════════
    # ПРИОРИТЕТ 8: Квалификация завершена — предлагаем созвон
    # ═══════════════════════════════════════════════════════════════════════
    if not state.meeting_agreed:
        return Action.PROPOSE_MEETING
    
    # Если всё сделано — подтверждаем созвон
    return Action.CONFIRM_MEETING


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


# === ТЕСТЫ ===

def test_planner():
    """Тест Planner"""
    from state_manager import ClientState
    
    print("=== ТЕСТ PLANNER ===\n")
    
    # Тест 1: Новый клиент → ASK_GOAL
    state = ClientState(user_id=1)
    action = get_next_action(state, "Привет", {})
    assert action == Action.ASK_GOAL, f"Ожидалось ASK_GOAL, получено {action}"
    print("✅ Тест 1: новый клиент → ASK_GOAL")
    
    # Тест 2: Есть goal → ASK_LOCATION
    state.goal = "investment"
    state.goal_confidence = "confirmed"
    action = get_next_action(state, "ок", {})
    assert action == Action.ASK_LOCATION, f"Ожидалось ASK_LOCATION, получено {action}"
    print("✅ Тест 2: есть goal → ASK_LOCATION")
    
    # Тест 3: Есть goal+location → ASK_BUDGET
    state.location = "sochi"
    state.location_confidence = "confirmed"
    action = get_next_action(state, "ок", {})
    assert action == Action.ASK_BUDGET, f"Ожидалось ASK_BUDGET, получено {action}"
    print("✅ Тест 3: есть goal+location → ASK_BUDGET")
    
    # Тест 4: Возражение → HANDLE_OBJECTION (приоритет)
    extraction = {"objection": "expensive"}
    action = get_next_action(state, "дорого", extraction)
    assert action == Action.HANDLE_OBJECTION, f"Ожидалось HANDLE_OBJECTION, получено {action}"
    print("✅ Тест 4: возражение → HANDLE_OBJECTION")
    
    # Тест 5: Вопрос → ANSWER_QUESTION (приоритет)
    extraction = {"question_type": "price"}
    action = get_next_action(state, "какие цены?", extraction)
    assert action == Action.ANSWER_QUESTION, f"Ожидалось ANSWER_QUESTION, получено {action}"
    print("✅ Тест 5: вопрос → ANSWER_QUESTION")
    
    # Тест 6: Полная квалификация → PROPOSE_MEETING
    state.budget = 10000000
    state.budget_confidence = "confirmed"
    state.payment_type = "mortgage"
    state.payment_type_confidence = "confirmed"
    state.first_payment = 2000000
    state.first_payment_confidence = "confirmed"
    state.lpr = "alone"
    state.lpr_confidence = "confirmed"
    action = get_next_action(state, "понятно", {})
    assert action == Action.PROPOSE_MEETING, f"Ожидалось PROPOSE_MEETING, получено {action}"
    print("✅ Тест 6: полная квалификация → PROPOSE_MEETING")
    
    # Тест 7: Согласие на созвон → CONFIRM_MEETING
    extraction = {"meeting_agreed": True, "meeting_datetime": "завтра 18:00"}
    action = get_next_action(state, "давайте завтра в 18", extraction)
    assert action == Action.CONFIRM_MEETING, f"Ожидалось CONFIRM_MEETING, получено {action}"
    print("✅ Тест 7: согласие на созвон → CONFIRM_MEETING")
    
    # Тест 8: После договорённости + короткое подтверждение → WAIT
    state.meeting_agreed = True
    action = get_next_action(state, "ок", {})
    assert action == Action.WAIT, f"Ожидалось WAIT, получено {action}"
    print("✅ Тест 8: после договорённости + 'ок' → WAIT")
    
    # Тест 9: После договорённости + содержательное сообщение → НЕ WAIT
    action = get_next_action(state, "а можно перенести на 19:00?", {})
    assert action != Action.WAIT, f"Ожидалось НЕ WAIT, получено {action}"
    print("✅ Тест 9: после договорённости + содержательное → НЕ WAIT")
    
    # Тест 10: Просит материалы без квалификации → DEFLECT_TO_CALL
    state2 = ClientState(user_id=2)
    state2.goal = "investment"
    state2.goal_confidence = "confirmed"
    extraction = {"wants_materials": True}
    action = get_next_action(state2, "скиньте что есть", extraction)
    assert action == Action.DEFLECT_TO_CALL, f"Ожидалось DEFLECT_TO_CALL, получено {action}"
    print("✅ Тест 10: просит материалы без квалификации → DEFLECT_TO_CALL")
    
    print("\n✅ Все тесты пройдены!")


if __name__ == "__main__":
    test_planner()
