#!/usr/bin/env python3
"""
Обработка диалогов для Sofia Bot
- Парсинг из TXT/RTF
- Автоматическая оценка качества
- Конвертация в JSONL для fine-tuning
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class Message:
    date: str
    time: str
    author: str
    text: str
    is_manager: bool

@dataclass
class DialogScore:
    total: int
    result: str  # "созвон", "подборка", "отказ", "неопределён"
    issues: List[str]
    positives: List[str]
    details: Dict[str, int]

# ============================================================
# ПАРСИНГ
# ============================================================

def decode_rtf(content: str) -> str:
    """Декодирует RTF с unicode в обычный текст"""
    content = re.sub(r'\\uc0', '', content)
    
    def replace_unicode(m):
        try:
            code = int(m.group(1))
            if 0xD800 <= code <= 0xDFFF:  # surrogate (emoji)
                return '😊'  # заменяем на generic emoji
            return chr(code)
        except:
            return ''
    
    content = re.sub(r'\\u(\d+)\s?', replace_unicode, content)
    content = re.sub(r'\{[^}]*\}', '', content)
    content = re.sub(r'\\[a-z]+\d*\s?', '', content)
    content = re.sub(r'\\\'[0-9a-f]{2}', '', content)
    content = re.sub(r'[\{\}]', '', content)
    content = content.replace('\\', '\n')
    return content.strip()

def parse_dialog(text: str, manager_names: List[str] = None) -> List[Message]:
    """
    Парсит диалог из текста.
    Формат: [дата время] Автор: текст
    """
    if manager_names is None:
        manager_names = ['София', 'Sofia', 'Сергей', 'Виктория', 'Оксана', 'Юлия', 'Игорь']
    
    # Паттерн для сообщений
    pattern = r'\[([^\]]+)\s+(\d{1,2}:\d{2})\]\s*([^:]+):\s*(.+?)(?=\n\n|\n\[|$)'
    
    messages = []
    for match in re.finditer(pattern, text, re.DOTALL):
        date, time, author, msg_text = match.groups()
        author = author.strip()
        msg_text = msg_text.strip()
        
        # Определяем, менеджер это или клиент
        is_manager = any(name.lower() in author.lower() for name in manager_names)
        
        if msg_text and len(msg_text) > 1:
            messages.append(Message(
                date=date.strip(),
                time=time.strip(),
                author=author,
                text=msg_text,
                is_manager=is_manager
            ))
    
    return messages

# ============================================================
# АВТОМАТИЧЕСКАЯ ОЦЕНКА
# ============================================================

def score_dialog(messages: List[Message]) -> DialogScore:
    """
    Автоматически оценивает качество диалога.
    Возвращает score 0-10 и детали.
    """
    score = 0
    issues = []
    positives = []
    details = {}
    
    # Объединяем весь текст
    full_text = ' '.join(m.text.lower() for m in messages)
    manager_texts = [m.text for m in messages if m.is_manager]
    client_texts = [m.text for m in messages if not m.is_manager]
    
    # 1. РЕЗУЛЬТАТ (0-3 балла)
    result = "неопределён"
    
    # Созвон назначен
    call_markers = ['созвонимся', 'встреча', 'телемост', 'zoom', 'видеопрезентация', 
                    'во сколько удобно', 'когда удобно', 'договорились']
    if any(m in full_text for m in call_markers):
        # Проверяем что клиент согласился
        agreement_markers = ['давайте', 'хорошо', 'договорились', 'да,', 'ок', 'в 17', 'в 15', 'после 13']
        client_agreed = any(m in ' '.join(t.lower() for t in client_texts) for m in agreement_markers)
        if client_agreed:
            score += 3
            result = "созвон"
            positives.append("✅ Созвон назначен")
            details['call_scheduled'] = 3
    
    # Подборка отправлена
    elif any(m in full_text for m in ['whatsapp', 'telegram', 'отправлю', 'пришлю подборку']):
        score += 1
        result = "подборка"
        positives.append("📋 Отправка подборки")
        details['materials_sent'] = 1
    
    # Отказ
    elif any(m in full_text for m in ['не интересно', 'не актуально', 'передумал', 'отказ']):
        result = "отказ"
        issues.append("❌ Клиент отказался")
        details['rejection'] = -1
    
    # 2. ГЛУБИНА КВАЛИФИКАЦИИ (0-2 балла)
    qualification_done = 0
    if any(m in full_text for m in ['инвестиц', 'для себя', 'для жизни', 'аренд', 'пассивный доход']):
        qualification_done += 1
        positives.append("✅ Выяснена цель")
    if any(m in full_text for m in ['сочи', 'крым', 'анапа', 'алтай', 'поляна', 'ольгинка']):
        qualification_done += 1
        positives.append("✅ Выяснена локация")
    
    score += min(qualification_done, 2)
    details['qualification'] = min(qualification_done, 2)
    
    # 3. ЖИВОСТЬ РЕЧИ (0-2 балла)
    live_speech = 0
    live_markers = ['порядка', 'примерно', 'около', 'кстати', 'как раз', 'крутой', 'классный', 'супер']
    manager_full = ' '.join(t.lower() for t in manager_texts)
    
    for marker in live_markers:
        if marker in manager_full:
            live_speech += 0.5
    
    live_speech = min(int(live_speech), 2)
    score += live_speech
    details['live_speech'] = live_speech
    if live_speech >= 1:
        positives.append("✅ Живая речь")
    
    # 4. ДЛИНА ДИАЛОГА (0-1 балл)
    if len(messages) >= 10:
        score += 1
        details['dialog_length'] = 1
        positives.append(f"✅ Диалог {len(messages)} сообщений")
    else:
        details['dialog_length'] = 0
        issues.append(f"⚠️ Короткий диалог ({len(messages)} сообщений)")
    
    # 5. НЕГАТИВНЫЕ СИГНАЛЫ (-2 балла максимум)
    negative = 0
    
    # Клиент раздражён
    irritation_markers = ['я же сказал', 'уже говорил', 'повторяю', 'вы меня не слышите']
    if any(m in ' '.join(t.lower() for t in client_texts) for m in irritation_markers):
        negative += 2
        issues.append("❌ Клиент раздражён")
    
    # Повторы вопросов (одинаковые фразы)
    manager_questions = [t for t in manager_texts if '?' in t]
    if len(manager_questions) != len(set(manager_questions)):
        negative += 1
        issues.append("⚠️ Повторяющиеся вопросы")
    
    score -= negative
    details['negative'] = -negative
    
    # Финальный score
    score = max(0, min(10, score))
    
    return DialogScore(
        total=score,
        result=result,
        issues=issues,
        positives=positives,
        details=details
    )

# ============================================================
# LLM-ОЦЕНКА (точная, платная)
# ============================================================

LLM_EVALUATION_PROMPT = """Ты — эксперт по оценке качества диалогов продаж недвижимости.

