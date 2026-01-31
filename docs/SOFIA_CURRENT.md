# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 31.01.2026

## ✅ Что сделано (сессия 30-31.01.2026)

### Мультиканальность через Radist
- Мультиканальный gateway v2.0 (Max + Telegram)
- Webhook для обоих каналов настроен
- Единая БД radist_messages для всех каналов

### Проактивная отправка (ГЛАВНОЕ!)
- Скрипт sofia_outreach.sh для первого контакта с клиентом
- Telegram: по @username
- Max: по номеру телефона
- Сохраняет первое сообщение в БД для контекста

### Observer Chat
- Группа "Диалоги Софья" — все диалоги в одном месте
- Формат: `[КАНАЛ] Клиент → сообщение` и `София → Клиент: ответ`
- Бот игнорирует сообщения в группах

## 🔄 Текущее состояние
- ✅ Max через Radist — работает
- ✅ Telegram через Radist — работает
- ✅ Telegram Bot (@humanAINeural_bot) — работает
- ✅ Проактивная отправка — работает
- ✅ Observer Chat — работает
- ⏳ WhatsApp — не подключён в Radist

## ⚠️ Известные баги
- BUG-001: dialog_finished не ставится при отказе клиента (см. SOFIA_BUGS.md)

## 🔜 Следующие шаги
1. Подключить WhatsApp через Radist
2. Фикс BUG-001 (напоминания при отказе)
3. Добавить эталонный пример в RAG ("ошибочный контакт")
4. Исследовать LLM-Planner v2.0 (свободный режим без детерминированного планера)

## 📁 Изменённые файлы
- `config/radist_config.py` — мультиканальный конфиг
- `sofia_radist_gateway.py` — gateway v2.0 с Observer
- `sofia_outreach.sh` — скрипт проактивной отправки
- `bot_server.py` — игнорирование групп
- `docs/SOFIA_BUGS.md` — новый файл с багами
- `docs/SOFIA_TASKS.md` — новые задачи

## 🔧 Команды
```bash
# Проактивная отправка
/opt/sofia-gpt/sofia_outreach.sh telegram @username [Имя]
/opt/sofia-gpt/sofia_outreach.sh max 79001234567 [Имя]

# Перезапуск сервисов
systemctl restart sofia-gpt        # Telegram Bot
systemctl restart sofia-radist     # Radist Gateway

# Логи
tail -f /opt/sofia-gpt/sofia_radist.log
tail -f /opt/sofia-gpt/sofia_bot.log
```
