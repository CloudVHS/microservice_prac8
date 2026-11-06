from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    service_name: str = 'user'
    database_url: str = 'sqlite:///./data/user.db'
    amqp_url: str = ''
    auth_secret: str = 'pr7-local-development-secret-change-before-deploy'
    internal_token: str = 'pr7-local-service-token'
    demo_admin_password: str = 'Admin-pr7-2026!'
    user_url: str = 'http://user:8000'
    dictionary_url: str = 'http://dictionary:8000'
    payment_url: str = 'http://payment:8000'
    token_ttl_seconds: int = 3600


@lru_cache
def settings() -> Settings:
    return Settings()
