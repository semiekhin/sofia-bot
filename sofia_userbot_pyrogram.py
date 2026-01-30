# sofia_userbot_pyrogram.py — Sofia как обычный пользователь Telegram
# Использует Pyrogram (работает стабильнее Telethon)
# Версия: 2.0

import asyncio
import sys
import os

from pyrogram import Client, filters, enums
from pyrogram.handlers import MessageHandler

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
SESSION_NAME = "sofia_pyrogram"

# Путь к основной логике Sofia
SOFIA_PATH = "/opt/sofia-gpt"

# Группа для трансляции диалогов (наблюдатели)
OBSERVER_CHAT_ID = -5206139579
sys.path.insert(0, SOFIA_PATH)

# ============================================
# ЗАГРУЗКА SOFIA
# ============================================

# Загружаем .env для OpenAI
from dotenv import load_dotenv
load_dotenv(f"{SOFIA_PATH}/.env")

SOFIA_AVAILABLE = False
try:
    from extractor import extract_sync, merge_extraction_to_state
    from state_manager import StateManager
    from planner import get_next_action, get_allowed_actions, get_action_context, Action, increment_slot_attempt
    from message_processor import process_message
    from sofia_prompt import get_system_prompt, BOT_NAME, PRICE_CATALOG
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
# ЛОГИРОВАНИЕ
# ============================================

LOG_PATH = "/opt/sofia-gpt/userbot.log"

def log(message: str):
    """Логирует в файл и консоль"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except:
        pass


async def broadcast_to_observers(app, user_name: str, user_id: int, user_msg: str, sofia_msg: str):
    """Транслирует диалог в группу наблюдателей"""
    if not OBSERVER_CHAT_ID:
        return
    
    try:
        text = f"""💬 <b>Диалог с {user_name}</b> (ID: {user_id})

👤 <b>Клиент:</b>
{user_msg}

🤖 <b>София:</b>
{sofia_msg}"""
        
        await app.send_message(
            OBSERVER_CHAT_ID, 
            text,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        log(f"⚠️ Ошибка трансляции: {e}")

# ============================================
# НАСТРОЙКИ v2.0 (синхронизированы с bot_server.py)
# ============================================

RAG_EXAMPLES_COUNT = 10

# Модель OpenAI (из .env, как в bot_server.py)
MODEL_MODE = os.getenv("MODEL_MODE", "gpt-5.2")
USE_LLM_PLANNER = os.getenv("USE_LLM_PLANNER", "false").lower() == "true"

# Маппинг action name → slot name (для несовпадающих имён)
ACTION_TO_SLOT = {"payment": "payment_type"}

# Маппинг Action → Stage для RAG
ACTION_TO_RAG_STAGE = {
    "ask_goal": "QUALIFICATION",
    "ask_location": "QUALIFICATION",
    "ask_budget": "QUALIFICATION",
    "ask_strategy": "QUALIFICATION",
    "ask_usage": "QUALIFICATION",
    "ask_family": "QUALIFICATION",
    "ask_payment": "QUALIFICATION",
    "ask_first_payment": "QUALIFICATION",
    "ask_lpr": "QUALIFICATION",
    "help_goal": "QUALIFICATION",
    "help_location": "QUALIFICATION",
    "help_budget": "QUALIFICATION",
    "help_payment": "QUALIFICATION",
    "help_lpr": "QUALIFICATION",
    "answer_question": "PRESENTATION",
    "handle_objection": "OBJECTION",
    "clarify_mentioned": "QUALIFICATION",
    "propose_meeting": "MEETING",
    "propose_meeting_1": "MEETING",
    "propose_meeting_2": "MEETING",
    "confirm_meeting": "CLOSING",
    "finish_with_materials": "CLOSING",
    "send_materials": "PRESENTATION",
    "ease_pressure": "OBJECTION",
    "greeting": "GREETING",
}

# ============================================
# ОБРАБОТКА СООБЩЕНИЙ
# ============================================

async def process_with_sofia(user_id: int, user_name: str, message: str) -> str:
    """Обрабатывает сообщение через единый message_processor"""
    
    if not SOFIA_AVAILABLE:
        return f"Эхо: {message}"
    
    try:
        # Получаем историю из памяти
        history = conversations.get(user_id, [])
        history_list = history[-8:] if history else []
        
        # Единая обработка через message_processor
        result = await process_message(
            user_id=user_id,
            user_name=user_name,
            message=message,
            history=history_list,
            state_manager=state_manager,
            channel="userbot"
        )
        
        # Если WAIT — не отвечаем
        if result["skip_response"]:
            log(f"⏸️ WAIT (Planner): пропускаем ответ")
            return None
        
        action_context = result["action_context"]
        client_state = result["client_state"]
        
        # RAG — ищем примеры
        action_value = result["action"]
        rag_stage = ACTION_TO_RAG_STAGE.get(action_value, "QUALIFICATION")
        examples = search_examples(rag_stage, message, limit=RAG_EXAMPLES_COUNT)
        examples_text = format_examples_for_prompt(examples) if examples else ""
        log(f"📚 RAG: {len(examples) if examples else 0} примеров для {rag_stage}")
        
        # Generator (OpenAI)
        response = await generate_with_openai(user_name, message, history_list, action_context, examples_text)
        
        # Сохраняем в историю
        if user_id not in conversations:
            conversations[user_id] = []
        conversations[user_id].append({"role": "user", "content": message})
        conversations[user_id].append({"role": "assistant", "content": response})
        
        return response
        
    except Exception as e:
        log(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return "Секунду, связь подвисла. Напишите ещё раз?"


async def generate_with_openai(user_name: str, message: str, history: list, action_context: dict, examples: str) -> str:
    """Генерирует ответ через OpenAI с полным промптом Sofia"""
    
    # Используем полный промпт из sofia_prompt.py
    system_prompt = get_system_prompt(user_name, action_context)
    
    # Добавляем RAG примеры
    if examples:
        system_prompt += f"""

