from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://networkwatcher:networkwatcher@localhost:5432/networkwatcher"
    secret_key: str = "change-me"


settings = Settings()
