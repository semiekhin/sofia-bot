# SESSION_LOG — Последние сессии

## 02.04.2026 — Битрикс: запуск БП раздачи после квалификации

**Сделано:**
- **core/bitrix.py**: `start_distribution_bp(lead_id)` — вызов `bizproc.workflow.start` с TEMPLATE_ID из env; `finalize_lead(db_path, lead_id)` — обёртка restore_assigned + BP start; `build_qualification_summary(state)` — итог квалификации в COMMENTS (цель, бюджет, оплата, созвон)
- **bot_server.py**: оба пути финализации (`_finalize_timeout` и `delayed_response`) используют `finalize_lead()` вместо `restore_assigned()`
- **.env**: `BITRIX_BP_TEMPLATE_ID=152`
- Radist не затронут — у него нет Bitrix-интеграции (P1 задача)
- web_api.py и voice_api.py не изменены

**Коммиты:** c1987ff5

**Файлы:** core/bitrix.py, bot_server.py, .env, BUILD_REPORT_BITRIX_BP.md

**Открытые вопросы:**
- Radist нужна Bitrix-интеграция (P1) прежде чем подключать БП
- TEMPLATE_ID=152 — одинаковый для dev/prod?
- E2E тест не проведён (нужен реальный диалог через Telegram)

---

## 30.03.2026 — CLAUDE.md: шаблон промптов для Claude Code

**Сделано:**
- Добавлена секция «Промпты для Claude Code» в CLAUDE.md — формат "Задача готова когда" с проверяемыми критериями (3–6 на задачу)

**Коммиты:** 1

**Файлы:** CLAUDE.md

---

## 29.03.2026 (ночь) — Промпт V5-V5.2, barge-in, meeting_agreed фикс

**Сделано:**
- **Промпт V5** (b34e5ffc): полная переработка голосового промпта
  - Persona: Sofia = эксперт по курортной недвижимости, тёплый тон
  - Few-shot примеры (5 сценариев: приветствие, квалификация, возражение, "ты робот?", завершение)
  - Позитивные инструкции вместо запретов
  - Примеры поведения с троллями и "ты робот?"
- **Промпт V5.1** (e2afcf54): убран пример с троллем (вызывал ложный [END]), добавлено правило уважения к клиенту
- **Промпт V5.2** (8e0a7738): few-shot для подтверждения приветствия — фикс галлюцинации "повторилось"
- **meeting_agreed фикс** (e9b47719): `meeting_agreed` срабатывает только если последнее сообщение Софии содержало "созвон/эксперт" — предотвращает ложный CLOSING на "да, давайте пообщаемся"
- **Transcript debounce 400ms** (e9b47719): ожидание окончания транскрипта от Retell → потом заменён на barge-in
- **Barge-in pending** (f83631ae): замена debounce на интеллектуальный механизм
  - Debounce убран — нулевая доп. задержка
  - Если клиент говорит во время ответа Софии: Retell останавливает TTS, текст сохраняется в `pending_text`
  - После завершения текущего ответа — склейка предыдущей фразы + продолжение → ответ на полный вопрос
  - Логи: `BARGE_IN_PENDING`, `BARGE_IN_COMBINED`
- **Context return на "ты робот?"** (f83631ae): после шутки про кофе — возвращается к предыдущей теме разговора

**Коммиты:** b34e5ffc → f83631ae (5 коммитов)

**Файлы:** core/pipeline.py, voice_api.py

**Открытые вопросы:**
- Живой тест промпта V5.2 + barge-in
- Retell Boosted Keywords — по-прежнему нужен API ключ или настройка в dashboard

**Следующий шаг:** живой тест barge-in + промпта V5.2

---

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


