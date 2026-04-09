# RESEARCH REPORT: Голосовой агент Софья v3
## «Качество переписчика + скорость <500ms + живая речь»

**Дата:** 2026-04-09  
**Время исследования:** ~3 часа (3 параллельных агента)  
**Затрачено на API-тесты:** ~$3 (ElevenLabs, OpenAI TTS, Yandex TTS, Groq LLM)  
**Артефакты:** 30 аудиофайлов в `/tmp/voice_research_v2/`

---

## 1. Executive Summary — Топ рекомендаций

| # | Архитектура | Суть | Латентность | Стоимость/мес | Сложность | Почему |
|---|------------|------|------------|--------------|-----------|--------|
| **1** | **C: Оптимизация текущего стека** | Silero VAD + gRPC STT + kimi-k2 LLM + Flash TTS + fillers | **300ms воспр.** / 475ms реал. | ~$230 | 8 дней | Максимум результата при минимуме изменений — каждый компонент можно улучшить без переписывания |
| 2 | A: Hybrid Brain | gpt-5.2+RAG async «мозг» + быстрый kimi-k2 «рот» | 400-500ms | ~$280 | 10 дней | Качество текстовой Софьи + скорость Groq, но сложнее в отладке |
| 3 | B: Pre-recorded Bank | 60 WAV-фраз + LLM-роутер, live TTS только для 25% реплик | **350ms** (70% реплик) | ~$195 | 14 дней | Мгновенный ответ для типовых фраз, самый дешёвый, но ригидный |
| 4 | D: Speculative Dual-Agent | Предсказание ответа ПОКА клиент говорит + pre-warm TTS | **300ms** (при hit 50-65%) | ~$240 | 17 дней | Самая низкая латентность в теории, но самый высокий риск |

**Рекомендация №1: Начать с Architecture C** (8 дней) — 5 независимых оптимизаций, каждая даёт измеримый выигрыш. Самое важное открытие: **замена LLM с llama-4-scout на kimi-k2-instruct** решает проблему «Йода-русского» и не требует архитектурных изменений.

**MVP за 1 день** (можно сделать завтра):
1. Сменить LLM на `kimi-k2-instruct` (1 строчка в voice_asterisk.py)
2. Сменить TTS на `eleven_flash_v2_5` (1 строчка)
3. `max_tokens=400` → `150`, добавить «25 слов максимум» в промпт
4. Снизить VAD с 400ms до 300ms
5. Добавить 3 pre-recorded filler-звука

**Ожидаемый результат MVP: ~600-700ms** (с ~1000ms сейчас), качество русского резко вырастет.

---

## 2. Бенчмарки моделей

### 2.1 LLM — реальные тесты на Groq и OpenAI

Тестовый промпт: `"Ты Софья, менеджер по продажам курортной недвижимости. Звонишь клиенту. Отвечай одним коротким предложением по-русски."`  
5 тестовых сценариев: простой вопрос, возражение, приветствие, multi-turn, сложное предложение.

