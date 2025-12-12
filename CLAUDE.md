# Sofia Bot — AI-продажник недвижимости

## Что это
AI-менеджер по продажам курортной недвижимости для Oazis Estate. Общается с клиентами в Telegram, квалифицирует и выводит на видеопрезентацию. Самообучается каждую ночь на основе оценок экспертов.

## Бот
- Prod: @SofiaOazisBot (или как называется)

## Сервер
```bash
ssh -p 2222 root@72.56.64.91
```
- `/opt/sofia-bot` — prod

## Стек
Python 3.12 · python-telegram-bot · OpenAI GPT-5-mini · SQLite · GPT-5.1 (анализ)

## Ключевые файлы
- `bot_server.py` — главный бот
- `sofia_prompt.py` — промпт Софии (автообновляется)
- `sofia_analyzer.py` — ночной анализатор (22:00)
- `prompt_health.py` — мониторинг здоровья
- `morning_ping.py` — утренние напоминания (ручной запуск)
- `sofia_conversations.db` — база диалогов и оценок

## Версия: 1.0.0

## Последняя сессия: 2025-12-11
- ✅ Запущена система автоанализа (GPT-5.1, 22:00 daily)
- ✅ Первый анализ выполнен, промпт улучшен
- ✅ Мониторинг здоровья промпта
- ✅ Утренний пинг готов (не активирован)

## TODO
- [ ] Создать GitHub репо
- [ ] Поднять GOOD rate с 56% до 80%
- [ ] Собрать 500 GOOD диалогов для fine-tuning
- [ ] Интеграция с WhatsApp Business API
- [ ] Claude-версия бота для сравнения

## Автоматизация (cron)
```
0 22 * * * — sofia_analyzer.py (анализ + улучшение промпта)
```

## Команды
```bash
# Статус бота
systemctl status sofia-bot

# Логи
journalctl -u sofia-bot -f

# Здоровье промпта
python3 prompt_health.py

# Ручной анализ
export $(cat .env | xargs) && python3 sofia_analyzer.py

# Утренний пинг (когда нужно)
export $(cat .env | xargs) && python3 morning_ping.py

# Откат промпта
cp backups/sofia_prompt_YYYYMMDD_HHMMSS.py sofia_prompt.py
systemctl restart sofia-bot
```

## Важные правила
- Токены в .env, НЕ в коде
- Бэкапы промптов в /backups/ (7 дней)
- Оценки экспертов — главный источник улучшений

## Документация
- `PROJECT_HISTORY.md` — история проекта
- `RESTORE.md` — восстановление
