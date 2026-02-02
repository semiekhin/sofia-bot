"""
Очередь сообщений для Sofia-GPT
Решает race condition при параллельных сообщениях от одного клиента

Версия: 1.0
Дата: 2026-02-02
"""

import asyncio
from datetime import datetime
from typing import Dict, Callable

# Хранилище: user_key → {"lock": Lock, "queue": [...], "processing": bool}
_user_data: Dict[str, dict] = {}


def _log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [QUEUE] {message}")


def _get_user_data(user_key: str) -> dict:
    """Получает или создаёт структуру данных для пользователя"""
    if user_key not in _user_data:
        _user_data[user_key] = {
            "lock": asyncio.Lock(),
            "queue": [],
            "processing": False
        }
    return _user_data[user_key]


async def process_with_queue(
    user_key: str,
    message: str,
    context: dict,
    processor: Callable
) -> None:
    """
    Обрабатывает сообщение с защитой от race condition.
    
    Если обработка уже идёт — добавляет в очередь.
    Если нет — запускает обработку.
    После генерации ответа проверяет очередь — если есть новые,
    объединяет и перегенерирует.
    
    Args:
        user_key: Уникальный ключ (например "telegram:38136000")
        message: Текст сообщения
        context: Контекст для processor
        processor: async функция(combined_message: str, context: dict) -> dict
    """
    data = _get_user_data(user_key)
    
    async with data["lock"]:
        if data["processing"]:
            # Обработка уже идёт — добавляем в очередь
            data["queue"].append({"message": message, "context": context})
            _log(f"📥 {user_key}: добавлено в очередь ({len(data['queue'])} сообщ.)")
            return
        
        # Начинаем обработку
        data["processing"] = True
        _log(f"🔄 {user_key}: начинаем обработку")
    
    # Обрабатываем (вне lock чтобы не блокировать добавление в очередь)
    try:
        await _process_loop(user_key, message, context, processor)
    except Exception as e:
        _log(f"❌ {user_key}: ошибка обработки: {e}")
    finally:
        async with data["lock"]:
            data["processing"] = False
            _log(f"🏁 {user_key}: обработка завершена")


async def _process_loop(
    user_key: str,
    message: str,
    context: dict,
    processor: Callable
) -> None:
    """
    Цикл обработки: генерирует ответ, проверяет очередь, при необходимости повторяет.
    """
    current_message = message
    current_context = context
    iteration = 0
    max_iterations = 5  # защита от бесконечного цикла
    
    while iteration < max_iterations:
        iteration += 1
        _log(f"🔄 {user_key}: итерация {iteration}, сообщение: '{current_message[:50]}...'")
        
        # Вызываем processor — генерирует ответ
        result = await processor(current_message, current_context)
        
        # Проверяем очередь ПЕРЕД отправкой
        data = _get_user_data(user_key)
        async with data["lock"]:
            if data["queue"]:
                # Есть новые сообщения — объединяем и перегенерируем
                queued = data["queue"]
                data["queue"] = []
                
                new_messages = [q["message"] for q in queued]
                combined = current_message + "\n" + "\n".join(new_messages)
                
                _log(f"📦 {user_key}: +{len(new_messages)} сообщ. в очереди, объединяем и перезапускаем")
                
                current_message = combined
                current_context = queued[-1]["context"]  # последний контекст
                continue  # Обрабатываем заново
            else:
                # Очередь пуста — отправляем
                _log(f"✅ {user_key}: очередь пуста, отправляем ответ")
                
                if result.get("send_callback"):
                    await result["send_callback"]()
                
                return
    
    _log(f"⚠️ {user_key}: достигнут лимит итераций ({max_iterations})")


def get_queue_stats() -> dict:
    """Статистика очередей (для отладки)"""
    return {
        user_key: {
            "queue_size": len(data["queue"]),
            "processing": data["processing"]
        }
        for user_key, data in _user_data.items()
    }
