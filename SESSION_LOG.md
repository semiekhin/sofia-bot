# SESSION_LOG — Последние сессии

## 08.04.2026 — Bitrix-Radist интеграция + RIZALTA промпт + git recovery

**Сделано:**

### Git recovery после краша
- Восстановлен контекст: 5 uncommitted файлов в DEV, 9 в PROD
- DEV: 3 коммита (Bitrix-Radist, docs, TTS model switch)
- PROD: 5 коммитов по каналам (core/bitrix, Telegram, Radist, Web API, docs)
- PROD push заблокирован by design (push URL = `no_push`)

### Bitrix-интеграция в Radist gateway (задача из прошлой сессии)
- Таблица radist_leads, привязка к ATL-лидам через find_recent_atlantis_lead
- Таймауты 15/60/15 мин (аналог bot_server.py)
- manager_active guard, финализация
- Окно матчинга 60 секунд в find_recent_atlantis_lead (core/bitrix.py)
- find_user_id_by_lead расширен для telegram_leads + radist_leads

### RIZALTA голосовой промпт
- Добавлена константа VOICE_SYSTEM_PROMPT_RIZALTA в core/pipeline.py
- Переключатель VOICE_PROMPT_MODE (env, default "atlantis")
- Обнаружено: voice_asterisk.py имеет захардкоженный greeting в _send_greeting()
- Фикс: переключатель в _send_greeting() по VOICE_PROMPT_MODE
- Промпт v1 (скриптовый, 3 диалога) → заменён на goal-oriented v1 (минималистичный)
- Деплой на VPS sofia-voice, .env VOICE_PROMPT_MODE=rizalta

### Тестовые звонки (Сергей)
- Звонок 1: Софья отвечала в Atlantis-стиле → найден баг (greeting не переключался)
- Звонок 2: после фикса greeting — RIZALTA-стиль, но диалог "плохой" (ударения, обрыв)
- Звонок 3: goal-oriented промпт — "не очень хорошо, перестала отвечать"
- **Вывод: нужна тонкая настройка промпта, таймингов, stability. Утром продолжим.**

### Прочее
- ElevenLabs TTS model switch: eleven_turbo_v2_5 → eleven_multilingual_v2 (для PVC)

**Коммиты:**
- 12e4bf18 feat: Bitrix CRM integration for Radist channel + 60s lead matching window
- ee24321b docs: session 07.04-08.04
- e72bc253 chore: switch ElevenLabs TTS to eleven_multilingual_v2
- 32c9996d feat(voice): add RIZALTA outbound prompt + VOICE_PROMPT_MODE switch
- 2d51ede5 feat(voice): wire VOICE_PROMPT_MODE switch into voice_asterisk.py greeting
- c47d1f1b feat(voice): goal-oriented RIZALTA prompt v1 (no script, no stages)

**Файлы:** core/pipeline.py, core/bitrix.py, sofia_radist_gateway.py, voice_asterisk.py, CLAUDE.md, BACKLOG.md

**Открытые проблемы для следующей сессии:**
- RIZALTA промпт: диалог обрывается, качество речи плохое
- Нужна тонкая настройка: ElevenLabs parameters, max_tokens, промпт
- Возможно eleven_multilingual_v2 хуже по latency чем turbo_v2_5
- Нужен анализ логов звонков для понимания где именно проблема

---

## 07.04.2026 — Research Qwen3-TTS + ElevenLabs voice tuning + VAD 0.4s + промпт-дамп

**Сделано:**

### Research: Qwen3-TTS качество для голосовой Софии
- Исследованы 5 API для Qwen3-TTS: WaveSpeed AI, DashScope (Alibaba), fal.ai, Replicate, HuggingFace
- Выбран WaveSpeed AI ($1 free credit, REST API, без карты)
- Сгенерировано **30 аудиофайлов** с реальными фразами Софии:
  - 20 базовых: 5 фраз × 4 голоса (Vivian, Serena, Sohee, VoiceDesign)
  - 10 со стилями: 3 голоса × 3 style_instruction + 2 voice_description варианта
