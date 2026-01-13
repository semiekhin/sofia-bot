# stage_detector.py — Stage Detector для Sofia Bot
# Определяет этап продаж по сообщению клиента и контексту диалога
# Версия: 1.0

import re
from typing import Optional, List, Dict

# 7 этапов продаж
STAGES = [
    "GREETING",      # Первый контакт
    "QUALIFICATION", # Бюджет, цель, локация
    "PRESENTATION",  # Показ объектов
    "OBJECTION",     # Работа с возражениями
    "MEETING",       # Назначение созвона
    "CLOSING",       # Закрытие сделки
    "POST_SALE"      # Сопровождение после покупки
]

# Паттерны для определения этапа
STAGE_PATTERNS = {
    "GREETING": [
        r"^привет",
        r"^здравствуй",
        r"^добр(ый|ое|ого)",
        r"^хай",
        r"^hello",
        r"^hi\b",
        r"да.{0,10}удобно",
        r"слушаю",
        r"говорите",
        r"можем пообщаться",
    ],
    
    "QUALIFICATION": [
        r"для (себя|жизни|отдыха|инвестиц|сдачи|аренд)",
        r"хочу (купить|взять|посмотреть|рассмотреть)",
        r"интересует",
        r"рассматриваю",
        r"(ищу|ищем)",
        r"бюджет",
        r"(сколько|какая).{0,20}(стоит|цена)",
        r"(какой|какая|какие).{0,10}(локаци|район|город)",
        r"(сочи|крым|анапа|алтай|поляна)",
        r"(ипотек|рассрочк|100%|наличк)",
        r"(платёж|платеж|взнос)",
        r"(квартир|апарт|студи|номер)",
    ],
    
    "PRESENTATION": [
        r"(покажите|пришлите|скиньте|отправьте)",
        r"(фото|видео|планировк|рендер)",
        r"(подборк|варианты|предложения)",
        r"(что есть|что предлагаете)",
        r"расскажите подробнее",
        r"(а что|что там) (с|по|за)",
        r"какие (есть|условия)",
        r"(цена|стоимость).{0,10}(какая|сколько)",
    ],
    
    "OBJECTION": [
        r"(дорого|недёшево|дороговато)",
        r"(далеко|неудобно)",
        r"(не нравится|не подходит|не то)",
        r"(подумаю|подумать|обсудить)",
        r"(сомневаюсь|не уверен)",
        r"(почему|зачем).{0,20}(так|столько)",
        r"(а если|а что если)",
        r"(риск|опасно|страшно)",
        r"(не сейчас|попозже|потом)",
        r"(муж|жена|супруг).{0,20}(обсуд|посоветов|спрос)",
        r"(отказ|передум|отмен)",
        r"не (справлюсь|потяну|смогу)",
        r"(нагрузк|финанс).{0,10}(сложно|тяжело)",
    ],
    
    "MEETING": [
        r"(созвон|звонок|позвон|перезвон)",
        r"(встреча|встретиться)",
        r"(видео|zoom|whatsapp|telegram).{0,10}(созвон|звонок)",
        r"(когда|во сколько).{0,10}(удобно|можем|можно)",
        r"(сегодня|завтра|на неделе).{0,10}(созвон|встреч|позвон)",
        r"(давайте|можем|хочу).{0,10}(созвон|обсуд)",
        r"(10|11|12|13|14|15|16|17|18|19|20).{0,5}(час|:00|:30)",
    ],
    
    "CLOSING": [
        r"(берём|берем|беру|забираю)",
        r"(оформля|бронир|резервир)",
        r"(договор|дду|сделк)",
        r"(оплат|платить|перевести|перевод)",
        r"(реквизит|счёт|счет)",
        r"(подпис|согласен|согласна|готов|готова)",
        r"(да|ок|окей).{0,5}(бер|оформ|брон)",
        r"куда (платить|переводить|перевести)",
    ],
    
    "POST_SALE": [
        r"(строительств|стройк).{0,10}(как|что|когда)",
        r"(прогресс|статус|новости)",
        r"(сдача|ввод).{0,10}(когда|срок)",
        r"(документ|акт|ключ)",
        r"(ремонт|мебель|техник)",
        r"(управляющ|ук|сервис)",
        r"(спасибо|благодар)",
        r"(рекоменд|порекоменд|посоветов)",
        r"(знаком|друг|коллег).{0,20}(интересует|хочет)",
    ],
}

