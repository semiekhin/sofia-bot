# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 22.01.2026 (ночь, ~01:40)
🏷️ **Версия:** v3.0 — "LLM-Planner"

## ✅ Что сделано (22.01.2026 ночь)

### LLM-Planner v3.0
- [x] `get_allowed_actions()` в planner.py — возвращает список допустимых actions
- [x] Новый модуль `llm_planner.py` — LLM выбирает лучший action + micro_goal + tone
- [x] Интеграция в bot_server.py с флагом `USE_LLM_PLANNER`
- [x] Синхронизация userbot с v3.0
- [x] Включен на проде: `USE_LLM_PLANNER=true`

### Исправление wants_materials
- [x] Проблема: "давай варианты и там и там" после "море или горы?" считалось отказом
- [x] Решение: wants_materials=true только при явной просьбе КАК АЛЬТЕРНАТИВА созвону
- [x] Обновлён промпт Extractor с примерами контекста

### Исследование RAG для LLM-Planner
- [x] Протестирован RAG — находит релевантные примеры (similarity 0.6-0.7)
- [x] Особенно хорош для: отказ от созвона, возражения, просьба материалов
- [ ] Интеграция RAG в LLM-Planner — следующая задача

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active + LLM-Planner
- Userbot sofia-userbot — active + LLM-Planner
- Латентные метрики (friction, call_readiness, engagement, urgency)
- Finance calculator — расчёт доходности
- Комбо-ответы через micro_goal

### 📊 Как работает LLM-Planner
1. Детерминированный Planner → `allowed_actions[]` (1-5 вариантов)
2. Если вариантов > 1 → LLM (gpt-5.2, reasoning:high) выбирает лучший
3. LLM возвращает: action + micro_goal + tone
4. micro_goal передаётся Generator для "комбо-ответов"
5. Fallback на детерминированный Planner при ошибке

## 🔜 Следующие шаги
1. **RAG для LLM-Planner** — показывать успешные примеры при выборе action
2. Мониторинг на реальных диалогах
3. (Опционально) Critic — проверка ответа перед отправкой

## 📁 Последние изменения
- `planner.py` — добавлен `get_allowed_actions()` (~200 строк)
- `llm_planner.py` — новый модуль (~250 строк)
- `bot_server.py` — интеграция LLM-Planner
- `sofia_userbot_pyrogram.py` — синхронизация с v3.0
- `extractor.py` — исправлено правило wants_materials
- `.env` — добавлен `USE_LLM_PLANNER=true`

## 🚀 Команды
```bash
# Перезапуск
systemctl restart sofia-gpt sofia-userbot

# Логи LLM-Planner
tail -f /opt/sofia-gpt/sofia_bot.log | grep -E "LLM|Allowed"

# Отправить первое сообщение клиенту
/opt/sofia-gpt/sofia_start.sh @username

# Откат на v2.2 (если нужно)
sed -i 's/USE_LLM_PLANNER=true/USE_LLM_PLANNER=false/' /opt/sofia-gpt/.env
systemctl restart sofia-gpt sofia-userbot
```
