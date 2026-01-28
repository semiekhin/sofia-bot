"""
Конфигурация Radist.Online API для Max мессенджера
Настроено: 28.01.2026
"""

RADIST_CONFIG = {
    # API
    "api_url": "https://api-ru.radist.online/v2",
    "api_key": "-cCC1Lbcwc6Et-s8mClF8_qPkE7mNF35VmTVUoZEIKYAZurc_Oyjjf2AdXTHqjvWm8cMp_U6NzJD_xNzl4jOZA",
    
    # Company & Connection
    "company_id": 205054,
    "connection_id": 80024,
    
    # Max account
    "phone": "+79284466701",
    "user_id": "174742776",
    "radist_token": "b7615c82-9aeb-42a0-ae98-8eb62021890b",
    
    # Webhook (TODO: настроить)
    "webhook_port": 5001,
    "webhook_path": "/webhook/radist",
}


def get_headers():
    """Возвращает заголовки для API запросов"""
    return {
        "X-Api-Key": RADIST_CONFIG["api_key"],
        "Content-Type": "application/json"
    }


def get_base_url():
    """Возвращает базовый URL с company_id"""
    return f"{RADIST_CONFIG['api_url']}/companies/{RADIST_CONFIG['company_id']}"