# Веса для определения этапа на основе контекста
CONTEXT_WEIGHTS = {
    "no_history": {"GREETING": 0.8, "QUALIFICATION": 0.2},
    "short_dialog": {"QUALIFICATION": 0.5, "PRESENTATION": 0.3, "MEETING": 0.2},
    "medium_dialog": {"PRESENTATION": 0.3, "OBJECTION": 0.3, "MEETING": 0.2, "CLOSING": 0.2},
    "after_payment": {"CLOSING": 0.5, "POST_SALE": 0.5},
}


def detect_stage(
    client_message: str,
    history: Optional[List[Dict]] = None,
    last_stage: Optional[str] = None
) -> Dict:
    """
    Определяет этап продаж по сообщению клиента.
    
    Args:
        client_message: Текущее сообщение клиента
        history: История диалога [{"role": "user/assistant", "content": "..."}]
        last_stage: Предыдущий определённый этап
    
    Returns:
        {
            "stage": "QUALIFICATION",
            "confidence": 0.85,
            "substage": "budget_discovery",
            "matched_patterns": ["бюджет", "ипотек"]
        }
    """
    message_lower = client_message.lower().strip()
    history = history or []
    
    # Подсчёт совпадений по каждому этапу
    stage_scores = {stage: 0.0 for stage in STAGES}
    matched_patterns = {stage: [] for stage in STAGES}
    
    for stage, patterns in STAGE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                stage_scores[stage] += 1.0
                matched_patterns[stage].append(pattern)
    
    # Учитываем контекст диалога
    dialog_length = len([m for m in history if m.get("role") == "user"])
    
    if dialog_length == 0:
        # Первое сообщение — скорее всего GREETING или QUALIFICATION
        stage_scores["GREETING"] += 0.5
        stage_scores["QUALIFICATION"] += 0.3
    elif dialog_length <= 3:
        # Короткий диалог — QUALIFICATION или PRESENTATION
        stage_scores["QUALIFICATION"] += 0.3
        stage_scores["PRESENTATION"] += 0.2
    elif dialog_length <= 8:
        # Средний диалог — PRESENTATION, OBJECTION, MEETING
        stage_scores["PRESENTATION"] += 0.2
        stage_scores["OBJECTION"] += 0.2
        stage_scores["MEETING"] += 0.2
    else:
        # Длинный диалог — CLOSING или POST_SALE
        stage_scores["CLOSING"] += 0.2
        stage_scores["POST_SALE"] += 0.2
    
    # Учитываем предыдущий этап (инерция)
    if last_stage:
        stage_scores[last_stage] += 0.3
        # Логичные переходы
        transitions = {
            "GREETING": ["QUALIFICATION"],
            "QUALIFICATION": ["PRESENTATION", "MEETING"],
            "PRESENTATION": ["OBJECTION", "MEETING", "CLOSING"],
            "OBJECTION": ["PRESENTATION", "MEETING", "CLOSING"],
            "MEETING": ["CLOSING", "PRESENTATION"],
            "CLOSING": ["POST_SALE"],
            "POST_SALE": ["QUALIFICATION", "PRESENTATION"],  # Повторные покупки
        }
        for next_stage in transitions.get(last_stage, []):
            stage_scores[next_stage] += 0.2
    
    # Находим этап с максимальным score
    max_stage = max(stage_scores, key=stage_scores.get)
    max_score = stage_scores[max_stage]
    
    # Нормализуем confidence (0-1)
    total_score = sum(stage_scores.values())
    confidence = max_score / total_score if total_score > 0 else 0.5
    
    # Определяем substage
    substage = _detect_substage(message_lower, max_stage)
    
    return {
        "stage": max_stage,
        "confidence": round(confidence, 2),
        "substage": substage,
        "matched_patterns": matched_patterns[max_stage],
        "all_scores": {k: round(v, 2) for k, v in stage_scores.items() if v > 0}
    }