## КАК ЧИТАТЬ ДИАЛОГ

Формат: [дата время] РОЛЬ (имя): текст

- МЕНЕДЖЕР — продавец недвижимости (Oazis Estate)
- КЛИЕНТ — потенциальный покупатель

## ЦЕЛИ МЕНЕДЖЕРА (воронка продаж)

1. КВАЛИФИКАЦИЯ — узнать:
   - Цель покупки (инвестиция / для себя / сдавать)
   - Желаемая локация
   - Бюджет или комфортный ежемесячный платёж

2. ЗАКРЫТИЕ НА СОЗВОН — назначить видео-встречу:
   - Предложить созвон
   - Объяснить ценность ("покажу на экране", "разберём под вас")
   - Отработать возражения если есть
   - Получить согласие и назначить время

## ТВОЯ ЗАДАЧА

Оцени диалог ПО КАЖДОМУ НАВЫКУ ОТДЕЛЬНО. Диалог может быть хорош для обучения одному навыку, но плох для другого.

## ОЦЕНКА КВАЛИФИКАЦИИ (0-10)

- 10: Узнал ВСЁ (цель + локация + бюджет), сделал это естественно, не как допрос
- 7-9: Узнал 2 из 3, хорошая техника
- 4-6: Узнал частично, есть недочёты
- 1-3: Почти не квалифицировал или сделал плохо
- 0: Не было попытки квалификации

## ОЦЕНКА ЗАКРЫТИЯ НА СОЗВОН (0-10)

- 10: Созвон назначен, клиент подтвердил время, отличная техника
- 7-9: Созвон назначен ИЛИ отличная попытка (клиент просто не готов)
- 4-6: Предложил созвон, но слабо отработал отказ
- 1-3: Слабая попытка закрыть или сразу сдался
- 0: Не предлагал созвон вообще

## ОЦЕНКА ОТРАБОТКИ ВОЗРАЖЕНИЙ (0-10)

- 10: Было возражение, отработал мастерски, клиент согласился
- 7-9: Хорошо отработал, даже если клиент не согласился
- 4-6: Попытался отработать, но слабо
- 1-3: Почти сдался сразу
- 0: Не было возражений ИЛИ сразу сдался
- null: Возражений не было (не оцениваем)

