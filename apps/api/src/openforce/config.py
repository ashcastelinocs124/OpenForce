from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_sync: str = ""
    openai_api_key: str
    openai_model: str = "gpt-4o"

    sf_client_id: str = ""
    sf_client_secret: str = ""
    sf_redirect_uri: str = "http://localhost:8000/auth/salesforce/callback"
    sf_login_url: str = "https://login.salesforce.com"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"

    app_secret: str = Field(min_length=16)
    log_level: str = "INFO"
    poll_interval_seconds: int = 300


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