- Файлы в `/tmp/qwen3_tts_test/`, REPORT.md с таблицей
- Вывод: для production нужен DashScope (streaming, Katerina для русского, $0.115/10k chars) или self-hosted GPU

### ElevenLabs Voice Settings (по настройкам Сергея из UI)
- stability: 0.5 → **0.35** (более выразительный)
- similarity_boost: 0.75 → **0.79**
- speed: **1.19** (новый параметр, top-level в API body)
- style и use_speaker_boost — протестированы, убраны (добавляли латентность)

### VAD threshold снижен
- VAD_SILENCE_THRESHOLD: 0.7s → **0.4s** (-300ms ощущаемой паузы)
- Задача A1 из бэклога выполнена (1.2 → 0.7 → 0.4)

### Промпт-дамп
- Создан `TASK_DUMP_SOFIA_PROMPTS.md` — полный дамп всех 9 промптов системы
- Карта: какой промпт где вызывается (Extractor → Analyzer → RAG → Generator)
- Анализ логов: 3 голосовых звонка + 1 текстовый диалог за 07.04

### Анализ диалогов — найденные проблемы
- LLM выдумал фейковый номер телефона (+7 123 456 78 90) — критический баг
- "В Сочи → в Туапсе" бессвязная логика (llama-4-scout)
- Реакция на мусор STT ("Эротика", "Зависят облака")
- Длинные ответы для голоса (194-240 символов при лимите 1-2 предложения)

**Коммиты:** TBD (текущий)

**Файлы:** voice_asterisk.py, TASK_DUMP_SOFIA_PROMPTS.md, /tmp/qwen3_tts_test/

**Текущие тайминги (обновлены):**
- VAD silence: **400ms** (было 700ms)
- STT: ~300ms
- LLM: ~500ms
- TTS first byte: ~450-700ms
- **Итого: ~1000ms** (было ~1300ms)

**Следующая сессия:** Сценарий исходящего обзвона — ЖК RIZALTA (сбор информации, оффер, новый промпт)

---

## 06.04.2026 — Голосовой стек: Телфин → Asterisk → AudioSocket → STT/LLM/TTS

**Сделано:**

### Фаза 1: Asterisk + SIP trunk Телфин
- SSH доступ к российскому VPS (`ssh sofia-voice`, 185.207.66.201)
- VPS очищен (x-ui, zabbix удалены, DNS починен, система обновлена)
- Asterisk 20 установлен, PJSIP trunk к sipproxy.telphin.ru:5068 (порт 5090)
- SIP регистрация работает, входящие звонки доходят до Asterisk

### Фаза 2: AudioSocket сервер
- voice_asterisk.py: TCP сервер на порту 9090, протокол AudioSocket (UUID=0x01, Audio=0x10, Hangup=0x00)
- Двусторонний аудиопоток подтверждён (433 фрейма за 8.7 сек, clean hangup)
- Документация протокола исправлена (официальная была неточной)

### Фаза 3: Полный pipeline STT → LLM → TTS
- **Проблема**: Groq/OpenAI/ElevenLabs заблокированы из России (403)
- **Решение**: nginx proxy на основном сервере (72.56.64.91:8095), UFW rule для VPS IP
- STT: Yandex SpeechKit REST (~300ms, напрямую с VPS)
- LLM: Groq llama-4-scout через proxy (~500ms)
- TTS: ElevenLabs Nastya через proxy
- Полный диалог работает: квалификация, ответы по контексту

### Попытка перенести Asterisk на основной сервер
- Телфин ответил 403 Forbidden Ip — IP 72.56.64.91 не в белом списке
- Asterisk на основном сервере отключен, вернулись на VPS