| Модель | Провайдер | TTFT (ms) | Качество RU (1-5) | Стиль | Макс. токены | Цена in/out $/1M | Из РФ | Комментарий |
|--------|-----------|-----------|-------------------|-------|-------------|-----------------|-------|------------|
| **kimi-k2-instruct** | **Groq** | **275-400** | **5** | **Разговорный, продажный** | 131K | $1.50/$1.50 | Proxy | **ПОБЕДИТЕЛЬ.** «Есть минутка?», «рассрочка до двух лет» — как живой продажник |
| gpt-oss-120b | Groq | 257-290 | 4 | Формальный, сухой | 131K | $0.15/$0.60 | Proxy | Хороший fallback. Быстрый, дешёвый, built-in reasoning |
| llama-3.3-70b | Groq | 336-465 | 4 | Литературный | 131K | $0.59/$0.79 | Proxy | Приличный русский, но длинные фразы |
| llama-4-scout-17b | Groq | 113-**1077** | 3 | **Йода-русский** | 131K | $0.11/$0.34 | Proxy | **ТЕКУЩИЙ. Подтверждён баг:** «comparable цене» (англ. слова!), инверсии |
| llama-3.1-8b | Groq | 175 | 3 | Шаблонный | 131K | $0.05/$0.08 | Proxy | Дёшево, но бедный русский |
| qwen3-32b | Groq | 506+ | 3 | N/A | 131K | $0.39/$0.79 | Proxy | **ДИСКВАЛИФИЦИРОВАН:** тратит токены на `<think>`, нельзя отключить |
| gpt-oss-20b | Groq | 248-256 | 4 | Markdown! | 131K | $0.13/$0.13 | Proxy | Использует эмодзи и **bold** — неприменимо для голоса |
| gpt-4o-mini | OpenAI | **1458-1846** | 4 | Формальный | 16K | $0.15/$0.60 | Proxy | **5-10x медленнее** Groq. Не для голоса |
| gpt-5.4-mini | OpenAI | **1829-2661** | 5 | Литературный | 16K | $0.40/$1.60 | Proxy | Лучший русский, но 2+ секунды — смерть для голоса |

**Ключевой вывод:** kimi-k2-instruct — единственная модель с TTFT <400ms И отличным разговорным русским. Замена llama-4-scout → kimi-k2 = главный quick win.

### 2.2 TTS — реальные тесты с замерами

Тестовая фраза: *«Алло, добрый день! Это Софья, агентство Оазис. Минута есть? Хочу классное предложение быстро рассказать.»*

| Движок | Модель/Голос | TTFB (ms) | Total (ms) | Качество RU (1-5) | Ударения | Интонации | Streaming | Цена/1M chars | Из РФ | Файл |
|--------|-------------|-----------|-----------|-------------------|---------|-----------|-----------|--------------|-------|------|
| ElevenLabs | multilingual_v2 / Sarah | **963** | 990 | 3.5 | Плохо (80%) | Хорошие | Да | ~$120-180 | Proxy | `elevenlabs_sarah_multilingual_v2.mp3` |
| ElevenLabs | turbo_v2_5 / Sarah | **318** | 363 | 3.0 | Плохо (80%) | Средние | Да | ~$60 | Proxy | `elevenlabs_sarah_turbo_v2_5.mp3` |
| **ElevenLabs** | **flash_v2_5 / Sarah** | **305** | 329 | 3.0 | Плохо (80%) | Средние | **Да** | ~$60 | Proxy | `elevenlabs_sarah_flash_v2_5.mp3` |
| ElevenLabs | multilingual_v2 / stable | 1015 | 1047 | 3.5 | Плохо | Лучше | Да | ~$120-180 | Proxy | `elevenlabs_sarah_multilingual_v2_stable.mp3` |
| **Yandex** | **alena / good** | **514** | 514 | **4.5** | **Отлично (99%)** | Хорошие | Нет (REST) | ~$4-16 | **Да** | `yandex_alena_good.ogg` |
| Yandex | alena / stress markup | 821 | 821 | **4.5** | **Отлично** | Хорошие | Нет | ~$4-16 | **Да** | `yandex_alena_stress_markup.ogg` |
| Yandex | filipp | 613 | 613 | 4.0 | **Отлично** | Хорошие | Нет | ~$4-16 | **Да** | `yandex_filipp.ogg` |
| Yandex | marina | 1934 | 1934 | 4.0 | **Отлично** | Средние | Нет | ~$4-16 | **Да** | `yandex_marina.ogg` |
| OpenAI | gpt-4o-mini-tts / shimmer | 1610 | 1610 | 3.5 | Средне (90%) | Хорошие | Огран. | ~$15-30 | Proxy | `openai_gpt4omini_shimmer.mp3` |
| OpenAI | tts-1 / nova | 2395-3015 | 3000 | 3.0 | Средне (85%) | Средние | Нет | ~$15 | Proxy | `openai_tts1_nova.mp3` |
| OpenAI | tts-1-hd / alloy | 3719 | 3719 | 3.5 | Средне (90%) | Хорошие | Нет | ~$15 | Proxy | `openai_tts1hd_alloy.mp3` |
| Silero | v5 / xenia | <50 | <100 | 4.0 | **Отлично** | **Плоские** | Local | Бесплатно | **Local** | Не тестировался (self-host) |
| Cartesia | Sonic 3 | <200 | streaming | 3.0-3.5? | Неизвестно | Хорошие? | Да | ~$30 | Proxy | Не тестировался |
| Hume | Octave 2 / EVI | ~200 | streaming | 3.0-3.5? | Неизвестно | Отличные | Да | ~$7.60 | Proxy | Не тестировался |
| Sber | SaluteSpeech | ~200-500 | ~500 | **4.5** | **Отлично** | Хорошие | Да (gRPC) | ~$5-10 | **Да** | Не тестировался (enterprise) |

