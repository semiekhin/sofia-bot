# Задачи Sofia-GPT

📅 Обновлено: 25.02.2026

## ✅ Выполнено
- [x] BUG-005: greeting сохраняется в историю (13.02)
- [x] Битрикс CRM webhook при [END] (13.02)
- [x] Веб-стратегия: 3 вопроса + контакт + вовлечение (13.02)
- [x] Актуальные цены Атлантиса в промпте (15.02)
- [x] finance_data.json — ЦБ 15.5% (15.02)
- [x] Финансовая экспертиза в промпте (15.02)
- [x] Виджет на invest-apartmens.online/atlantis (15.02)
- [x] Web API + observer для web-канала
- [x] CORS для atlantis-invest.ru, sochiremstroy.tilda.ws, invest-apartmens.online
- [x] Dynamic greeting по page_url
- [x] Виджет v2 (localStorage) установлен на всех 3 сайтах (16.02)
- [x] web_sessions + /api/session/resume (16.02)
- [x] "@username" → "ник в Telegram" в промпте (17.02)
- [x] SOFIA_PROJECT_MAP.md — полная карта проекта с аудитом (16-17.02)
- [x] Реструктуризация документации 85→29 КБ (18.02)
- [x] Новая стратегия продаж: цены только через контакт (25.02)
- [x] Проценты вместо рублей в промпте (25.02)
- [x] Выбор Telegram/звонок при сборе контакта (25.02)
- [x] @username убран из промпта повторно (25.02)
- [x] Смена OpenAI API ключа (25.02)
- [x] sofia-bot.service отключён, дубль устранён (25.02)
- [x] /api/docs/file — эндпоинт Claude-оркестратора (25.02)

## 🔥 Приоритет (следующая сессия)
1. Битрикс ASSIGNED_BY_ID: 426 → 24932 (ждём подтверждение программиста)
2. BUG-004: EN-layout текст ломает Extractor (Generator понимает, Extractor — нет)

## 📛 Бэклог
- Унификация generate_response() — архдолг P0 (3 копии в bot_server, radist_gateway, web_api)
- Голосовые звонки (Vapi.ai / Voximplant)
- Расширение виджета на новые сайты
- Cold lead актуализация (стратегия реактивации)

## 🔴 Выявлено аудитом (16-17.02) + сессия 25.02
- [ ] **P1:** Bitrix в bot_server.py и radist_gateway — лиды теряются
- [ ] **P1:** radist_gateway history limit 8→100 — контекст теряется
- [ ] **P2:** sofia_prompt_v2 ставка ЦБ ~16% → 15.5%
- [ ] **P2:** Оптимизация скорости: стриминг Generator, облегчение Analyzer (17-24с → цель <12с)
- [ ] **P3:** Мёртвый импорт sofia_prompt v1 в radist_gateway

## 📊 Замер скорости (25.02)
- Extractor: 6.4с (АН Эва: 5.0с)
- Analyzer: 5.4с (АН Эва: 2.3с) ← узкое место
- RAG: 2.8с (АН Эва: 2.6с)
- Generator: 9.2с полный / нет стриминга (АН Эва: 0.6с первый токен)
- Итого: 17-24с (АН Эва: 11с)
