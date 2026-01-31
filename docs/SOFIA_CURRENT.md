# Sofia-GPT Current Status

📅 **Обновлено:** 31.01.2026

## Текущее состояние

### ✅ Работает
- **Telegram Bot** (@humanAINeural_bot) — основной бот, полный цикл
- **Max Gateway** (Radist.Online) — интеграция работает, message_processor подключен
- **message_processor.py** — единая логика для всех каналов

### ⚠️ Проблемы

#### 1. Telegram Userbot — не работает
- Коды авторизации не приходят (ни в app, ни на почту, ни по SMS)
- Номер: +79181038493 (@SofiaOazis)
- **Workaround:** использовать Telegram через Radist.Online (как Max)

#### 2. Подписка Radist — истекает 31.01.2026!
- Нужно продлить для продолжения работы Max
- Также для подключения Telegram/WhatsApp через Radist

#### 3. dialog_finished не устанавливается
- При фразах "Вопрос решён", "Не актуально", "Спасибо, не надо" — состояние не обновляется
- **Влияние:** Нет (в Max нет напоминаний)
- **Нужно:** Обновить extractor для распознавания завершающих фраз

### 📊 Архитектура
```
┌─────────────────────────────────────────────────────────────┐
│                    ВХОДЯЩИЕ КАНАЛЫ                          │
├─────────────────────────────────────────────────────────────┤
│  Telegram Bot ✅      Userbot ❌         Max ✅              │
│  bot_server.py       (не работает)    sofia_radist_gateway  │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               └───────────┬───────────────────┘
                           ↓
              ┌────────────────────────┐
              │   message_processor.py │
              │   (единая логика)      │
              └────────────────────────┘
                           ↓
              Extractor → State → Planner → Generator
```

## Сервисы
```bash
# Статус
systemctl status sofia-bot        # Telegram Bot
systemctl status sofia-radist     # Max Gateway

# Логи
tail -f /opt/sofia-gpt/sofia_bot.log
tail -f /opt/sofia-gpt/sofia_radist.log
journalctl -u sofia-bot -f
journalctl -u sofia-radist -f
```

## Команды
```bash
# Отправить первое сообщение через Max
./sofia_max_start.sh +79001234567

# Сбросить состояние клиента (Max)
sqlite3 sofia_gpt.db "DELETE FROM client_state WHERE user_id = -39XXXXXX;"
```