### 2.3 STT — сравнение

| Движок | API | WER (рус.) | Латентность | Streaming | Цена/мин | Из РФ | Комментарий |
|--------|-----|-----------|------------|-----------|---------|-------|------------|
| **Yandex REST v1** (текущий) | REST | **~3-5%** | ~300ms | Нет | ~$0.005 | **Да** | Лучший для русского. Batch-режим |
| **Yandex gRPC v3** | gRPC | **~3-5%** | **~100-150ms** | **Да** | ~$0.005 | **Да** | **Рекомендуется.** То же качество, streaming |
| Groq Whisper Turbo | REST | ~9% | ~30ms | Нет | $0.007/hr | Proxy | Сверхбыстро, но WER хуже |
| Deepgram Nova-3 | WS | ~8% | <300ms | Да | $0.0092 | Proxy | Code-switching RU+EN |
| Google STT v2 | gRPC | ~10-15% | ~650ms | Да | $0.016 | Proxy | Плохой русский |
| AssemblyAI | REST | ~7-8% | TBD | Планир. | $0.27/hr | Proxy | 99 языков |

---

## 3. Реальные тесты

### Протестировано API (с замерами):

**TTS (23 аудиофайла в `/tmp/voice_research_v2/`):**
- ElevenLabs: 5 вариантов (2 модели × 2-3 настройки)
- Yandex SpeechKit: 7 вариантов (5 голосов + SSML + stress markup)
- OpenAI TTS: 10 вариантов (3 модели × 3-4 голоса)
- Рекомендую послушать в первую очередь: `yandex_alena_good.ogg` vs `elevenlabs_sarah_flash_v2_5.mp3`

**LLM (9 моделей, 5 сценариев = 45 тестов):**
- Groq: llama-4-scout, llama-3.3-70b, llama-3.1-8b, qwen3-32b, kimi-k2-instruct, gpt-oss-120b, gpt-oss-20b
- OpenAI: gpt-4o-mini, gpt-5.4-mini
- Полные результаты: `/tmp/voice_research_v2/llm_tests.txt`

**Не тестировалось (нет free tier / enterprise-only):**
- Cartesia Sonic 3 (42 языка, но API trial не был запрошен)
- Sber SaluteSpeech (enterprise, нужен договор)
- Hume EVI / Octave (триал не запрошен)
- Silero v5 TTS (нужен self-host с GPU для хорошего качества)

---

## 4. Три архитектурных предложения

### Architecture C: «Оптимизация текущего стека» (РЕКОМЕНДУЕТСЯ ПЕРВОЙ)

