# ElevenLabs Eleven v3 — Research Report

**Дата:** 2026-04-10
**Цель:** Оценить eleven_v3 и eleven_multilingual_v2 как альтернативу eleven_flash_v2_5 для PVC голоса Nastya

---

## 1. Доступность через API

**Да**, `eleven_v3` доступен через стандартный `POST /v1/text-to-speech/{voice_id}` и streaming endpoint `/stream`.

- **model_id:** `eleven_v3`
- **Проверено на нашем Starter плане** — работает, HTTP 200
- **Ограничение:** НЕ поддерживает параметр `optimize_streaming_latency` (HTTP 400 при попытке). Этот параметр работает только с Flash/Multilingual v2.

## 2. Streaming

Поддерживает streaming через `/v1/text-to-speech/{voice_id}/stream`. Возвращает MP3 чанками.

## 3. Латентность (реальные замеры, NL → ElevenLabs)

| Модель | TTFB (streaming) | Total time | Примечание |
|--------|------------------|------------|------------|
| eleven_flash_v2_5 | **367ms** | 861ms | optimize_streaming_latency=4 |
| eleven_multilingual_v2 (stab=0.5) | 3060ms | 4780ms | Огромный TTFB! |
| eleven_multilingual_v2 (stab=0.7) | 585ms | 3622ms | stability влияет на TTFB |
| eleven_v3 | 700-900ms | 4700-5100ms | Без optimize_streaming_latency |

**Через proxy (+20-30ms):** реальные цифры для VPS будут на 20-30ms выше.

**Вывод:** v3 TTFB ~700-900ms — в 2-3x медленнее Flash. Для голосового pipeline это +400-500ms к паузе, что ломает текущий бюджет (600-700ms total → 1000-1200ms).

## 4. Языки

- **Русский поддерживается** во всех трёх моделях
- v3: 70+ языков
- MLv2: 29 языков
- Flash v2.5: 32 языка

## 5. Новые фичи v3

### Audio Tags
Поддерживает inline теги в тексте:
```
[laughs] [whispers] [sighs] [exhales] [sarcastic] [curious]
[excited] [crying] [applause] [clapping] [gasps] [sings] [friendly]
```
Пример: `[friendly] Здравствуйте! Это София...`

### SSML
`<break time="0.3s"/>` — поддерживается (протестировано).

### Режимы генерации
Creative / Natural / Robust — управление вариативностью (аналог stability).

### Text to Dialogue API
Новый endpoint для многоголосого диалога — не релевантно для нас.

## 6. Цена

| Модель | Кредиты за символ | Max chars/request |
|--------|-------------------|-------------------|
| eleven_v3 | 1 кредит/символ | 5,000 |
| eleven_multilingual_v2 | 1 кредит/символ | 10,000 |
| eleven_flash_v2_5 | 0.5 кредита/символ | 40,000 |

**v3 и MLv2 = 2x дороже Flash** по кредитам. На Starter плане (30,000 символов/мес) это критично для production.

## 7. PVC совместимость

> "Professional Voice Clones (PVCs) are currently not fully optimized for Eleven v3, resulting in potentially lower clone quality compared to earlier models."

Источник: [ElevenLabs docs](https://elevenlabs.io/docs/overview/models)

**MLv2 = рекомендуемая модель для PVC** (подтверждено UI ElevenLabs).

## 8. Доступность на планах

v3 доступен на **всех планах** включая Starter. Проверено эмпирически — наш API ключ работает.

---

## Итоговая таблица сравнения

| Критерий | Flash v2.5 | Multilingual v2 | Eleven v3 |
|----------|------------|-----------------|-----------|
| TTFB | **367ms** | 585-3060ms | 700-900ms |
| Качество PVC | Хорошее | **Лучшее** (рекомендовано) | Не оптимизировано |
| Ударения русский | ~80% | ~85-90% (субъективно) | TBD (надо слушать) |
| Цена (кредиты) | **0.5x** | 1x | 1x |
| Audio tags | Нет | Нет | Да |
| SSML breaks | Да | Да | Да |
| Max chars | 40,000 | 10,000 | 5,000 |
| optimize_streaming_latency | Да | Да | **Нет** |

## Рекомендация

**Для production голосового pipeline (real-time):** оставить **Flash v2.5**. TTFB 367ms vs 700-900ms (v3) или 585-3060ms (MLv2) — разница критична для UX.

**Для улучшения качества без потери скорости:** рассмотреть **sentence-level streaming** (A3 задача) — по мере получения предложений от LLM сразу отправлять в TTS. Это позволит использовать MLv2 или v3 на первом предложении, пока LLM генерирует остальные.

**Для прослушивания:** Сергею нужно сравнить 6 семплов и оценить:
1. Стоит ли качество MLv2/v3 дополнительных 300-500ms латентности?
2. Как звучит Nastya PVC на v3 (не оптимизирован)?

---

*Источники:*
- [Models overview](https://elevenlabs.io/docs/overview/models)
- [Streaming docs](https://elevenlabs.io/docs/api-reference/streaming)
- [ElevenLabs cheat sheet](https://www.webfuse.com/elevenlabs-cheat-sheet)
- [v3 announcement](https://elevenlabs.io/blog/eleven-v3)
- Эмпирические тесты API (этот отчёт)
