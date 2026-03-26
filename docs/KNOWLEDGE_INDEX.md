# KNOWLEDGE_INDEX.md — база знаний Sofia-GPT

📅 Создан: 08.03.2026 | Обновлён: 26.03.2026

## Формат записи
### [Дата] Название задачи
- **Что сделано:** ...
- **Почему:** ...
- **Файлы:** ...
- **Как откатить:** ...

---

## 26.03.2026 — ASSIGNED_BY_ID=428 + деплой P0 + Voice V1 + Pipecat V2

### ASSIGNED_BY_ID=428 (Sofia AI) — ЗАДЕПЛОЕНО

- **Что сделано:**
  1. `SOFIA_AI_USER_ID = 428` — константа в core/bitrix.py
  2. `create_lead()` ставит ASSIGNED_BY_ID=428 (вместо 426) при создании
  3. `find_recent_atlantis_lead()` → dict с assigned_by_id, сохраняет original
  4. `restore_assigned(db_path, lead_id)` — возвращает ответственного (original → fallback 426)
  5. Таблица `lead_assigned`: lead_id → original_assigned_by_id (auto-migrate)
  6. Webhook: проверяет ASSIGNED_BY_ID ≠ 428 → менеджер перехватил → его ID
  7. 4 сценария: meeting_agreed, двойной отказ, таймаут, перехват
- **Почему:** Битрикс робот-распределитель раздаёт лиды менеджерам сразу. Sofia AI (428) — ответственный на время квалификации, робот не трогает.
- **Файлы:** core/bitrix.py, bot_server.py, web_api.py
- **Коммиты:** 320cbdd2, 7ae37c0a
- **Как откатить:** Восстановить из backups/20260326_0724/

### Битрикс только для source-сессий — ЗАДЕПЛОЕНО

- **Что сделано:** `_is_bitrix_session(user_id)` — Битрикс API вызывается только при наличии source_object (ATL и др.)
- **Почему:** Обычные диалоги /start без параметра не должны создавать лиды в CRM
- **Файлы:** bot_server.py
- **Коммит:** 7ae37c0a

### Деплой P0 в прод — 26.03.2026

- **Что задеплоено:** core/bitrix.py, bot_server.py, web_api.py
- **Бэкап:** `/opt/sofia-gpt/backups/20260326_0724/`
- **Как откатить:**
```bash
cp /opt/sofia-gpt/backups/20260326_0724/bitrix.py.bak /opt/sofia-gpt/core/bitrix.py
cp /opt/sofia-gpt/backups/20260326_0724/bot_server.py.bak /opt/sofia-gpt/bot_server.py
cp /opt/sofia-gpt/backups/20260326_0724/web_api.py.bak /opt/sofia-gpt/web_api.py
sudo systemctl restart sofia-gpt sofia-web-api sofia-radist
```

### Voice Вариант 1 — оптимизация stream_voice_response()

- **Что сделано:**
  1. VOICE_MODEL = "gpt-4.1-mini" (вместо gpt-5.2)
  2. RAG: 3 → 10 примеров
  3. VOICE_PROMPT_ADDON — 7 правил голосового режима (убрано "всегда заканчивай вопросом")
  4. max_output_tokens: 4000 → 800
  5. Async Extractor: extract_sync + merge_extraction_to_state в asyncio.create_task (НЕ через process_message — он сбрасывает dialog_finished)
  6. [END] проверка post-stream
- **Почему:** Ускорить voice + вернуть качество (Extractor, RAG)
- **Файлы:** core/pipeline.py
- **Коммиты:** 07045919, 48b654be
- **ВАЖНО:** process_message() сбрасывает dialog_finished=False (строка 52-56). Async Extractor вызывает extract_sync + merge напрямую чтобы не сбрасывать.

### Voice Вариант 2 — Pipecat бот (dev, В ПРОЦЕССЕ)

- **Что сделано:**
  1. Pipecat 0.0.107 установлен (openai, elevenlabs, silero, webrtc, daily extras)
  2. voice_pipecat.py — SmallWebRTC транспорт (НЕ РАБОТАЕТ — NAT блокирует ICE)
  3. Coturn TURN сервер установлен на 72.56.64.91:3478 (user: sofia / sofia2026turn) — не помог
  4. voice_pipecat_daily.py — Daily WebRTC транспорт
  5. Daily аккаунт: sofia-oazis.daily.co, домен настроен, карта привязана
  6. Pipeline работает: STT распознаёт → LLM генерирует → TTS озвучивает (подтверждено логами)
  7. Nginx: `/voice-v2/`, `/start`, `/sessions/` → порт 8082
- **Блокер:** ElevenLabs TTS — аудио генерируется (логи: "Generating TTS [Здравствуйте...]", TTFB 5-13с), но клиент НЕ слышит. Попытки: eleven_flash_v2_5 и eleven_multilingual_v2, с/без language="ru" — не помогло. Вероятная причина: аудио-фреймы не доходят от TTS до Daily transport output
- **ElevenLabs голоса:** Nastya (YjESejviApN7SHrbfnA2) НЕТ на аккаунте (была в Retell). Используется Victoria (FZGeNF7bE3syeQOynDKC), eleven_multilingual_v2
- **Файлы:** voice_pipecat.py, voice_pipecat_daily.py
- **Как откатить:** Просто остановить процесс, прод не затронут

---

## 25.03.2026 — Исследование голосового агента

- **Что сделано:** Полное исследование голосового стека: 8 направлений, 50+ решений.
- **Ключевые выводы:**
  - Целевой стек: Pipecat + Yandex SpeechKit + Groq/Qwen3-32B + gpt-4.1-mini + Задарма
  - gpt-4.1-mini: 0.7с TTFT, без reasoning overhead, 15x дешевле gpt-5.2
- **Файлы:** `docs/VOICE_RESEARCH_2026.md`

---

## 22.03.2026 — Битрикс в bot_server.py + таймауты + Тильда привязка

- **Что сделано:** core/bitrix.py подключён к bot_server.py, таймауты, привязка к лиду Тильды
- **Коммит:** 4214a17b (dev), задеплоен в прод 26.03.2026
- **Как откатить:** Восстановить из backups/20260326_0724/

---

## 21.03.2026 — SOFIA_PATH fix + полный деплой dev→prod + core/bitrix.py

- **Бэкап:** `/opt/sofia-gpt-backup-20260321_1355` (НЕ УДАЛЯТЬ)
- **Как откатить:** `cp -r /opt/sofia-gpt-backup-20260321_1355/* /opt/sofia-gpt/ && systemctl restart sofia-gpt sofia-web-api sofia-radist`

---

## 10.03.2026 — voice_api.py + voice_mode + stream_voice_response

- **Retell данные:** Agent `agent_d428a1d13067a563faf30a88bb`, голос Nastya
- **User ID формула voice:** `7_000_000 + (md5(call_id)[:8] as int % 1_000_000)`

---

## 09.03.2026 — core/pipeline.py + dev radist

- **core/pipeline.py** — единый пайплайн для всех каналов

---

## 08.03.2026 — Создание dev-окружения

- `/opt/sofia-gpt-dev/`, отдельная БД, systemd сервис