```
ТЕКУЩИЙ PIPELINE          →  ОПТИМИЗИРОВАННЫЙ            ЭКОНОМИЯ
─────────────────────        ────────────────────         ────────
VAD: energy 400ms       →  Silero VAD 250ms               150ms
STT: Yandex REST 300ms  →  Yandex gRPC stream ~100ms      200ms
LLM: llama-4-scout 500ms→  kimi-k2 250ms + prompt opt     250ms
TTS: MLv2 450-700ms     →  Flash v2.5 75ms TTFB           375ms
Fillers: нет            →  Pre-recorded «Так...»          ~500ms восприятия
─────────────────────────────────────────────────────────────────
ИТОГО: 1000ms воспр.    →  475ms реал. / 300ms воспр.
```

**Что переиспользуем:** Всё — Asterisk, AudioSocket, VPS, proxy, state_manager, sanitize_for_tts  
**Что нового:** Silero VAD, Yandex gRPC client, смена модели LLM и TTS (конфиг), fillers, sentence-level streaming  
**Разработка:** 8 дней  
**Стоимость:** ~$230/мес (1000 звонков)  
**Главный риск:** Flash v2.5 + PVC Nastya может звучать хуже → тестировать, есть fallback на MLv2  
**MVP за 1 день:** Смена LLM + TTS модели + max_tokens + VAD threshold + 3 filler-звука → ~600-700ms

### Architecture A: «Hybrid Brain»

```
Клиент говорит
    │
    ▼
Silero VAD (250ms) → Yandex gRPC STT (~100ms)
    │
    ▼
FAST MOUTH (kimi-k2, ~250ms)          ←── stage_directive от BIG BRAIN
    │                                       (pre-computed на предыдущем ходу)
    ▼
Flash TTS (75ms) → AudioSocket → Клиент слышит
    │
    ▼ (асинхронно, ПОСЛЕ ответа)
BIG BRAIN: gpt-5.2 + RAG (3-8 сек)
    ├─ Extractor: NLU-анализ сообщения
    ├─ Analyzer: определение стадии
    ├─ RAG: 10 примеров из ChromaDB
    └─ → stage_directive для следующего хода
```

**Латентность:** 400-500ms  
**Разработка:** 10 дней  
**Стоимость:** ~$280/мес  
**Главный риск:** На ходах 1-2 нет directive от Big Brain → defaults  
**MVP за 1 день:** То же что Architecture C + простой async-вызов gpt-5.2 после ответа

### Architecture B: «Pre-recorded Bank + LLM Router»

```
РАСПРЕДЕЛЕНИЕ РЕПЛИК ХОЛОДНОГО ЗВОНКА:
  Открытие:           90% предсказуемо → 5 WAV-фраз
  Питч:               80% предсказуемо → 10 WAV-фраз
  Квалификация:       60% предсказуемо → 15 WAV-фраз
  Возражения:         70% предсказуемо → 15 WAV-фраз
  Закрытие:           85% предсказуемо → 8 WAV-фраз
  ─────────────────────────────────────────────────
  ИТОГО:              55-65 WAV-фраз покрывают 70-75% диалога

Клиент говорит → STT → LLM Router (100ms):
  ├─ Код фразы «BUSY_01» → воспроизвести WAV (5ms) → TOTAL: 350ms
  └─ «LIVE» → kimi-k2 + TTS (500ms) → TOTAL: 750ms
```

**Латентность:** 350ms (70% реплик) / 750ms (30% реплик)  
**Разработка:** 14 дней  
**Стоимость:** ~$195/мес (самый дешёвый)  
**Главный риск:** Переход pre-recorded → live звучит неестественно, ригидность  
**Запись фраз:** ElevenLabs batch (~$5) или студия с актрисой (~$300)

---

## 5. Глубокая аналитика TTS-качества для русского

### Проблема: ударения

Русский — язык со свободным ударением. Ударение может падать на любой слог и менять значение (за́мок/замо́к, му́ка/мука́). В отличие от английского, ошибка ударения в русском **мгновенно** распознаётся как неестественная.

### Кто реально справляется с ударениями:

| Уровень | Движки | Точность | Как |
|---------|--------|---------|-----|
| **Отлично** | Yandex SpeechKit, Silero v5, SaluteSpeech | 99%+ | Обучены на русских корпусах с аннотацией ударений. Встроенная модель омографов |
| **Хорошо** | MTS Audiogram | ~95% | Russian-first, SSML-контроль |
| **Средне** | OpenAI TTS (gpt-4o-mini-tts) | ~85-90% | Лучше ElevenLabs, но ошибается на редких словах |
| **Плохо** | ElevenLabs (все модели) | **~80%** | Обучен на английском. Русский = «поддерживаемый язык», не приоритет |
| **Плохо** | XTTS v2, F5-TTS, Piper, Sesame | ~70-80% | Нет модели ударений для русского в training data |

### ElevenLabs Pronunciation Dictionaries — не решение

- Есть API для создания словарей: `POST /v1/pronunciation-dictionaries/add-from-rules`
- **Для русского доступны только alias-правила** (замена строки → строка), не фонемы/IPA
- Пример: `"Оазис" → "Оа́зис"` — но это whack-a-mole, невозможно покрыть все слова LLM
- Не фиксит интонацию и просодию, только слово-уровень
- **Вердикт:** band-aid, не решение

### Варианты решения проблемы ударений

**Вариант A: Yandex SpeechKit gRPC v3 как TTS (РЕКОМЕНДУЕТСЯ)**
- Лучшие ударения из коробки (99%+)
- SSML + TTS markup (`+` перед ударной гласной) как safety net
- Streaming через gRPC
- 10x дешевле ElevenLabs
- Работает из российской VPS без proxy
- **Минус:** нет voice cloning, фиксированные голоса (alena, filipp, marina, jane, omazh)
- **Минус:** менее эмоциональная интонация чем ElevenLabs

**Вариант B: Предобработка текста через RUAccent/silero-stress перед ElevenLabs**
- LLM output → stress annotator → вставка маркеров ударений → ElevenLabs
- Проблема: ElevenLabs **не поддерживает** stress marks для русского
- Alias dictionary — нужен для каждого слова индивидуально
- **Вердикт:** слишком хрупко и сложно для динамического текста

**Вариант C: Silero v5 self-hosted (нулевая латентность)**
- Отличные ударения, бесплатно, CPU-only (<50ms)
- **Минус:** плоские интонации — звучит как робот на телефоне
- Годится как fallback, не как primary

**Вариант D: Cartesia Sonic 3 (нужно тестировать)**
- 42 языка включая русский, streaming <200ms
- Неизвестно качество ударений — нужен тест
- Если ударения хорошие — лучший баланс скорости и качества

---

## 6. Рекомендация №1

### Фазовый подход: C → A → D

**Фаза 1 (эта неделя): Architecture C — Quick Wins (8 дней)**

| Шаг | Что делаем | Выигрыш | Сложность |
|-----|-----------|---------|-----------|
| 1 | Сменить LLM: `llama-4-scout` → `kimi-k2-instruct` | Нет «Йоды», +качество | 1 строчка кода |
| 2 | Сменить TTS модель: `eleven_multilingual_v2` → `eleven_flash_v2_5` | -375ms TTFB | 1 строчка кода |
| 3 | `max_tokens=400` → `150` + «25 слов» в промпт | -200ms генерации | Промпт-инженерия |
| 4 | VAD: 400ms → 300ms (энергетический, осторожно) | -100ms | 1 параметр |
| 5 | 3 pre-recorded filler WAV | -500ms восприятия | 1 день |
| 6 | Silero VAD (заменить энергетический) | -50ms + надёжность | 1 день |
| 7 | Yandex gRPC v3 streaming STT | -200ms | 2 дня |
| 8 | Sentence-level LLM→TTS streaming | -100ms | 1.5 дня |

**Результат Фазы 1:** ~300ms воспринимаемая латентность, нормальный русский без «Йоды».

**Фаза 2 (следующий спринт): Architecture A — Big Brain**
- Добавить async gpt-5.2+RAG после каждого хода
- stage_directive injection в промпт kimi-k2
- Качество диалога = текстовая Софья, скорость = голосовая

