"""
Конфигурация Radist.Online API — мультиканальная версия
Обновлено: 30.01.2026
Каналы: Max, Telegram, WhatsApp (будет добавлен)
"""

import os

# ============================================
# API НАСТРОЙКИ
# ============================================

RADIST_API = {
    "api_url": "https://api-ru.radist.online/v2",
    "api_key": "-cCC1Lbcwc6Et-s8mClF8_qPkE7mNF35VmTVUoZEIKYAZurc_Oyjjf2AdXTHqjvWm8cMp_U6NzJD_xNzl4jOZA",
    "company_id": 205054,
}

# ============================================
# ПОДКЛЮЧЕНИЯ (КАНАЛЫ)
# ============================================

CHANNELS = {
    "max": {
        "connection_id": 80024,
        "name": "Софья Max",
        "phone": "+79284466701",
        "type": "max_personal",
        "enabled": True,
    },
    "telegram": {
        "connection_id": 80200,
        "name": "Софья Telegram",
        "phone": "+79181038493",
        "type": "telegram_personal",
        "enabled": True,
    },
    # WhatsApp будет добавлен позже
    # "whatsapp": {
    #     "connection_id": None,
    #     "name": "Софья WhatsApp",
    #     "phone": "+79...",
    #     "type": "whatsapp_personal",
    #     "enabled": False,
    # },
}

# Маппинг connection_id → channel name
CONNECTION_TO_CHANNEL = {
    80024: "max",
    80200: "telegram",
}

# ============================================
# DEV MODE
# ============================================
# True = логировать ответы, НЕ отправлять клиенту (dev получает те же webhook что прод)
DEV_MODE = os.getenv("RADIST_DEV_MODE", "false").lower() == "true"

# ============================================
# WEBHOOK НАСТРОЙКИ
# ============================================

WEBHOOK_CONFIG = {
    "port": 5002 if DEV_MODE else 5001,
    "path": "/webhook/radist",
}

# ============================================
# LEGACY (для совместимости)
# ============================================

RADIST_CONFIG = {
    "api_url": RADIST_API["api_url"],
    "api_key": RADIST_API["api_key"],
    "company_id": RADIST_API["company_id"],
    "connection_id": CHANNELS["max"]["connection_id"],  # default: Max
    "phone": CHANNELS["max"]["phone"],
    "webhook_port": WEBHOOK_CONFIG["port"],
    "webhook_path": WEBHOOK_CONFIG["path"],
}


# ============================================
# HELPER FUNCTIONS
# ============================================


def get_headers():
    """Возвращает заголовки для API запросов"""
    return {"X-Api-Key": RADIST_API["api_key"], "Content-Type": "application/json"}


def get_base_url():
    """Возвращает базовый URL с company_id"""
    return f"{RADIST_API['api_url']}/companies/{RADIST_API['company_id']}"


def get_channel_by_connection_id(connection_id: int) -> str:
    """Определяет канал по connection_id"""
    return CONNECTION_TO_CHANNEL.get(connection_id, "unknown")


def get_connection_id_by_channel(channel: str) -> int:
    """Получает connection_id по имени канала"""
    if channel in CHANNELS:
        return CHANNELS[channel]["connection_id"]
    return None
