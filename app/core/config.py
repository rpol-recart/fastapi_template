from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppSettings(BaseSettings):
    app_name: str = Field(default="fastapi-oracle-template", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=True, alias="LOG_JSON")

    oracle_user: str = Field(alias="ORACLE_USER")
    oracle_password: str = Field(alias="ORACLE_PASSWORD")
    oracle_dsn: str = Field(alias="ORACLE_DSN")
    oracle_pool_min: int = Field(default=1, alias="ORACLE_POOL_MIN")
    oracle_pool_max: int = Field(default=5, alias="ORACLE_POOL_MAX")
    oracle_pool_inc: int = Field(default=1, alias="ORACLE_POOL_INC")

    # Новые параметры отказоустойчивости
    oracle_retry_attempts: int = Field(default=2, alias="ORACLE_RETRY_ATTEMPTS")         # 2 повтора
    oracle_retry_delay_ms: int = Field(default=200, alias="ORACLE_RETRY_DELAY_MS")       # 200 мс между повторами

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")