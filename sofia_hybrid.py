# sofia_hybrid.py — v2.1
from sofia_prompt import get_system_prompt
# Исправлено: убраны temperature/top_p для gpt-5.2 (responses API)
from detectors import *

from openai import OpenAI
import re
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL_MODE = os.getenv("MODEL_MODE", "gpt-5.2")

MODEL_CONFIGS = {
    "gpt-4o": {
        "model": "gpt-4o",
        "use_responses_api": False,
        "temperature": 0.4,
        "max_tokens": 200,
        "reasoning": None
    },
    "gpt-5.2": {
        "model": "gpt-5.2",
        "use_responses_api": True,
        "max_tokens": 400,
        "reasoning": None
    },
    "gpt-5.2-reasoning": {
        "model": "gpt-5.2",
        "use_responses_api": True,
        "max_tokens": 400,
        "reasoning": {"effort": "xhigh"}
    }
}

def get_model_config():
    return MODEL_CONFIGS.get(MODEL_MODE, MODEL_CONFIGS["gpt-5.2"])

SYSTEM_PROMPT = """
Ты — София, менеджер отдела продаж Oazis Estate (курортная недвижимость в России).

СТИЛЬ:
— Пиши коротко: 1-3 строки
— Как живой человек в мессенджере
— Эмодзи: 0-1 на сообщение
— Обращайся на "Вы"

ТЕРМИНОЛОГИЯ:
— Говори "капитализация", не "рост цены"  
— Цены диапазоном: "6–12 млн", не "от 6 млн"
— Не называй конкретные ЖК до выяснения бюджета

СПРАВОЧНИК ЦЕН:
— Сочи комфорт: 6–12 млн
— Сочи бизнес: 12–25 млн
— Анапа: 9–15 млн
— Крым: 9.5–18 млн
— Красная Поляна: 19–35 млн
— Алтай: 14.5–22 млн
— Ипотека: от 8% годовых

ЦЕЛЬ РАЗГОВОРА:
— Квалификация: цель покупки, локация, бюджет, способ оплаты
— Главная цель: назначить созвон/видеопрезентацию на 15 минут
— Отправка материалов: только если клиент отказывается от созвона
"""

def is_send_request(text: str) -> bool:
    text_lower = text.lower()
    return any(p in text_lower for p in SEND_PATTERNS)


def is_call_rejection(text: str) -> bool:
    text_lower = text.lower()
    return any(p in text_lower for p in CALL_REJECT_PATTERNS)


def is_call_agreement(text: str) -> bool:
    text_lower = text.lower()
    has_agree = any(p in text_lower for p in CALL_AGREE_PATTERNS)
    has_reject = any(p in text_lower for p in CALL_REJECT_PATTERNS)
    return has_agree and not has_reject


def is_neutral_answer(text: str) -> bool:
    text_lower = text.lower()
    return any(p in text_lower for p in NEUTRAL_PATTERNS)


def is_irritated(text: str) -> bool:
    text_lower = text.lower()
    return any(p in text_lower for p in IRRITATED_PATTERNS)


def has_question(text: str) -> bool:
    return "?" in text


