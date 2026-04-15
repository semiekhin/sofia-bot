# Sprint Contract Template v2

Универсальный шаблон Sprint Contract от оркестратора (Claude.ai) к Claude Code для проекта Sofia-GPT. Версия v2 (15.04.2026): XML-структура вместо markdown headings — Claude парсит XML-теги значительно надёжнее.

**Как пользоваться:** оркестратор копирует весь блок ниже в новый чат с Claude Code, заполняет обязательные секции под конкретную задачу, удаляет неприменимые опциональные секции, оставляет два встроенных блока (`<anti_overengineering>` и `<investigate_before_answering>`) дословно. Filling example в конце документа — НЕ часть копируемого шаблона, это эталон для оркестратора как должен выглядеть заполненный контракт.

---

## Шаблон (копировать всё ниже до маркера `END OF TEMPLATE`)

<anti_overengineering>
Минимально достаточное решение. Не создавай новых абстракций, конфигов, env-переменных, файлов — если задача решается правкой существующего кода. Если кажется что нужен рефакторинг соседнего кода — НЕ делай его в этой задаче, только упомяни в Build Report как «обнаруженная побочная проблема».
</anti_overengineering>

<investigate_before_answering>
Не предполагай содержимое файлов и состояние системы. Если ссылаешься на файл — сначала прочитай его (cat / view). Если на состояние сервиса — сначала проверь (systemctl status / ps / журналы). Вывод «по памяти» в этом проекте = баг.
</investigate_before_answering>

<role>
[По умолчанию: backend-инженер на production-кодовой базе Sofia-GPT (Python 3.12, FastAPI, SQLite, OpenAI, Telegram, Bitrix CRM, Asterisk voice). Оркестратор может переопределить под конкретную задачу — например «фронтенд-разработчик HTML/CSS виджета», «sysadmin VPS», «технический писатель документации».]
</role>

<context>
[Почему задача возникла. Какая история. Что предшествовало. Без воды — 2-5 предложений. Если задача — продолжение прошлой сессии, дать ссылку на коммит/секцию SESSION_LOG.]
</context>

<task>
[Что конкретно сделать. Одна-две фразы. Цель должна формулироваться в виде глагола: «добавить X в файл Y», «починить Z в сервисе W», «создать файл F со спецификацией S». Не «разобраться с», не «улучшить» — конкретный артефакт на выходе.]
</task>

<investigate_first>
[Что прочитать/проверить ДО действий. Перечислять прямо файлы и команды. Лечит баг «отвечаю по памяти». Примеры: `cat core/pipeline.py`, `sqlite3 sofia_gpt_dev.db ".schema messages"`, `systemctl status sofia-radist-dev`, `git log --oneline -5 -- core/bitrix.py`. Если задача тривиальна — написать «не требуется».]
</investigate_first>

<acceptance_criteria>
[Нумерованный список из 3-6 проверяемых критериев. Каждый формулируется как «при X происходит Y», не «работает правильно». Примеры:
1. `grep -c "def new_function" file.py` возвращает `1`
2. При POST /api/endpoint с payload `{...}` ответ содержит поле `status: "ok"`
3. После рестарта сервиса в `journalctl -u sofia-radist-dev -n 20` нет ERROR-строк
4. `flake8 file.py --max-line-length=120` проходит без замечаний]
</acceptance_criteria>

<do_not>
ALWAYS-applicable (оставить как есть в каждом контракте):
- Не создавать новых файлов, если задача решается правкой существующих
- Не добавлять env-переменные и конфиги, не описанные в задаче
- Не рефакторить соседний код «по пути»
- Не делать `git push` в `/opt/sofia-gpt/` (PROD заблокирован by design)
- Не трогать `/etc/asterisk/`
- Не перезапускать Asterisk (`systemctl restart asterisk`) без явного разрешения в задаче
- При git-операциях в multi-repo окружении (DEV + PROD) — всегда явный `cd /opt/sofia-gpt-dev` или `cd /opt/sofia-gpt` перед git-вызовом, не полагаться на текущую cwd
- При фильтрах к Bitrix API / SQL: если результат пустой — попробовать второй способ проверки, не делать вывод «значит ничего нет»

Task-specific (заполняет оркестратор под конкретную задачу):
- [специфичный запрет 1, если есть]
- [специфичный запрет 2, если есть]
</do_not>

<rollback>
[Конкретные команды с конкретными путями. Пример: `git -C /opt/sofia-gpt-dev checkout HEAD -- core/bitrix.py && sudo systemctl restart sofia-radist-dev`. Для отката коммита: `cd /opt/sofia-gpt-dev && git reset --hard HEAD~1`. Если задача read-only — написать «read-only, rollback не требуется».]
</rollback>

<build_report_format>
После выполнения Claude Code присылает оркестратору отчёт в этом формате:

```
# Build Report: <SPRINT_NAME>

## Артефакт
| Поле     | Значение                                |
|----------|-----------------------------------------|
| Путь     | /opt/sofia-gpt-dev/...                  |
| Размер   | N байт                                  |
| md5      | <hash>                                  |
| Коммит   | <sha> <commit message subject>          |

## Acceptance Criteria
| # | Критерий          | Статус | Факт проверки                |
|---|-------------------|--------|------------------------------|
| 1 | <текст AC>        | ✅     | <команда + результат>        |

## Решённые неоднозначности
- [что Claude Code трактовал по своему усмотрению, если в задаче была неоднозначность]

## Не смог проверить
- [честно: что не смог проверить и почему — нет браузера, нет GPU, нет доступа к внешней системе]

## Обнаруженные побочные проблемы
- [что заметил по дороге, но не трогал — баги, технический долг, расхождения документации с реальностью]
```
</build_report_format>

<done_when>
Build Report содержит чек-лист по `<acceptance_criteria>` выше, каждый пункт с фактической проверкой (например «грепнул, нашёл N совпадений: ...», «curl вернул HTTP 200 с body ...»), а не «выполнено».
</done_when>

---

## Опциональные секции (включать только если применимо, иначе удалить)

<subagents>
[Опционально. Если задача декомпозируется на 2+ независимые ветки разведки, дать подсказку использовать параллельные subagents через Agent tool. Пример: «3 независимых разведки A/B/C — рассмотри запуск трёх Explore-subagents параллельно». Без подсказки Claude Code обычно идёт последовательно.]
</subagents>

<stop_for_confirmation>
[Опционально. Точки остановки внутри сложного спринта, где Claude Code должен показать промежуточный результат и дождаться подтверждения оркестратора перед следующей фазой. Используется в спринтах с риском: PROD-деплой, миграции БД, ребуты сервисов, удаление файлов с диска. Если задача низкорисковая — секция удаляется.]
</stop_for_confirmation>

<edge_cases>
[Опционально. Известные edge cases которые Claude Code должен учесть, но которые не очевидны из задачи. Примеры: iOS Safari `env(safe-area-inset-bottom)` поддержка с 11.2; экраны <360px и ellipsis; idempotency при повторном запуске. Если не известны — секция удаляется.]
</edge_cases>

<external_artifacts>
[Опционально. Base64-данные, длинные конфиги, JSON-схемы, которые были бы шумом в `<task>`/`<acceptance_criteria>`. Пример: base64 аватарка для виджета, эталонный YAML-конфиг. Если нет — секция удаляется.]
</external_artifacts>

END OF TEMPLATE

---

## Filling example (как выглядит заполненный контракт на тривиальной задаче)

Ниже — пример заполнения шаблона на простой задаче «добавить логирование вызова finalize_lead в core/bitrix.py». Этот пример показывает уровень детализации, который оркестратор должен соблюдать.

```
<anti_overengineering>
Минимально достаточное решение. Не создавай новых абстракций, конфигов,
env-переменных, файлов — если задача решается правкой существующего кода.
Если кажется что нужен рефакторинг соседнего кода — НЕ делай его в этой
задаче, только упомяни в Build Report как «обнаруженная побочная проблема».
</anti_overengineering>

<investigate_before_answering>
Не предполагай содержимое файлов и состояние системы. Если ссылаешься на
файл — сначала прочитай его (cat / view). Если на состояние сервиса —
сначала проверь (systemctl status / ps / журналы). Вывод «по памяти» в
этом проекте = баг.
</investigate_before_answering>

<role>backend-инженер на Sofia-GPT</role>

<context>
finalize_lead() пишет в Bitrix, но в journalctl -u sofia-gpt не видно
самого факта вызова — только результата. При диагностике лидов 05.04
из-за этого пришлось гадать когда именно вызов был. Нужна одна log.info
строка перед HTTP-запросом.
</context>

<task>
В функции finalize_lead() в core/bitrix.py добавить log.info("[finalize_lead]
called for lead_id=%s", lead_id) первой строкой тела функции.
</task>

<investigate_first>
- cat /opt/sofia-gpt-dev/core/bitrix.py — найти функцию finalize_lead,
  убедиться что log = logging.getLogger(...) уже определён в модуле
- grep -n "def finalize_lead" /opt/sofia-gpt-dev/core/bitrix.py
</investigate_first>

<acceptance_criteria>
1. grep "[finalize_lead] called" core/bitrix.py возвращает ровно 1 совпадение
2. Строка находится первой в теле функции finalize_lead (после def)
3. flake8 core/bitrix.py --max-line-length=120 без замечаний
</acceptance_criteria>

<do_not>
ALWAYS-applicable секция как в шаблоне.
Task-specific: не менять никакие другие функции в bitrix.py.
</do_not>

<rollback>
git -C /opt/sofia-gpt-dev checkout HEAD -- core/bitrix.py
</rollback>

<done_when>
Build Report содержит чек-лист AC с фактическими grep/flake8-выводами.
</done_when>
```

Для сложных задач (DISK_RESCUE_v2, ATLANTIS_CHAT_WIDGET_v1) добавляются опциональные `<stop_for_confirmation>`, `<edge_cases>`, `<external_artifacts>`.