def _detect_substage(message: str, stage: str) -> str:
    """Определяет подэтап внутри основного этапа."""
    
    substages = {
        "GREETING": {
            "first_contact": [r"привет", r"здравствуй", r"добр"],
            "ready_to_talk": [r"да.{0,10}удобно", r"слушаю", r"говорите"],
        },
        "QUALIFICATION": {
            "goal_discovery": [r"для (себя|жизни|отдыха|инвестиц)"],
            "location_discovery": [r"сочи|крым|анапа|алтай|поляна|локаци"],
            "budget_discovery": [r"бюджет|платёж|платеж|взнос|ипотек|рассрочк"],
            "format_discovery": [r"квартир|апарт|студи|номер|дом|участок"],
        },
        "PRESENTATION": {
            "request_materials": [r"покажите|пришлите|скиньте|отправьте"],
            "price_inquiry": [r"цена|стоимость|сколько стоит"],
            "details_inquiry": [r"расскажите|подробнее|что там"],
        },
        "OBJECTION": {
            "price_concern": [r"дорого|недёшево"],
            "timing_concern": [r"не сейчас|попозже|потом|подумаю"],
            "family_discussion": [r"муж|жена|супруг|обсуд"],
            "financial_hardship": [r"не справлюсь|не потяну|нагрузк"],
            "location_concern": [r"далеко|неудобно|локаци"],
        },
        "MEETING": {
            "call_agreement": [r"давайте|можем|хочу.{0,10}созвон"],
            "time_discussion": [r"когда|во сколько|сегодня|завтра"],
        },
        "CLOSING": {
            "decision_made": [r"берём|берем|беру|забираю"],
            "payment_inquiry": [r"реквизит|куда.{0,10}плат"],
            "contract_discussion": [r"договор|дду|подпис"],
        },
        "POST_SALE": {
            "construction_update": [r"строительств|стройк|прогресс"],
            "gratitude": [r"спасибо|благодар"],
            "referral": [r"рекоменд|знаком|друг|коллег"],
        },
    }
    
    stage_substages = substages.get(stage, {})
    for substage_name, patterns in stage_substages.items():
        for pattern in patterns:
            if re.search(pattern, message):
                return substage_name
    
    return "general"


def get_stage_context(stage: str) -> Dict:
    """Возвращает контекст для этапа (для промпта)."""
    
    contexts = {
        "GREETING": {
            "goal": "Установить контакт, узнать удобно ли говорить",
            "next_step": "Перейти к QUALIFICATION",
            "key_action": "Программирование: объяснить что сейчас будет",
        },
        "QUALIFICATION": {
            "goal": "Узнать цель, локацию, бюджет/платёж",
            "next_step": "Предложить созвон (MEETING) или показать варианты (PRESENTATION)",
            "key_action": "Один вопрос за раз, не торопиться с подборкой",
        },
        "PRESENTATION": {
            "goal": "Показать подходящие варианты",
            "next_step": "Работа с возражениями (OBJECTION) или созвон (MEETING)",
            "key_action": "Давать диапазон цен, не просто 'от X'",
        },
        "OBJECTION": {
            "goal": "Понять и снять возражение",
            "next_step": "Вернуться к PRESENTATION или предложить MEETING",
            "key_action": "Не спорить, искать альтернативы",
        },
        "MEETING": {
            "goal": "Назначить конкретное время созвона",
            "next_step": "CLOSING или повторный MEETING",
            "key_action": "Зафиксировать дату + время + канал связи",
        },
        "CLOSING": {
            "goal": "Оформить сделку",
            "next_step": "POST_SALE",
            "key_action": "Чёткие инструкции по оплате и документам",
        },
        "POST_SALE": {
            "goal": "Поддерживать контакт, получать рефералы",
            "next_step": "Новая QUALIFICATION при повторной покупке",
            "key_action": "Проактивные апдейты, забота, не продавать агрессивно",
        },
    }
    
    return contexts.get(stage, {"goal": "Продолжить диалог", "next_step": "—", "key_action": "—"})


# Для тестирования
if __name__ == "__main__":
    test_messages = [
        "Привет!",
        "Да, удобно, слушаю",
        "Хочу квартиру для инвестиций в Сочи",
        "Какой бюджет нужен?",
        "Дороговато, надо подумать",
        "Давайте созвонимся завтра в 15:00",
        "Берём! Куда платить?",
        "Как там стройка продвигается?",
    ]
    
    for msg in test_messages:
        result = detect_stage(msg)
        print(f"'{msg}' → {result['stage']} ({result['confidence']}) [{result['substage']}]")