## КРИТЕРИИ ДЛЯ ОБУЧЕНИЯ

Диалог ПОДХОДИТ для обучения навыку, если:
- Оценка навыка >= 7
- Речь живая и естественная (не роботная)
- Нет грубых ошибок в этой части диалога

Ответь ТОЛЬКО валидным JSON:
{
  "overall_score": <0-10>,
  "result": "<созвон|договорённость|в_процессе|отказ|игнор>",
  "goal_achieved": <true|false>,
  
  "qualification": {
    "score": <0-10>,
    "learned_goal": <true|false>,
    "learned_location": <true|false>,
    "learned_budget": <true|false>,
    "good_for_training": <true|false>,
    "verdict": "<ПОДХОДИТ/НЕ ПОДХОДИТ для обучения квалификации: причина>"
  },
  
  "closing": {
    "score": <0-10>,
    "call_offered": <true|false>,
    "call_scheduled": <true|false>,
    "value_explained": <true|false>,
    "good_for_training": <true|false>,
    "verdict": "<ПОДХОДИТ/НЕ ПОДХОДИТ для обучения закрытия: причина>"
  },
  
  "objection_handling": {
    "score": <0-10 или null если не было возражений>,
    "had_objections": <true|false>,
    "handled_well": <true|false>,
    "good_for_training": <true|false>,
    "verdict": "<ПОДХОДИТ/НЕ ПОДХОДИТ для обучения возражений: причина или 'возражений не было'>"
  },
  
  "communication": {
    "natural_speech": <true|false>,
    "no_repeats": <true|false>,
    "client_comfortable": <true|false>
  },
  
  "strengths": ["<что хорошо>", ...],
  "mistakes": ["<что плохо>", ...],
  "summary": "<3-4 предложения: общая оценка диалога>"
}
"""

def format_dialog_for_llm(messages: List[Message], max_messages: int = 50) -> str:
    """Форматирует диалог для отправки в LLM"""
    lines = []
    for msg in messages[:max_messages]:
        role = "МЕНЕДЖЕР" if msg.is_manager else "КЛИЕНТ"
        # Показываем короткое имя для читаемости
        short_name = msg.author[:20] + "..." if len(msg.author) > 20 else msg.author
        lines.append(f"[{msg.date} {msg.time}] {role} ({short_name}): {msg.text}")
    
    if len(messages) > max_messages:
        lines.append(f"\n... (ещё {len(messages) - max_messages} сообщений)")
    
    return "\n".join(lines)

def llm_score_dialog_openai(messages: List[Message], api_key: str, model: str = "gpt-4o-mini") -> Dict:
    """Оценка через OpenAI API"""
    import openai
    
    client = openai.OpenAI(api_key=api_key)
    
    dialog_text = format_dialog_for_llm(messages)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": LLM_EVALUATION_PROMPT},
            {"role": "user", "content": f"Оцени этот диалог:\n\n{dialog_text}"}
        ],
        temperature=0.1,
        max_completion_tokens=2000  # Увеличил с 500 до 2000
    )
    
    result_text = response.choices[0].message.content.strip()
    
    # Парсим JSON
    try:
        # Убираем возможные markdown-блоки
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]
        
        return json.loads(result_text.strip())
    except json.JSONDecodeError as e:
        # Логируем ошибку для отладки
        print(f"\n   ⚠️ JSON parse error: {e}")
        print(f"   Raw response (first 300 chars): {result_text[:300]}")
        return {
            "overall_score": 0,
            "result": "ошибка_парсинга",
            "goal_achieved": False,
            "qualification": {},
            "closing": {},
            "objection_handling": {},
            "communication": {},
            "strengths": [],
            "mistakes": [f"JSON parse error: {str(e)[:100]}"],
            "summary": f"Raw: {result_text[:150]}"
        }

def llm_score_dialog_anthropic(messages: List[Message], api_key: str, model: str = "claude-3-haiku-20240307") -> Dict:
    """Оценка через Anthropic API"""
    import anthropic
    
    client = anthropic.Anthropic(api_key=api_key)
    
    dialog_text = format_dialog_for_llm(messages)
    
    response = client.messages.create(
        model=model,
        max_tokens=2000,  # Увеличил с 500 до 2000
        messages=[
            {"role": "user", "content": f"{LLM_EVALUATION_PROMPT}\n\nОцени этот диалог:\n\n{dialog_text}"}
        ]
    )
    
    result_text = response.content[0].text.strip()
    
    # Парсим JSON
    try:
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]
        
        return json.loads(result_text.strip())
    except json.JSONDecodeError as e:
        print(f"\n   ⚠️ JSON parse error: {e}")
        print(f"   Raw response (first 300 chars): {result_text[:300]}")
        return {
            "overall_score": 0,
            "result": "ошибка_парсинга",
            "goal_achieved": False,
            "qualification": {},
            "closing": {},
            "objection_handling": {},
            "communication": {},
            "strengths": [],
            "mistakes": [f"JSON parse error: {str(e)[:100]}"],
            "summary": f"Raw: {result_text[:150]}"
        }

def llm_score_dialog(messages: List[Message], api_key: str, provider: str = "openai", model: str = None) -> Dict:
    """
    Универсальная функция оценки через LLM.
    
    provider: "openai" или "anthropic"
    model: название модели (если None, используется дефолтная)
    """
    if provider == "openai":
        model = model or "gpt-5.2"
        return llm_score_dialog_openai(messages, api_key, model)
    elif provider == "anthropic":
        model = model or "claude-3-haiku-20240307"
        return llm_score_dialog_anthropic(messages, api_key, model)
    else:
        raise ValueError(f"Unknown provider: {provider}")

# ============================================================
# КОНВЕРТАЦИЯ В JSONL
# ============================================================

def dialog_to_jsonl(messages: List[Message], system_prompt: str = None) -> Dict:
    """
    Конвертирует диалог в формат для fine-tuning.
    """
    if system_prompt is None:
        system_prompt = "Ты — София, ассистент отдела продаж Oazis Estate. Твоя задача — квалифицировать клиента и довести до созвона."
    
    conversations = [{"from": "system", "value": system_prompt}]
    
    for msg in messages:
        role = "gpt" if msg.is_manager else "human"
        conversations.append({
            "from": role,
            "value": msg.text
        })
    
    return {"conversations": conversations}

# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def process_file(filepath: str, manager_names: List[str] = None) -> Tuple[List[Message], DialogScore, Dict]:
    """
    Полная обработка файла диалога.
    Возвращает: (messages, score, jsonl_data)
    """
    path = Path(filepath)
    
    # Читаем файл
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Декодируем если RTF
    if path.suffix.lower() == '.rtf':
        content = decode_rtf(content)
    
    # Парсим
    messages = parse_dialog(content, manager_names)
    
    # Оцениваем
    score = score_dialog(messages)
    
    # Конвертируем
    jsonl_data = dialog_to_jsonl(messages)
    
    return messages, score, jsonl_data

def process_directory(dirpath: str, min_score: int = 5) -> List[Dict]:
    """
    Обрабатывает все диалоги в директории.
    Возвращает только диалоги с score >= min_score.
    """
    results = []
    dir_path = Path(dirpath)
    
    for filepath in dir_path.glob('*'):
        if filepath.suffix.lower() in ['.txt', '.rtf']:
            try:
                messages, score, jsonl_data = process_file(str(filepath))
                results.append({
                    'file': filepath.name,
                    'messages_count': len(messages),
                    'score': score.total,
                    'result': score.result,
                    'positives': score.positives,
                    'issues': score.issues,
                    'jsonl': jsonl_data if score.total >= min_score else None
                })
            except Exception as e:
                print(f"Error processing {filepath}: {e}")
    
    return sorted(results, key=lambda x: x['score'], reverse=True)

# ============================================================
# ТЕСТ
# ============================================================

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        messages, score, jsonl_data = process_file(filepath)
        
        print(f"\n{'='*50}")
        print(f"Файл: {filepath}")
        print(f"Сообщений: {len(messages)}")
        print(f"{'='*50}")
        print(f"\n📊 ОЦЕНКА: {score.total}/10")
        print(f"Результат: {score.result}")
        print(f"\n✅ Позитивное:")
        for p in score.positives:
            print(f"   {p}")
        print(f"\n⚠️ Проблемы:")
        for i in score.issues:
            print(f"   {i}")
        print(f"\nДетали: {score.details}")
        
        # Показываем первые сообщения
        print(f"\n{'='*50}")
        print("Первые 5 сообщений:")
        for msg in messages[:5]:
            role = "👔" if msg.is_manager else "👤"
            print(f"{role} [{msg.date} {msg.time}] {msg.author[:20]}:")
            print(f"   {msg.text[:100]}...")
    else:
        print("Usage: python dialog_processor.py <file.txt|file.rtf>")
