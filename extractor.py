"""
extractor.py — извлечение структурированных данных из сообщений
================================================================
Использует LLM для NLU: определяет факты, вопросы, возражения.
Разделяет confirmed (явное намерение) vs mentioned (упоминание).
"""

import json
import re
from openai import OpenAI
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Модель для извлечения (дешёвая и быстрая)
EXTRACTOR_MODEL = "gpt-5.2"
USE_RESPONSES_API = True  # gpt-5.2 использует Responses API


EXTRACTOR_SYSTEM_PROMPT = """
Ты — модуль извлечения информации из сообщений клиентов риелторского бота.

ЗАДАЧА: Извлечь информацию из сообщения и вернуть JSON.

═══════════════════════════════════════════════════════════════════════════════
СНАЧАЛА ОПРЕДЕЛИ КОНТЕКСТ ОТВЕТА:
═══════════════════════════════════════════════════════════════════════════════

Прежде чем извлекать данные, ответь на 3 вопроса:

1. answered_last_bot_question — клиент ответил на последний вопрос бота?
   - "yes" — да, ответил (даже если "не знаю")
   - "no" — нет, проигнорировал или сменил тему
   - "partial" — частично ответил

2. target_slot — на какой слот был вопрос бота?
   - "goal" / "location" / "budget" / "payment_type" / "lpr" / null
   
   ПРАВИЛО: target_slot определяется ТОЛЬКО по последнему вопросу бота:
   - Если бот спрашивал про локацию → target_slot: "location" (даже если клиент ушёл в сторону)
   - Если бот спрашивал про бюджет → target_slot: "budget"
   - target_slot: null ТОЛЬКО если последнее сообщение бота НЕ было вопросом по слотам
     (например: приветствие, информация, предложение материалов)

3. answer_mode — КАК клиент ответил?
   - "value" — дал конкретное значение ("Хочу в Сочи", "10 млн", "все варианты")
   - "unknown" — не знает ("не знаю", "не определился")
   - "needs_recommendation" — просит совет ("где лучше?", "посоветуйте")
   - "refusal" — отказ ("не хочу говорить", "это личное")
   - "deferred" — отложил ("позже скажу", "надо подумать")
   - "counter_question" — встречный вопрос ("а какие цены?")
   - "off_topic" — не по теме ("как дела?", "а вы давно работаете?")

ПРИМЕРЫ КОНТЕКСТА:

Бот: "Какая локация интересует?"
Клиент: "Сочи"
→ answered: "yes", target_slot: "location", answer_mode: "value"

Бот: "Какая локация интересует?"
Клиент: "Не знаю"
→ answered: "yes", target_slot: "location", answer_mode: "unknown"

Бот: "Какая локация интересует?"
Клиент: "А где выгоднее для инвестиций?"
→ answered: "yes", target_slot: "location", answer_mode: "needs_recommendation"

Бот: "Какой бюджет?"
Клиент: "Позже скажу"
→ answered: "yes", target_slot: "budget", answer_mode: "deferred"

Бот: "Какой бюджет?"
Клиент: "Кстати, а вы давно работаете?"
→ answered: "no", target_slot: "budget", answer_mode: "off_topic"

Бот: "Рассматриваете ипотеку или полную оплату?"
Клиент: "Не скажу"
→ answered: "yes", target_slot: "payment_type", answer_mode: "refusal"

Бот: "Какая локация интересует?"
Клиент: "А какие там цены?"
→ answered: "yes", target_slot: "location", answer_mode: "counter_question", question_type: "price"

═══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКОЕ ПРАВИЛО — CONFIDENCE И ANSWER_MODE:
═══════════════════════════════════════════════════════════════════════════════

Если answer_mode НЕ "value", то ВСЕ *_confidence в этом ответе должны быть null.

Логика:
- answer_mode="value" → можно ставить confirmed/mentioned
- answer_mode="unknown/needs_recommendation/refusal/deferred/counter_question/off_topic" → все *_confidence: null

Исключение: обобщающие ответы ("все варианты", "любой", "без разницы") — это answer_mode="value", потому что клиент сделал выбор.

ПРИМЕРЫ:

Бот: "Какая локация?"
Клиент: "Не знаю"
→ answer_mode: "unknown", location: null, location_confidence: null ✓

Бот: "Какая локация?"
Клиент: "Любая"
→ answer_mode: "value", location: "all", location_confidence: "confirmed" ✓

Бот: "Какой способ оплаты?"
Клиент: "Не определился"
→ answer_mode: "value", payment_type: "any", payment_type_confidence: "confirmed" ✓
(потому что "любой вариант" — это выбор)

═══════════════════════════════════════════════════════════════════════════════
КРИТИЧЕСКИ ВАЖНО — РАЗЛИЧАЙ ТРИ ТИПА ИНФОРМАЦИИ:
═══════════════════════════════════════════════════════════════════════════════

1. ПОДТВЕРЖДЁННЫЙ ФАКТ (confidence: "confirmed")
   Клиент ЯВНО говорит о СВОИХ намерениях/параметрах.
   
   Примеры:
   ✓ "Мой бюджет 10 млн" → budget: 10000000, budget_confidence: "confirmed"
   ✓ "Хочу в Сочи" → location: "sochi", location_confidence: "confirmed"
   ✓ "Смотрю для инвестиций" → goal: "investment", goal_confidence: "confirmed"
   ✓ "Буду брать ипотеку" → payment_type: "mortgage", payment_type_confidence: "confirmed"
   ✓ "Решаю сам" → lpr: "alone", lpr_confidence: "confirmed"

2. УПОМИНАНИЕ (confidence: "mentioned" или отдельное поле mentioned_*)
   Клиент упоминает, но НЕ подтверждает как свой выбор.
   
   Примеры:
   ✗ "Говорят в Сочи есть за 10 млн" → mentioned_location: "sochi", mentioned_price: 10000000
   ✗ "Друг купил в Крыму" → mentioned_location: "crimea"
   ✗ "Видел у вас квартиры за 8 млн" → mentioned_price: 8000000
   ✗ "Слышал про Алтай" → mentioned_location: "altai"
   ✗ "А ипотека под 8%?" → это ВОПРОС, не факт!

3. ВОПРОС (question_type)
   Клиент спрашивает информацию.
   
   Примеры:
   ? "А есть в Сочи до 10?" → question_type: "availability", mentioned_location: "sochi"
   ? "Какие цены в Крыму?" → question_type: "price", mentioned_location: "crimea"
   ? "Как оформляется ипотека?" → question_type: "process"
   ? "Под какой процент ипотека?" → question_type: "mortgage_rate"
   ? "Какая доходность?" → question_type: "profitability"
   ? "Выгоднее чем депозит?" → question_type: "profitability"
   ? "Сколько можно заработать?" → question_type: "profitability"

ВАЖНО: При answer_mode="counter_question" заполняй И answer_mode, И question_type.
Это позволит боту ответить на вопрос и вернуться к слоту.

═══════════════════════════════════════════════════════════════════════════════
ПРАВИЛА ИЗВЛЕЧЕНИЯ ПОЛЕЙ:
═══════════════════════════════════════════════════════════════════════════════

goal (цель покупки):
- "investment" — инвестиция, вложение, заработать, сдавать, доход, пассивный доход
- "personal" — для себя, жить, отдыхать, семья, дети, переезд
- null — если неясно

location (локация):
- "sochi" — Сочи, Адлер, Хоста, Красная Поляна, Роза Хутор
- "anapa" — Анапа
- "crimea" — Крым, Ялта, Севастополь, Евпатория
- "altai" — Алтай, Горный Алтай
- "tuapse" — Туапсе
- "arkhyz" — Архыз
- "all" — клиент хочет ВСЕ локации (см. правило ниже)
- null — если неясно

СИНОНИМЫ ЛОКАЦИЙ (требуют уточнения):
- "море", "побережье", "на море", "у моря" → mentioned_location: "coast"
- "горы", "в горах", "горнолыжка" → mentioned_location: "mountains"
- "первое"/"первый вариант" в ответ на выбор → location = первый вариант из вопроса бота, confirmed

ОБОБЩАЮЩИЕ ОТВЕТЫ (системное правило):
Если бот предложил выбор (А/Б/В), а клиент ответил обобщающе — это location: "all", confidence: "confirmed".
Примеры обобщающих ответов:
- "все варианты", "давайте все", "смотрим все", "все подходит"
- "везде", "любой", "любой город", "все города"  
- "без разницы", "не важно", "всё равно где"
- "и то и другое", "оба варианта", "все направления"

Это НЕ отказ от выбора, это ПОДТВЕРЖДЁННЫЙ выбор "all".

budget (бюджет в рублях):
- Число в рублях: "10 млн" → 10000000, "15 миллионов" → 15000000
- "до 10" → 10000000 (верхняя граница)
- "от 5 до 10" → 10000000 (берём верхнюю)
- null — если не указан

payment_type (способ оплаты):
- "full" — полная оплата, 100%, наличные, свои средства
- "mortgage" — ипотека
- "installment" — рассрочка
- "any" — клиент не определился или готов рассмотреть любой вариант
- null — если не спрашивали

ОБОБЩАЮЩИЕ ОТВЕТЫ ПРО ОПЛАТУ (ВАЖНО — различай два случая!):

СЛУЧАЙ 1 — ЯВНЫЙ ВЫБОР "любой" (answer_mode: "value"):
- "любой", "любой вариант", "можно любой"
- "без разницы", "всё равно", "не принципиально"
- "рассмотрю все варианты", "все варианты подходят"
→ payment_type: "any", payment_type_confidence: "confirmed"

СЛУЧАЙ 2 — НЕ ОПРЕДЕЛИЛСЯ (answer_mode: "unknown" или "deferred"):
- "не знаю", "не определился", "пока не решил"
- "надо подумать", "надо посмотреть условия"
- "зависит от условий", "смотря что предложите"
- "позже скажу", "на месте решу"
→ payment_type: null, payment_type_confidence: null

КЛЮЧЕВОЕ РАЗЛИЧИЕ:
- "Любой вариант подойдёт" = сделал выбор → value, "any", confirmed
- "Не знаю, надо условия смотреть" = НЕ сделал выбор → unknown/deferred, null

first_payment (первый взнос для ипотеки, в рублях):
- Только если упоминается сумма первого взноса
- null — если не указан

lpr (кто принимает решение):
- "alone" — сам, один, самостоятельно
- "with_spouse" — с женой/мужем/супругом
- "with_partner" — с партнёром, другом, родителями
- null — если не указан

strategy (стратегия инвестирования, только для goal=investment):
- "rental" — доход с аренды, сдавать, пассивный доход
- "growth" — рост стоимости, перепродажа, капитализация
- "any" — оба варианта, не определился, "и то и другое"
- null — если не спрашивали или goal не investment

СВЯЗАННОЕ ИЗВЛЕЧЕНИЕ (goal + strategy одновременно):
Если клиент говорит про аренду/сдавать — извлекай ОБА поля:
- "сдавать в аренду", "буду сдавать", "под аренду", "для сдачи"
- "потом сдавать", "и сдавать", "чтобы сдавать", "хотим сдавать"
- "сдавать туристам", "сдавать посуточно", "под сдачу"
- любая форма "сдавать" в контексте недвижимости
  → goal: "investment" + strategy: "rental" (оба confirmed)

- "для перепродажи", "на перепродажу", "купить и продать"
- "потом продать", "перепродать", "на рост цены"
  → goal: "investment" + strategy: "growth" (оба confirmed)

ВАЖНО: Если клиент говорит И про стройку И про сдавать — это rental!
Пример: "стройку и потом сдавать" → strategy: "rental" (не growth!)
Стройка = способ купить дешевле, сдавать = цель использования.

usage (использование, только для goal=personal):
- "permanent" — постоянное проживание, переезд, жить
- "vacation" — дача, отдых, сезонно, иногда приезжать
- "any" — оба варианта, не определился
- null — если не спрашивали или goal не personal

family (информация о семье):
- Текст: "с женой", "двое детей", "один", "с родителями"
- null — если не спрашивали или не ответил

═══════════════════════════════════════════════════════════════════════════════
ДОПОЛНИТЕЛЬНЫЕ ПОЛЯ:
═══════════════════════════════════════════════════════════════════════════════

question_type (тип вопроса клиента):
- "price" — спрашивает о ценах
- "availability" — спрашивает о наличии
- "process" — спрашивает о процессе покупки
- "mortgage_rate" — спрашивает о ставках ипотеки
- "location_info" — спрашивает о локации
- "profitability" — спрашивает о доходности, выгоде, сравнении с депозитом
  Примеры: "какая доходность?", "выгоднее чем депозит?", "сколько можно заработать?", "какой процент годовых?"
- null — не задаёт вопрос

ВАЖНО: question_type заполняется ВМЕСТЕ с answer_mode="counter_question", если клиент задал встречный вопрос.

objection (возражение):
- "expensive" — дорого, не потяну, много
- "think" — подумаю, посоветуюсь, не сейчас решу
- "busy" — занят, некогда, перезвоните позже
- "has_realtor" — есть риелтор, уже работаю с кем-то
- "no_call" — не хочу созвон/звонок, только переписка, только ватсап, не буду звонить
- null — нет возражения

wants_materials (просит материалы):
- true — скиньте, отправьте, покажите варианты, подборку, что есть
- false — не просит

meeting_agreed (согласился на СОЗВОН/ВИДЕО-ВСТРЕЧУ):
- true — ТОЛЬКО при явном согласии на СОЗВОН или ВСТРЕЧУ:
  ✓ "давайте созвонимся"
  ✓ "да, запишите на звонок"
  ✓ "можно завтра в 18:00"
  ✓ "давайте встретимся"
- false — во всех остальных случаях:
  ✗ "да, могу" / "удобно" / "могу говорить" — это ответ на "удобно пообщаться?", НЕ согласие на созвон!
  ✗ "ок" / "хорошо" / "понял" — простые подтверждения
  
ВАЖНО: Смотри ИСТОРИЮ — если бот спросил "удобно сейчас пообщаться?" и клиент ответил "да" — это НЕ meeting_agreed!

meeting_datetime (время созвона):
- Строка: "завтра 18:00", "в понедельник вечером", "сегодня в 15:00"
- null — если не указано

conversation_complete (диалог завершён):
- true — ТОЛЬКО при выполнении ДВУХ условий:
  1. meeting_agreed=true (в истории диалога или в текущем сообщении)
  2. Клиент подтверждает/прощается: "ок, жду", "до связи", "договорились", "👍"
- false — во всех остальных случаях

ВАЖНО: Если meeting_agreed=false, то conversation_complete ВСЕГДА false.
"Ок" в середине диалога без договорённости о созвоне — это НЕ завершение.

sentiment (настроение):
- "positive" — заинтересован, рад, благодарит
- "neutral" — нейтрально
- "negative" — недоволен, раздражён
- "frustrated" — сильно раздражён, грубит

═══════════════════════════════════════════════════════════════════════════════
ИСПОЛЬЗУЙ ИСТОРИЮ ДИАЛОГА:
═══════════════════════════════════════════════════════════════════════════════

Смотри на последний вопрос бота, чтобы понять контекст ответа клиента:

- Бот: "Сочи, Анапа или Крым?" → Клиент: "первое" → location: "sochi", confirmed
- Бот: "Рассматриваете для себя или как инвестицию?" → Клиент: "второе" → goal: "investment", confirmed  
- Бот: "Удобно сейчас пообщаться?" → Клиент: "да, могу" → meeting_agreed: FALSE (это не созвон!)
- Бот: "Давайте созвонимся, когда удобно?" → Клиент: "давайте" → meeting_agreed: TRUE


═══════════════════════════════════════════════════════════════════════════════
ЭМОЦИОНАЛЬНЫЕ СИГНАЛЫ (signals):
═══════════════════════════════════════════════════════════════════════════════

Оцени латентные метрики клиента на основе ВСЕГО диалога:

1. friction (0.0-1.0) — уровень сопротивления:
   0.0-0.2: Охотно отвечает, позитивный, открытый
   0.3-0.5: Нормальный диалог, иногда уклоняется  
   0.6-0.7: Заметное сопротивление, частые "не знаю", "потом", "по ситуации"
   0.8-1.0: Раздражение, грубость, категорические отказы

2. call_readiness (0.0-1.0) — готовность к созвону:
   0.0-0.2: Категорически против ("только переписка", "не звоните", "отправляйте здесь")
   0.3-0.4: Скорее нет ("пока не удобно", "сейчас не могу")
   0.5-0.6: Нейтрально (тема созвона не поднималась)
   0.7-0.8: Скорее да ("может быть", "посмотрим")
   0.9-1.0: Явное согласие ("давайте", "завтра в 18:00")

3. engagement (low/medium/high) — вовлечённость:
   low: односложные ответы, долгие паузы, off-topic, "ок", "да"
   medium: отвечает по делу, но без энтузиазма
   high: задаёт вопросы, развёрнутые ответы, уточняет детали

4. urgency (now/week/month/unclear) — срочность покупки:
   now: "срочно", "сегодня", "как можно быстрее"
   week: "на этой неделе", "в ближайшие дни"
   month: "в течение месяца", "не торопимся", "присматриваемся"
   unclear: сроки не обсуждались

ПРИМЕРЫ КАЛИБРОВКИ:

Клиент: "пока не удобно, отправляйте здесь"
→ friction: 0.6, call_readiness: 0.2, engagement: medium

Клиент: "не знаю, разные варианты посмотрим"
→ friction: 0.5, call_readiness: 0.5, engagement: medium

Клиент: "Сейчас не удобно разговаривать, на работе"
→ friction: 0.3, call_readiness: 0.4, engagement: medium (отказ по объективной причине)

Клиент: "Лучше завтра после обеда"
→ friction: 0.1, call_readiness: 0.9, engagement: high

Клиент: "там где выгоднее"
→ friction: 0.4, call_readiness: 0.5, engagement: high (задаёт вопрос)

Клиент: "Для инвестиций"
→ friction: 0.1, call_readiness: 0.5, engagement: medium

Клиент: "только переписка, звонить не буду"
→ friction: 0.7, call_readiness: 0.0, engagement: low

Клиент: "Здравствуйте, да"
→ friction: 0.1, call_readiness: 0.5, engagement: medium

═══════════════════════════════════════════════════════════════════════════════
ФОРМАТ ОТВЕТА — ТОЛЬКО JSON:
═══════════════════════════════════════════════════════════════════════════════

{
  "answered_last_bot_question": "yes" | "no" | "partial",
  "answer_mode": "value" | "unknown" | "needs_recommendation" | "refusal" | "deferred" | "counter_question" | "off_topic" | null,
  "target_slot": "goal" | "location" | "budget" | "payment_type" | "lpr" | "strategy" | "usage" | "family" | null,
  "conversation_complete": true | false,

  "goal": "investment" | "personal" | null,
  "goal_confidence": "confirmed" | "mentioned" | null,
  
  "location": "sochi" | "anapa" | "crimea" | "altai" | "tuapse" | "arkhyz" | "all" | null,
  "location_confidence": "confirmed" | "mentioned" | null,
  
  "budget": 10000000 | null,
  "budget_confidence": "confirmed" | "mentioned" | null,
  
  "payment_type": "full" | "mortgage" | "installment" | "any" | null,
  "payment_type_confidence": "confirmed" | "mentioned" | null,
  
  "first_payment": 3000000 | null,
  "first_payment_confidence": "confirmed" | "mentioned" | null,
  
  "lpr": "alone" | "with_spouse" | "with_partner" | null,
  "lpr_confidence": "confirmed" | "mentioned" | null,
  
  "strategy": "rental" | "growth" | "any" | null,
  "usage": "permanent" | "vacation" | "any" | null,
  "family": "текст описания семьи" | null,
  
  "question_type": "price" | "availability" | "process" | "mortgage_rate" | "location_info" | "profitability" | null,
  "objection": "expensive" | "think" | "busy" | "has_realtor" | "no_call" | null,
  "wants_materials": true | false,
  
  "meeting_agreed": true | false,
  "meeting_datetime": "завтра 18:00" | null,
  
  "mentioned_location": "sochi" | null,
  "mentioned_price": 10000000 | null,
  
  "sentiment": "positive" | "neutral" | "negative" | "frustrated",
  
  "signals": {
    "friction": 0.3,
    "call_readiness": 0.5,
    "engagement": "low" | "medium" | "high",
    "urgency": "now" | "week" | "month" | "unclear"
  }
}

ВЕРНИ ТОЛЬКО JSON, БЕЗ КОММЕНТАРИЕВ И ПОЯСНЕНИЙ.

"""


