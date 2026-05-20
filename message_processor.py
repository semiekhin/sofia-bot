"""
Единый процессор сообщений Sofia-GPT v3.0
Extractor → State → Signals
Planner убран — решения принимает LLM-Генератор (архитектура v3.0)
"""

from datetime import datetime

# Импорты из проекта
from extractor import extract_sync, merge_extraction_to_state


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
    channel: str = "telegram",
    count_materials: bool = True,
) -> dict:
    """
    Обработка сообщений v3.0: Extractor → State → Signals.
    
    Planner и LLM-Planner убраны — все решения по ответу
    принимает LLM-Генератор на основе полного контекста.
    
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
    
    # 2. Если диалог был завершён [END], но клиент написал снова — сбрасываем
    #    (промпт: "Если клиент после [END] напишет снова — отвечай нормально")
    if client_state.dialog_finished:
        state_manager.update_state(user_id, {"dialog_finished": False, "finish_type": None})
        client_state.dialog_finished = False
        client_state.finish_type = None
        log(f"🔄 [{channel}] dialog_finished сброшен — клиент написал снова")
    
    # 3. Извлекаем факты из сообщения (Extractor / NLU)
    history_for_extractor = [{"role": m["role"], "content": m["content"]} for m in history]
    extraction = extract_sync(message, history_for_extractor)
    log(f"🔍 [{channel}] Extractor: {extraction}")
    
    # 4. Обновляем состояние клиента
    state_updates = merge_extraction_to_state(client_state.to_dict(), extraction)
    client_state = state_manager.update_state(user_id, state_updates)
    log(f"📊 [{channel}] State: {client_state.summary()}")
    
    # 5. Сохраняем латентные метрики (signals)
    signals = extraction.get("signals", {})
    if signals:
        signal_updates = {
            "friction": signals.get("friction", 0.3),
            "call_readiness": signals.get("call_readiness", 0.5),
            "engagement": signals.get("engagement", "medium"),
            "urgency": signals.get("urgency", "unclear"),
        }
        state_manager.update_state(user_id, signal_updates)
    
    # 6. Счётчик отказов от созвона (на основе Extractor)
    #    Нужен для state_summary → Генератор видит "БЫЛ 1 ОТКАЗ ОТ СОЗВОНА".
    #    count_materials=False — инкремент откладывается до send_callback
    #    (Radist cancel-restart: иначе rerun накручивает счётчик). Флаг
    #    wants_materials возвращается ниже для отложенного инкремента.
    if client_state.wants_materials and count_materials:
        new_count = (client_state.materials_request_count or 0) + 1
        state_manager.update_state(user_id, {"materials_request_count": new_count})
        log(f"📊 [{channel}] materials_request_count → {new_count}")
    
    # 7. Очищаем временные флаги
    state_manager.clear_temporary_flags(user_id)
    
    return {
        "client_state": client_state,
        "skip_response": False,
        "wants_materials": bool(client_state.wants_materials),
    }
