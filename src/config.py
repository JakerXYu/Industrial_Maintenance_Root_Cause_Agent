"""Application configuration.

Settings are read from environment variables; secrets are never hard-coded and
never printed. Phase 0 uses this only to establish the config/secret boundary.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    project_name: str = "industrial-maintenance-agent"

    data_dir: Path = Path("data")
    db_path: Path = Path("data") / "industrial.db"
    traces_dir: Path = Path("traces")

    llm_model: str = "deepseek-chat"
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[SecretStr] = Field(default=None, repr=False)

    default_work_order_lookup_days: int = Field(default=30, ge=1, le=365)

    @classmethod
    def from_env(cls) -> "Settings":
        def _path(key: str, default: Path) -> Path:
            value = os.getenv(key)
            return Path(value) if value else default

        api_key = os.getenv("LLM_API_KEY")
        return cls(
            project_name=os.getenv("PROJECT_NAME", "industrial-maintenance-agent"),
            data_dir=_path("DATA_DIR", Path("data")),
            db_path=_path("DB_PATH", Path("data") / "industrial.db"),
            traces_dir=_path("TRACES_DIR", Path("traces")),
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_api_key=SecretStr(api_key) if api_key else None,
            default_work_order_lookup_days=int(
                os.getenv("DEFAULT_WORK_ORDER_LOOKUP_DAYS", "30")
            ),
        )


@lru_cache(maxsize=None)
def get_settings() -> Settings:
    return Settings.from_env()
