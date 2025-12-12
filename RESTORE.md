# Sofia Bot — Восстановление

## Быстрый старт (5 минут)

### 1. Подключение
```bash
ssh -p 2222 root@72.56.64.91
cd /opt/sofia-bot
```

### 2. Если бот упал
```bash
systemctl restart sofia-bot
journalctl -u sofia-bot -f
```

### 3. Если промпт сломался
```bash
# Смотрим бэкапы
ls -la backups/

# Откатываем на последний рабочий
cp backups/sofia_prompt_XXXXXXXX_XXXXXX.py sofia_prompt.py
systemctl restart sofia-bot
```

---

## Полное восстановление (30 минут)

### 1. Новый сервер
```bash
apt update && apt install -y python3-venv python3-pip git ufw fail2ban
```

### 2. Клонировать
```bash
cd /opt
git clone git@github.com:USERNAME/sofia-bot.git sofia-bot
cd sofia-bot
```

### 3. Секреты
```bash
cat > .env << 'ENVEOF'
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=512319063
ENVEOF
chmod 600 .env
```

### 4. Зависимости
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Systemd
```bash
cat > /etc/systemd/system/sofia-bot.service << 'SVCEOF'
[Unit]
Description=Sofia Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sofia-bot
ExecStart=/opt/sofia-bot/venv/bin/python bot_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable sofia-bot
systemctl start sofia-bot
```

### 6. Cron
```bash
crontab -e
# Добавить:
0 22 * * * cd /opt/sofia-bot && export $(cat .env | xargs) && python3 sofia_analyzer.py >> analyzer.log 2>&1
```

### 7. Проверка
```bash
systemctl status sofia-bot
python3 prompt_health.py
```
