# sofia_userbot_pyrogram.py — Sofia как обычный пользователь Telegram
# Использует Pyrogram (работает стабильнее Telethon)
# Версия: 1.0

import asyncio
import sys
import os

from pyrogram import Client, filters, enums
from pyrogram.handlers import MessageHandler

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

API_ID = 32374021
API_HASH = "6dc50b91611d636fcc22f5ecb8c96bc6"
SESSION_NAME = "sofia_pyrogram"

# Путь к основной логике Sofia
SOFIA_PATH = "/opt/sofia-gpt"
sys.path.insert(0, SOFIA_PATH)

# ============================================
# ЗАГРУЗКА SOFIA
# ============================================

# Загружаем .env для OpenAI
from dotenv import load_dotenv
load_dotenv(f"{SOFIA_PATH}/.env")

SOFIA_AVAILABLE = False
try:
    from extractor import extract_sync
    from state_manager import StateManager
    from planner import get_next_action, get_action_context, Action
    from rag_module import search_examples, format_examples_for_prompt, init_vector_store
    import openai
    
    # Инициализация
    state_manager = StateManager(f"{SOFIA_PATH}/sofia_gpt.db")
    init_vector_store()
    
    # OpenAI client
    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    SOFIA_AVAILABLE = True
    print("✅ Логика Sofia подключена")
except ImportError as e:
    print(f"⚠️ Sofia не подключена: {e}")
    print("   Бот будет работать в режиме эхо")

# История диалогов (в памяти)
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
        
        # 1. Extractor
        extraction = extract_sync(message, history[-6:] if history else None)
        
        # 2. State Manager
        client_state = state_manager.get_state(user_id)
        if extraction:
            state_updates = {}
            for field in ['goal', 'location', 'budget', 'payment_type', 'lpr']:
                if extraction.get(field):
                    state_updates[field] = extraction[field]
                    conf_field = f"{field}_confidence"
                    if extraction.get(conf_field):
                        state_updates[conf_field] = extraction[conf_field]
            if state_updates:
                client_state = state_manager.update_state(user_id, state_updates)
        
        # 3. Planner
        action = get_next_action(client_state, message, extraction or {})
        action_context = get_action_context(action, client_state, extraction or {})
        
        # 4. RAG
        examples = search_examples("QUALIFICATION", message, limit=3)
        examples_text = format_examples_for_prompt(examples) if examples else ""
        
        # 5. Generator (OpenAI)
        response = await generate_with_openai(user_name, message, history, action_context, examples_text)
        
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


async def generate_with_openai(user_name: str, message: str, history: list, action_context: dict, examples: str) -> str:
    """Генерирует ответ через OpenAI"""
    
    system_prompt = f"""Ты — София, менеджер по продаже курортной недвижимости Oazis Estate.
Говори кратко (1-3 предложения), дружелюбно, по делу.
Задавай один вопрос за раз.
Клиента зовут {user_name}.

{action_context.get('action_description', '')}

{examples}
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Добавляем историю
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ OpenAI ошибка: {e}")
        return generate_fallback(action_context, user_name)


def generate_fallback(action_context: dict, user_name: str) -> str:
    """Запасные ответы если OpenAI недоступен"""
    
    action = action_context.get('action', 'unknown')
    
    responses = {
        "ASK_GOAL": f"{user_name}, подскажите — рассматриваете для себя или как инвестицию?",
        "ASK_LOCATION": "По локации — море или горы интересуют?",
        "ASK_BUDGET": "На какой бюджет ориентируетесь?",
        "ASK_PAYMENT": "По оплате — полная сумма или рассрочка?",
        "ASK_LPR": "Решение сами принимаете или с кем-то?",
        "PROPOSE_MEETING": f"{user_name}, давайте созвонимся на 15 минут — покажу варианты. Когда удобно?",
    }
    
    return responses.get(action, "Расскажите подробнее, что для вас важно?")


# ============================================
# PYROGRAM HANDLERS
# ============================================

app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, workdir=".")

@app.on_message(filters.private & filters.incoming & ~filters.me)
async def handle_message(client, message):
    """Обрабатывает входящие личные сообщения"""
    
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "друг"
    text = message.text
    
    if not text:
        return
    
    print(f"📩 {user_name}: {text}")
    
    # Показываем "печатает..."
    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    await asyncio.sleep(1.5)
    
    # Обрабатываем
    response = await process_with_sofia(user_id, user_name, text)
    
    # Отправляем
    await message.reply(response)
    print(f"📤 София: {response}")


# ============================================
# КОМАНДЫ ДЛЯ ОТПРАВКИ ПЕРВЫМ
# ============================================

async def send_first_message(target: str, text: str):
    """Отправляет первое сообщение (главная фишка!)"""
    async with app:
        try:
            await app.send_message(target, text)
            print(f"✅ Отправлено → {target}")
            return True
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False


# ============================================
# ИНТЕРАКТИВНЫЙ РЕЖИМ
# ============================================

async def interactive():
    """Интерактивный режим"""
    print("\n" + "="*50)
    print("🤖 Sofia Userbot (Pyrogram)")
    print("="*50)
    print("\nКоманды:")
    print("  /send @username Текст — отправить первое сообщение")
    print("  /send +79123456789 Текст — отправить по номеру")
    print("  /quit — выход")
    print("\nВходящие сообщения обрабатываются автоматически.")
    print("="*50 + "\n")
    
    while True:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(None, input, "Sofia> ")
            
            if cmd.startswith("/send "):
                parts = cmd[6:].split(" ", 1)
                if len(parts) == 2:
                    target, text = parts
                    await app.send_message(target, text)
                    print(f"✅ Отправлено → {target}")
                else:
                    print("Формат: /send @username Текст")
                    
            elif cmd == "/quit":
                print("👋 Выход...")
                await app.stop()
                break
                
        except Exception as e:
            print(f"Ошибка: {e}")


async def main():
    print("🚀 Запуск Sofia Userbot...")
    
    await app.start()
    
    me = await app.get_me()
    print(f"✅ Авторизован как: {me.first_name} (@{me.username or 'нет'})")
    
    await interactive()


if __name__ == "__main__":
    app.run(main())
