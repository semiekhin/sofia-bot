# Известные баги Sofia-GPT

## BUG-001: dialog_finished не устанавливается при отказе клиента (31.01.2026)

**Проблема:** При фразах типа:
- "Вопрос решён"
- "Не актуально"  
- "Просьба не беспокоить"
- "Заявку не оставлял"

София отвечает корректно, НО `dialog_finished` остаётся `false`.

**Влияние:**
- Max/Telegram через Radist: ✅ НЕ критично (нет напоминаний в gateway)
- Telegram Bot (@humanAINeural_bot): ⚠️ Может отправить напоминание "На связи?" через час

**Фикс (TODO):**
1. `extractor.py`: добавить `objection: "not_interested"` для фраз отказа
2. `message_processor.py`: при `not_interested` ставить `dialog_finished=true`
3. `bot_server.py`: добавить проверку `state.dialog_finished` в `send_reminder()`

**Приоритет:** Средний (фиксить в следующей сессии с тестированием)