### TTS оптимизация: streaming
- ElevenLabs streaming endpoint + optimize_streaming_latency=4
- MP3 stream → ffmpeg pipe → 8kHz PCM (proper resampling)
- First audio: **~400-500ms** (было 5-8 сек полное ожидание)
- Voice ID исправлен: YjESejviApN7SHrbfnA2 (Nastya, был Jessica)

### Промпт: фикс "Повторите пожалуйста" loop
- LLM не понимал "Завтра" как ответ на "Когда удобнее?"
- Добавлен пример и явное правило для дат/времени в VOICE_SYSTEM_PROMPT

### A1: VAD + barge-in
- VAD silence threshold: 1.2с → 0.7с (-500ms ощущаемой паузы)
- Barge-in: клиент перебивает → TTS мгновенно останавливается
- 5+ фреймов (~100ms) sustained speech для подтверждения barge-in
- Barge-in аудио → VAD → STT → LLM (не теряется контекст)

**Коммиты:** f59186fb → 4c5b34ad (6 коммитов)

**Файлы:** voice_asterisk.py, core/pipeline.py, asterisk/pjsip.conf, asterisk/extensions.conf, asterisk/logger.conf, /etc/nginx/sites-available/llm-proxy

**Текущие тайминги (конец речи → первый звук):**
- VAD silence: 700ms (клиент не ощущает)
- STT: ~300ms
- LLM: ~500ms
- TTS first byte: ~500ms
- **Итого до первого звука: ~1300ms** (ощущаемая пауза ~1300ms)

**Оставлено на завтра:** B1 (filler звуки), A3 (LLM streaming + sentence-level TTS)

---

## 05.04.2026 — Диагностика застрявших лидов, фикс SOFIA_PATH + логирование

**Сделано:**

### Диагностика 4 лидов (264270, 264264, 264260, 264252)
- Все 4 лида "Планировки Атлантис" (SOURCE_ID=397) уже распределены менеджерам — ни один не застрял на София AI (428)
- Клиенты заполнили форму Тильды ночью, но НЕ перешли в Telegram-бот → София их не видела
- Битрикс-робот раздал лиды напрямую, без квалификации Софией
- 0 лидов с ASSIGNED=428 во всём Битрикс с 1 апреля

### Фикс SOFIA_PATH (повтор бага 21.03)
- Prod `.env` не содержал `SOFIA_PATH` → бот использовал дефолт `/opt/sofia-gpt-dev` и писал в DEV базу данных
- Добавлен `SOFIA_PATH=/opt/sofia-gpt` в prod `.env`
- При рестарте таблица `telegram_leads` автоматически создана в prod БД (ранее не существовала)

### Фикс логирования bitrix.py в bot_server.py
- `bot_server.py` не вызывал `logging.basicConfig()` → все `log.info()/warning()` из `core/bitrix.py` молча проглатывались
- Добавлен `logging.basicConfig(level=INFO)` — логи `[sofia.bitrix]` теперь видны в `journalctl -u sofia-gpt`
- Все вызовы `finalize_lead`, `start_distribution_bp`, `set_lead_assigned` теперь логируются

### Деплой в PROD
- Оба фикса задеплоены, `sofia-gpt.service` перезапущен
- Верификация: DB_PATH=/opt/sofia-gpt/sofia_gpt.db, telegram_leads создана, логи видны

**Коммиты:** (текущий)

**Файлы (prod):** /opt/sofia-gpt/.env, /opt/sofia-gpt/bot_server.py

---

## 04.04.2026 — Деплой Bitrix-интеграции в прод, фикс дублей и таймаутов

**Сделано:**

### Диагностика и фикс дублей лидов
- **core/bitrix.py**: `find_lead_by_phone()` — поиск существующего лида по телефону через `crm.lead.list` перед созданием нового
- **core/bitrix.py**: дедупликация в `create_or_update_lead()` — если `lead_id=None` и есть телефон → ищет в Битрикс, обновляет вместо создания

