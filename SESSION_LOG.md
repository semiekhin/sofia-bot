# SESSION_LOG — Последние сессии

## 18.04.2026 — FAIL2BAN_DEPLOY_v1: второй слой защиты VPS sofia-voice

**Сделано:**

- Установлен `fail2ban 1.0.2-3ubuntu0.1` на VPS `185.207.66.201` (Ubuntu 24.04)
- `/etc/fail2ban/jail.local` с двумя jail:
  - `[sshd]` — `backend=systemd`, `maxretry=10`, `bantime=3600`, `findtime=600`
  - `[asterisk]` — `backend=auto`, `logpath=/var/log/asterisk/messages.log`, `port=5090,5060`, `maxretry=5`, `bantime=3600`, `findtime=600`
- `[DEFAULT] banaction=ufw`, `ignoreip = 127.0.0.1/8 ::1 46.229.221.93 72.56.64.91 77.106.252.172` (Telfin + главный sofia-gpt сервер + личный IP Сергея)
- С первого старта из systemd journal sshd поймано и забанено через `ufw prepend reject` **9 SSH-сканеров** (maxretry=5 на момент первичного обнаружения пакетным дефолтом, далее новые баны идут с нашим threshold=10)
- Базовые UFW allow-правила (22/tcp, 5090/udp←46.229.221.93, 10000-20000/udp) **не тронуты** — fail2ban только prepend'ит reject выше
- `sofia-voice`, `asterisk`, `fail2ban` — все три active после деплоя

Изменения — только на VPS (pкет+config), в git-репо sofia-gpt-dev не коммитились. Рабочая SSH-сессия (72.56.64.91→185.207.66.201) не пострадала благодаря ignoreip.

**Побочные находки (пополнят CLAUDE.md «Уроки»):**

1. **apt install сразу стартует fail2ban** с дефолтным `banaction=nftables` из `/etc/fail2ban/jail.d/defaults-debian.conf`. После правки `jail.local` нужен `systemctl restart fail2ban`, **не** `reload` — reload не перевыполняет actionban, остаются phantom in-memory баны без реальных правил firewall. После restart состояние восстанавливается из persistence DB корректно.
2. **Приоритет fail2ban-конфигов:** `jail.d/*.conf` → `jail.local` → побеждает последний. Наш `jail.local` корректно перекрывает `defaults-debian.conf` по banaction. Но любой будущий `*.local` в `jail.d/` побьёт наш `jail.local`.
3. **Asterisk не пишет в systemd journal** на этой сборке Ubuntu — `journalctl -u asterisk` пусто, логи только в `/var/log/asterisk/{messages,full}.log`. Глобальный дефолт `backend=systemd` оставил бы asterisk-jail с пустым источником → фильтр никогда бы не сматчил. Явный `backend=auto` в `[asterisk]` — обязательно.
4. **`maxretry=5` в UFW-комментариях** при конфиге `maxretry=10` — это `<failures>` на момент первого бана (до загрузки нашего jail.local). Новые баны идут с threshold=10, комментарий в существующих правилах не обновляется. Не требует правки.

**Эффект:**

| Слой | Что покрывает |
|---|---|
| UFW (17.04) | Блокирует ~100% SIP-сканеров на SYN до Asterisk. `full.log` рост 44 KB/s → 0 B/s |
| fail2ban (18.04) | SSH brute-force через открытый 22/tcp; sip-атаки, если кто-то пролезет через whitelisted IP (маловероятно, но копеечная страховка) |

**Следующее:**

1. **Yandex STT v3 gRPC streaming** (P1, 1-2 дня) — архитектурное упрощение, server-side EOU убирает кастомную VAD+silence-threshold логику целиком. `docs/VOICE_RESEARCH_2026_04_16.md` идея #1.
2. **Мониторинг fail2ban:** `fail2ban-client status <jail>` раз в неделю, смотреть на рост `Total banned` и список IP. В P3 можно завести алерт на рост сверх baseline.

---

## 17.04.2026 — VOICE_STACK_STABILIZATION_v1: barge-in fixes × 4 + Silero VAD + UFW

**Сделано:**

### 1. Barge-in buffer reset (утренний fix, коммит `5104a0cc`)

**Trigger:** звонок 21b96626 (16.04 вечер). После cancel TTS `_process_turn` finally переносил barge-in buffer (~13KB) в `_speech_buffer` → garbled STT «Со стороны» → LLM-фолбэк «плохо слышно» из блока «Не расслышала» RIZALTA.

**Fix:** в `_process_turn` finally **не** re-feed'ить barge-in buffer, а просто `.clear()`. VAD начинает слушать свежий поток после cooldown. Правка ~10 строк в voice_asterisk.py.

### 2. Silero VAD миграция (коммиты `761ef1eb`, `97934f47`)

**Research:** `docs/VOICE_RESEARCH_2026_04_16.md` идея #4 — energy-based VAD ловил мусор (кашель, шум) → STT вернул «Эротика», «Зависят облака». Silero ONNX модель 1.8MB, <1ms CPU, 8kHz natively.

**v5 vs v4 discovery:**
- Скачали v5 (2.3MB) → offline-тест дал 13% детектирования на чистой речи greeting_rizalta.pcm
- Причина: v5 оптимизирован под 16kHz, 8kHz — деградация. Confirmed через debug probability distribution.
- Скачали v4 (1.8MB, md5 `03da8de2fec4108a089b39f1b4abefef`) → 73% detection на том же файле, 86% на speech+noise
- v5 сохранена как `silero_vad_v5.onnx.legacy` для будущих re-tests

**Integration:**
- `SileroVAD` класс per-call с LSTM state (`h`, `c`, [2,1,64])
- Singleton ONNX session (loaded once at startup: «Silero VAD loaded: ... (v4, 8kHz, md5=...)»)
- env `VOICE_VAD_PROVIDER=silero` (default) / `energy` (rollback)
- Dispatch в `_process_audio_vad` и `_detect_barge_in` через `self._vad is not None`
- Threshold 0.5 для normal VAD и barge-in (изначально пробовали 0.6 для barge-in — не пробивался)
- Зависимости: `onnxruntime 1.24.4`, `numpy 2.4.4` (pulled by onnxruntime)

**Коммит `761ef1eb`** — первый Silero live (threshold 0.5).

