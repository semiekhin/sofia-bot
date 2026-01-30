"""
Единый процессор сообщений Sofia-GPT
Точка входа для всех каналов: Telegram, Userbot, Max, WhatsApp
"""

from datetime import datetime

# Импорты из проекта
from extractor import extract_sync, merge_extraction_to_state
from planner import get_next_action, get_allowed_actions, get_action_context, Action, increment_slot_attempt

# Флаг использования LLM Planner
USE_LLM_PLANNER = True


def log(message: str):
    """Логирование с временной меткой"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


async def process_message(
    user_id: int,
    user_name: str,
    message: str,
    history: list,
    state_manager,
    channel: str = "telegram"
) -> dict:
    """
    Единая точка обработки сообщений для всех каналов.
    
    Args:
        user_id: ID пользователя
        user_name: Имя пользователя
        message: Текст сообщения
        history: История сообщений [{"role": "user"/"assistant", "content": "..."}]
        state_manager: Экземпляр StateManager
        channel: Канал (telegram, userbot, max, whatsapp)
    
    Returns:
        dict с результатами обработки
    """
    
    log(f"📨 [{channel}] {user_name}: {message[:50]}...")
    
    # 1. Получаем текущее состояние клиента
    client_state = state_manager.get_state(user_id)
    
    # 2. Подготовка истории для Extractor
    history_for_extractor = [{"role": m["role"], "content": m["content"]} for m in history]
    
    # 3. Извлекаем данные из сообщения (NLU)
    extraction = extract_sync(message, history_for_extractor)
    log(f"🔍 Extractor: {extraction}")
    
    # 4. Обновляем состояние клиента
    state_updates = merge_extraction_to_state(client_state.to_dict(), extraction)
    client_state = state_manager.update_state(user_id, state_updates)
    log(f"📊 State: {client_state.summary()}")
    
    # 5. Определяем следующее действие (Planner)
    micro_goal = None
    tone = "warm"
    
    if USE_LLM_PLANNER:
        try:
            from llm_planner import llm_select_action
            allowed_actions = get_allowed_actions(client_state, message, extraction)
            log(f"🔀 Allowed actions: {[a.value for a in allowed_actions]}")
            
            if len(allowed_actions) > 1:
                llm_result = llm_select_action(allowed_actions, client_state, message, history, extraction)
                action = llm_result["action"]
                micro_goal = llm_result.get("micro_goal")
                tone = llm_result.get("tone", "warm")
                log(f"🤖 LLM Planner: {action.value} | micro_goal: {micro_goal} | tone: {tone}")
            else:
                action = allowed_actions[0]
                log(f"🎯 Single action: {action.value}")
        except Exception as e:
            log(f"⚠️ LLM Planner error: {e}, fallback to deterministic")
            action = get_next_action(client_state, message, extraction)
    else:
        action = get_next_action(client_state, message, extraction)
    
    # Формируем контекст действия
    action_context = get_action_context(action, client_state, extraction)
    if micro_goal:
        action_context["micro_goal"] = micro_goal
    action_context["tone"] = tone
    log(f"🎯 Planner: {action.value} → {action_context.get('action_description', '')[:50]}...")
    
    # 5.0.1 Обогащение финансовым расчётом
    if action == Action.ANSWER_QUESTION and extraction.get("question_type") == "profitability":
        if client_state.budget and client_state.budget > 0:
            try:
                from finance_calculator import compare_investments, format_short_comparison
                fin_result = compare_investments(amount=client_state.budget, construction_years=2, total_years=5)
                action_context["finance_calculation"] = format_short_comparison(fin_result)
                log(f"💰 Finance: расчёт для {client_state.budget/1_000_000:.1f} млн")
            except Exception as e:
                log(f"⚠️ Finance error: {e}")
        else:
            action_context["finance_calculation"] = "Бюджет пока не известен — дай общие цифры (8-12% аренда, 20-30% рост на стройке)"
    
    # 5.1 Увеличиваем счётчик попыток для слота
    ACTION_TO_SLOT = {"payment": "payment_type"}
    if action.value.startswith("ask_"):
        slot = action.value.replace("ask_", "")
        slot = ACTION_TO_SLOT.get(slot, slot)
        increment_slot_attempt(client_state, slot, "ask")
        state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
    elif action.value.startswith("help_"):
        slot = action.value.replace("help_", "")
        slot = ACTION_TO_SLOT.get(slot, slot)
        increment_slot_attempt(client_state, slot, "help")
        state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
    
    # 5.1.1 Увеличиваем счётчик предложений созвона
    if action in [Action.PROPOSE_MEETING_1, Action.PROPOSE_MEETING_2]:
        client_state.call_proposal_count = getattr(client_state, 'call_proposal_count', 0) + 1
    
    # 5.2 Сохраняем поля изменённые в Planner
    v2_updates = {
        "branch": client_state.branch,
        "call_proposal_count": client_state.call_proposal_count,
        "materials_request_count": client_state.materials_request_count,
    }
    
    # 5.2.1 Сохраняем латентные метрики (signals)
    signals = extraction.get("signals", {})
    if signals:
        v2_updates["friction"] = signals.get("friction", 0.3)
        v2_updates["call_readiness"] = signals.get("call_readiness", 0.5)
        v2_updates["engagement"] = signals.get("engagement", "medium")
        v2_updates["urgency"] = signals.get("urgency", "unclear")
    
    # Определяем завершение диалога
    should_notify = False
    notification_type = None
    
    if action == Action.FINISH_WITH_MATERIALS:
        v2_updates["dialog_finished"] = True
        v2_updates["finish_type"] = "materials"
        should_notify = True
        notification_type = "materials"
    elif action == Action.CONFIRM_MEETING:
        v2_updates["dialog_finished"] = True
        v2_updates["finish_type"] = "meeting"
        should_notify = True
        notification_type = "meeting"
    
    state_manager.update_state(user_id, v2_updates)
    
    # 6. Проверка WAIT
    if action == Action.WAIT:
        log(f"⏸️ WAIT (Planner): пропускаем ответ")
        return {
            "response": None,
            "action": action.value,
            "action_context": action_context,
            "client_state": client_state,
            "should_notify": False,
            "notification_type": None,
            "skip_response": True
        }
    
    # 7. Очищаем временные флаги
    state_manager.clear_temporary_flags(user_id)
    
    return {
        "response": None,
        "action": action.value,
        "action_context": action_context,
        "client_state": client_state,
        "should_notify": should_notify,
        "notification_type": notification_type,
        "skip_response": False
    }