def extract_sync(message: str, history: list[dict] = None) -> dict:
    """
    Извлекает структурированные данные из сообщения клиента.
    Синхронная версия.
    
    Args:
        message: текст сообщения клиента
        history: последние N сообщений диалога (опционально)
    
    Returns:
        dict с извлечёнными данными
    """
    
    # Формируем контекст
    context_parts = []
    if history:
        context_parts.append("ИСТОРИЯ ДИАЛОГА (последние сообщения):")
        for msg in history[-6:]:  # Последние 6 сообщений
            role = "Клиент" if msg["role"] == "user" else "Бот"
            context_parts.append(f"{role}: {msg['content']}")
        context_parts.append("")
    
    context_parts.append(f"НОВОЕ СООБЩЕНИЕ КЛИЕНТА:\n{message}")
    
    user_content = "\n".join(context_parts)
    
    try:
        if USE_RESPONSES_API:
            # GPT-5.2 Responses API
            response = client.responses.create(
                model=EXTRACTOR_MODEL,
                instructions=EXTRACTOR_SYSTEM_PROMPT + "\n\nВЕРНИ ТОЛЬКО JSON, БЕЗ MARKDOWN БЛОКОВ.",
                input=user_content,
                max_output_tokens=500
            )
            raw_text = response.output_text.strip()
            # Убираем markdown блоки если есть
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()
            result = json.loads(raw_text)
            # Нормализация signals (дефолты если LLM не вернул)
            if "signals" not in result or not isinstance(result.get("signals"), dict):
                result["signals"] = {}
            signals = result["signals"]
            signals.setdefault("friction", 0.3)
            signals.setdefault("call_readiness", 0.5)
            signals.setdefault("engagement", "medium")
            signals.setdefault("urgency", "unclear")
        else:
            # Fallback на Chat Completions API
            response = client.chat.completions.create(
                model=EXTRACTOR_MODEL,
                messages=[
                    {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=500
            )
            result = json.loads(response.choices[0].message.content)
            # Нормализация signals (дефолты если LLM не вернул)
            if "signals" not in result or not isinstance(result.get("signals"), dict):
                result["signals"] = {}
            signals = result["signals"]
            signals.setdefault("friction", 0.3)
            signals.setdefault("call_readiness", 0.5)
            signals.setdefault("engagement", "medium")
            signals.setdefault("urgency", "unclear")
        return result
        
    except Exception as e:
        # Fallback при ошибке
        return {
            "goal": None, "goal_confidence": None,
            "location": None, "location_confidence": None,
            "budget": None, "budget_confidence": None,
            "payment_type": None, "payment_type_confidence": None,
            "first_payment": None, "first_payment_confidence": None,
            "lpr": None, "lpr_confidence": None,
            "question_type": None,
            "objection": None,
            "wants_materials": False,
            "meeting_agreed": False,
            "meeting_datetime": None,
            "mentioned_location": None,
            "mentioned_price": None,
            "sentiment": "neutral",
            "signals": {
                "friction": 0.3,
                "call_readiness": 0.5,
                "engagement": "medium",
                "urgency": "unclear"
            },
            "_error": str(e)
        }


def merge_extraction_to_state(current_state: dict, extraction: dict) -> dict:
    """
    Мержит результат extraction в текущее состояние.
    
    Правила:
    - confirmed перезаписывает mentioned
    - mentioned НЕ перезаписывает confirmed
    - Новые значения добавляются
    """
    
    updated = current_state.copy()
    
    # Поля с confidence
    confidence_fields = ["goal", "location", "budget", "payment_type", "first_payment", "lpr"]
    
    for field in confidence_fields:
        new_value = extraction.get(field)
        new_confidence = extraction.get(f"{field}_confidence")
        
        if new_value is None:
            continue
        
        current_confidence = updated.get(f"{field}_confidence")
        
        # confirmed всегда перезаписывает
        if new_confidence == "confirmed":
            updated[field] = new_value
            updated[f"{field}_confidence"] = "confirmed"
        
        # mentioned только если нет confirmed
        elif new_confidence == "mentioned" and current_confidence != "confirmed":
            updated[field] = new_value
            updated[f"{field}_confidence"] = "mentioned"
    
    # Простые поля (перезаписываем если не None)
    simple_fields = [
        "question_type", "objection", "wants_materials",
        "meeting_agreed", "meeting_datetime",
        "mentioned_location", "mentioned_price", "sentiment"
    ]
    
    for field in simple_fields:
        new_value = extraction.get(field)
        if new_value is not None:
            updated[field] = new_value
    
    # Устанавливаем call_refused при возражении no_call
    if extraction.get("objection") == "no_call":
        updated["call_refused"] = True

    return updated


# === ТЕСТЫ ===

EXTRACTION_TESTS = [
    {
        "message": "Хочу в Сочи до 10 млн для инвестиций",
        "expected": {
            "goal": "investment", "goal_confidence": "confirmed",
            "location": "sochi", "location_confidence": "confirmed",
            "budget": 10000000, "budget_confidence": "confirmed"
        }
    },
    {
        "message": "Говорят в Сочи есть квартиры за 10 млн",
        "expected": {
            "goal": None,
            "location": None,  # НЕ confirmed!
            "budget": None,    # НЕ confirmed!
            "mentioned_location": "sochi",
            "mentioned_price": 10000000
        }
    },
    {
        "message": "Дорого как-то",
        "expected": {
            "objection": "expensive",
            "sentiment": "negative"
        }
    },
    {
        "message": "Давайте завтра в 18:00",
        "expected": {
            "meeting_agreed": True,
            "meeting_datetime": "завтра в 18:00"
        }
    },
    {
        "message": "Скиньте что есть",
        "expected": {
            "wants_materials": True
        }
    },
    {
        "message": "Буду брать ипотеку, первый взнос 3 млн",
        "expected": {
            "payment_type": "mortgage", "payment_type_confidence": "confirmed",
            "first_payment": 3000000, "first_payment_confidence": "confirmed"
        }
    },
    {
        "message": "Решаем вместе с женой",
        "expected": {
            "lpr": "with_spouse", "lpr_confidence": "confirmed"
        }
    },
    {
        "message": "А какие цены в Крыму?",
        "expected": {
            "question_type": "price",
            "mentioned_location": "crimea"
        }
    }
]


def test_extractor():
    """Тест Extractor на примерах"""
    print("=== ТЕСТ EXTRACTOR ===\n")
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(EXTRACTION_TESTS, 1):
        message = test["message"]
        expected = test["expected"]
        
        print(f"Тест {i}: '{message}'")
        
        result = extract_sync(message)
        
        # Проверяем ожидаемые поля
        errors = []
        for key, expected_value in expected.items():
            actual_value = result.get(key)
            if actual_value != expected_value:
                errors.append(f"  {key}: ожидалось {expected_value}, получено {actual_value}")
        
        if errors:
            print(f"❌ FAILED:")
            for err in errors:
                print(err)
            failed += 1
        else:
            print(f"✅ PASSED")
            passed += 1
        
        print()
    
    print(f"Результат: {passed}/{passed+failed} тестов пройдено")
    return failed == 0


def test_merge():
    """Тест merge логики"""
    print("=== ТЕСТ MERGE ===\n")
    
    # Начальное состояние
    state = {
        "goal": None, "goal_confidence": None,
        "location": "sochi", "location_confidence": "mentioned",
        "budget": None, "budget_confidence": None
    }
    
    # Extraction с confirmed location
    extraction = {
        "location": "crimea", "location_confidence": "confirmed",
        "budget": 10000000, "budget_confidence": "confirmed"
    }
    
    result = merge_extraction_to_state(state, extraction)
    
    # Проверки
    assert result["location"] == "crimea", "confirmed должен перезаписать mentioned"
    assert result["location_confidence"] == "confirmed"
    assert result["budget"] == 10000000
    print("✅ confirmed перезаписывает mentioned")
    
    # Теперь mentioned НЕ должен перезаписать confirmed
    state2 = result.copy()
    extraction2 = {
        "location": "altai", "location_confidence": "mentioned"
    }
    
    result2 = merge_extraction_to_state(state2, extraction2)
    assert result2["location"] == "crimea", "mentioned НЕ должен перезаписать confirmed"
    print("✅ mentioned НЕ перезаписывает confirmed")
    
    print("\n✅ Все тесты merge пройдены!")


if __name__ == "__main__":
    # Сначала тест merge (без API)
    test_merge()
    print()
    
    # Потом тест extractor (с API)
    print("Запуск тестов с API (может занять 10-20 сек)...")
    test_extractor()
