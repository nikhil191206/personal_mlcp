"""Configuration loaded from environment variables / an ignored .env file."""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    databricks_host: str
    databricks_token: SecretStr
    databricks_catalog: str = "atlas_poc"
    databricks_schema: str = "default"
    databricks_volume: str = "data"

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.databricks_catalog}/{self.databricks_schema}/{self.databricks_volume}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
