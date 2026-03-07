#!/usr/bin/env python3
"""
Патч bot_server.py: source routing → GREETING для первых сообщений
Построчная обработка — надёжнее чем замена блоков текста
"""

filepath = '/opt/sofia-gpt/bot_server.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"📄 Читаю {filepath} ({len(lines)} строк)")

# ═══════════════════════════════════════════════════════════════
# Находим функцию generate_response_with_rag
# ═══════════════════════════════════════════════════════════════

func_start = None
func_end = None
for i, line in enumerate(lines):
    if 'async def generate_response_with_rag' in line:
        func_start = i
    elif func_start is not None and i > func_start + 5:
        if line.startswith('async def ') or line.startswith('def ') or line.startswith('# Legacy'):
            func_end = i
            break

if func_start is None:
    print("❌ Функция generate_response_with_rag НЕ найдена!")
    exit(1)

if func_end is None:
    func_end = len(lines)

print(f"📍 generate_response_with_rag: строки {func_start+1}-{func_end}")

# ═══════════════════════════════════════════════════════════════
# Находим ключевые маркеры внутри функции
# ═══════════════════════════════════════════════════════════════

state_summary_line = None
rag_stage_line = None
rag_query_line = None
analyzer_try_line = None
analyzer_except_end = None
set_user_stage_line = None

for i in range(func_start, func_end):
    s = lines[i].strip()
    if 'state_summary = format_state_summary(state)' in lines[i] and state_summary_line is None:
        state_summary_line = i
    if s == 'rag_stage = "QUALIFICATION"' and rag_stage_line is None:
        rag_stage_line = i
    if s == 'rag_query = user_message' and rag_stage_line is not None and rag_query_line is None:
        rag_query_line = i
    if s == 'try:' and rag_stage_line is not None and analyzer_try_line is None:
        if i + 1 < len(lines) and 'Analyzer' in lines[i+1]:
            analyzer_try_line = i
    if 'Analyzer error' in lines[i] and analyzer_try_line is not None and analyzer_except_end is None:
        analyzer_except_end = i
    if 'set_user_stage(chat_id, rag_stage)' in lines[i] and rag_stage_line is not None and set_user_stage_line is None:
        set_user_stage_line = i

markers = {
    'state_summary': state_summary_line,
    'rag_stage': rag_stage_line,
    'rag_query': rag_query_line,
    'analyzer_try': analyzer_try_line,
    'analyzer_except_end': analyzer_except_end,
    'set_user_stage': set_user_stage_line,
}

print(f"📍 Маркеры найдены:")
for name, val in markers.items():
    status = f"строка {val+1}" if val is not None else "❌ НЕ НАЙДЕН"
    print(f"   {name}: {status}")

for name, val in markers.items():
    if val is None:
        print(f"\n❌ Маркер '{name}' НЕ найден! Патч невозможен.")
        exit(1)

# ═══════════════════════════════════════════════════════════════
# ПАТЧ 1: вставляем skip_analyzer после state_summary
# ═══════════════════════════════════════════════════════════════

insert_block = [
    '\n',
    "    # Source routing: при source_object + первые сообщения → GREETING, пропуск Analyzer\n",
    "    user_msg_count = sum(1 for m in history if m['role'] == 'user')\n",
    '    skip_analyzer = False\n',
    '    if state and state.source_object and user_msg_count <= 2:\n',
    '        rag_stage = "GREETING"\n',
    '        rag_query = "приветствие клиент с сайта интерес к объекту"\n',
    '        skip_analyzer = True\n',
    '        log(f"\\U0001f3f7\\ufe0f Source routing: force stage=GREETING (user_msgs={user_msg_count}, object={state.source_object})")\n',
]

insert_pos = state_summary_line + 1
lines[insert_pos:insert_pos] = insert_block
offset = len(insert_block)

# Обновляем маркеры
rag_stage_line += offset
rag_query_line += offset
analyzer_try_line += offset
analyzer_except_end += offset
set_user_stage_line += offset

print(f"\n✅ Патч 1: skip_analyzer блок вставлен (после строки {state_summary_line+1})")

# ═══════════════════════════════════════════════════════════════
# ПАТЧ 2: оборачиваем rag_stage..except в if not skip_analyzer
# ═══════════════════════════════════════════════════════════════

# 2a: Вставляем "if not skip_analyzer:" перед rag_stage
lines.insert(rag_stage_line, '    if not skip_analyzer:\n')
rag_stage_line += 1
rag_query_line += 1
analyzer_try_line += 1
analyzer_except_end += 1
set_user_stage_line += 1

# 2b: Добавляем 4 пробела ко всем непустым строкам от rag_stage до set_user_stage (не включая)
for i in range(rag_stage_line, set_user_stage_line):
    if lines[i].strip():  # не трогаем пустые строки
        lines[i] = '    ' + lines[i]

print(f"✅ Патч 2: Analyzer обёрнут в if not skip_analyzer")

# ═══════════════════════════════════════════════════════════════
# ПАТЧ 3: подсказка Analyzer про source routing
# Вставляем между rag_query и try (внутри if not skip_analyzer)
# ═══════════════════════════════════════════════════════════════

hint_block = [
    '\n',
    '        # Подсказка Analyzer про source routing\n',
    '        if state and state.source_object:\n',
    '            analyzer_input += "\\n\\nВАЖНО: Клиент пришёл с сайта объекта (" + state.source_object + "). Первые сообщения — НЕ возражения, а начало диалога."\n',
    '\n',
]

# Ищем пустую строку между rag_query и try (после сдвига)
hint_pos = rag_query_line + 1
lines[hint_pos:hint_pos] = hint_block

print(f"✅ Патч 3: подсказка Analyzer вставлена")

# ═══════════════════════════════════════════════════════════════
# СОХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════════

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

total_added = len(insert_block) + 1 + len(hint_block)
print(f"\n{'='*50}")
print(f"✅ Файл сохранён: {filepath}")
print(f"   Добавлено строк: ~{total_added}")
print(f"   Итого строк: {len(lines)}")
print(f"\n🔍 Проверь:")
print(f"   grep -n 'skip_analyzer' {filepath}")
print(f"   grep -n 'Source routing' {filepath}")
