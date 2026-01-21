"""
llm_planner.py — LLM-обёртка над детерминированным Planner
==========================================================
Получает список allowed_actions от Planner и выбирает лучший с помощью LLM.
Добавляет micro_goal и tone для более живых ответов.

v3.0: Фаза 2
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI

from planner import Action, ACTION_DESCRIPTIONS

# Настройка логирования
logger = logging.getLogger(__name__)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Конфигурация LLM-Planner
LLM_PLANNER_MODEL = "gpt-5.2"
LLM_PLANNER_REASONING = {"effort": "high"}  # Включаем "думание"
LLM_PLANNER_MAX_TOKENS = 300


def llm_select_action(
    allowed_actions: List[Action],
    state: Any,
    message: str,
    history: List[Dict],
    extraction: Dict
) -> Dict[str, Any]:
    """
    Выбирает лучшее действие из allowed_actions с помощью LLM.
    
    Args:
        allowed_actions: Список допустимых действий от Planner
        state: Состояние клиента (ClientState)
        message: Последнее сообщение клиента
        history: История сообщений [{role, content}, ...]
        extraction: Результат Extractor
        
    Returns:
        {
            "action": Action,           # Выбранное действие
            "micro_goal": str | None,   # Дополнительная цель (например, "спросить бюджет в конце")
            "tone": str,                # Тон ответа (warm, professional, empathetic, playful)
            "reasoning": str            # Почему выбрано это действие
        }
    """
    
    # Если только один вариант — не тратим токены
    if len(allowed_actions) == 1:
        return {
            "action": allowed_actions[0],
            "micro_goal": None,
            "tone": "warm",
            "reasoning": "single_option"
        }
    
    # Формируем промпт
    prompt = _build_planner_prompt(allowed_actions, state, message, history, extraction)
    
    try:
        response = client.responses.create(
            model=LLM_PLANNER_MODEL,
            instructions=_get_system_instructions(),
            input=[{"role": "user", "content": prompt}],
            reasoning=LLM_PLANNER_REASONING,
            text={"verbosity": "low"},
            max_output_tokens=LLM_PLANNER_MAX_TOKENS,
            store=False
        )
        
        result_text = response.output_text.strip()
        logger.info(f"LLM Planner response: {result_text}")
        
        # Парсим JSON
        parsed = _parse_response(result_text, allowed_actions)
        return parsed
        
    except Exception as e:
        logger.error(f"LLM Planner error: {e}")
        # Fallback: первый action из списка
        return {
            "action": allowed_actions[0],
            "micro_goal": None,
            "tone": "warm",
            "reasoning": f"fallback_error: {str(e)}"
        }


def _get_system_instructions() -> str:
    """Системные инструкции для LLM-Planner."""
    return """Ты — стратег продаж недвижимости. Твоя задача — выбрать ЛУЧШЕЕ действие из списка допустимых.

ПРАВИЛА:
1. Выбирай действие которое ПРОДВИГАЕТ диалог к созвону
2. Если клиент задал вопрос — обычно лучше сначала ответить
3. Если клиент расслаблен и вовлечён — можно предлагать созвон
4. Если клиент напряжён — лучше продолжить квалификацию, не давить
5. micro_goal используй чтобы "дописать" к основному действию (например, ответить на вопрос И спросить бюджет)

ФОРМАТ ОТВЕТА (строго JSON):
{
  "action": "название_действия",
  "micro_goal": "дополнительная цель или null",
  "tone": "warm|professional|empathetic|playful",
  "reasoning": "короткое объяснение выбора"
}"""


def _build_planner_prompt(
    allowed_actions: List[Action],
    state: Any,
    message: str,
    history: List[Dict],
    extraction: Dict
) -> str:
    """Формирует промпт для LLM-Planner."""
    
    # Форматируем allowed_actions
    actions_text = []
    for i, action in enumerate(allowed_actions, 1):
        desc = ACTION_DESCRIPTIONS.get(action, "")
        # Берём только первую строку описания
        short_desc = desc.split('\n')[0] if desc else ""
        actions_text.append(f"{i}. {action.value}: {short_desc}")
    
    # Форматируем известные факты о клиенте
    known_facts = []
    if state.goal:
        known_facts.append(f"Цель: {state.goal} ({state.goal_confidence})")
    if state.location:
        known_facts.append(f"Локация: {state.location}")
    if state.budget:
        known_facts.append(f"Бюджет: {state.budget/1_000_000:.1f} млн")
    if state.payment_type:
        known_facts.append(f"Оплата: {state.payment_type}")
    if getattr(state, 'strategy', None):
        known_facts.append(f"Стратегия: {state.strategy}")
    
    # Сигналы из extraction
    signals = extraction.get("signals", {})
    signals_text = []
    if signals:
        if "friction" in signals:
            signals_text.append(f"friction: {signals['friction']}")
        if "call_readiness" in signals:
            signals_text.append(f"call_readiness: {signals['call_readiness']}")
        if "engagement" in signals:
            signals_text.append(f"engagement: {signals['engagement']}")
    
    # Последние 3 сообщения для контекста
    recent = history[-6:] if len(history) > 6 else history  # 3 пары user/assistant
    history_text = []
    for msg in recent:
        role = "Клиент" if msg.get("role") == "user" else "София"
        content = msg.get("content", "")[:100]  # Обрезаем длинные
        history_text.append(f"{role}: {content}")
    
    prompt = f"""СИТУАЦИЯ:
Последнее сообщение клиента: "{message}"

ДОПУСТИМЫЕ ДЕЙСТВИЯ:
{chr(10).join(actions_text)}

ИЗВЕСТНО О КЛИЕНТЕ:
{chr(10).join(known_facts) if known_facts else "Пока ничего"}

СИГНАЛЫ:
{', '.join(signals_text) if signals_text else "Нет данных"}

КОНТЕКСТ ДИАЛОГА:
{chr(10).join(history_text) if history_text else "Начало диалога"}

ДОПОЛНИТЕЛЬНО:
- question_type: {extraction.get('question_type', 'нет')}
- objection: {extraction.get('objection', 'нет')}
- sentiment: {extraction.get('sentiment', 'neutral')}
- answer_mode: {extraction.get('answer_mode', 'direct')}

Выбери лучшее действие и ответь JSON."""

    return prompt


def _parse_response(text: str, allowed_actions: List[Action]) -> Dict[str, Any]:
    """Парсит JSON ответ LLM."""
    
    # Убираем markdown если есть
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    
    text = text.strip()
    
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Пробуем найти JSON в тексте
        import re
        match = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except:
                return _fallback_result(allowed_actions, "json_parse_error")
        else:
            return _fallback_result(allowed_actions, "no_json_found")
    
    # Валидируем action
    action_str = data.get("action", "")
    selected_action = None
    
    for action in allowed_actions:
        if action.value == action_str:
            selected_action = action
            break
    
    if not selected_action:
        # LLM выбрал action не из списка — берём первый
        logger.warning(f"LLM selected invalid action: {action_str}")
        selected_action = allowed_actions[0]
    
    return {
        "action": selected_action,
        "micro_goal": data.get("micro_goal"),
        "tone": data.get("tone", "warm"),
        "reasoning": data.get("reasoning", "")
    }


def _fallback_result(allowed_actions: List[Action], reason: str) -> Dict[str, Any]:
    """Fallback результат при ошибке парсинга."""
    return {
        "action": allowed_actions[0],
        "micro_goal": None,
        "tone": "warm",
        "reasoning": f"fallback: {reason}"
    }


# === ТЕСТ ===

def test_llm_planner():
    """Тест LLM Planner (требует API key)."""
    from state_manager import ClientState
    
    print("=== ТЕСТ LLM Planner ===\n")
    
    # Создаём тестовое состояние
    state = ClientState(user_id=999)
    state.goal = "investment"
    state.goal_confidence = "confirmed"
    state.branch = "investment"
    state.strategy = "rental"
    
    allowed = [Action.ANSWER_QUESTION, Action.ASK_BUDGET]
    message = "А какие цены в Сочи?"
    history = [
        {"role": "user", "content": "Хочу инвестировать"},
        {"role": "assistant", "content": "Отлично! Что важнее: доход с аренды или рост стоимости?"},
        {"role": "user", "content": "Аренда"},
        {"role": "assistant", "content": "Понял, сдавать в аренду. А какие цены в Сочи?"},
    ]
    extraction = {
        "question_type": "price",
        "signals": {"friction": 0.3, "call_readiness": 0.5, "engagement": "medium"}
    }
    
    print(f"Allowed actions: {[a.value for a in allowed]}")
    print(f"Message: {message}")
    print()
    
    result = llm_select_action(allowed, state, message, history, extraction)
    
    print(f"Selected action: {result['action'].value}")
    print(f"Micro goal: {result['micro_goal']}")
    print(f"Tone: {result['tone']}")
    print(f"Reasoning: {result['reasoning']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_llm_planner()