### Деплой finalize_lead + start_distribution_bp в PROD
- **core/bitrix.py**: `finalize_lead()` и `start_distribution_bp()` были только в DEV — задеплоены в PROD
- **bot_server.py**: `restore_assigned()` → `finalize_lead()` (строки 790, 986)
- **web_api.py**: `restore_assigned()` → `finalize_lead()` (строка 272)
- **.env prod**: `BITRIX_BP_TEMPLATE_ID=152`

### Фикс ASSIGNED_BY_ID для БП
- БП 152 не срабатывает при ASSIGNED_BY_ID=428 (София AI)
- **core/bitrix.py**: `finalize_lead()` теперь ставит `BITRIX_BP_ASSIGNED_ID=24932` перед запуском БП (вместо `restore_assigned`)
- **.env**: `BITRIX_BP_ASSIGNED_ID=24932` (dev + prod)

### Фикс краша таймаута (manager_active)
- Таймаут падал: `no such column: manager_active` — колонка не в `state_manager.py`
- **state_manager.py**: добавлены `manager_active` и `finance_interested` в ClientState, get_state(), _save_state(), CREATE TABLE
- **bot_server.py**: ALTER TABLE миграции в init_db() (не зависеть от web-api)

### Фикс webhook-токена
- Старый токен (`z61d...`) не имел прав на `bizproc` → ошибка "higher privileges"
- **.env**: новый `BITRIX_BASE_URL` с токеном `uviwr0b350u3m6gf` (crm + bizproc)

### Фикс Тильды
- Redirect вёл на dev-бота (`SofiaDev01_bot`) → клиенты не попадали в прод
- Исправлено на `t.me/humanAINeural_bot?start=ATL`

### Документация
- **docs/LEAD_LIFECYCLE.md**: полная архитектура интеграции с CRM, конфигурация, масштабирование
- **docs/NEW_CLIENT_ONBOARDING.md**: пошаговая инструкция подключения нового ЖК

### Успешный E2E тест
- Форма Тильды → лид #264242 в Битрикс → /start ATL → привязка → 15 мин таймаут → ASSIGNED=24932 → BP 152 started → статус лида изменился

**Коммиты:** 276aebf6 → 9ee60d22 (5 коммитов)

**Файлы:** core/bitrix.py, bot_server.py, web_api.py, state_manager.py, docs/LEAD_LIFECYCLE.md, docs/NEW_CLIENT_ONBOARDING.md, BUILD_REPORT_BITRIX_DEPLOY.md

**Логи:** бот пишет в файл `/opt/sofia-gpt/sofia_bot.log` (не journalctl!), Bitrix-операции — в journalctl через logging

---

## 02.04.2026 — Битрикс: запуск БП раздачи после квалификации

**Сделано:**
- **core/bitrix.py**: `start_distribution_bp(lead_id)` — вызов `bizproc.workflow.start` с TEMPLATE_ID из env; `finalize_lead(db_path, lead_id)` — обёртка restore_assigned + BP start; `build_qualification_summary(state)` — итог квалификации в COMMENTS (цель, бюджет, оплата, созвон)
- **bot_server.py**: оба пути финализации (`_finalize_timeout` и `delayed_response`) используют `finalize_lead()` вместо `restore_assigned()`
- **.env**: `BITRIX_BP_TEMPLATE_ID=152`
- Radist не затронут — у него нет Bitrix-интеграции (P1 задача)
- web_api.py и voice_api.py не изменены

**Коммиты:** c1987ff5

**Файлы:** core/bitrix.py, bot_server.py, .env, BUILD_REPORT_BITRIX_BP.md

---

## 30.03.2026 — CLAUDE.md: шаблон промптов для Claude Code

**Сделано:**
- Добавлена секция «Промпты для Claude Code» в CLAUDE.md — формат "Задача готова когда" с проверяемыми критериями (3–6 на задачу)

**Коммиты:** 1

**Файлы:** CLAUDE.md

---

---