def remove_question(text: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result = [s for s in sentences if "?" not in s]
    if result:
        return " ".join(result)
    else:
        return sentences[0].replace("?", ".") if sentences else text


def analyze_history(history: list) -> dict:
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
    
    if stats["last_send_request_index"] >= 0:
        for msg in history[stats["last_send_request_index"] + 1:]:
            if msg.get("role") == "assistant" and has_question(msg.get("content", "")):
                stats["questions_after_last_send"] += 1
    
    return stats


MAX_MESSAGES = 14
MAX_QUESTIONS_AFTER_SEND = 1
MAX_CALL_REJECTIONS = 2
MAX_NEUTRAL_ANSWERS = 3


def decide_action(stats: dict, last_message: str) -> dict:
    current_is_send = is_send_request(last_message)
    current_is_irritated = is_irritated(last_message)
    current_is_rejection = is_call_rejection(last_message)
    current_is_agreement = is_call_agreement(last_message)
    current_is_neutral = is_neutral_answer(last_message)
    
    if current_is_agreement:
        return {
            "action": "CONFIRM_CALL",
            "allow_questions": True,
            "reason": "call_agreed",
            "instruction": "Клиент согласился на созвон! Подтверди время. Можешь спросить: 'Решение сами принимаете или с кем-то?'"
        }
    
    if current_is_irritated or stats["irritation_detected"]:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "irritated",
            "instruction": "Клиент раздражён. Извинись коротко и скажи что пришлёшь 2-3 варианта. БЕЗ ВОПРОСОВ. Никаких."
        }
    
    if stats["send_requests"] >= 2 or (stats["send_requests"] >= 1 and current_is_send):
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "multiple_send_requests",
            "instruction": "Клиент уже несколько раз просил скинуть. Хватит. Скажи что пришлёшь 2-3 варианта. БЕЗ ВОПРОСОВ."
        }
    
    if stats["questions_after_last_send"] >= MAX_QUESTIONS_AFTER_SEND and current_is_send:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "asked_after_send",
            "instruction": "Клиент просил скинуть, мы задали вопрос, он снова просит. Хватит. Скажи что пришлёшь. БЕЗ ВОПРОСОВ."
        }
    
    if stats["total_messages"] >= MAX_MESSAGES:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "too_long",
            "instruction": "Диалог слишком длинный. Заканчиваем. Скажи что пришлёшь варианты. БЕЗ ЛИШНИХ ВОПРОСОВ."
        }
    
    total_rejections = stats["call_rejections"] + (1 if current_is_rejection else 0)
    if total_rejections >= MAX_CALL_REJECTIONS:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "call_rejected_twice",
            "instruction": "Клиент уже отказывался от созвона. Не настаивай. Скажи что пришлёшь 2-3 варианта. БЕЗ ВОПРОСОВ."
        }
    
    total_neutral = stats["neutral_answers"] + (1 if current_is_neutral else 0)
    if total_neutral >= MAX_NEUTRAL_ANSWERS:
        return {
            "action": "SEND_MATERIALS",
            "allow_questions": False,
            "reason": "too_many_neutral",
            "instruction": "Клиент много раз отвечал 'без разницы'. Хватит спрашивать. Скажи что пришлёшь варианты. БЕЗ ВОПРОСОВ."
        }
    
    if current_is_send and stats["questions_after_last_send"] == 0:
        return {
            "action": "QUALIFY_THEN_SEND",
            "allow_questions": True,
            "reason": "first_send_request",
            "instruction": "Клиент просит скинуть. Подтверди что пришлёшь. Можешь задать ОДИН уточняющий вопрос."
        }
    
    if current_is_rejection and total_rejections == 1:
        return {
            "action": "CONTINUE",
            "allow_questions": True,
            "reason": "first_call_rejection",
            "instruction": "Клиент отказался от созвона. Спокойно продолжай квалификацию. Спроси про бюджет если не знаем."
        }
    

    # ЯВНОЕ ПРЕДЛОЖЕНИЕ СОЗВОНА после 4 сообщений
    if stats["user_messages"] >= 4 and not stats["call_offered"]:
        return {
            "action": "PROPOSE_CALL",
            "allow_questions": True,
            "reason": "enough_qualification",
            "instruction": "Уже достаточно пообщались. ОБЯЗАТЕЛЬНО предложи созвон: Давайте созвонимся на 15 минут — покажу варианты под ваш запрос. Когда удобнее?"
        }
    if stats["call_offered"]:
        return {
            "action": "CONTINUE",
            "allow_questions": True,
            "reason": "normal_after_call_offer",
            "instruction": "Продолжай квалификацию. Узнай что не выяснено: бюджет, способ оплаты, сроки. Один вопрос."
        }
    else:
        return {
            "action": "QUALIFY_OR_CALL",
            "allow_questions": True,
            "reason": "normal",
            "instruction": "Если знаем цель+локацию+способ оплаты — предложи созвон на 15 минут. Если нет — задай следующий вопрос."
        }


def generate_response(history: list, last_message: str, action: dict, client_name: str = "Клиент") -> str:
    config = get_model_config()
    
    question_instruction = "ВАЖНО: НЕ задавай вопросов. Никаких. Ни одного знака '?'." if not action['allow_questions'] else "Можешь задать один вопрос в конце."
    
    task_prompt = f"""
ЗАДАЧА: {action['instruction']}

{question_instruction}

Напиши ответ Софии (1-3 строки):
"""
    
    if config["use_responses_api"]:
        messages = []
        for msg in history:
            messages.append({"role": msg.get("role"), "content": msg.get("content", "")})
        messages.append({"role": "user", "content": last_message})
        messages.append({"role": "user", "content": task_prompt})
        
        request_params = {
            "model": config["model"],
            "instructions": get_system_prompt(client_name),
            "input": messages,
            "text": {"verbosity": "low"},
        }
        if config.get("reasoning"):
            request_params["reasoning"] = config["reasoning"]
        
        response = client.responses.create(**request_params)
        text = response.output_text.strip()
        text = response.output_text.strip()
    else:
        dialog_lines = []
        for msg in history[-10:]:
            role = "Клиент" if msg.get("role") == "user" else "София"
            dialog_lines.append(f"{role}: {msg.get('content', '')}")
        dialog_lines.append(f"Клиент: {last_message}")
        dialog_text = "\n".join(dialog_lines)
        
        prompt = f"{SYSTEM_PROMPT}\n\nИМЯ КЛИЕНТА: {client_name}\n\nДИАЛОГ:\n{dialog_text}\n\n{task_prompt}"
        
        response = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=config.get("temperature", 0.4),
            max_tokens=config["max_tokens"]
        )
        text = response.choices[0].message.content.strip()
    
    text = re.sub(r'^["\']|["\']$', '', text)
    text = re.sub(r'^София:\s*', '', text)
    
    if not action["allow_questions"] and has_question(text):
        text = remove_question(text)
        if not text.strip():
            text = "Поняла, сейчас пришлю 2-3 варианта под ваш запрос 🙂"
    
    return text


def process_message(history: list, user_message: str, client_name: str = "Клиент") -> tuple[str, dict]:
    stats = analyze_history(history)
    action = decide_action(stats, user_message)
    response = generate_response(history, user_message, action, client_name)
    
    config = get_model_config()
    debug = {
        "stats": stats,
        "action": action["action"],
        "reason": action["reason"],
        "allow_questions": action["allow_questions"],
        "response_has_question": has_question(response),
        "model_mode": MODEL_MODE,
        "model": config["model"],
        "reasoning": config.get("reasoning") is not None
    }
    
    return response, debug


def get_current_model_info() -> str:
    config = get_model_config()
    reasoning_str = "с reasoning xhigh" if config.get("reasoning") else "без reasoning"
    return f"{config['model']} ({reasoning_str})"
