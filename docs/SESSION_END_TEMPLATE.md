# ИНСТРУКЦИЯ ЗАВЕРШЕНИЯ СЕССИИ

Когда пользователь говорит "ЗАВЕРШАЕМ СЕССИЮ" или "актуализируем" — выполни этот чеклист.

---

## 1. Обнови документацию на сервере

### SOFIA_CURRENT.md (ОБЯЗАТЕЛЬНО)
```bash
cat > /opt/sofia-gpt/docs/SOFIA_CURRENT.md << 'CURRENT'
# Текущий статус Sofia-GPT

📅 **Последняя сессия:** {ДАТА И ВРЕМЯ}

## ✅ Что сделано
- {Конкретное действие 1}
- {Конкретное действие 2}

## 🔄 Текущее состояние
- {Что работает}
- {Что не работает}

## 🔜 Следующие шаги
1. {Приоритет 1}
2. {Приоритет 2}

## 📁 Последние изменения
- `{файл}` — {что изменили}
CURRENT
```

### SOFIA_KNOWLEDGE.md (если были важные решения)
Добавь новую секцию:
```
### {Дата}: {Название решения}
**Проблема:** {Описание}
**Решение:** {Что сделали}
**Почему:** {Аргументы}
```

### SOFIA_TASKS.md (если изменились задачи)
- Перенеси выполненные в ✅ Выполнено
- Добавь новые задачи
- Обнови метрики

### SOFIA_ARCHITECTURE.md (если изменилась структура)
- Новые компоненты
- Изменённые потоки данных

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

**ВАЖНО:** Ссылки на документацию даём с GitHub (raw), не с сервера!

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

- [ ] SOFIA_CURRENT.md обновлён с датой и статусом
- [ ] Все изменённые файлы указаны
- [ ] Git commit + push выполнен
- [ ] Следующие шаги понятны для нового чата
- [ ] Блок для копирования готов (со ссылками на GitHub)

---

## Пример завершения

**Пользователь:** ЗАВЕРШАЕМ СЕССИЮ

**Claude:**
1. Обновляю SOFIA_CURRENT.md...
2. Добавляю в SOFIA_KNOWLEDGE.md решение про счётчик повторов...
3. Git commit + push...

**Блок для нового чата:**
```
Актуализируем проект Sofia-GPT.
Сервер: 72.56.64.91:2222
Путь: /opt/sofia-gpt/
Бот: @humanAINeural_bot
Последняя сессия: 15.01.2026 — унификация HELP_* логики

Главное изменение: HELP_* теперь объясняют зачем нужна информация

TODO: протестировать новую логику

Документация на GitHub:
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_CONTEXT.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_CURRENT.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_ARCHITECTURE.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_KNOWLEDGE.md
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/docs/SOFIA_TASKS.md
```
