"""Application settings loaded from environment variables / .env.

Every external integration has a ``mock`` mode so the whole pipeline can run
before IT grants real Microsoft 365 / Azure access (plan §10).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- runtime -------------------------------------------------------
    environment: Literal["development", "test", "demo", "production"] = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'dev.db'}"
    redis_url: str = "redis://localhost:6379/0"
    queue_mode: Literal["rq", "thread", "sync"] = "sync"
    storage_dir: Path = BACKEND_DIR / "storage"
    samples_dir: Path = REPO_DIR / "samples"
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = ""  # e.g. ^https://ai-meeting[a-z0-9-]*\.vercel\.app$ (Vercel previews)
    public_api_base: str = "http://localhost:8000"
    public_web_base: str = "http://localhost:3000"

    # --- provider switches ---------------------------------------------
    auth_mode: Literal["mock", "entra"] = "mock"
    graph_mode: Literal["mock", "real"] = "mock"
    stt_provider: Literal["mock", "azure", "gemini"] = "mock"
    summarizer: Literal["mock", "azure_openai", "gemini"] = "mock"

    # --- Microsoft Entra ID --------------------------------------------
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""  # App Registration of this backend API
    entra_api_client_secret: str = ""  # used only for On-Behalf-Of; keep in Key Vault
    entra_api_audience: str = ""  # defaults to api://<client id>
    entra_approver_role: str = ""  # optional app role required to approve MoM
    graph_scopes_sharepoint_read: str = "https://graph.microsoft.com/Files.Read.All"
    graph_scopes_sharepoint_write: str = "https://graph.microsoft.com/Files.ReadWrite.All"
    graph_scopes_teams_read: str = (
        "https://graph.microsoft.com/Chat.ReadBasic https://graph.microsoft.com/ChatMember.Read"
    )
    graph_scopes_teams_send: str = (
        "https://graph.microsoft.com/ChatMessage.Send https://graph.microsoft.com/Chat.Read"
    )

    # --- SharePoint -----------------------------------------------------
    sharepoint_allowed_site_ids: str = ""  # comma separated full site ids
    sharepoint_report_drive_id: str = ""  # empty = same drive as the source audio
    sharepoint_report_folder: str = "MeetingReports"

    # --- Azure AI Speech ------------------------------------------------
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_endpoint: str = ""  # optional custom domain / private endpoint
    azure_speech_api_version: str = "2024-11-15"
    stt_chunk_seconds: int = 1800

    # --- Summarisation --------------------------------------------------
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite"  # summariser; comma list = fallback order
    gemini_stt_model: str = "gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite"  # must accept audio input
    gemini_stt_chunk_seconds: int = 600  # shorter chunks = more accurate timestamps, small inline payloads
    summary_chunk_chars: int = 12000
    llm_timeout_seconds: int = 120

    # --- limits & policy ------------------------------------------------
    max_upload_mb: int = 300
    max_audio_minutes: int = 180
    temp_audio_retention_hours: int = 24
    rate_limit_per_minute: int = 20
    docx_font: str = "Tahoma"
    display_timezone: str = "Asia/Bangkok"
    default_language: str = "th-TH"

    dev_mock_users: list[str] = Field(default_factory=lambda: ["dev-user", "other-user"])

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        """Hosting providers (e.g. Render) hand out postgres:// URLs; SQLAlchemy needs the driver name."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_site_ids(self) -> list[str]:
        return [s.strip() for s in self.sharepoint_allowed_site_ids.split(",") if s.strip()]

    @property
    def api_audience(self) -> str:
        return self.entra_api_audience or f"api://{self.entra_api_client_id}"

    def ensure_dirs(self) -> None:
        for sub in ("audio", "reports", "mock_sharepoint", "mock_teams"):
            (self.storage_dir / sub).mkdir(parents=True, exist_ok=True)


SUPPORTED_LANGUAGES = {
    "th-TH": "ไทย",
    "en-US": "English",
    "th-TH+en-US": "ไทยปนอังกฤษ",
}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
