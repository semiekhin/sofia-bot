# ИНСТРУКЦИЯ ЗАВЕРШЕНИЯ СЕССИИ

## Порядок закрытия (важен!)
1. Сначала закрыть Claude Code (`session end` → `/exit`)
2. Потом закрыть claude.ai (`Закрываем сессию`)

---

## Claude Code — `session end`

1. `git diff` — посмотреть что изменилось
2. Обновить `docs/SOFIA_CURRENT.md` — что сделано, статус, следующие шаги
3. Обновить `docs/SOFIA_TASKS.md` — статусы чеклиста
4. Обновить `docs/SOFIA_KNOWLEDGE.md` — новые уроки
5. Обновить `docs/KNOWLEDGE_INDEX.md` — детали задач, как откатить
6. Обновить `CLAUDE.md` если изменилась структура
7. `git add -A && git commit -m "docs: сессия ДД.ММ.ГГГГ — описание" && git push`
8. **Синхронизировать доки в прод:**
```bash
cp /opt/sofia-gpt-dev/docs/SOFIA_CURRENT.md /opt/sofia-gpt/docs/
cp /opt/sofia-gpt-dev/docs/SOFIA_TASKS.md /opt/sofia-gpt/docs/
cp /opt/sofia-gpt-dev/docs/SOFIA_KNOWLEDGE.md /opt/sofia-gpt/docs/
cp /opt/sofia-gpt-dev/docs/KNOWLEDGE_INDEX.md /opt/sofia-gpt/docs/
```

---

## claude.ai — `Закрываем сессию`

Claude.ai читает обновлённую документацию и выдаёт промпт для следующего чата со свежими ссылками:
```bash
V=$(date +%Y%m%d_%H%M) && echo "
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_CURRENT.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_TASKS.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_KNOWLEDGE.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SESSION_END_TEMPLATE.md&v=$V
"
```

---

## Шаблон промпта для следующего чата
```
Актуализируем проект Sofia-GPT.
Сервер: 72.56.64.91:2222
Прод: /opt/sofia-gpt/ | Dev: /opt/sofia-gpt-dev/
Бот: @humanAINeural_bot | Dev: @SofiaDev01_bot
Последняя сессия: {дата} — {что сделали}

TODO: {приоритеты}

Документация:
{ссылки с &v=}

SOFIA_ARCHITECTURE.md — в Project Knowledge Claude.ai (обновлён {дата}).
```