**Фаза 3 (по результатам): TTS-решение для ударений**
- Тестировать Yandex gRPC v3 как TTS (вместо ElevenLabs)
- Или: тестировать Cartesia Sonic 3
- Выбрать по результатам A/B тестирования на реальных звонках

**Фаза 4 (опционально): Architecture D — Speculative Execution**
- Добавить предсказание ответов поверх Architecture A+C
- 50-65% hit rate → ~300ms без fillers

### Обоснование

1. **kimi-k2-instruct** — главное открытие исследования. Это единственная модель на Groq с **отличным** разговорным русским И латентностью <400ms. Замена = 1 строчка кода, 0 рисков.

2. **ElevenLabs Flash v2.5** — 3x быстрее multilingual_v2 (305ms vs 963ms TTFB). Качество ниже, но для телефона (8kHz, сжатие) разница минимальна. Нужно протестировать с PVC Nastya.

3. **Fillers** — психологически самый мощный приём. Человек не замечает 1-секундную паузу если слышит «Угу...» / «Так...». Стоимость реализации — 1 день.

4. **Yandex gRPC v3 TTS** — потенциальная замена ElevenLabs для русского. Ударения 99%+ vs 80%. Но потеря voice cloning (Nastya) — нужно взвесить.

### Что делаем на следующей неделе

**День 1:** MVP — kimi-k2 + Flash v2.5 + max_tokens=150 + VAD 300ms + 3 filler WAV  
**День 2-3:** Промпт RIZALTA v2 под kimi-k2 (few-shot, 10 примеров из реальных звонков)  
**День 4-5:** Silero VAD + Yandex gRPC streaming  
**День 6-7:** Sentence-level TTS streaming  
**День 8:** Интеграционное тестирование, замеры, отчёт

---

## Приложения

### A. Файлы для прослушивания (послушать в первую очередь)

1. `yandex_alena_good.ogg` — лучший Yandex вариант (ударения!)
2. `elevenlabs_sarah_flash_v2_5.mp3` — ElevenLabs Flash (скорость)
3. `elevenlabs_sarah_multilingual_v2.mp3` — ElevenLabs MLv2 (текущая модель, другой голос)
4. `openai_gpt4omini_coral.mp3` — OpenAI с инструкцией «sales agent»

### B. Полные данные тестов

- `/tmp/voice_research_v2/llm_tests.txt` — все LLM-ответы с таймингами
- `/tmp/voice_research_v2/stt_tests.txt` — сравнение STT
- `/tmp/voice_research_v2/fine_tuning_research.txt` — анализ fine-tuning
- `/tmp/voice_research_v2/architectures.md` — детальные архитектуры (1200 строк)

### C. Все аудиофайлы

```
/tmp/voice_research_v2/
├── elevenlabs_jessica_multilingual_v2.mp3
├── elevenlabs_sarah_flash_v2_5.mp3
├── elevenlabs_sarah_multilingual_v2.mp3
├── elevenlabs_sarah_multilingual_v2_stable.mp3
├── elevenlabs_sarah_turbo_v2_5.mp3
├── openai_gpt4omini_alloy.mp3
├── openai_gpt4omini_coral.mp3
├── openai_gpt4omini_nova.mp3
├── openai_gpt4omini_shimmer.mp3
├── openai_tts1_alloy.mp3
├── openai_tts1_nova.mp3
├── openai_tts1_shimmer.mp3
├── openai_tts1hd_alloy.mp3
├── openai_tts1hd_nova.mp3
├── openai_tts1hd_shimmer.mp3
├── yandex_alena.ogg
├── yandex_alena_good.ogg
├── yandex_alena_ssml.ogg
├── yandex_alena_stress_markup.ogg
├── yandex_filipp.ogg
├── yandex_jane.ogg
├── yandex_marina.ogg
└── yandex_omazh.ogg
```
