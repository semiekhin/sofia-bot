# Установка виджета Софии

## Файл
`sofia-widget.html` — автономный сниппет (CSS + HTML + JS в одном файле)

## API
`https://api.atlantis-invest.ru/api` (nginx → порт 8080 → web_api.py)

## Ключевой параметр
`page_url: window.location.href` — передаётся при создании сессии.
Если URL содержит "atlantis" → dynamic greeting + контекст Атлантиса.

## CORS (разрешённые домены в web_api.py)
- atlantis-invest.ru (и www)
- sochiremstroy.tilda.ws
- invest-apartmens.online
- localhost:3000, 127.0.0.1:5500 (дев)

## Установка на сайт
Вставить содержимое `sofia-widget.html` перед `</body>` на странице.

### Для Тильды
Настройки сайта → Ещё → HTML-код → вставить перед </body>

### Для обычного сайта
Скопировать код в HTML страницы перед </body>

## Где установлен
- ✅ atlantis-invest.ru — виджет встроен в index.html (не сниппет)
- ✅ sochiremstroy.tilda.ws — сниппет через настройки Тильды  
- ✅ invest-apartmens.online/atlantis — сниппет передан заказчику

## Кнопки на сайте
Сайт atlantis-invest.ru имеет кнопки с `onclick="openChat('...')"`:
- "Обсудить с Софьей"
- "Узнать стоимость" (по каждой планировке)
- "Получить расчёт окупаемости"
- "Рассчитать доходность"
Они открывают чат и автоматически отправляют первое сообщение.

## Виджет v2 (обновлено 16.02.2026)

### localStorage persistence
- При создании сессии → `localStorage.setItem('sofia_session_id', id)`
- При открытии → проверяет localStorage → если есть → `POST /api/session/resume`
- Если сессия не найдена → очищает localStorage, создаёт новую
- Переживает: перезагрузку, закрытие вкладки, закрытие браузера
- Очищается только при ручной очистке данных сайта или инкогнито

### Эндпоинт resume
`POST /api/session/resume` — возвращает историю (до 50 сообщений)
Серверная часть: web_sessions таблица в SQLite (стабильный user_id через автоинкремент)
