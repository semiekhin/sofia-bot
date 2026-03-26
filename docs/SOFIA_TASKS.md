# Задачи Sofia-GPT

📅 Обновлено: 26.03.2026

## 🚀 P0 — Ближайшие

- [x] **Битрикс: ASSIGNED_BY_ID=428 (Sofia AI)** — ЗАДЕПЛОЕНО 26.03.2026. create_lead() ставит 428, restore_assigned() возвращает при завершении, 4 сценария покрыты
- [x] **Деплой bot_server.py + web_api.py + core/bitrix.py в прод** — ЗАДЕПЛОЕНО 26.03.2026. Бэкап: backups/20260326_0724/
- [x] **Битрикс только для source-сессий (ATL)** — _is_bitrix_session() проверяет source_object
- [ ] **Ссылка в Тильде** — URL успеха: `https://t.me/humanAINeural_bot?start=ATL`

## 🎙️ Голосовой агент

### Исследование ✅ ЗАВЕРШЕНО (25.03.2026)
- [x] Полное исследование: 8 направлений, 50+ решений → `docs/VOICE_RESEARCH_2026.md`
- [x] Целевой стек определён: Pipecat + Yandex SpeechKit + Groq/Qwen3 + gpt-4.1-mini + Задарма

### Вариант 1 — Быстрый ✅ ЗАВЕРШЁН (26.03.2026)
- [x] gpt-4.1-mini в stream_voice_response() (VOICE_MODEL константа)
- [x] Voice-specific prompt (VOICE_PROMPT_ADDON — 7 правил, без "всегда заканчивай вопросом")
- [x] RAG вернуть на 10 примеров (ChromaDB ~50ms)
- [x] Async Extractor после ответа (extract_sync + merge, не сбрасывает dialog_finished)
- [x] Post-stream проверка [END]
- [x] max_output_tokens: 800

### Вариант 2 — Pipecat (В ПРОЦЕССЕ)
- [x] Pipecat 0.0.107 установлен
- [x] voice_pipecat.py — SmallWebRTC бот (НЕ РАБОТАЕТ — NAT)
- [x] Coturn TURN сервер установлен (не помог с SmallWebRTC)
- [x] voice_pipecat_daily.py — Daily WebRTC бот
- [x] Daily аккаунт: sofia-oazis.daily.co, API key получен
- [x] Pipeline работает: STT → LLM → TTS (подтверждено логами)
- [ ] **БЛОКЕР: ElevenLabs TTS TTFB 5-13с** — клиент не слышит ответ
- [ ] Подключить наш pipeline (core/pipeline.py) к Pipecat
- [ ] Yandex SpeechKit STT (кастомный Pipecat процессор)
- [ ] Yandex SpeechKit TTS (вместо ElevenLabs)
- [ ] Задарма SIP телефония

### Retell AI (dev-only, Вариант 1)
- [x] voice_api.py — WebSocket адаптер
- [x] Оптимизация: gpt-4.1-mini, async Extractor, полный RAG

## ⚙️ Единое ядро ✅ ЗАДЕПЛОЕНО

- [x] core/pipeline.py — Analyzer → RAG → Generator
- [x] core/bitrix.py — Битрикс CRM + ASSIGNED_BY_ID=428
- [x] stream_voice_response() — voice Вариант 1
- [x] Деплой в прод — 21.03.2026 (core/), 26.03.2026 (bitrix + bot_server)

## 🔥 Технический долг

- [x] SOFIA_PATH баг — ПОЧИНЕН 21.03.2026
- [x] Bitrix в bot_server.py — ЗАДЕПЛОЕН 26.03.2026
- [x] Bitrix: ASSIGNED_BY_ID=428 — ЗАДЕПЛОЕН 26.03.2026
- [ ] Bitrix в radist_gateway.py — P1
- [ ] deploy.sh
- [ ] Очистка мусора в проде
- [ ] BUG-004 EN-раскладка
- [ ] core/channel.py, core/observer.py
