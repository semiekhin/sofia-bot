# sofia_userbot.py — Sofia как обычный пользователь Telegram
# Может писать первым, выглядит как человек
# Версия: 1.0

import asyncio
import os
import sys
from telethon import TelegramClient, events
from telethon.tl.types import PeerUser

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

API_ID = 32374021
API_HASH = "6dc50b91611d636fcc22f5ecb8c96bc6"
SESSION_NAME = "sofia_session"

# Путь к основной логике Sofia
SOFIA_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SOFIA_PATH)

# ============================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Импортируем логику Sofia (после добавления пути)
try:
    from extractor import extract_sync
    from planner import Planner, Action
    from state_manager import StateManager
    from sofia_prompt import get_system_prompt
    from rag_module import search_examples, format_examples_for_prompt

    SOFIA_AVAILABLE = True
    print("✅ Логика Sofia подключена")
except ImportError as e:
    SOFIA_AVAILABLE = False
    print(f"⚠️ Sofia не подключена: {e}")
    print("   Бот будет работать в режиме эхо")

# State manager
if SOFIA_AVAILABLE:
    state_manager = StateManager(f"{SOFIA_PATH}/sofia_gpt.db")
    planner = Planner()

# История диалогов (в памяти для userbot)
conversations = {}

# ============================================
# ОБРАБОТКА СООБЩЕНИЙ
# ============================================


async def process_with_sofia(user_id: int, user_name: str, message: str) -> str:
    """Обрабатывает сообщение через логику Sofia"""

    if not SOFIA_AVAILABLE:
        return f"Эхо: {message}"

    try:
        # Получаем историю
        history = conversations.get(user_id, [])

        # 1. Extractor — понимаем что сказал клиент
        extraction = extract_sync(message, history[-6:] if history else None)

        # 2. State Manager — обновляем состояние
        client_state = state_manager.get_state(user_id)
        if extraction:
            state_updates = {}
            for field in ["goal", "location", "budget", "payment_type", "lpr"]:
                if extraction.get(field):
                    state_updates[field] = extraction[field]
                    conf_field = f"{field}_confidence"
                    if extraction.get(conf_field):
                        state_updates[conf_field] = extraction[conf_field]
            if state_updates:
                client_state = state_manager.update_state(user_id, state_updates)

        # 3. Planner — выбираем действие
        action, action_context = planner.plan(client_state, extraction or {})

        # 4. RAG — ищем примеры
        examples = search_examples("QUALIFICATION", message, limit=3)
        examples_text = format_examples_for_prompt(examples) if examples else ""

        # 5. Generator — генерируем ответ (упрощённая версия)
        # В полной версии здесь вызов OpenAI
        response = generate_simple_response(
            action, action_context, user_name, extraction
        )

        # Сохраняем в историю
        if user_id not in conversations:
            conversations[user_id] = []
        conversations[user_id].append({"role": "user", "content": message})
        conversations[user_id].append({"role": "assistant", "content": response})

        return response

    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback

        traceback.print_exc()
        return "Секунду, связь подвисла. Напишите ещё раз?"


def generate_simple_response(
    action, context: dict, user_name: str, extraction: dict
) -> str:
    """Простой генератор ответов (без OpenAI для теста)"""

    action_name = action.name if hasattr(action, "name") else str(action)

    responses = {
        "ASK_GOAL": f"{user_name}, подскажите — рассматриваете для себя или как инвестицию под сдачу?",
        "ASK_LOCATION": "А по локации — море или горы больше интересуют?",
        "ASK_BUDGET": "На какой бюджет ориентируетесь, примерно?",
        "ASK_PAYMENT": "По оплате — полная сумма или рассматриваете рассрочку/ипотеку?",
        "ASK_LPR": "Решение будете принимать сами или с кем-то советоваться?",
        "PROPOSE_MEETING": f"{user_name}, давайте сделаем короткий видео-созвон на 15 минут — покажу конкретные варианты под ваш запрос. Когда удобно?",
        "HELP_GOAL": "Просто от этого зависит выбор объекта — под сдачу одни варианты, для себя другие. Что ближе?",
        "HELP_LOCATION": "Море и горы — разная доходность и сезонность. Что вам ближе по духу?",
        "HELP_BUDGET": "Примерно: до 10 млн — студии, 10-15 млн — апартаменты, от 15 млн — премиум. Куда смотрим?",
        "WAIT": "Хорошо, жду!",
    }

    return responses.get(
        action_name, f"Поняла! Расскажите подробнее, что для вас важно?"
    )


# ============================================
# ОБРАБОТЧИК ВХОДЯЩИХ СООБЩЕНИЙ
# ============================================


@client.on(events.NewMessage(incoming=True))
async def handle_incoming(event):
    """Обрабатывает входящие сообщения"""

    # Игнорируем групповые чаты и каналы
    if event.is_group or event.is_channel:
        return

    sender = await event.get_sender()
    user_id = sender.id
    user_name = sender.first_name or "друг"
    message = event.message.text

    if not message:
        return

    print(f"📩 {user_name}: {message}")

    # Показываем "печатает..."
    async with client.action(event.chat_id, "typing"):
        await asyncio.sleep(1.5)  # Имитация набора

        # Обрабатываем через Sofia
        response = await process_with_sofia(user_id, user_name, message)

    # Отправляем ответ
    await event.respond(response)
    print(f"📤 София: {response}")


# ============================================
# КОМАНДЫ
# ============================================


async def send_first_message(phone_or_username: str, message: str):
    """Отправляет первое сообщение (главная фишка userbot!)"""
    try:
        await client.send_message(phone_or_username, message)
        print(f"✅ Отправлено → {phone_or_username}: {message}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False


async def interactive_mode():
    """Интерактивный режим для тестирования"""
    print("\n" + "=" * 50)
    print("🤖 Sofia Userbot запущен!")
    print("=" * 50)
    print("\nКоманды:")
    print("  /send @username Текст — отправить первое сообщение")
    print("  /send +79123456789 Текст — отправить по номеру")
    print("  /quit — выход")
    print("\nВходящие сообщения обрабатываются автоматически.")
    print("=" * 50 + "\n")

    while True:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(None, input, "Sofia> ")

            if cmd.startswith("/send "):
                parts = cmd[6:].split(" ", 1)
                if len(parts) == 2:
                    target, text = parts
                    await send_first_message(target, text)
                else:
                    print("Формат: /send @username Текст")

            elif cmd == "/quit":
                print("👋 Выход...")
                break

            elif cmd:
                print("Неизвестная команда. Используй /send или /quit")

        except EOFError:
            break


# ============================================
# ЗАПУСК
# ============================================


async def main():
    print("🚀 Запуск Sofia Userbot...")

    await client.start()

    me = await client.get_me()
    print(f"✅ Авторизован как: {me.first_name} (@{me.username or 'без username'})")
    print(f"   Номер: +{me.phone}")

    # Запускаем интерактивный режим
    await interactive_mode()


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
