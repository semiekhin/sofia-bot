# SESSION_LOG — Последние сессии

## 28.03.2026 (ночь) — Groq интеграция, P0 баги, промпт V4

**Сделано:**
- A/B тест round 1: gpt-5.4-mini vs qwen3-32b (Groq). Qwen 2.9x быстрее (141 vs 403ms), но 5x "Поняла" и галлюцинации времени
- A/B тест round 2: промпт V2 + llama-4-scout-17b. Три модели, 12 кейсов, 2 прогона:
  - OpenAI gpt-5.4-mini: TTFT 377ms, quality 96%
  - Groq qwen3-32b (V2): TTFT 151ms, quality 88% (2+ вопроса)
  - **Groq llama-4-scout (V2): TTFT 108ms, quality 92%** — лучший баланс
- Multi-turn тест: 4 сценария × 7 ходов. llama-4-scout = gpt-5.4-mini по качеству (96%), TTFT 99ms vs 381ms
- **Voice pipeline v4**: Groq llama-4-scout primary, OpenAI fallback
  - Groq клиент через OpenAI-compatible SDK
  - VOICE_PROVIDER env var ("groq"/"openai"), автоматический fallback
  - Промпт V3: строгие запреты "Поняла", галлюцинации времени, anti-looping
- **P0 баги:**
  - Дедупликация транскриптов: 3-уровневая (exact + prefix + word overlap 85%)
  - Budget парсинг: _parse_budget_from_text() — "десять-пятнадцать", "от 8 до 12", дефис, без "миллион"
  - Retell Boosted Keywords: нет RETELL_API_KEY — нужна ручная настройка в dashboard
- **Промпт V4** (по итогам живого звонка 21:48):
  - Блок ФАКТЫ: доходность 8-15% аренда, 20-30% стройка
  - [END] правила: "пришлите варианты" = интерес, не отказ
  - Anti-looping: не повторять "эксперт покажет" подряд
  - max_tokens 300→400 (фикс обрезки mid-word)
  - finish_reason логирование
  - Stage MEETING override из assistant history

**Тайминги (Groq, живой звонок):**
- Медиана TTFT: ~185ms (было 600ms gpt-4.1-mini, 325ms gpt-5.4-mini)
- Худший ход: 851ms (rate limit?)
- Лучший ход: 107ms

**Коммиты:** 636c08ac → cd05b8a9 (6 коммитов)

**Файлы:** core/pipeline.py, voice_api.py, .env, tests/ab_test_voice_llm.py, tests/multiturn_test.py, docs/VOICE_LATENCY_RESEARCH.md

**Открытые вопросы:**
- Retell Boosted Keywords — нужен API ключ или ручная настройка в dashboard
- Groq rate limits на бесплатном плане (28 из 40 запросов в A/B тесте throttled)
- llama-4-scout looping "эксперт покажет" — промпт V4 должен помочь, нужен повторный живой тест
- Retell begin_message — возможно другой голос на приветствии

**Следующий шаг:** живой тест промпта V4, Retell Boosted Keywords, Groq платный план

---

## 28.03.2026 (вечер) — Исследование альтернативных LLM для голоса

**Сделано:**
- Практические замеры TTFT на 8 моделях Groq (streaming, 3 прогона каждая)
- YandexGPT протестирован — наш YANDEX_SPEECHKIT_API_KEY работает для LLM API (folder_id=b1giu7d61rvmondibc51)
- Сетевая задержка замерена до 5 провайдеров (Yandex, Groq, Fireworks, Together, DeepSeek)
- Веб-исследование: Yandex AI Studio (Alice AI, Qwen3-235B), Together AI, Fireworks AI, DeepSeek API
- Полный отчёт → docs/VOICE_LATENCY_RESEARCH.md секция 8

**Ключевые результаты (streaming TTFT с нашего сервера):**

| Модель | Провайдер | TTFT медиана | Русский |
|--------|-----------|-------------|---------|
| gpt-5.4-mini (текущая) | OpenAI | 325ms | Отличный |
| qwen3-32b + /no_think | Groq | 79ms | Очень хороший |
| llama-4-scout-17b | Groq | 108ms | Хороший |
| llama-3.3-70b | Groq | 118ms | Хороший |
| gpt-oss-20b | Groq | 148ms | Хороший |
| YandexGPT Lite (sync!) | Yandex | 724ms* | Отличный |
| YandexGPT Pro (sync!) | Yandex | 988ms* | Отличный |

*YandexGPT замерен sync (полное время), streaming TTFT будет ниже.

**Находки:**
- Groq qwen3-32b — 4x быстрее gpt-5.4-mini (79 vs 325ms), очень хороший русский
- Qwen3 требует `/no_think` в промпте и strip `<think>` тегов из ответа
- Yandex AI Studio предлагает Alice AI LLM (лидер SLAVA бенчмарка) и Qwen3-235B на серверах в РФ
- DeepSeek напрямую — слишком медленный (330ms только сеть, 2-3с TTFT)
- Fireworks Qwen3-30B — перспективен (~300ms est.), нужен практический тест

**Файлы:** docs/VOICE_LATENCY_RESEARCH.md

**Следующий шаг:** A/B тест Groq qwen3-32b vs gpt-5.4-mini на 20 диалогах

