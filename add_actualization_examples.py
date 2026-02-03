#!/usr/bin/env python3
"""
Скрипт для добавления ВСЕХ примеров ACTUALIZATION в rag_training_data.json.
Подхватывает оба файла:
  - actualization_rag_examples.json (15 основных сценариев)
  - actualization_rag_examples_extra.json (7 крайних случаев)

Запуск:
  cd /opt/sofia-gpt
  python3 add_actualization_examples.py
"""

import json
import shutil
from datetime import datetime

RAG_FILE = '/opt/sofia-gpt/rag_training_data.json'
EXAMPLE_FILES = [
    '/opt/sofia-gpt/actualization_rag_examples.json',
    '/opt/sofia-gpt/actualization_rag_examples_extra.json',
]

def main():
    # 1. Бэкап
    backup_name = f"{RAG_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_pre_actualization_examples"
    shutil.copy2(RAG_FILE, backup_name)
    print(f"✅ Бэкап: {backup_name}")
    
    # 2. Загрузка текущих данных
    with open(RAG_FILE, 'r', encoding='utf-8') as f:
        rag_data = json.load(f)
    
    current_count = len(rag_data.get('dialogs', []))
    existing_ids = {d['dialog_id'] for d in rag_data['dialogs']}
    print(f"📊 Текущих диалогов: {current_count}")
    
    # 3. Загрузка и мерж всех файлов
    total_added = 0
    for filepath in EXAMPLE_FILES:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            
            new_dialogs = new_data['dialogs']
            unique_new = [d for d in new_dialogs if d['dialog_id'] not in existing_ids]
            skipped = len(new_dialogs) - len(unique_new)
            
            rag_data['dialogs'].extend(unique_new)
            existing_ids.update(d['dialog_id'] for d in unique_new)
            total_added += len(unique_new)
            
            print(f"📥 {filepath}: +{len(unique_new)} диалогов" + (f" (пропущено {skipped} дубликатов)" if skipped else ""))
        except FileNotFoundError:
            print(f"⚠️  Файл не найден: {filepath}")
    
    # 4. Обновление метаданных
    rag_data['total_dialogs'] = len(rag_data['dialogs'])
    rag_data['updated'] = datetime.now().strftime('%Y-%m-%d')
    
    # 5. Сохранение
    with open(RAG_FILE, 'w', encoding='utf-8') as f:
        json.dump(rag_data, f, ensure_ascii=False, indent=2)
    
    final_count = len(rag_data['dialogs'])
    print(f"\n✅ Добавлено всего: {total_added} диалогов")
    print(f"📊 Итого диалогов: {final_count}")
    
    # 6. Статистика по стадиям
    act_exchanges = 0
    act_dialogs = set()
    for d in rag_data['dialogs']:
        for e in d.get('exchanges', []):
            if e.get('stage') == 'ACTUALIZATION':
                act_exchanges += 1
                act_dialogs.add(d['dialog_id'])
    print(f"📊 Диалогов с ACTUALIZATION: {len(act_dialogs)}")
    print(f"📊 Обменов ACTUALIZATION: {act_exchanges}")
    
    # 7. Пересоздание RAG индекса
    print("\n🔄 Пересоздание RAG индекса...")
    try:
        from rag_module import rebuild_index
        rebuild_index()
        print("✅ RAG индекс пересоздан!")
    except ImportError:
        print("⚠️  rag_module не найден. Пересоздайте вручную:")
        print("    python3 -c 'from rag_module import rebuild_index; rebuild_index()'")
    except Exception as e:
        print(f"⚠️  Ошибка: {e}")
        print("    python3 -c 'from rag_module import rebuild_index; rebuild_index()'")
    
    print("\n✅ Готово! Перезапустите сервис:")
    print("    systemctl restart sofia-radist")

if __name__ == '__main__':
    main()
