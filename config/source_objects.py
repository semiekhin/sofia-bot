"""
Source Objects — маппинг объектов недвижимости.
Распознаёт объект по ключевым словам в первом сообщении.

Добавить новый объект:
1. Создать карточку objects/<key>_context.md
2. Положить презентацию objects/<key>_presentation.pdf
3. Добавить запись в SOURCE_OBJECTS
"""

SOURCE_OBJECTS = {
    "atlantis": {
        "key": "atlantis",
        "name": "Cosmos Crimea Atlantis Therms & Resort",
        "short_name": "АК Атлантис",
        "city": "Крым, Новофёдоровка",
        "keywords": ["атлантис", "atlantis", "#ATL"],
        "context_file": "objects/atlantis_context.md",
        "presentation_url": "https://api.atlantis-invest.ru/objects/atlantis_presentation.pdf",
        "greeting": "Рада, что заинтересовались Атлантисом! Вот презентация с планировками. Спрашивайте что угодно — а я задам пару вопросов, чтобы подобрать лучший вариант)",
        "prompt_addon": """Контакт клиента уже получен через форму на сайте. НЕ запрашивай телефон, email или другие контактные данные. После квалификации сразу предлагай удобное время для созвона с экспертом.

ПЕРЕДАЁТ ДИАЛОГ МЕНЕДЖЕРУ, если клиент:

- Просит высказать политическое мнение или обсудить политическую ситуацию (в т.ч. по теме безопасности региона — кроме случаев когда это возражение по покупке, см. блок РАБОТА С ВОЗРАЖЕНИЯМИ).
- Задаёт юридические или финансовые вопросы о компании Оазис или о застройщике (структура сделки, налоги, право собственности, юридические риски, фин. показатели).
- Спрашивает про влияние СВО на покупку / продажу / инвестиции, или любые вопросы с упоминанием СВО.
- Высказывает дискриминационные позиции или просит обсудить такие темы.
- Предлагает или спрашивает про незаконные схемы (отмывание, уход от налогов, серые схемы оплаты).
- Делает мошеннические запросы (попытки получить данные других клиентов, выдать себя за сотрудника и т.п.).

В этих случаях Sofia отвечает в духе:
«Этот вопрос лучше обсудить с менеджером — он свяжется с вами в ближайшее время и ответит подробно.»

После такого ответа Sofia не пытается продолжать квалификацию по этому витку и ждёт следующего сообщения клиента.""",
    },
}


def detect_source(text: str) -> tuple:
    """
    Ищет объект по ключевым словам в тексте.
    Возвращает (object_config, clean_text) или (None, text).
    """
    text_lower = text.lower()
    for obj_id, config in SOURCE_OBJECTS.items():
        for keyword in config["keywords"]:
            if keyword.lower() in text_lower:
                # Убираем только хэштег-маркеры, ключевые слова оставляем
                import re

                clean = text
                if keyword.startswith("#"):
                    clean = re.sub(
                        re.escape(keyword), "", text, flags=re.IGNORECASE
                    ).strip()
                return config, clean
    return None, text


def get_object_by_key(key: str) -> dict:
    """Возвращает конфиг объекта по key."""
    return SOURCE_OBJECTS.get(key)


def load_object_context(config: dict) -> str:
    """Загружает текст карточки объекта из файла."""
    import os

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filepath = os.path.join(base_path, config["context_file"])
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Объект: {config['name']}, {config['city']}"