════════════════════════════════════════════════════════════════════════════════
ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ (RAG)
════════════════════════════════════════════════════════════════════════════════
{examples}
"""
    
    # Формируем messages для API (без system — он идёт в instructions)
    messages = []
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})
    
    try:
        # GPT-5.2 Responses API (как в bot_server.py)
        response = openai_client.responses.create(
            model=MODEL_MODE,
            instructions=system_prompt,
            input=messages,
            text={"verbosity": "low"},
        )
        return response.output_text
    except Exception as e:
        log(f"❌ OpenAI ошибка: {e}")
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
    
    log(f"📩 {user_name}: {text}")
    
    # Показываем "печатает..."
    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    await asyncio.sleep(1.5)
    
    # Обрабатываем
    response = await process_with_sofia(user_id, user_name, text)
    
    # Проверяем WAIT
    if response is None:
        log(f"⏸️ WAIT: не отвечаем на это сообщение")
        return
    
    # Отправляем
    await message.reply(response)
    log(f"📤 София: {response}")
    
    # Транслируем в группу наблюдателей
    # ТЕСТ:     await broadcast_to_observers(app, user_name, user_id, text, response)


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
# УМНЫЙ СТАРТ ДИАЛОГА
# ============================================

async def start_smart_dialog(target: str, lead_info: dict = None) -> bool:
    """
    Начинает диалог с новым лидом через логику Sofia.
    
    target: @username или +79123456789
    lead_info: опционально {name: "Иван", source: "avito", ...}
    """
    try:
        print(f"\n{'='*60}")
        log(f"🚀 START_SMART_DIALOG: {target}")
        print(f"{'='*60}")
        
        # Получаем user_id из Telegram
        user = await app.get_users(target)
        user_id = user.id
        user_name = user.first_name or "друг"
        
        log(f"📱 Telegram user: {user_name} (ID: {user_id})")
        log(f"📋 Lead info: {lead_info}")
        
        # Сбрасываем состояние (новый лид)
        state_manager.reset_state(user_id)
        log(f"🗑️ State reset для user_id={user_id}")
        
        # Создаём начальное состояние
        client_state = state_manager.get_state(user_id)
        log(f"📊 Initial state: goal={client_state.goal}, location={client_state.location}, budget={client_state.budget}")
        
        # Если есть инфо о лиде — сохраняем
        if lead_info:
            updates = {}
            if lead_info.get('goal'):
                updates['goal'] = lead_info['goal']
                updates['goal_confidence'] = 'mentioned'
            if lead_info.get('location'):
                updates['location'] = lead_info['location']
                updates['location_confidence'] = 'mentioned'
            if lead_info.get('budget'):
                updates['budget'] = lead_info['budget']
                updates['budget_confidence'] = 'mentioned'
            if updates:
                client_state = state_manager.update_state(user_id, updates)
        
        # Planner определяет первое действие
        action = get_next_action(client_state, "", {})
        action_context = get_action_context(action, client_state, {})
        
        log(f"🎯 PLANNER DECISION:")
        log(f"   Action: {action.value}")
        log(f"   is_qualified: {client_state.is_qualified()}")
        log(f"   missing_fields: {client_state.get_missing_fields()}")
        log(f"   slot_attempts: {client_state.slot_attempts}")
        
        # Генерируем первое сообщение
        # Для первого сообщения используем специальный промпт
        first_message = await generate_first_message(user_name, action_context, lead_info)
        
        # Отправляем
        log(f"📝 GENERATED MESSAGE:")
        log(f"   {first_message}")
        
        await app.send_message(target, first_message)
        log(f"✅ SENT TO TELEGRAM → {target}")
        
        # Сохраняем в историю
        if user_id not in conversations:
            conversations[user_id] = []
        conversations[user_id].append({"role": "assistant", "content": first_message})
        
        # Инкрементируем счётчик если это ASK_*
        if action.value.startswith("ask_"):
            slot = action.value.replace("ask_", "")
            slot = ACTION_TO_SLOT.get(slot, slot)  # payment → payment_type
            increment_slot_attempt(client_state, slot, "ask")
            state_manager.update_state(user_id, {"slot_attempts": client_state.slot_attempts})
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


async def generate_first_message(user_name: str, action_context: dict, lead_info: dict = None) -> str:
    """Генерирует первое сообщение для нового лида"""
    
    # Контекст откуда пришёл лид
    source_context = ""
    if lead_info:
        if lead_info.get('source') == 'avito':
            source_context = "Клиент оставил заявку на Avito."
        elif lead_info.get('source') == 'cian':
            source_context = "Клиент оставил заявку на ЦИАН."
        elif lead_info.get('source') == 'website':
            source_context = "Клиент оставил заявку на сайте."
        elif lead_info.get('ad_text'):
            source_context = f"Клиент откликнулся на объявление: {lead_info['ad_text'][:100]}"
    
    # Используем базовый промпт Sofia + специфика первого сообщения
    base_prompt = get_system_prompt(user_name, action_context)
    
    system_prompt = f"""{base_prompt}