**Sliding-silence reset (коммит `97934f47`):** звонок bcf67956 показал **0 BARGE-IN confirmed** за 6 turns (57с TTS). Root cause: AudioSocket frames 320B / Silero chunks 512B → `is_speech()` **альтернирует True/False** на каждом фрейме. Старая логика `_barge_in_buffer.clear()` при любом False сбрасывала counter — 5 consecutive никогда не набиралось. Fix: track `_last_barge_in_speech_ts`, clear buffer только после 300ms sustained silence.

### 3. TTS race (коммит `830a5722`)

**Trigger:** звонок 89dadd55. После sliding-silence fix barge-in стал срабатывать, но **2 turn'а с TTS played=0s** — Sofia сгенерировала ответ, клиент услышал тишину.

**Root cause:** `_is_responding=True` с начала `_process_turn` (включая STT+LLM). Клиент договаривал свою реплику, Silero детектил → BARGE-IN confirmed → `_cancel_playback=True` ДО того как TTS начал играть. Первый же `_send_audio` видел cancel → break → total=first_chunk (0s audio).

**Fix:** новый флаг `_tts_playing` (True только с первой реально отправленной фрейма). В `_handle_packet` barge-in dispatch только при `_tts_playing=True`. Во время STT/LLM фазы фреймы от клиента **игнорируются** (он договаривает свою же реплику).

### 4. UFW firewall (нет коммита — VPS config)

**Trigger:** рост `/var/log/asterisk/full.log` 8GB/сутки от SIP-сканеров (193.46.255.104 давал 99% трафика).

**Разведка:**
- Telfin IP: `46.229.221.93` (DNS sipproxy.telphin.ru, /32, подтверждено `pjsip show registrations` Active)
- PJSIP bind: `UDP 5090` (из pjsip.conf)
- RTP: 10000-20000 UDP (rtp.conf)
- Открыты наружу также UDP 5060 (chan_sip legacy), UDP 4569 (IAX2) — только для сканеров, закрываем

**Rules (порядок строгий):**
```
ufw allow 22/tcp                                            # SSH (ПЕРЕД enable!)
ufw allow from 46.229.221.93 to any port 5090 proto udp     # Telfin SIP
ufw allow 10000:20000/udp                                   # RTP media
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
```

**Результат:** baseline 43697 B/s (44 KB/s, 3.77 GB/день) → **0 B/s** (замер 60с после enable). SYN-пакеты сканеров блокируются до Asterisk, в лог не пишутся. `pjsip show registrations` — Active (Telfin trunk не затронут).

### 5. VAD_RELAX (коммит `95b4eeae`)

**Trigger:** звонок e177d7ad. Клиент: «Скажите примерно минимальную цену **и** [срок]» — `VAD_SILENCE_THRESHOLD=300ms` сработал на паузе между «и» и «срок», обрезал фразу посреди. Затем одиночное «ээ» ~100ms (5 frames) триггернуло `BARGE-IN confirmed` → deadlock (Sofia молчит, клиент ждёт, 17с тишины → hangup).

**Fix (bifurcate по провайдеру):**
- `VAD_SILENCE_THRESHOLD` 0.3 → **0.5 сек** (глобально, любой провайдер)
- barge-in confirm: `confirm_frames = 10 if self._vad is not None else 5` — Silero 10 frames (~200ms real speech с учётом chunking), energy 5 frames (kept for rollback fidelity через `VOICE_VAD_PROVIDER=energy`)

**Временная заплатка** до Yandex STT v3 gRPC streaming (server-side EOU определяет конец фразы, убирает silence threshold вообще).

### Финальный тест (звонок UUID `95e12e88-63dc-4ff8-bf03-fe91e4fb9d13`, 8 turns)

| Метрика | e177d7ad (до VAD_RELAX) | **95e12e88 (итог)** |
|---|---|---|
| USER turns | 2 + deadlock | **8 полноценных** |
| BARGE-IN confirmed | 1 (false на «ээ») | **1 (legit, 10-frame confirm)** |
| TTS 0s played | 0 | **0** |
| «плохо слышно» fallback | 0 | **0** |
| Audio too short skips | 2 | **0** |
| Deadlock 10+ сек | да | **нет** |
| ERROR/WARNING/Exceptions | 0 | **0** |

**Полный продажный flow:** питч → уточнение города → согласие → доходность/окупаемость → выбор Telegram → **диктовка ника «@сергей_7ид»** → прощание. Лид-конверсия через voice канал работает.

**Turn 4 «А сколько окупаемости и сколько годовой доход примерно»** (4.10с, 65600 bytes, 13.2 chars/sec) — фраза с союзом «и» в середине, ровно такая структура сломала e177d7ad. Прошла целиком.

**Turn 7 «Собака сергей нижнее подчеркивание 7 ид»** (4.76с) — клиент диктовал Telegram-ник с длинными паузами. Полная фраза.

### Коммиты 17.04 (в порядке времени MSK)

| SHA | Время | Сообщение |
|---|---|---|
| `5104a0cc` | 23:07 (16 → 17) | fix(voice): barge-in buffer reset instead of re-feed to VAD |
| `761ef1eb` | 23:39 | fix(voice): lower Silero barge-in threshold 0.6 → 0.5 (initial Silero integration) |
| `97934f47` | 23:59 | fix(voice): sliding-silence reset for Silero barge-in buffer |
| `830a5722` | 00:45 | fix(voice): introduce _tts_playing flag, ignore pre-TTS barge-in race |
| `95b4eeae` | 01:10 | fix(voice): relax VAD silence 0.3→0.5s, barge-in confirm 5→10 (Silero only) |

Плюс VPS config: UFW enabled, Silero VAD v4 model file `/opt/sofia-voice/silero_vad.onnx`.

### Текущее состояние voice pipeline

- **VAD**: Silero VAD v4 ONNX, threshold 0.5 normal+barge-in, `VAD_SILENCE_THRESHOLD=500ms`, `VAD_MIN_SPEECH_DURATION=300ms`, `MIN_SPEECH_BYTES_FOR_STT=10240`
- **Barge-in suppression**: `BARGE_IN_COOLDOWN=0.5s`, `BARGE_IN_SILENCE_RESET=0.3s`, 10-frame confirm Silero / 5-frame energy, `_tts_playing` флаг для STT/LLM phase-gate
- **STT**: Yandex SpeechKit v1 REST, ~200ms медиана
- **LLM**: YandexGPT 5 Pro, ~620ms медиана, promo RIZALTA v3 prompt
- **TTS**: Yandex Alena v1 REST lpcm 8kHz, TTFB ~155ms
- **Firewall**: UFW whitelist (22/tcp, 46.229.221.93:5090/udp, 10000-20000/udp), default deny incoming
- **Service**: sofia-voice.service active, PID 107061, память ~54M

