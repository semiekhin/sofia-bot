# Задачи Sofia-GPT

📅 Обновлено: 18.01.2026

## ✅ Выполнено

### v2.0 Core (17.01.2026)
- [x] Миграция БД — 8 новых колонок в client_state
- [x] state_manager.py — все v2.0 поля
- [x] planner.py — две ветки INVESTMENT/PERSONAL, два созвона
- [x] extractor.py — новые слоты strategy/usage/family
- [x] sofia_prompt.py — директивы PROPOSE_MEETING_*
- [x] RAG — диалог oksana_scripts_v2 (13 примеров)
- [x] Фикс slot_attempts (маппинг payment → payment_type)

### Сессия 18.01.2026
- [x] Уведомления менеджеру при dialog_finished=True
- [x] RAG по action Planner'а (не по Stage Detector)
- [x] "Живой" промпт — эмодзи, разнообразие, человечность
- [x] RAG_EXAMPLES_COUNT увеличен до 10

## 🔄 В процессе

### Тестирование "живой" Софии
- [ ] Разнообразие начал (не повторяются подряд)
- [ ] Эмодзи естественно
- [ ] Off-topic с возвратом к делу
- **Статус:** Ожидает утреннего теста

## 📋 TODO

### Приоритет 1: Userbot v2.0
**Время:** ~1 час

1. Восстановить из бэкапа:
```bash
   cp /opt/sofia-gpt/sofia_userbot_pyrogram.py.backup_20260117_132806 /opt/sofia-gpt/sofia_userbot_pyrogram.py
```

2. Добавить фикс slot_attempts (маппинг payment → payment_type):
```python
   ACTION_TO_SLOT = {"payment": "payment_type"}
```

3. Проверить/добавить:
   - `merge_extraction_to_state()` из extractor.py
   - `increment_slot_attempt()` из planner.py
   - Команда `/start @username` для умного старта

4. Создать systemd сервис:
```bash
   # /etc/systemd/system/sofia-userbot.service
```

5. Протестировать

### Приоритет 2: Мониторинг качества
- [ ] Дашборд: сравнение action Planner vs текст Generator
- [ ] Алерты если Generator игнорирует директивы
- [ ] Логирование conversation_complete rate

### Приоритет 3: Улучшения RAG (опционально)
- [ ] Синтетические "золотые" примеры живого общения
- [ ] Фильтр quality: "exceptional" для лучших примеров
- [ ] A/B тест: 10 vs 15 примеров

## 🐛 Известные проблемы

| Проблема | Статус | Решение |
|----------|--------|---------|
| ~~slot_attempts не инкрементировался~~ | ✅ Исправлено | Маппинг ACTION_TO_SLOT |
| ~~RAG по неправильному stage~~ | ✅ Исправлено | ACTION_TO_RAG_STAGE |
| ~~Generator игнорировал PROPOSE_MEETING_1~~ | ✅ Исправлено | Усилены директивы |
| Userbot не имеет v2.0 логики | ⏳ Ожидает | Восстановить из бэкапа |

## 📊 Метрики

- **RAG примеров:** 1939
- **RAG на запрос:** 10
- **Quality distribution:** excellent 76%, good 18%, poor 6%
