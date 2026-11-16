"""Application settings, loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

APP_NAME = "AGRI-SENSE"
APP_VERSION = "1.0.0"
SERVICE_ID = "agri-sense-api"
# backend/.env, regardless of the directory the server is started from.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    # Phase 2 wires this to Supabase Postgres. Empty means "not configured".
    database_url: str = ""

    # Supabase Auth. SUPABASE_URL enables JWKS (ES256/RS256) verification and issuer checks;
    # SUPABASE_JWT_SECRET additionally accepts legacy HS256 tokens. At least one is required.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    # Optional: where to fetch signing keys when the API reaches Supabase at a different address than the
    # token issuer (e.g. a container using host.docker.internal). Defaults to <issuer>/.well-known/jwks.json.
    supabase_jwks_url: str = ""

    # Sensor simulator (Phase 5). Generates readings for sensors with source='simulated'.
    simulator_enabled: bool = True
    simulator_interval_seconds: float = Field(default=10.0, ge=2, le=3600)

    # Automatic alerts (Phase 17): rules re-evaluated for every farm on this interval.
    alerts_enabled: bool = True
    alert_interval_seconds: float = Field(default=300.0, ge=10, le=86_400)

    # HTTP hardening (Phase 19). Limits are per process; see docs/SECURITY.md.
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=300, ge=10, le=100_000)
    rate_limit_expensive_per_minute: int = Field(default=20, ge=1, le=10_000)

    # Plant recognition (Phase 9): uploaded images are re-encoded (EXIF stripped) and kept here.
    upload_dir: Path = Path(__file__).resolve().parents[2] / "uploads"
    max_upload_mb: float = Field(default=8.0, gt=0, le=50)

    @property
    def auth_configured(self) -> bool:
        return bool(self.supabase_url.strip() or self.supabase_jwt_secret.strip())

    @property
    def auth_issuer(self) -> str | None:
        url = self.supabase_url.strip().rstrip("/")
        return f"{url}/auth/v1" if url else None

    @property
    def jwks_url(self) -> str | None:
        if self.supabase_jwks_url.strip():
            return self.supabase_jwks_url.strip()
        return f"{self.auth_issuer}/.well-known/jwks.json" if self.auth_issuer else None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip().rstrip("/") for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
