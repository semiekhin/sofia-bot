# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 10.02.2026 (ночь)

## ✅ Что сделано

### Web API для чат-виджета — ЗАДЕПЛОЕН И РАБОТАЕТ
- Создан `web_api.py` — FastAPI сервер (порт 8080, systemd: sofia-web-api)
- Тот же пайплайн: process_message() → Analyzer → RAG → Generator
- Веб-юзеры получают user_id в диапазоне 9M+ (не пересекаются с Telegram)
- Общая БД с Telegram-ботом (sofia_gpt.db)
- CORS настроен для atlantis-invest.ru

### DNS + SSL для API
- A-запись: `api.atlantis-invest.ru` → `72.56.64.91` (reg.ru)
- Nginx reverse proxy → localhost:8080
- Let's Encrypt SSL (до 10.05.2026, автообновление certbot)
- Endpoint: `https://api.atlantis-invest.ru/api/chat`

### Виджет на сайте — ПОДКЛЮЧЁН К РЕАЛЬНОЙ СОФЬЕ
- Обновлён `<script>` блок в index.html на atlantis-invest.ru
- Заглушка getDemoResponse() заменена на fetch() к API
- Fallback: если API недоступен — работают демо-ответы
- Сессии хранятся в sessionStorage браузера

### Закоммичено и запушено
- `web_api.py` → GitHub (коммит 157ed909)

## 🐛 BUG-004: повторный вопрос при смене раскладки

**Проблема:** Клиент написал "lkz bydtcnbwbq" (= "для инвестиций" в EN-раскладке). Generator понял и ответил "Поняла, для инвестиций". Но Extractor НЕ распознал → goal не записался в state → Generator переспросил.

**Причина:** Generator и Extractor — независимые LLM-вызовы. Generator понимает контекст шире, Extractor парсит буквально.

**Решения:**
- (А) Автоконверсия EN→RU раскладки перед Extractor
- (Б) Extractor учитывает что Generator уже подтвердил факт

**Статус:** НЕ ИСПРАВЛЕН

## 🔄 Текущее состояние

### ✅ Работает
- Бот Sofia v3.0 (Eva) — Telegram @humanAINeural_bot
- Web API — `https://api.atlantis-invest.ru` (systemd: sofia-web-api)
- Виджет на сайте — atlantis-invest.ru
- SSL — сайт и API
- RAG — 2001 пример

### ❌ Не работает
- Max канал — ЗАБАНЕН

### ⏳ Ожидает
- WABA — не подключен
- Битрикс endpoint — не создан
- Планировки на сайте — нужны изображения
- Сессии web_api — в памяти, при рестарте теряются

## 🔜 Следующие шаги
1. **BUG-004** — повторный вопрос при EN-раскладке
2. **WABA подключение** — SIM, 360Dialog, шаблон
3. **Битрикс endpoint** — /api/bitrix/lead
4. **Планировки** — реальные изображения на сайт
5. **Persistence сессий** — web_api сессии в SQLite

## 📁 Последние изменения
- `web_api.py` — NEW: FastAPI сервер для виджета
- `index.html` (reg.ru) — виджет подключён к API
- `/etc/nginx/sites-available/sofia-api` — reverse proxy
- `/etc/systemd/system/sofia-web-api.service` — systemd сервис

## 🚀 Команды
```bash
# Web API
systemctl status sofia-web-api
systemctl restart sofia-web-api
tail -f /opt/sofia-gpt/web_api.log

# Основной бот
systemctl status sofia-radist

# Nginx
systemctl status nginx

# Тест API
curl -s https://api.atlantis-invest.ru/api/health
```
