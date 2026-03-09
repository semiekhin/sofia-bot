# Session Guide — чеклист начала/конца сессии

## Начало сессии

1. Открыть claude.ai, вставить промпт с ссылками вида:

https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_CURRENT.md&v=YYYYMMDD
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_TASKS.md&v=YYYYMMDD
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_KNOWLEDGE.md&v=YYYYMMDD

ВАЖНО: менять v=YYYYMMDD на текущую дату при каждом новом чате.
Сегодня например: v=20260309
Это обходит кэш Claude — без этого он читает старую версию.

2. Убедиться что Claude показал дату последней сессии из SOFIA_CURRENT.md
3. Обсудить задачу, получить план
4. ssh sofia-dev -> cd /opt/sofia-gpt-dev -> claude
5. Выполнить задачу в Claude Code

## Конец сессии

6. В Claude Code: session end -> подтвердить коммит
7. Обновить SOFIA_CURRENT.md и SOFIA_TASKS.md на сервере
8. В claude.ai: Закрываем сессию -> получить промпт для следующей
9. Сохранить промпт с актуальной датой в v=