---

## 28.03.2026 — Voice Pipeline v2: новая архитектура

**Сделано:**
- Диагностическое логирование VOICE_DIAG: каждый шаг с таймингами (RAG, LLM TTFT, full, sanitize, WS)
- Полный анализ таймингов: 14 ходов под микроскопом, найдены bottleneck-и
- Новая архитектура voice pipeline:
  - Убран RAG (экономия 150-800ms на ход)
  - Убран async Extractor gpt-5.2 (экономия 3000ms async + $)
  - Убран get_system_prompt_v2 + VOICE_PROMPT_ADDON → новый компактный VOICE_SYSTEM_PROMPT
  - Промпт: 20000 → 2673 символов (5000 → 668 токенов)
  - Rule-based state extraction вместо LLM-парсинга
  - Stage определяется из state: GOAL→BUDGET→PAYMENT→MEETING→CLOSING
  - Sync LLM (один yield целиком) вместо стриминга по токенам
- Модель: gpt-4.1-mini → gpt-5.4-mini (TTFT 606→325ms по бенчмарку)
- Промпт: скрипт-вектор + техники Белочкиной (объясни зачем, упрости выбор, два созвона)
- Дедупликация транскриптов от Retell (частичная, нужна доработка)
- Лимит истории 16 сообщений для голоса
- Voice latency research: 7 направлений исследованы → docs/VOICE_LATENCY_RESEARCH.md
- Приветствие: Oazis Estate → Оазис Эстэйт (кириллица для TTS)
- Формат логов web_api.py: %(name)s вместо хардкода [WEB-API]

**Результат таймингов:**
- Pipeline медиана: 1200-2000ms → ~900ms
- Выбросы: 3300ms → 2048ms (только первый ход)
- RAG: 150-800ms → 0ms
- Extractor: 3000ms → 0ms

**Файлы:** core/pipeline.py, voice_api.py, web_api.py, docs/VOICE_LATENCY_RESEARCH.md

**Промпт-правки:**
- "Поняла" запрещено
- Один вопрос за ответ (строго)
- Не оценивать слова клиента
- Не пугать ограничениями
- После GOAL — сразу к бюджету, без уточнений про стратегию
- Prompt caching (1024+ токенов) протестирован — замедляет, откачен к 668 токенам

**Открытые баги:**
- Дедупликация: точные совпадения транскрипта не ловятся
- Budget: "десять-пятнадцать" без "миллион" парсит, но через дефис нет
- Retell begin_message — возможно другой голос на приветствии
- Retell Boosted Keywords не добавлены

**Следующий шаг:** фикс дедупликации, boosted keywords, тест accuracy mode

---

## 26.03.2026 (вечер) — Voice V2: TTS/STT/Pipeline deep dive

**Сделано:**
- Решён ElevenLabs блокер: причина — бесплатный план (402) + таймауты Pipecat. Оплачен Starter, патч AUDIO_CONTEXT_TIMEOUT=15с
- Протестированы TTS: OpenAI nova, ElevenLabs Nastya (flash+multilingual), Yandex alena (REST v1)
- Протестированы STT: OpenAI Whisper (работает), Yandex gRPC v3 (ломает turn detection)
- core/pipeline.py подключён к Pipecat: SofiaPipelineProcessor ловит LLMContextFrame
- sanitize_for_tts(): Latin → Cyrillic, удаление URL/email/@username
- Фикс Retell двойного ответа: is_responding флаг в voice_api.py
- Оптимизация VAD: stop_secs 0.8→0.3, промпт 533→212 токенов, max_tokens→200

**Файлы:** core/pipeline.py, voice_pipecat_daily.py, voice_api.py, yandex_tts.py, yandex_stt.py

**Решения:**
- user_aggregator пушит LLMContextFrame, НЕ LLMRunFrame — ловим именно его
- Async Extractor вызывает extract_sync напрямую (НЕ через process_message — сбрасывает dialog_finished)
- Патч в системном пакете pipecat — повторять при обновлении

**Следующий шаг:** Yandex TTS gRPC v3 + unsafe_mode для качественных русских ударений

---

## 26.03.2026 — P0 деплой: Битрикс ASSIGNED=428 + Voice V1

**Сделано:**
- SOFIA_AI_USER_ID=428 — София ответственная на время квалификации, робот-распределитель не трогает
- restore_assigned(): возврат оригинального менеджера из lead_assigned, fallback 426
- Webhook: если ASSIGNED != 428 → менеджер перехватил → manager_active=1
- _is_bitrix_session(): Битрикс только для source-сессий (ATL)
- Деплой в PROD: core/bitrix.py, bot_server.py, web_api.py
- stream_voice_response(): VOICE_MODEL=gpt-4.1-mini, RAG 10 примеров, async Extractor
- VOICE_PROMPT_ADDON: 7 правил голосового режима

**Файлы:** core/bitrix.py, bot_server.py, web_api.py, core/pipeline.py

**Решения:**
- 4 сценария завершения: meeting_agreed, double refusal, timeout, interception
- Бэкап перед деплоем: /opt/sofia-gpt/backups/20260326_0724/

**Следующий шаг:** Ссылка в Тильде → `https://t.me/humanAINeural_bot?start=ATL`

