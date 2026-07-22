"""
EasyPrint Server Configuration
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Server
    APP_NAME: str = "EasyPrint Server"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # HTTP API
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8080

    # TCP Gateway
    TCP_HOST: str = "0.0.0.0"
    TCP_PORT: int = 9100

    # UDP Discovery
    UDP_PORT: int = 20000

    # Database (use absolute path in Docker)
    DATABASE_URL: str = "sqlite+aiosqlite:////app/data/easyprint.db"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24

    # Paths (use absolute path in Docker)
    DATA_DIR: Path = Path("/app/data")
    LOGS_DIR: Path = Path("/app/logs")

    # Limits
    MAX_CONNECTIONS: int = 1000
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    CHUNK_SIZE: int = 64 * 1024  # 64KB

    # Heartbeat
    HEARTBEAT_INTERVAL: int = 30  # seconds
    HEARTBEAT_TIMEOUT: int = 90  # seconds (3 missed heartbeats)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)