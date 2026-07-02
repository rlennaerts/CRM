from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///crm_hub.db"
    secret_key: str = "change-me"
    app_env: str = "development"

    vwe_base_url: str = "https://mijn.vwe.nl"
    vwe_username: str = ""
    vwe_password: str = ""

    gaston_export_dir: str = "imports/gaston"
    sam_export_dir: str = "imports/sam"

    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    notify_email: Optional[str] = None

    host: str = "127.0.0.1"
    port: int = 8000

    vwe_sync_interval: int = 30
    gaston_sync_interval: int = 15
    sam_sync_interval: int = 15

    # Toegestane origins voor de Sales Portal (komma-gescheiden).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    class Config:
        env_file = ".env"


settings = Settings()
