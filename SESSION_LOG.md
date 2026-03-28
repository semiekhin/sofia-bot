# SESSION_LOG — Последние сессии

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

