# detectors.py — Детекторы для Sofia Bot (Claude)
# Извлечено из анализа 5,698 сообщений клиентов (03.01.2026)
# Адаптировано из sofia-hybrid

import re
from typing import List, Dict

# ============================================
# ПАТТЕРНЫ
# ============================================

IRRITATED_PATTERNS = [
    'не надо', 'не нужно', 'хватит', 'достаточно', 'прекратите',
    'отстаньте', 'надоело', 'надоели', 'достали', 'утомили',
    'замучили', 'издевательство', 'что за', 'зачем вы', 'перестаньте',
    'будем прощаться', 'не звонить', 'не писать', 'не беспокоить',
    'отписаться', 'удалите', 'заблокирую', 'спам', 'не интересно',
    'неинтересно', 'не актуально', 'неактуально', 'передумал',
    'передумала', 'раздражает', 'бесит', 'отвалите', 'отвяжитесь',
    'сколько можно', 'опять вы', 'снова вы', 'много вопросов',
    'допрос', 'не хочу', 'отстань'
]

SEND_PATTERNS = [
    'пришлите', 'скиньте', 'отправьте', 'вышлите', 'покажите',
    'скинь', 'пришли', 'отправь', 'вышли', 'дай ссылку',
    'дайте ссылку', 'хочу посмотреть', 'можно посмотреть',
    'презентацию', 'каталог', 'буклет', 'материал', 'фото',
    'фотки', 'фотографии', 'планировк', 'план', 'прайс',
    'расчет', 'расчёт', 'калькуляц', 'на почту', 'на ватсап',
    'на whatsapp', 'на телеграм', 'ссылку', 'pdf', 'точку на карте',
    'адрес', 'где находится', 'подборку', 'варианты', 'информацию'
]

CALL_REJECT_PATTERNS = [
    'не могу говорить', 'не удобно', 'неудобно', 'занят', 'занята',
    'позже', 'потом', 'не сейчас', 'перезвоните', 'на работе',
    'в отпуске', 'за рулем', 'за рулём', 'совещание', 'встреча',
    'не звоните', 'только писать', 'только в переписке',
    'только текстом', 'чуть позже', 'на связи', 'сейчас не могу',
    'подумаю', 'надо подумать', 'посоветуюсь', 'обсужу',
    'переварить', 'осмыслить', 'свяжусь сам', 'свяжусь сама',
    'перезвоню', 'напишу сам', 'напишу позже', 'попозже',
    'позже напишу', 'позже посмотрю', 'не сегодня', 'пока не готов'
]

CALL_AGREE_PATTERNS = [
    'давайте созвонимся', 'можем созвониться', 'позвоните',
    'жду звонка', 'готов говорить', 'готова говорить', 'удобно',
    'можно звонить', 'да, звоните', 'хорошо, звоните', 'ок, звоните',
    'звоните', 'набирайте', 'подключаемся', 'подключусь',
    'буду онлайн', 'zoom', 'зум', 'видеозвонок', 'телемост',
    'пойдет', 'подойдёт', 'подойдет', 'устроит', 'договорились',
    'записывайте', 'запишите', 'жду', 'буду ждать', 'давайте в',
    'удобно в', 'свободен в', 'свободна в'
]

NEUTRAL_PATTERNS = [
    'посмотрим', 'там видно', 'время покажет', 'не знаю',
    'возможно', 'может быть', 'наверное', 'скорее всего',
    'пока не решил', 'пока не определился', 'еще думаю',
    'ещё думаю', 'сложно сказать', 'трудно сказать',
    'затрудняюсь', 'не уверен', 'не уверена', 'пока думаю',
    'надо посмотреть'
]

SHORT_CONFIRM_PATTERNS = [
    'ок', 'ok', 'окей', 'okay', 'хорошо', 'ладно', 'понял',
    'понятно', 'ясно', 'принято', 'согласен', 'согласна',
    'да', 'угу', 'ага', 'есть', 'добро', 'принял',
    '👍', '👌', '+', '✅', 'так точно'
]

POSITIVE_INTEREST_PATTERNS = [
    'интересно', 'интересует', 'нравится', 'понравилось',
    'понравился', 'заинтересовал', 'заинтересовала', 'хочу',
    'хотим', 'хотел бы', 'расскажите подробнее', 'подробнее',
    'детальнее', 'сколько стоит', 'какая цена', 'какие условия',
    'какие варианты', 'отлично', 'супер', 'класс', 'круто',
    'здорово', 'прекрасно'
]

GOODBYE_PATTERNS = [
    'до свидания', 'всего доброго', 'всего хорошего',
    'спасибо за информацию', 'благодарю', 'спасибо большое',
    'удачи', 'хорошего дня', 'до встречи', 'до связи',
    'созвонимся', 'будем на связи', 'пока'
]

# ============================================
# ДЕТЕКТОРЫ
# ============================================

def is_send_request(text: str) -> bool:
    """Клиент просит прислать материалы."""
    text_lower = text.lower()
    return any(p in text_lower for p in SEND_PATTERNS)


