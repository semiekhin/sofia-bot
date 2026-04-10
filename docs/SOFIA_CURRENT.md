# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 10.04.2026 (A/B test TTS → Eleven v3 locked)

## Архитектурная карта: ПРОД vs DEV

### ПРОД (`/opt/sofia-gpt/`, порт 8080)
- `bot_server.py` — Telegram бот (@humanAINeural_bot) → `core/pipeline.py` + `core/bitrix.py` (**задеплоен 26.03.2026**)
- `web_api.py` — веб виджет (порт 8080) → `core/pipeline.py` + `core/bitrix.py` (**задеплоен 26.03.2026**)
- `sofia_radist_gateway.py` — Radist gateway (порт 5001) → `core/pipeline.py` (**без Bitrix**)
- **`core/pipeline.py`** — единый пайплайн, задеплоен 21.03.2026
- **`core/bitrix.py`** — модуль Битрикс с ASSIGNED_BY_ID=428, задеплоен 26.03.2026
- **Голосового канала НЕТ в проде** — voice только в dev
- Бэкапы: `/opt/sofia-gpt-backup-20260321_1355`, `/opt/sofia-gpt/backups/20260326_0724/`

### DEV (`/opt/sofia-gpt-dev/`, порт 8081)
- Все каналы: `bot_server.py`, `web_api.py`, `sofia_radist_gateway.py`, `voice_api.py`
- **`core/pipeline.py`** — единый пайплайн + voice pipeline v2 (gpt-5.4-mini, без RAG, без Extractor, rule-based state, sync LLM)
- **`core/bitrix.py`** — модуль Битрикс с ASSIGNED_BY_ID=428
- **voice_api.py** — Retell AI WebSocket адаптер (Voice V1, **РАБОТАЕТ**, дедупликация транскриптов)
- **voice_pipecat_daily.py** — Pipecat + Daily WebRTC (Voice V2, **РАБОТАЕТ** с core/pipeline.py)
- **yandex_tts.py** — кастомный Yandex SpeechKit TTS процессор для Pipecat (REST v1, alena neutral)
- **yandex_stt.py** — кастомный Yandex SpeechKit STT процессор для Pipecat (gRPC v3 streaming)
- **yandex_proto/** — скомпилированные proto файлы Yandex Cloud STT v3
- Nginx: `/voice-v2/` → порт 8082, `/voice-samples/` → статика
- БД: `sofia_gpt_dev.db`
- ElevenLabs: оплачен (Starter), голос Nastya (YjESejviApN7SHrbfnA2)

## ✅ Что сделано

### Сессия 26.03.2026 (вечерняя) — Voice V2 deep dive

**Блокер ElevenLabs TTS РЕШЁН:**
- Корень проблемы: бесплатный план ElevenLabs → HTTP 402 на API, WebSocket молча глотал ошибку
- Два таймаута в Pipecat убивали аудио: `stop_frame_timeout_s=2.0` и `AUDIO_CONTEXT_TIMEOUT=3.0`
- Пропатчен `AUDIO_CONTEXT_TIMEOUT=15.0` в `/usr/local/lib/python3.12/dist-packages/pipecat/services/tts_service.py:1364`
- После оплаты Starter плана — ElevenLabs работает, TTFB 0.1-1.1с

**Протестированные TTS:**
- OpenAI TTS nova — работает, TTFB ~0.9с, акцент на русском
- ElevenLabs Nastya eleven_flash_v2_5 — TTFB 0.11с, ударения средние
- ElevenLabs Nastya eleven_multilingual_v2 — TTFB 0.4-1.1с, ударения лучше
- Yandex TTS alena neutral (REST v1) — TTFB 0.5с, нативный русский, но ломается на латинице

**Протестированные STT:**
- OpenAI Whisper gpt-4o-mini-transcribe — TTFB 0.8-1.3с, работает с turn detection
- Yandex SpeechKit STT v3 gRPC — распознаёт идеально, но ломает turn detection (5с fallback)

**Оптимизации pipeline:**
- VAD stop_secs: 0.8 → 0.3с (−0.5с на каждом ходе)
- System prompt: 533 → 212 токенов (−60%)
- max_completion_tokens: 800 → 200
- LLM буфер: LLMFullResponseBuffer копит весь ответ → TTS одним куском

**core/pipeline.py подключён к Pipecat:**
- SofiaPipelineProcessor заменяет OpenAILLMService
- Ловит LLMContextFrame от user_aggregator (не LLMRunFrame!)
- Вызывает stream_voice_response() — полный промпт, RAG, Extractor
- sanitize_for_tts() — постобработка: латиница → кириллица, удаление URL/email

**VOICE_PROMPT_ADDON обновлён:**
- Добавлено: "НИКОГДА не используй латиницу, URL, email, @юзернеймы"
- Добавлено: "Пиши Оазис Эстэйт вместо Oazis Estate"

**Баг Retell — двойной ответ ПОЧИНЕН:**
- Retell слал два response_required подряд → Reply #4 прерывал Reply #3
- Фикс: `is_responding` флаг в voice_api.py — пропускает новые запросы пока стримит

**Новые файлы:**
- `yandex_tts.py` — Yandex SpeechKit TTS v1 REST процессор для Pipecat
- `yandex_stt.py` — Yandex SpeechKit STT v3 gRPC streaming процессор для Pipecat
- `yandex_proto/` — скомпилированные proto файлы (stt_pb2, stt_service_pb2_grpc)
- `static/voice-samples/` — тестовые WAV файлы голосов

### Сессия 26.03.2026 (утренняя) — Деплой P0 + Voice V1

(без изменений — см. предыдущую версию)

### Сессия 25.03.2026 — Исследование голосового агента

(без изменений)

## 🔄 Текущее состояние сервисов

| Сервис | Порт | Статус | Пайплайн |
|--------|------|--------|----------|
| sofia-gpt.service (Telegram bot prod) | — | running | core/pipeline.py + core/bitrix.py (ATL only) |
| sofia-web-api.service (prod) | 8080 | running | core/pipeline.py + core/bitrix.py |
| sofia-radist.service (prod) | 5001 | running | core/pipeline.py |
| sofia-web-api-dev.service (dev) | 8081 | running | core/pipeline.py + voice_api.py (Retell) |
| sofia-radist-dev.service (dev) | 5002 | running | core/pipeline.py |
| voice_pipecat_daily.py (dev) | 8083 | manual | Pipecat + Daily + core/pipeline.py |

## Голосовой стек (locked 10.04.2026)

**Архитектура:** VPS 185.207.66.201 (Asterisk + AudioSocket) → proxy 72.56.64.91:8095 → Groq/ElevenLabs

| Компонент | Значение |
|-----------|----------|
| TTS | **eleven_v3**, Nastya PVC (YjESejviApN7SHrbfnA2) |
| VoiceSettings | stability=0.50, similarity_boost=0.85, speed=1.10 |
| LLM | kimi-k2-instruct (Groq via proxy) |
| STT | Yandex SpeechKit REST v1 |
| VAD | energy-based, silence threshold 0.3s |
| max_tokens | 150 |
| SSML | add_ssml_breaks (0.3s between sentences, max 2) |
| Prompt | VOICE_SYSTEM_PROMPT_RIZALTA v2 (canonical pitch) |

**Решение по модели (A/B тест 10.04):** v3 выбран за просодию и ударения. Flash v2.5 отклонён (быстрее, но хуже качество). MLv2 отклонён (медленнее v3, не лучше по качеству).

**Тайминги (конец речи → первый звук ответа):**
| Этап | Время |
|------|-------|
| VAD silence | 300ms |
| STT (Yandex) | ~300ms |
| LLM (Groq kimi-k2 via proxy) | ~300ms |
| TTS TTFB (ElevenLabs v3 via proxy) | ~700-900ms |
| **Итого** | **~900-1100ms** |

## Тайминги Voice (Retell, устаревшее, 28.03.2026)

| Этап | Retell STT | LLM (gpt-5.4-mini) | Retell TTS | Итого |
|------|------------|---------------------|------------|-------|
| TTFB | ~300-500ms | 325-900ms | ~200-400ms | **~0.9-1.8с** |

## .env: dev

| Ключ | Dev | Prod |
|------|-----|------|
| OPENAI_API_KEY | + | + |
| TELEGRAM_BOT_TOKEN | + | + |
| ELEVENLABS_API_KEY | + (Starter оплачен) | — |
| YANDEX_SPEECHKIT_API_KEY | + | — |
| GROQ_API_KEY | + | — |
| DAILY_API_KEY | + | — |

## 🔜 Следующие шаги

### P0 — срочно
1. **Ссылка в Тильде** — URL успеха: `https://t.me/humanAINeural_bot?start=ATL`
2. **Фикс дедупликации транскриптов** — точные совпадения не ловятся
3. **Budget парсинг** — "десять-пятнадцать" без "миллион" не парсится
4. **Retell Boosted Keywords** — инвестиция, рассрочка, ипотека, Сочи, Туапсе, Анапа, Крым, Архыз, Алтай, миллион, бюджет, стройка, аренда

### P1 — следующая итерация
5. **Retell begin_message** — убрать или настроить тот же голос
6. **Retell Transcription Mode** — accuracy vs speed тест
7. **Post-Call Data Extraction** — goal, budget, payment_type, meeting_agreed
8. **Битрикс в radist_gateway.py** — подключить core/bitrix.py к Radist каналу
9. deploy.sh скрипт

### P2 — улучшения Voice
10. **Yandex TTS gRPC v3 + unsafe_mode (#1, #2)** — ключ к хорошему русскому голосу
11. **Задарма SIP (#17)** — реальные звонки
12. WebRTC кнопка в веб-виджете

### P3 — техдолг
13. Очистка мусора в проде
14. core/channel.py, core/observer.py
15. BUG-004 EN-раскладка
