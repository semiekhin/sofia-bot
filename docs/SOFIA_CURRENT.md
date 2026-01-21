# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 22.01.2026 (ночь, ~02:45)
🏷️ **Версия:** v3.1 — "LLM-Planner + RAG"

## ✅ Что сделано (22.01.2026 ночь)

### RAG → LLM-Planner
- [x] Добавлен импорт `search_examples` в llm_planner.py
- [x] Маппинг `ACTION_TO_RAG_STAGE` для поиска примеров
- [x] Функция `_get_rag_examples()` — триггеры:
  - `objection: "no_call"` — отказ от созвона
  - `wants_materials: true` — просит подборку
  - `HANDLE_OBJECTION`, `PROPOSE_MEETING_*` в allowed_actions
- [x] RAG примеры добавляются в промпт LLM-Planner

### Баг call_proposal_count
- [x] Проблема: после первого отказа бот снова предлагал созвон
- [x] Причина: `call_proposal_count` не инкрементировался в bot_server.py
- [x] Решение: добавлен инкремент после PROPOSE_MEETING_1/2

### Защита userbot от рестартов
- [x] systemd: лимит 5 рестартов за 10 минут (было: бесконечно)
- [x] Код: обработка AUTH_KEY_UNREGISTERED → выход без рестарта
- [ ] Авторизация: ждём разблокировки Telegram (лимит попыток)

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active + LLM-Planner + RAG
- RAG примеры подтягиваются для сложных кейсов
- Счётчик call_proposal_count корректно работает

### ⏳ Ожидает
- Userbot sofia-userbot — ОСТАНОВЛЕН (сессия истекла, лимит Telegram)
- Когда разблокируют (1-24ч):
  1. `rm -f /opt/sofia-gpt/sofia_pyrogram.session`
  2. `python /opt/sofia-gpt/sofia_userbot_pyrogram.py` (авторизация)
  3. `systemctl enable sofia-userbot && systemctl start sofia-userbot`

## 🔜 Следующие шаги
1. Восстановить userbot после разблокировки Telegram
2. Протестировать сценарий "отказ от созвона → продолжение квалификации"
3. Мониторинг RAG примеров в реальных диалогах

## 📁 Последние изменения
- `llm_planner.py` — интеграция RAG (import, маппинг, _get_rag_examples)
- `bot_server.py` — инкремент call_proposal_count после PROPOSE_MEETING
- `sofia_userbot_pyrogram.py` — обработка AUTH_KEY_UNREGISTERED
- `/etc/systemd/system/sofia-userbot.service` — лимит рестартов

## 🚀 Команды
```bash
# Перезапуск основного бота
systemctl restart sofia-gpt

# Логи с RAG
tail -f /opt/sofia-gpt/sofia_bot.log | grep -E "RAG|LLM|Allowed"

# Статус userbot (сейчас остановлен)
systemctl status sofia-userbot

# После разблокировки Telegram — авторизация userbot
rm -f /opt/sofia-gpt/sofia_pyrogram.session
python /opt/sofia-gpt/sofia_userbot_pyrogram.py
```