def is_call_rejection(text: str) -> bool:
    """Клиент отказывается от созвона."""
    text_lower = text.lower()
    return any(p in text_lower for p in CALL_REJECT_PATTERNS)


def is_call_agreement(text: str) -> bool:
    """Клиент соглашается на созвон."""
    text_lower = text.lower()
    has_agree = any(p in text_lower for p in CALL_AGREE_PATTERNS)
    has_reject = any(p in text_lower for p in CALL_REJECT_PATTERNS)
    return has_agree and not has_reject


def is_neutral_answer(text: str) -> bool:
    """Нейтральный ответ (не знаю, посмотрим)."""
    text_lower = text.lower()
    return any(p in text_lower for p in NEUTRAL_PATTERNS)


def is_irritated(text: str) -> bool:
    """Клиент раздражён."""
    text_lower = text.lower()
    return any(p in text_lower for p in IRRITATED_PATTERNS)


def is_positive(text: str) -> bool:
    """Позитивный интерес."""
    text_lower = text.lower()
    return any(p in text_lower for p in POSITIVE_INTEREST_PATTERNS)


def is_goodbye(text: str) -> bool:
    """Прощание."""
    text_lower = text.lower()
    return any(p in text_lower for p in GOODBYE_PATTERNS)


def has_question(text: str) -> bool:
    """Есть ли вопрос в тексте."""
    return "?" in text


