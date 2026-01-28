# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 28.01.2026, ~14:45

## ✅ Что сделано (28.01.2026)

### Max интеграция через Radist.Online
- [x] Создан `sofia_radist_gateway.py` — webhook сервер для входящих из Max
- [x] Создан `sofia_max_start.sh` — скрипт для исходящих сообщений
- [x] Зарегистрирован webhook в Radist API (id: 130e4e59-439f-4a71-8bed-2c0a699c8bc6)
- [x] Открыт порт 5001 в ufw
- [x] Фильтрация outbound сообщений (чтобы не отвечать самой себе)

### Баг-фикс в extractor.py (затрагивает ВСЕ боты)
- [x] Добавлены strategy, usage, family в `merge_extraction_to_state()`
- Эти поля никогда не сохранялись — баг существовал с момента добавления v2.0

## ⚠️ Известные проблемы

### Max Gateway — неполная логика
- `materials_request_count` — добавлен фикс, но НЕ ПРОТЕСТИРОВАН корректно
- После первого отказа от созвона снова предлагает созвон вместо продолжения квалификации
- **Причина:** Gateway копирует логику из bot_server.py, но возможно не полностью

### Архитектурная проблема
- Логика Sofia продублирована в 3 файлах: bot_server.py, sofia_userbot_pyrogram.py, sofia_radist_gateway.py
- Фиксы в одном месте не попадают в другие
- **Решение:** Вынести общую логику в message_processor.py (TODO)

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — работает с исправленным extractor.py
- Max Gateway — запускается, принимает webhook, отвечает

### ⚠️ Требует доработки
- Max Gateway — логика квалификации работает некорректно (петля созвонов)
- Userbot — остановлен (сессия Telegram истекла)

## 🔜 Следующие шаги
1. **СРОЧНО:** Изучить planner.py и понять полную логику после отказа от созвона
2. Исправить логику в gateway чтобы соответствовала bot_server.py
3. Протестировать полный цикл квалификации в Max
4. ⚠️ Подписка Radist до 31.01.2026!

## 📁 Изменённые файлы
- `extractor.py` — добавлены strategy, usage, family в simple_fields
- `sofia_radist_gateway.py` — СОЗДАН (webhook для Max)
- `sofia_max_start.sh` — СОЗДАН (исходящие в Max)
- `config/radist_config.py` — уже существовал

## 🚀 Команды
```bash
# Gateway Max
pkill -f sofia_radist_gateway
cd /opt/sofia-gpt && source venv/bin/activate && nohup python sofia_radist_gateway.py > sofia_radist.log 2>&1 &

# Отправить сообщение в Max
./sofia_max_start.sh +79001234567

# Логи Max
tail -f /opt/sofia-gpt/sofia_radist.log

# Основной бот
systemctl restart sofia-gpt
```
