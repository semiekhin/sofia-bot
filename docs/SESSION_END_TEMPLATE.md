# ИНСТРУКЦИЯ ЗАВЕРШЕНИЯ СЕССИИ

Когда пользователь говорит "ЗАВЕРШАЕМ СЕССИЮ" или "актуализируем" — выполни этот чеклист.

---

## 0. ПРОЧИТАЙ ВСЕ ДОКИ (ОБЯЗАТЕЛЬНЫЙ ПЕРВЫЙ ШАГ)

Перед любыми изменениями — прочитай содержимое КАЖДОГО файла:
```bash
cat /opt/sofia-gpt/docs/SOFIA_CONTEXT.md
cat /opt/sofia-gpt/docs/SOFIA_ARCHITECTURE.md
cat /opt/sofia-gpt/docs/SOFIA_CURRENT.md
cat /opt/sofia-gpt/docs/SOFIA_KNOWLEDGE.md
cat /opt/sofia-gpt/docs/SOFIA_TASKS.md
```

Сравни с реальным состоянием проекта. Если документ устарел — обнови, независимо от того что делалось в текущей сессии. Новый чат будет читать эти файлы первыми — если они врут, он начнёт с ложных предпосылок.

---

## 1. Обнови ВСЕ устаревшие документы

### SOFIA_CONTEXT.md
Общее описание проекта, инфраструктура, версия, каналы. Должно отражать текущую реальность.

### SOFIA_ARCHITECTURE.md
Архитектура, схемы, потоки данных, компоненты. Если описывает старую версию — переписать.

### SOFIA_CURRENT.md
Что сделано в последней сессии, текущий статус, следующие шаги, последние изменения файлов.

### SOFIA_KNOWLEDGE.md
Важные решения, баги, уроки. Добавь новые записи если были.

### SOFIA_TASKS.md
Выполненные задачи → в ✅, новые → добавить, приоритеты обновить.

### Дополнительные доки (ATLANTIS_PRICES.md, WIDGET_INSTALL.md и др.)
Проверь актуальность, обнови если нужно.

---

## 2. Git коммит и пуш (ОБЯЗАТЕЛЬНО)
```bash
cd /opt/sofia-gpt
git add -A
git commit -m "docs: сессия {ДД.ММ.ГГГГ} — {краткое описание}"
git push
```

---

## 3. Выдай блок для нового чата

Формат:
```
Актуализируем проект Sofia-GPT.
Сервер: 72.56.64.91:2222
Путь: /opt/sofia-gpt/
Бот: @humanAINeural_bot
Последняя сессия: {дата} — {что сделали}

{Краткое описание главного изменения}

TODO: {что нужно сделать}

Документация на GitHub:
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_CONTEXT.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_CURRENT.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_ARCHITECTURE.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_KNOWLEDGE.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_TASKS.md
```

---

## 4. Проверь перед завершением

- [ ] Все 5+ документов прочитаны и проверены на актуальность
- [ ] Устаревшие документы обновлены (даже если не связаны с текущей сессией)
- [ ] Git commit + push выполнен
- [ ] Следующие шаги понятны для нового чата
- [ ] Блок для копирования готов