def remove_question(text: str) -> str:
    """Удаляет предложения с вопросами из текста."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result = [s for s in sentences if "?" not in s]
    if result:
        return " ".join(result)
    else:
        # Если весь текст — вопрос, заменяем на дефолт
        return sentences[0].replace("?", ".") if sentences else text


# ============================================
# ЛИМИТЫ
# ============================================

MAX_MESSAGES = 30  # Мягкий лимит для предложения созвона
MAX_QUESTIONS_AFTER_SEND = 1
MAX_CALL_REJECTIONS = 2
MAX_NEUTRAL_ANSWERS = 3


# ============================================
# АНАЛИЗ ИСТОРИИ
# ============================================

def analyze_history(history: List[Dict]) -> Dict:
    """
    Анализирует историю диалога и возвращает статистику.
    """
    stats = {
        "total_messages": len(history),
        "user_messages": 0,
        "bot_messages": 0,
        "send_requests": 0,
        "call_rejections": 0,
        "call_agreements": 0,
        "neutral_answers": 0,
        "irritation_detected": False,
        "questions_after_last_send": 0,
        "last_send_request_index": -1,
        "call_offered": False
    }
    
    for i, msg in enumerate(history):
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "user":
            stats["user_messages"] += 1
            if is_send_request(content):
                stats["send_requests"] += 1
                stats["last_send_request_index"] = i
            if is_call_rejection(content):
                stats["call_rejections"] += 1
            if is_call_agreement(content):
                stats["call_agreements"] += 1
            if is_neutral_answer(content):
                stats["neutral_answers"] += 1
            if is_irritated(content):
                stats["irritation_detected"] = True
        elif role == "assistant":
            stats["bot_messages"] += 1
            if "созвон" in content.lower() or "видеопрезентац" in content.lower():
                stats["call_offered"] = True
    
    # Сколько вопросов бот задал после последнего запроса на материалы
    if stats["last_send_request_index"] >= 0:
        for msg in history[stats["last_send_request_index"] + 1:]:
            if msg.get("role") == "assistant" and has_question(msg.get("content", "")):
                stats["questions_after_last_send"] += 1
    
    return stats


# ============================================
# ПРИНЯТИЕ РЕШЕНИЯ
# ============================================

def decide_action(stats: Dict, last_message: str) -> Dict:
    """
    Принимает решение о действии на основе статистики и последнего сообщения.
    
    Returns:
        {
            "action": "SEND_MATERIALS" | "CONTINUE" | "PROPOSE_CALL" | ...,
            "allow_questions": True | False,
            "reason": str,
            "instruction": str  # Инструкция для LLM
        }
    """
    current_is_send = is_send_request(last_message)
    current_is_irritated = is_irritated(last_message)
    current_is_rejection = is_call_rejection(last_message)
    current_is_agreement = is_call_agreement(last_message)
    current_is_neutral = is_neutral_answer(last_message)
    
    # 1. Согласие на созвон — приоритет
    if current_is_agreement:
        return {
            "action": "CONFIRM_CALL",
            "allow_questions": True,
            "reason": "call_agreed",
            "instruction": "Клиент согласился на созвон! Подтверди время. Можешь спросить: 'Решение сами принимаете или с кем-то?'"
        }
    
    # 2. Раздражение — СТОП вопросам
    if current_is_irritated or stats["irritation_detected"]:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "irritated",
            "instruction": "Клиент раздражён. Извинись коротко и скажи что пришлёшь 2-3 варианта. БЕЗ ВОПРОСОВ. Никаких."
        }
    
    # 3. Несколько запросов на материалы
    if stats["send_requests"] >= 2 or (stats["send_requests"] >= 1 and current_is_send):
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "multiple_send_requests",
            "instruction": "Клиент уже несколько раз просил скинуть. Хватит. Скажи что пришлёшь 2-3 варианта. БЕЗ ВОПРОСОВ."
        }
    
    # 4. Уже спросили после запроса — и он снова просит
    if stats["questions_after_last_send"] >= MAX_QUESTIONS_AFTER_SEND and current_is_send:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "asked_after_send",
            "instruction": "Клиент просил скинуть, мы задали вопрос, он снова просит. Хватит. Скажи что пришлёшь. БЕЗ ВОПРОСОВ."
        }
    
    # 5. Длинный диалог — мягко направляем к созвону
    if stats["total_messages"] >= 20 and not stats["call_offered"]:
        return {
            "action": "SOFT_PROPOSE_CALL",
            "allow_questions": True,
            "reason": "long_dialog_suggest_call",
            "instruction": "Диалог идёт давно. Мягко предложи созвон с объяснением: 'Вижу, у вас много вопросов — это здорово! Чтобы не затягивать переписку, давайте созвонимся на 15 минут? Покажу всё наглядно и отвечу на все вопросы сразу. Так будет быстрее и удобнее для вас. Когда комфортнее?'"
        }
    
    # 5b. Очень длинный диалог после предложения созвона — ещё раз мягко
    if stats["total_messages"] >= MAX_MESSAGES:
        return {
            "action": "SOFT_PROPOSE_CALL",
            "allow_questions": True,
            "reason": "very_long_dialog",
            "instruction": "Диалог очень длинный. Ещё раз мягко предложи созвон: 'Понимаю, что хочется всё выяснить заранее. Но в переписке это может затянуться — давайте я за 15 минут на созвоне покажу варианты и отвечу на все вопросы? Ценю ваше время 🙂 Когда удобнее?'"
        }
    
    # 6. Много отказов от созвона
    total_rejections = stats["call_rejections"] + (1 if current_is_rejection else 0)
    if total_rejections >= MAX_CALL_REJECTIONS:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "call_rejected_twice",
            "instruction": "Клиент уже отказывался от созвона. Не настаивай. Скажи что пришлёшь 2-3 варианта. БЕЗ ВОПРОСОВ."
        }
    
    # 7. Много нейтральных ответов
    total_neutral = stats["neutral_answers"] + (1 if current_is_neutral else 0)
    if total_neutral >= MAX_NEUTRAL_ANSWERS:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "too_many_neutral",
            "instruction": "Клиент много раз отвечал 'без разницы'. Хватит спрашивать. Скажи что пришлёшь варианты. БЕЗ ВОПРОСОВ."
        }
    
    # 8. Первый запрос на материалы — можно один вопрос
    if current_is_send and stats["questions_after_last_send"] == 0:
        return {
            "action": "QUALIFY_THEN_SEND",
            "allow_questions": True,
            "reason": "first_send_request",
            "instruction": "Клиент просит скинуть. Подтверди что пришлёшь. Можешь задать ОДИН уточняющий вопрос."
        }
    
    # 9. Первый отказ от созвона — продолжаем
    if current_is_rejection and total_rejections == 1:
        return {
            "action": "CONTINUE",
            "allow_questions": True,
            "reason": "first_call_rejection",
            "instruction": "Клиент отказался от созвона. Спокойно продолжай квалификацию. Спроси про бюджет если не знаем."
        }
    
    # 10. Пора предложить созвон (после 4 сообщений)
    if stats["user_messages"] >= 4 and not stats["call_offered"]:
        return {
            "action": "PROPOSE_CALL",
            "allow_questions": True,
            "reason": "enough_qualification",
            "instruction": "Уже достаточно пообщались. ОБЯЗАТЕЛЬНО предложи созвон: 'Давайте созвонимся на 15 минут — покажу варианты под ваш запрос. Когда удобнее?'"
        }
    
    # 11. После предложения созвона — продолжаем квалификацию
    if stats["call_offered"]:
        return {
            "action": "CONTINUE",
            "allow_questions": True,
            "reason": "normal_after_call_offer",
            "instruction": "Продолжай квалификацию. Узнай что не выяснено: бюджет, способ оплаты, сроки. Один вопрос."
        }
    
    # 12. По умолчанию — квалификация или созвон
    return {
        "action": "QUALIFY_OR_CALL",
        "allow_questions": True,
        "reason": "normal",
        "instruction": "Если знаем цель+локацию+способ оплаты — предложи созвон на 15 минут. Если нет — задай следующий вопрос по лестнице."
    }


# Для тестирования
if __name__ == "__main__":
    # Тест детекторов
    test_messages = [
        "Скиньте варианты",
        "Хватит, достали уже",
        "Давайте завтра в 15:00 созвонимся",
        "Не знаю пока",
        "Не сейчас, занят",
    ]
    
    for msg in test_messages:
        print(f"\n'{msg}':")
        print(f"  send_request: {is_send_request(msg)}")
        print(f"  irritated: {is_irritated(msg)}")
        print(f"  call_agree: {is_call_agreement(msg)}")
        print(f"  call_reject: {is_call_rejection(msg)}")
        print(f"  neutral: {is_neutral_answer(msg)}")
