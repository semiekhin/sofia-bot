#!/bin/bash
# switch_system.sh — Переключение между системами Sofia Bot
# Использование: ./switch_system.sh [hybrid|legacy]

set -e

HYBRID_DIR="/opt/sofia-hybrid"
LEGACY_DIR="/opt/sofia-bot"
ACTIVE_LINK="/opt/sofia-active"
SERVICE_NAME="sofia-bot"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_status() {
    echo ""
    echo "=== Текущий статус ==="
    
    if [ -L "$ACTIVE_LINK" ]; then
        CURRENT=$(readlink "$ACTIVE_LINK")
        if [[ "$CURRENT" == *"hybrid"* ]]; then
            echo -e "Активная система: ${GREEN}HYBRID${NC}"
        else
            echo -e "Активная система: ${YELLOW}LEGACY${NC}"
        fi
    else
        echo -e "Активная система: ${RED}НЕ НАСТРОЕНА${NC}"
    fi
    
    echo ""
    systemctl status $SERVICE_NAME --no-pager | head -5
    echo ""
}

switch_to_hybrid() {
    log_info "Переключение на HYBRID систему..."
    
    # Проверяем наличие файлов
    if [ ! -f "$HYBRID_DIR/bot_server_hybrid.py" ]; then
        log_error "Файлы гибридной системы не найдены в $HYBRID_DIR"
        exit 1
    fi
    
    # Останавливаем сервис
    log_info "Останавливаем сервис..."
    systemctl stop $SERVICE_NAME || true
    
    # Обновляем симлинк
    rm -f "$ACTIVE_LINK"
    ln -s "$HYBRID_DIR" "$ACTIVE_LINK"
    
    # Обновляем systemd сервис
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Sofia Bot (Hybrid)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$HYBRID_DIR
EnvironmentFile=/opt/sofia-bot/.env
ExecStart=/usr/bin/python3 $HYBRID_DIR/bot_server_hybrid.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Перезапускаем
    systemctl daemon-reload
    systemctl start $SERVICE_NAME
    
    log_info "Переключено на HYBRID систему"
    show_status
}

switch_to_legacy() {
    log_info "Переключение на LEGACY систему..."
    
    # Проверяем наличие файлов
    if [ ! -f "$LEGACY_DIR/bot_server.py" ]; then
        log_error "Файлы legacy системы не найдены в $LEGACY_DIR"
        exit 1
    fi
    
    # Останавливаем сервис
    log_info "Останавливаем сервис..."
    systemctl stop $SERVICE_NAME || true
    
    # Обновляем симлинк
    rm -f "$ACTIVE_LINK"
    ln -s "$LEGACY_DIR" "$ACTIVE_LINK"
    
    # Обновляем systemd сервис
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Sofia Bot (Legacy)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$LEGACY_DIR
EnvironmentFile=$LEGACY_DIR/.env
ExecStart=/usr/bin/python3 $LEGACY_DIR/bot_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Перезапускаем
    systemctl daemon-reload
    systemctl start $SERVICE_NAME
    
    log_info "Переключено на LEGACY систему"
    show_status
}

# Главная логика
case "$1" in
    hybrid)
        switch_to_hybrid
        ;;
    legacy)
        switch_to_legacy
        ;;
    status)
        show_status
        ;;
    *)
        echo "Использование: $0 {hybrid|legacy|status}"
        echo ""
        echo "  hybrid  - Переключить на гибридную систему (код + LLM)"
        echo "  legacy  - Переключить на старую систему (только LLM)"
        echo "  status  - Показать текущий статус"
        echo ""
        show_status
        exit 1
        ;;
esac
