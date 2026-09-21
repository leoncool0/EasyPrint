"""
EasyPrint Client Configuration
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # App Info
    APP_NAME: str = "EasyPrint Client"
    APP_VERSION: str = "0.1.3"
    DEBUG: bool = True

    # Server Connection
    SERVER_HOST: str = "10.1.2.110"
    SERVER_TCP_PORT: int = 9100
    SERVER_HTTP_PORT: int = 8080

    # Device Info
    DEVICE_NAME: str = ""
    DEVICE_TYPE: str = "user"  # host, user, mixed
    DEVICE_ID: str = ""

    # Auth
    TOKEN: str = ""

    # Paths
    CONFIG_DIR: Path = Path("./config")
    CACHE_DIR: Path = Path("./cache")
    LOGS_DIR: Path = Path("./logs")

    # Network
    RECONNECT_INTERVAL: int = 5  # seconds
    HEARTBEAT_INTERVAL: int = 30  # seconds
    CHUNK_SIZE: int = 64 * 1024  # 64KB

    # UI
    SHOW_TRAY_ICON: bool = True
    START_WITH_SYSTEM: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()

# Ensure directories exist
settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)