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

    # Team contact address put in the User-Agent. Required by the Compliance Gate; no default on purpose.
    contact_email: str = ""

    # Folder inside the Volume that every path is placed under. Empty = the real (demo) location.
    # Developers set e.g. "dev/ragini" so test runs never touch the demo folders.
    atlas_path_prefix: str = ""

    @property
    def volume_root(self) -> str:
        root = f"/Volumes/{self.databricks_catalog}/{self.databricks_schema}/{self.databricks_volume}"
        prefix = self.atlas_path_prefix.strip("/")
        return f"{root}/{prefix}" if prefix else root


@lru_cache
def get_settings() -> Settings:
    return Settings()