### Следующая сессия — P0

1. **fail2ban deploy** (контракт готов в истории чата — два jail для sshd и asterisk, `banaction=ufw`, `ignoreip=46.229.221.93`). UFW закрывает ~100% трафика, fail2ban = multi-layered defense. Не срочно — можно в утренние часы.
2. **Yandex STT v3 gRPC streaming** (docs/VOICE_RESEARCH_2026_04_16.md идея #1, 1-2 дня) — архитектурное упрощение: server-side EOU уберёт нашу VAD+silence-threshold кастомную логику целиком.

---

## 16.04.2026 — VOICE_YANDEX_MIGRATION_v1: полная миграция голосового стека на Yandex

**Сделано:**

### Диагностика (начало сессии)
- Groq убрал модель `moonshotai/kimi-k2-instruct` без предупреждения (HTTP 404)
- OpenAI fallback мёртв (GeoIP 403 с VPS). Голосовой канал полностью неработоспособен
- 4 клиента RIZALTA получили "подвисла" утром до фикса

### Sprint 1: миграция LLM + TTS на Yandex (VOICE_YANDEX_MIGRATION_v1)
- **LLM:** Groq kimi-k2-instruct → YandexGPT через OpenAI-compatible endpoint (`llm.api.cloud.yandex.net/v1/chat/completions`), openai SDK 2.30.0
- **TTS:** ElevenLabs eleven_v3 Nastya (через proxy) → Yandex SpeechKit Alena v1 REST (напрямую), format=lpcm 8kHz, emotion=neutral, speed=1.1. ffmpeg убран из hot path
- **Cached greeting:** greeting_rizalta.pcm (83KB, 5.2s) и greeting_atlantis.pcm (95KB) предгенерированы через Yandex TTS, TTFB=0ms
- **Anti-hallucination:** YandexGPT генерировал fake-диалоги (маркеры "Пользователь:", "Ассистент:"). Фикс: (1) CRITICAL-инструкция в начало VOICE_SYSTEM_PROMPT_RIZALTA и VOICE_SYSTEM_PROMPT, (2) regex post-filter в stream_voice_response() обрезает на маркерах
- **SSML break fix:** Yandex отвергает `<break time="0.3s"/>` (дробные секунды). Заменено на `<break time="300ms"/>`
- **Dead branches:** legacy Groq/ElevenLabs код сохранён под `VOICE_PROVIDER=groq` и `VOICE_TTS_PROVIDER=elevenlabs`
- **5 тестовых звонков Сергея:** 2 на этапе B (ElevenLabs TTS), 2 на этапе C (SSML баг), 1 финальный (полный успех, 4 turns, 66.9s)

### A/B тест 4 моделей YandexGPT (живые звонки, одинаковый скрипт RIZALTA)
| Модель | LLM медиана | User pause | "Откуда данные" | Вердикт |
|--------|------------|------------|-----------------|---------|
| YandexGPT Lite | 815ms | ~1070ms | FAIL (сдалась) | быстро но тупо |
| Qwen3-235B-A22B-FP8 | 2340ms | ~2726ms | OK (подробно) | умно но медленно |
| **YandexGPT 5 Pro** | **638ms** | **~860ms** | OK (кратко) | **ЛУЧШИЙ БАЛАНС** |
| Alice AI LLM | 1290ms | ~2160ms | OK (полный) | умнее всех но многословна |

**Решение:** YandexGPT 5 Pro (`yandexgpt/latest`) для голоса. Переключено на VPS через .env.

### Финальные метрики (звонок d3e92e56 + A/B серия)
| Метрика | Старый стек (ElevenLabs+Groq) | Новый стек (Yandex) | Delta |
|---------|------|------|-------|
| TTS TTFB | 1100ms медиана | **177ms медиана** | -84% |
| LLM latency | 379-1677ms | **638ms медиана (Pro)** | улучшение |
| STT latency | 201-247ms | 158-239ms | ~same |
| User pause (end-to-end) | ~1300ms | **~860ms (Pro)** | -34% |
| Greeting TTFB | 1106-1818ms | **0ms** (cached) | -100% |
| Proxy dependency | Да | Нет | eliminated |

**Коммиты:** `a7f45612` feat(voice): migrate LLM+TTS to Yandex stack (VOICE_YANDEX_MIGRATION_v1)
**Файлы:** voice_asterisk.py, core/pipeline.py, .env (VPS)
**Env добавлены (VPS):** YC_API_KEY, YC_FOLDER_ID, VOICE_MODEL_YANDEX, VOICE_TTS_PROVIDER, YANDEX_TTS_VOICE, YANDEX_TTS_EMOTION
**Env изменены (VPS):** VOICE_PROVIDER=yandex (было groq), VOICE_MODEL_YANDEX=yandexgpt/latest (Pro)
**Rollback:** VOICE_PROVIDER=groq / VOICE_TTS_PROVIDER=elevenlabs в .env + systemctl restart sofia-voice

**Побочные находки:**
- SIP-сканеры (193.46.255.104 + 172.110.223.135) раздувают Asterisk full.log ~8G/сутки, диск рос 15%→45% за сутки → fail2ban/UFW переведён в P0

### Sprint 1 продолжение: Barge-in fix + RIZALTA v3 + voice research

**Barge-in cascade fix:**
- После миграции на Yandex Alena TTS (быстрее ElevenLabs) barge-in стал заметнее — 50% пустых STT на звонках с перебиванием, каскад ложных VAD после cancel TTS
- Добавлено в `voice_asterisk.py`: константы `BARGE_IN_COOLDOWN=0.5`, `MIN_SPEECH_BYTES_FOR_STT=10240`, поле `_barge_in_cooldown_until`
- Гейт в `_handle_packet` AUDIO-ветке: `time.monotonic() < _barge_in_cooldown_until` → дропать фрейм
- Cooldown активируется в `_detect_barge_in` при подтверждении barge-in (вместе с `_cancel_playback=True`)
- MIN_BYTES проверка в `_process_audio_vad` перед созданием `_process_turn` task → debug-лог `Audio too short (N bytes < 10240), skipping STT`
- Проверено в живом звонке 16.04 18:40 (UUID 21b96626): cooldown сработал 2×, MIN_BYTES 3×

**RIZALTA промпт v3 (коммит `ef2888ae`):**
- **Без представления** («Алло, здравствуйте! У меня для вас важная новость...» сразу в greeting)
- **Двухчастный питч:** часть 1 — крючок с доходностью (greeting); часть 2 — регион/спрос/Сибирь (после согласия)
- **Логика мессенджеров:** Ватсап/Макс = номер уже знаем, прощаемся; Телеграм = уточняем ник; иначе — спрашиваем «Куда удобнее?»
- **Вход повышен** 10 млн → 15 млн рублей (по факту проекта)
- Добавлены: Совкомбанк ипотека, траншевая ипотека Сбербанка, сравнение с депозитом, минимальный гарантированный платёж
- Запрещены фразы «скину пакет» / «в Телеграм пакет» (неестественно)
- Cached greeting `greeting_rizalta.pcm` регенерирован через Yandex Alena (190 chars → 198318 bytes PCM, 12.4s аудио, 346ms синтез)
- Hardcoded greeting в `voice_asterisk.py:506-511` обновлён на питч-часть-1

**Тестовый звонок с перебиванием (UUID 21b96626, 81.8s):**
- Greeting проиграл целиком (1ms TTFB, 12.4s без прерываний)
- Turn 1 barge-in через 10с игры TTS → cooldown 500ms сработал
- **Проблема:** 13120-байтовый barge-in buffer (0.82с, порог 10240 прошёл) отправился в STT → garbled «Со стороны» → LLM-ответ «Простите, плохо слышно» из блока «Не расслышала» промпта
- Логика мессенджеров дошла: «Куда отправить? Телеграм, ватсап или макс?» на «Да давайте» ✅

### Исследование voice stack (отчёт `docs/VOICE_RESEARCH_2026_04_16.md`)

- 20 идей улучшения, каждая с gain/effort/risk/priority/источниками
- Сравнение 5 мировых платформ (Vapi, Retell, LiveKit, Pipecat, 11L Conversational)
- Обзор 6 отечественных стеков (Yandex, Sber SaluteSpeech, Tinkoff VoiceKit, T-one OSS, GigaAM v3, Silero TTS v5)
- **Топ-5 по gain/effort:** Silero VAD (0.5д, −150ms), Yandex STT v3 gRPC streaming (1-2д, −300ms), sentence-level LLM→TTS (2д, −350ms), TTS cache + fillers (1.5д, перцептивно→0ms), per-turn JSON metrics (1д, observability)
- **Целевая метрика:** 860ms median user-perceived pause → **300-400ms** + субъективно <100ms через filler маскирование
- Эффорт top-5 ≈ 7 дней чистой работы

### Следующая сессия — P0

1. **Barge-in buffer reset** вместо re-feed в VAD (сейчас `_process_turn` finally копирует barge-in buffer в `_speech_buffer` → 13120-байтный polluted fragment попал в STT). Вариант: после cooldown просто очищать buffer, ждать свежую речь
2. **Silero VAD** замена energy-based RMS (0.5 дня, drop-in замена, +90% precision)
3. **Yandex STT v3 gRPC streaming** — убрать REST TLS handshake + VAD 300ms timeout (−150-300ms)
4. **Sentence-level LLM streaming → TTS pipelining** (−200-350ms на репликах >1 предложения)

**Коммиты 16.04:**
- `3edc908f` docs: session 16.04 — voice diag (Groq model removed)
- `a7f45612` feat(voice): migrate LLM+TTS to Yandex stack (VOICE_YANDEX_MIGRATION_v1)
- `ae61ed8d` docs: session 16.04 — voice yandex migration + 4-way A/B
- `ef2888ae` feat(voice): RIZALTA v3 prompt + voice research report

**Файлы:** voice_asterisk.py, core/pipeline.py, docs/VOICE_RESEARCH_2026_04_16.md, greeting_rizalta.pcm (VPS)

---

## 15.04.2026 — Аудит расхождений + DISK_RESCUE + правила оркестратора

**Сделано:**

### 1. Context reconciliation (CONTEXT_RECONCILIATION_v1)
- Сверка модели Claude Code с реальностью по 7 пунктам
- Найдено критичное: VPS sofia-voice диск снова 100% (4 дня после прошлой чистки вместо прогноза 4-6 недель)
- Sprint 2 (Radist username→Bitrix) verified в production: лид 265712 (Arkadiy, @pordiregrwe) прошёл полный цикл — UF_CRM_TELEGRAM заполнен, ASSIGNED восстановлен на менеджера 14708, БП 152 отработал
- Edge-case клиент без публичного username (лид 265590) обработан корректно — поле не заполнено, не затёрто пустотой
- Тильда: единственная ссылка `https://t.me/m/QinKZEsTNmRi` стабильно отдаётся для всех User-Agent
- Урок: фильтр Bitrix `TITLE LIKE "AI-бот"` не работает для ATL (Sofia обновляет существующий Tilda-лид, не создаёт). Правильный фильтр — `SOURCE_ID=397 + DATE_MODIFY` + кросс-проверка с `radist_leads`

### 2. DISK_RESCUE_v2 (пятиэтапный спринт)
- **Диагностика:** на 185.207.66.201 диск 100% (29 GB / 29 GB)
- **Корневая причина найдена:** `/etc/logrotate.d/asterisk` (поставленный с пакетом в 2022) имел сломанные glob-паттерны — `messages` вместо `messages.log`, `full` вместо `full.log`, `*_log` вместо `*.log`. logrotate каждую неделю отрабатывал, ничего не находил, тихо завершался. Файлы росли неограниченно 4 года. Это баг сборки Asterisk-пакета для Debian/Ubuntu — старые версии писали без расширения, новые с .log, конфиг logrotate в пакете не обновили.
- **Очистка диска:** освобождено 25 GB
  - Этап 3: `rm` архивных `full.log.0` + `messages.log.0` (по 9.9 GB) + `journalctl --vacuum-size=200M` + `truncate` btmp = +21 GB
  - Этап 4: `asterisk -rx 'logger rotate'` (родная команда, корректно переоткрывает fd через inode change) + `rm` ротированных = +3 GB
- **logrotate починен:** новый `/etc/logrotate.d/asterisk` с явными `full.log`, `messages.log`, `queue_log`, `daily rotate 7 compress`, postrotate через `asterisk -rx 'logger rotate'`. Бэкап старого в `/etc/logrotate.d/asterisk.broken.20260415`
- **Финальное состояние:** диск 15% used / 85% free, asterisk + sofia-voice оба active, голосовой канал ожил после очистки, mtime `/etc/asterisk/logger.conf` не изменился (доказательство неприкосновенности)
- **Усиление методологии:** Claude Code применил inode-check вместо опасного size-check для подтверждения ротации (поправка в Этапе 4)

### 3. Правила оркестратора зафиксированы в отдельном документе
- Создан `docs/ORCHESTRATOR_RULES.md` с правилами работы Claude.ai как оркестратора
- В CLAUDE.md добавлена ссылка на новый документ
- Поводом стали ошибки сегодняшней сессии: захардкоженный systemd-unit без знания файлов (10.04), длинные ответы на простые вопросы (15.04), отсутствие прохода "что забыл" перед отдачей контракта (15.04)

### 4. Gitpull-гигиена (UPDATE_GITPULL_DOCS)
- Найдено: `start-session.sh` (на локалке Сергея) копирует только CLAUDE.md / SESSION_LOG.md / BACKLOG.md, новый `docs/ORCHESTRATOR_RULES.md` в контекст Claude.ai не попадал. Без этого правила оркестратора, записанные сегодня, при следующем `start-session.sh sofia` оркестратор бы не увидел.
- Блок «Gitpull» в CLAUDE.md дополнен: `mkdir -p ~/projects_claude/Sofia/docs` + 4-я scp-команда для `docs/ORCHESTRATOR_RULES.md`
- Блок «Session End» дополнен: новый пункт 3 «при изменении правил оркестратора — обновить ORCHESTRATOR_RULES.md», файл добавлен в `git add`-команду
- Сергей синхронно обновил локальный `start-session.sh` — проверено на следующем запуске
- Урок: любой новый файл, который должен попадать в контекст Claude.ai, требует **парной** правки: и CLAUDE.md, и локального скрипта, иначе документация и реальный flow расходятся

### 5. ATLANTIS_CHAT_WIDGET_v1
- Создан `widgets/atlantis_chat_widget.html` (15.9 KB) — самодостаточный HTML-блок для Tilda T123
- Десктоп: фиксированный круг 72×72 справа по центру, золотой градиент, два concentric pulse-ring через `::before/::after`, hover scale 1.08
- Мобильный: фиксированная плашка снизу с base64-аватаркой Софии, зелёной точкой онлайн, двумя строками текста, slide-up анимацией, iOS `env(safe-area-inset-bottom)`
- Все CSS-классы `atl-chat-*`, z-index 99999, никакого JS, никаких внешних ресурсов
- Ведёт в @SofiaOazis через Telegram Business Link `https://t.me/m/Fiw3ldhkN2My` (вторая ссылка, не основной QinKZEsTNmRi)
- Правка по фидбеку Сергея: круг зелёный `#4ade80 → #16a34a` вместо золота (точечная замена одной строки CSS)
- Коммит `3de1fbf9`

### 6. SPRINT_TEMPLATE_v2 + wiring
- Создан `docs/SPRINT_TEMPLATE_v2.md` (13.3 KB) — универсальный шаблон Sprint Contract на XML-структуре по гайду Anthropic
- 9 обязательных секций (role/context/task/investigate_first/acceptance_criteria/do_not/rollback/build_report_format/done_when) + 4 опциональных (subagents/stop_for_confirmation/edge_cases/external_artifacts)
- Два встроенных блока: `<anti_overengineering>` и `<investigate_before_answering>` — копируются в каждый контракт дословно. Filling example в конце с эталоном заполнения
- Коммит `057b6811`
- TEMPLATE_V2_WIRING (`71103849`) — добавил правило в ORCHESTRATOR_RULES.md п.4 «новые контракты строить по SPRINT_TEMPLATE_v2.md», добавил scp-строку в Gitpull блок CLAUDE.md, обновил git add в Session End
- Урок закрепился: шаблон без проводки в Gitpull — остаётся сиротой. Парная правка (репо + локальный скрипт) обязательна

### 7. SAFETY_RULES_v1 — промпт-правила (DEV)
- В `sofia_prompt_v2.py` добавлен блок «ЧЕГО SOFIA НЕ ДЕЛАЕТ» (+18 строк) между «ПРИНЦИПЫ ОБЩЕНИЯ» (строка 321) и «ТЕХНИКИ ПРОДАЖ» — универсальные запреты для всех каналов: не запрашивать паспорт/реквизиты/коды, не давать юр. гарантий, не обещать доходность, не заключать сделки, не подтверждать бронь окончательно
- В `config/source_objects.py` `prompt_addon` Атлантиса расширен с 1 строки до triple-quoted multi-line с блоком «ПЕРЕДАЁТ ДИАЛОГ МЕНЕДЖЕРУ» — триггеры: политическое мнение (с уточнением про отличие от возражения по безопасности региона), юр/фин о компании, СВО, дискриминация, незаконные схемы, мошеннические запросы
- Stop-point после разведки: обнаружен конфликт старого возражения «В Крыму опасно / политика / нападения» со новым триггером, решён переформулировкой первого триггера
- Коммит `772cbe6e` с `--no-verify` (pre-existing долг в `format_state_summary` по `black`, не связан со scope; явное разрешение оркестратора)
- DEV Smoke #1 (Атлантис + СВО): Sofia НЕ применила новое правило — выяснилось что web_api.py вообще не устанавливает `source_object` в state, поэтому Atlantis-addon никогда не склеивается в промпт через web. Плюс Analyzer классифицировал СВО как OBJECTION → RAG затянул примеры возражений
- DEV Smoke #2 (банковские реквизиты + СМС-код через общий web): Sofia **корректно** применила все три правила общего блока — явно предупредила не присылать СМС-код, отказалась выдавать реквизиты, сослалась на менеджера, не выдала внутреннюю инфу

### 8. SAFETY_RULES_DEPLOY_PROD — split-deploy в PROD
- Задача: port коммита 772cbe6e в PROD. Получилось только наполовину — по очень хорошей причине
- Разведка PROD показала: `sofia_prompt_v2.py` PROD vs DEV — чистый diff (только +18 моих строк). `config/source_objects.py` — есть pre-existing косметический drift (black на `detect_source`/`load_object_context`, backport не делался)
- Первая попытка — `git cherry-pick 772cbe6e` в PROD — упала с `fatal: bad revision`: PROD и DEV **разные git-репо**, SHA одного недоступен в другом. Мой пропуск в рекомендации
- Вторая попытка — `git format-patch | git am` — упала с `patch does not apply at config/source_objects.py:18`
- Анализ конфликта открыл **большую находку**: в PROD `config/source_objects.py` **вообще нет** ключа `prompt_addon` в Атлантисе, а в PROD `core/pipeline.py` **нет** ветки `if obj_config.get("prompt_addon")` — весь Atlantis-addon-механизм DEV-only, никогда не был в PROD. Это подтверждает давний пункт BACKLOG про «prompt_addon только в dev, не закоммичен», но масштаб больше: там **400+ строк** разницы в `core/pipeline.py` DEV vs PROD
- Решение (вариант D, split): применить **только** `sofia_prompt_v2.py` часть через `git show 772cbe6e -- sofia_prompt_v2.py | git apply --index -`, Atlantis-часть отложить до отдельного спринта `ATLANTIS_ADDON_INFRA_PORTBACK`
- PROD коммит `d60e9b0b` feat(prompts): safety rules (core only) — port from dev 772cbe6e (atlantis-addon deferred). Локальный, без push
- Рестарт всех трёх PROD-сервисов (sofia-gpt / sofia-web-api / sofia-radist) — все active running, 0 ERROR в логах за 5-минутный мониторинг
- PROD smoke с тем же СМС-триггером — Sofia PROD применила все 3 правила общего блока, буквальный ответ зафиксирован в Build Report

### 9. GAPS_CLOSE_BEFORE_NEXT_SESSION
- Перед закрытием сессии зафиксированы 3 пробела:
- `docs/ORCHESTRATOR_RULES.md` «Стиль ответов» расширен пунктами 6-10: «lf» = «да», запрет ритуальных оборотов, короткое признание ошибок без самозащиты, «по шагам» = один шаг/сообщение, «человеческим языком» как сигнал усталости Сергея
- `CLAUDE.md` Gitpull блок дополнен scp-командами для 4 критичных memory-файлов: `project_prod_dev_drift.md`, `user_sergey.md`, `project_voice_sprint_next.md`, `project_voice_vps.md`. `mkdir` объединён (`docs` + `memory`). Без этого оркестратор Claude.ai в новой сессии не увидит каталог PROD↔DEV drift и свежие наблюдения про Сергея
- `BACKLOG.md` P3: добавлен пункт «Обновить userMemories оркестратора» — устарели на сутки, оркестратор сам обновит через memory_user_edits в начале следующей сессии
- Коммит `3081ea0e`

**Коммиты DEV (15.04, полный список):**
- `923f229c` docs: session 15.04 close — DISK_RESCUE + orchestrator rules
- `5fee930c` docs: добавить ORCHESTRATOR_RULES.md в Gitpull блок CLAUDE.md
- `b5eb6822` docs: финализация session 15.04 — UPDATE_GITPULL_DOCS зафиксирован
- `3de1fbf9` feat(widget): atlantis chat widget for tilda T123
- `057b6811` feat(docs): sprint contract template v2 with xml structure
- `71103849` docs: wire SPRINT_TEMPLATE_v2 into orchestrator rules and gitpull
- `772cbe6e` feat(prompts): safety rules + manager handoff triggers (atlantis)
- `d3d20d9e` docs: session 15.04 close (часть 2) — widget + template + safety rules + prod deploy
- `3081ea0e` docs: close 3 pre-session gaps (style rules, memory gitpull, userMemories backlog)

**Коммит PROD:**
- `d60e9b0b` feat(prompts): safety rules (core only) — port from dev 772cbe6e (sofia_prompt_v2.py only, atlantis-addon deferred)

**Уроки сессии (зафиксированы в CLAUDE.md + ORCHESTRATOR_RULES.md):**
- `git cherry-pick` **не работает** между отдельными git-репозиториями (PROD/DEV — отдельные репо, а не ветки одного). Нужно `git format-patch | git am` или `git fetch <path> && git cherry-pick FETCH_HEAD`
- При деплое DEV→PROD в investigate_first обязательно сравнивать не только целевые файлы, но и **файлы-потребители** целевых изменений (pipeline.py когда трогаем config/*.py, bot_server.py когда трогаем core/bitrix.py и т.д.)
- PROD может содержать не «DEV минус целевой коммит», а «DEV минус целая фича». Сегодня: Atlantis-addon как механизм отсутствует в PROD целиком (данные + код-потребитель), 400+ строк разницы в pipeline.py
- Правило «ловить нестыковки контракта ДО выполнения» работает: 3 stop-point'а сегодня (A→A'→A'', A'→конфликт, D→split) сэкономили откатов и ошибок

**Файлы сессии (DEV):**
- sofia_prompt_v2.py (+18)
- config/source_objects.py (+16/-1)
- widgets/atlantis_chat_widget.html (новый, 15.9 KB, круг зелёный)
- docs/SPRINT_TEMPLATE_v2.md (новый, 13.3 KB)
- docs/ORCHESTRATOR_RULES.md (новый + дополнения)
- CLAUDE.md (Gitpull блок, Session End блок, Docs ссылки, 5+ новых уроков)
- SESSION_LOG.md, BACKLOG.md

**Файлы сессии (PROD):**
- sofia_prompt_v2.py (+18, через git apply, коммит d60e9b0b)

**Открытые задачи после сессии:**
- 🔴 **ATLANTIS_ADDON_INFRA_PORTBACK (P0)** — полный аудит pipeline.py PROD vs DEV (400+ строк разницы), план порта Atlantis-addon-механизма в PROD. Блокер для работы Atlantis-specific safety-триггеров в production
- Кнопка «Чат с менеджером» на сайте — Сергей использует готовый виджет из widgets/
- 20-минутный робот Bitrix у админа (ждём)
- SIP-сканеры на VPS (P2)
- Whisper STT vs Yandex SpeechKit несоответствие (P2)
- chore(format): run black on prompt files (sofia_prompt_v2.py + source_objects.py backport в PROD)

---

## 11.04.2026 — Деплой Radist username→Bitrix в PROD

**Сделано:**

### Деплой Спринта 2 (RADIST_USERNAME_DEPLOY_PROD_v1)
- Фича из коммита 8b504869 (DEV) выведена в production
- Файлы: sofia_radist_gateway.py (+76 строк), core/bitrix.py (+12 строк)
- Pre-deploy: diff показал только username-изменения, ничего постороннего
- Снапшоты PROD сохранены: `/tmp/radist_gw.prod.before_deploy`, `/tmp/bitrix.prod.before_deploy`
- ast.parse обоих файлов OK
- `sudo systemctl restart sofia-radist.service` → active (running), PID 2460093
- Логи чистые: БД init, каналы active (max, telegram), 0 ошибок
- Git commit в PROD: `1146ea2c` (без push — by design)
- Функциональная проверка отложена до первого реального ATL-клиента

**Коммиты:**
- 1146ea2c (PROD) — feat(radist): deploy username→Bitrix from dev (8b504869)

**Файлы (PROD):** sofia_radist_gateway.py, core/bitrix.py

---

## 10.04.2026 — Аудит Атлантис + merge bot_server.py (Observer portback)

**Сделано:**

### 1. Полный аудит Атлантиса (docs/AUDIT_ATLANTIS_2026-04-10.md)
- Зафиксирован переход на @SofiaOazis через Telegram Business Link
  (https://t.me/m/QinKZEsTNmRi) — Тильда переключена на всех 3 формах
  invest-apartmens.online, старая ссылка t.me/humanAINeural_bot?start=ATL
  нигде не используется
- ATL-flow через Radist работает полностью: 8 сессий за 2 дня, 6 реальных
  клиентов, 5 из 6 финализированы через БП 152
- Radist dedup fix (3892c648) фактически верифицирован живым трафиком
- Виджет на invest-apartmens.online/atlantis отключён 04.04, код страницы
  очищен от упоминаний Sofia (возврат — Спринт 3)
- 3 домена виджета по web_sessions: invest-apartmens.online (180),
  atlantis-invest.ru (6), sochiremstroy (2)
- rizaltabelokurikha.ru — другой виджет (EvaChatWidget), не наш
- Атлантис = Крым, Новофёдоровка, Cosmos Crimea (не Сочи — зафиксировано
  исправление в userMemories)

### 2. Расследование зависших лидов на ASSIGNED=428
- Лид #264518 (Роман) — Тильда-форма "Презентация в WhatsApp", клиент
  не дошёл до бота, висит 87ч. Sofia такого клиента не видит в принципе.
- Лид #264372 ("пывп") — тест-мусор, 110ч
- Системная причина: safety-net для Тильда-лидов без диалога
  отсутствует. 20-минутный Bitrix-робот должен был быть настроен 04.04,
  админ забыл — добивает сегодня
- Добавлено в BACKLOG P1: safety-net verification после настройки робота

### 3. Спринт: merge bot_server.py — Observer portback (коммит 75b779a5)
- Проблема: коммит 49659ffb (08.04) добавил Observer напрямую в PROD,
  не был портирован в DEV. Любой будущий деплой DEV→PROD молча удалил бы
  Observer из PROD.
- Разведка Фазы 1: первая попытка Claude Code ошибочно показала одинаковый
  49659ffb в обеих ветках (неправильный cwd при git log). Повторная
  проверка подтвердила: коммит есть только в PROD, в DEV его никогда не
  было, reflog чистый, shell history чистый — Observer никто специально
  не отключал, просто не дошёл до dev
- Merge: 6 блоков (86 строк) перенесены из PROD в DEV:
  1. import logging + logging.basicConfig (строки 27, 29-34)
  2. OBSERVER_CHAT_ID (структура из PROD, env-default "-5206139579" для
     dev-группы сохранён)
  3. CREATE TABLE observer_topics_bot (339-345)
  4. get_or_create_bot_topic() + notify_bot_observer() (896-961)
  5. notify_bot_observer для входящего (979-981)
  6. notify_bot_observer для ответа Софии (1035-1037)
- Итоговый diff PROD vs DEV: ровно 1 строка (OBSERVER_CHAT_ID default),
  остальные 86 строк идентичны
- flake8 + black проходят, ast.parse + import bot_server OK
- PROD не трогали, snapshot /tmp/bot_server.prod.snapshot и
  /tmp/bot_server.dev.snapshot оставлены как rollback

### 4. Спринт 2: Radist username → Bitrix (коммит 8b504869)
- chat.username и chat.profile_link из Radist webhook теперь извлекаются
  и передаются в Bitrix: UF_CRM_TELEGRAM = https://t.me/username (кликабельная
  ссылка) + COMMENTS строка "Telegram: @username"
- Нормализация: пустой username → не пишем, не затираем существующее.
  Fallback: profile_link если username пуст
- tg_username сохраняется в radist_chats (миграция ALTER TABLE) для доступа
  при финализации по таймауту
- Dry-run тест: payload с username содержит UF_CRM_TELEGRAM, без username —
  поле отсутствует (не затирает)
- Файлы: sofia_radist_gateway.py (+76), core/bitrix.py (+12)

### 5. Спринт: sofia-voice systemd unit (VPS 185.207.66.201)
- **Инцидент:** ребут сервера хостингом (апгрейд 14→29 GB диск,
  961 MB → 1.9 GB RAM), voice_asterisk.py не поднялся (~40 мин даунтайма)
- Создан `/etc/systemd/system/sofia-voice.service`: Type=simple,
  Restart=on-failure, RestartSec=3, EnvironmentFile, LOGURU_COLORIZE=false
- systemctl enable + start → active (running), MainPID=2941, 34.6M памяти
- Auto-restart протестирован: kill -9 → NRestarts=1, новый PID через 3 сек
- Голосовой канал восстановлен и защищён от будущих ребутов
- **Подсветка:** логи voice_asterisk говорят "Whisper STT", CLAUDE.md
  говорит "Yandex SpeechKit" — требует проверки что реально используется

### 6. Зафиксировано на будущее (см. ниже — в CLAUDE.md как правила)
- Правило: любой прямой коммит в PROD должен немедленно портироваться
  в DEV или явно фиксироваться в SESSION_LOG
- Нужна регулярная git-sanity проверка расхождений prod vs dev по всем
  файлам (как минимум core/, config/, *_server.py, *_gateway.py)

**Коммиты:**
- 75b779a5 (DEV) — merge: bot_server.py — Observer portback из PROD
- 8b504869 (DEV) — feat(radist): Telegram-username → Bitrix

**Файлы:**
- docs/AUDIT_ATLANTIS_2026-04-10.md (новый)
- bot_server.py (DEV, +86 строк Observer portback)
- sofia_radist_gateway.py (DEV, +76 строк username)
- core/bitrix.py (DEV, +12 строк telegram_url)
- /etc/systemd/system/sofia-voice.service (VPS, новый)
- SESSION_LOG.md, BACKLOG.md, CLAUDE.md (этот апдейт)

**Открыто для следующих спринтов:**
- Спринт 3: возврат виджета в новом формате (slide-out side tab), ждёт
  verification 20-минутного робота Bitrix
- source_objects.py prompt_addon (DEV-only, не закоммичен) — требует
  разделения логики запроса контактов по каналам (виджет vs Telegram)
- git-sanity полный scan prod vs dev — можно выполнить отдельным мини-спринтом
- Деплой Radist username → Bitrix в PROD — отдельный шаг после визуальной
  проверки Сергеем

---

## 10.04.2026 — Stress Research + TTS A/B Test + Eleven v3 Locked

**Сделано:**

### 1. Stress Research (ruaccent + U+0301)
- ruaccent 1.5.8.3 протестирован на 16 словах-ловушках: **75% точность** (12/16)
- Латентность ruaccent: **388ms среднее** — превышает порог 200ms в 2x
- Баг ONNX: `token_type_ids` отсутствует, патч `np.zeros_like(input_ids)` в accent_model.py
- U+0301 (combining acute accent) — **не документирован** в ElevenLabs
- Phoneme tags — только для английского, только eleven_flash_v2
- **Решение: Вариант B — ручной словарь фонетических замен** (0ms, 100% контроль)
- Отчёт: `docs/STRESS_RESEARCH.md`
- Тестовые аудио: `voice_samples_v2/stress_test/` (4 mp3)

### 2. TTS Model Research (Flash v2.5 vs MLv2 vs v3)
- eleven_v3 доступен через API на Starter плане, model_id = `eleven_v3`
- v3 TTFB = 700-900ms (Flash = 367ms, MLv2 = 585-3060ms)
- v3 НЕ поддерживает `optimize_streaming_latency`
- v3 PVC "not fully optimized" по документации, но по факту Nastya звучит хорошо
- v3 = 2x дороже Flash по кредитам (1 vs 0.5 за символ)
- Отчёт: `docs/ELEVENLABS_V3_RESEARCH.md`
- Семплы: `voice_samples_v2/v3_vs_multilingual/` (6 mp3), `voice_samples_v2/stability_test/` (8 mp3)

### 3. Live A/B Test (на реальных звонках)
- Этап 1: v3 → Сергей: "прекрасно звучит"
- Этап 2: MLv2 stable (stab=0.7, sim=0.9) → отклонён
- **Решение: eleven_v3 = production TTS модель**
- Компромисс: TTFB +400-500ms vs Flash, компенсируется fillers (следующий спринт)

### 4. Sync DEV от VPS
- VPS → DEV: voice_asterisk.py (Flash v2.5 → v3, add_ssml_breaks, VoiceSettings, RIZALTA prompt v2)
- Два коммита: `8d468477` (sync), `04d9a710` (v3 adoption)

### 5. CLAUDE.md обновлён
- ElevenLabs: Flash v2.5 → eleven_v3
- Тайминги обновлены: TTS TTFB ~700-900ms

**Коммиты DEV:** `8d468477` (sync), `04d9a710` (v3 lock)
**Файлы:** voice_asterisk.py, core/pipeline.py, docs/STRESS_RESEARCH.md, docs/ELEVENLABS_V3_RESEARCH.md, docs/SOFIA_CURRENT.md, SESSION_LOG.md

**Текущие тайминги (обновлены):**
- VAD silence: 300ms
- STT (Yandex): ~300ms
- LLM (Groq kimi-k2 via proxy): ~300ms
- TTS TTFB (ElevenLabs v3 via proxy): ~700-900ms
- **Итого: ~900-1100ms ощущаемая пауза** (было ~600-700ms с Flash)

**Следующий спринт:** Fillers (B1) для маскировки латентности v3

---

## 09.04.2026 — Radist dedup fix + Voice Research + Voice Stack Tuning v2 + RIZALTA Prompt v2

**Сделано:**

### 1. Диагностика и фикс дублирования сообщений в Radist (DIAG+FIX)
- Диагностика: клиентские реплики дублировались кумулятивно в radist_messages, Observer и Bitrix COMMENTS
- Причина: `save_message()` и `notify_observer()` вызывались на каждой итерации `_process_loop` в message_queue.py
- Фикс: вынос save/notify в замыкание `save_user_and_notify()`, вызов один раз через `send_callback`
- Доп. фикс: `get_history()` ORDER BY timestamp → id (устранение недетерминированности)
- DEV коммит: `7f4c96a2`, PROD cherry-pick: `3892c648`
- Деплой в PROD: рестарт sofia-radist.service, подтверждён работающим

### 2. Voice Research Sprint (3 часа, 3 параллельных агента)
- Протестировано: 9 LLM (Groq+OpenAI), 16 TTS движков, 7 STT
- Сгенерировано: 23 коротких + 12 длинных + 19 finalists = 54 аудиофайла
- Главное открытие: **kimi-k2-instruct** на Groq — лучший русский для голоса (TTFT ~300ms, качество 5/5)
- ElevenLabs Flash v2.5 = Turbo v2.5 (deprecated) — 3x быстрее MLv2
- Yandex SpeechKit: лучшие ударения (99%), но нет voice cloning
- Отчёт: `docs/RESEARCH_REPORT_VOICE_AGENT_v1.md`
- Семплы: `voice_samples_v2/` (short + long + finalists)

### 3. Voice Stack Tuning v2 (деплой на VPS sofia-voice)
- LLM: llama-4-scout → **kimi-k2-instruct** (устранение Йода-русского)
- TTS: eleven_multilingual_v2 → **eleven_flash_v2_5** (TTFB 960ms→300ms)
- VoiceSettings: stability 0.35→0.50, similarity 0.79→0.85, speed 1.19→1.10
- max_tokens: 400→150
- VAD: 0.4→0.3
- SSML: `add_ssml_breaks()` — автовставка `<break time="0.3s"/>` между предложениями (без `<speak>` обёртки!)

### 4. RIZALTA Prompt v2
- Полностью новый промпт: канонический питч (дословный), ГЛАВНОЕ ПРАВИЛО «всегда вопрос после информации», 6 примеров диалогов
- Софья → София (глобально в RIZALTA)
- Greeting: «Здравствуйте! Это София, агентство Оазис. Вам удобно сейчас разговаривать?»
- Первый тестовый звонок — «в целом приемлемо, не идеально, ударения и паузы требуют доработки»

### Баг найден и пофиксен в процессе
- `<speak>` обёртка SSML ломала ElevenLabs streaming endpoint (30s timeout) — убрана, breaks идут инлайн

**Ключевые метрики:**
- Латентность: ~1000ms → ~600-700ms (perceived)
- Качество русского LLM: 3/5 → 5/5 (kimi-k2 vs llama-4-scout)
- TTS TTFB: ~960ms → ~300ms

**Коммиты DEV:** `7f4c96a2` (radist dedup)
**Файлы на VPS:** voice_asterisk.py, core/pipeline.py, .env (прямые правки, без git)

---

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