════════════════════════════════════════════════════════════════════════════════
СПЕЦИФИКА: ЭТО ПЕРВОЕ СООБЩЕНИЕ
════════════════════════════════════════════════════════════════════════════════

{source_context}

Это ПЕРВОЕ сообщение — клиент ещё не писал тебе.

ФОРМАТ ПЕРВОГО СООБЩЕНИЯ:
"{user_name}, добрый день! Это София, по недвижимости. Вы оставляли заявку на сайте — удобно сейчас пообщаться?"

После ответа клиента начнёшь квалификацию.
НЕ задавай квалификационные вопросы в первом сообщении!
"""

    messages = [
        {"role": "user", "content": "Сгенерируй первое сообщение клиенту."}
    ]
    
    try:
        # GPT-5.2 Responses API
        response = openai_client.responses.create(
            model=MODEL_MODE,
            instructions=system_prompt,
            input=messages,
            text={"verbosity": "low"},
        )
        return response.output_text
    except Exception as e:
        log(f"❌ OpenAI ошибка: {e}")
        # Fallback
        return f"Привет, {user_name}! Я София из Oazis Estate. Подскажите, рассматриваете недвижимость для себя или как инвестицию?"


# ============================================
# ИНТЕРАКТИВНЫЙ РЕЖИМ
# ============================================

async def interactive():
    """Интерактивный режим"""
    print("\n" + "="*50)
    print("🤖 Sofia Userbot (Pyrogram)")
    print("="*50)
    print("\nКоманды:")
    print("  /start @username — умный старт диалога (через Planner)")
    print("  /start @username avito — старт с указанием источника")
    print("  /send @username Текст — отправить произвольный текст")
    print("  /quit — выход")
    print("\nВходящие сообщения обрабатываются автоматически.")
    print("="*50 + "\n")
    
    while True:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(None, input, "Sofia> ")
            
            if cmd.startswith("/start "):
                parts = cmd[7:].split()
                if len(parts) >= 1:
                    target = parts[0]
                    source = parts[1] if len(parts) > 1 else None
                    lead_info = {"source": source} if source else None
                    await start_smart_dialog(target, lead_info)
                else:
                    print("Формат: /start @username [источник]")
            
            elif cmd.startswith("/send "):
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


async def main_daemon():
    """Daemon режим — только слушает входящие, без интерактивных команд"""
    print("🚀 Запуск Sofia Userbot (daemon)...")
    
    try:
        await app.start()
    except Exception as e:
        error_msg = str(e)
        if "AUTH_KEY_UNREGISTERED" in error_msg or "401" in error_msg:
            log("❌ СЕССИЯ ИСТЕКЛА! Требуется ручная авторизация:")
            log("   1. systemctl stop sofia-userbot")
            log("   2. rm /opt/sofia-gpt/sofia_pyrogram.session")
            log("   3. python /opt/sofia-gpt/sofia_userbot_pyrogram.py")
            log("   4. systemctl start sofia-userbot")
            sys.exit(0)  # Выход без ошибки — не рестартовать
        else:
            log(f"❌ Ошибка запуска: {e}")
            raise
    
    me = await app.get_me()
    print(f"✅ Авторизован как: {me.first_name} (@{me.username or 'нет'})")
    print("📡 Слушаю входящие сообщения... (Ctrl+C для выхода)")
    
    # Просто держим процесс активным
    from pyrogram import idle
    await idle()


async def main():
    """Интерактивный режим — с командами /start, /send"""
    print("🚀 Запуск Sofia Userbot...")
    
    await app.start()
    
    me = await app.get_me()
    print(f"✅ Авторизован как: {me.first_name} (@{me.username or 'нет'})")
    
    await interactive()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        app.run(main_daemon())
    else:
        app.run(main())
