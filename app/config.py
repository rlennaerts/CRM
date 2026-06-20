from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/crm_hub"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    app_env: str = "development"

    vwe_base_url: str = "https://mijn.vwe.nl"
    vwe_username: str = ""
    vwe_password: str = ""

    gaston_export_dir: str = "/data/imports/gaston"
    sam_export_dir: str = "/data/imports/sam"

    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    notify_email: Optional[str] = None

    vwe_sync_interval: int = 30
    gaston_sync_interval: int = 15
    sam_sync_interval: int = 15

    class Config:
        env_file = ".env"


settings = Settings()
