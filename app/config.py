"""
app/config.py - SAS - Symbiotic Autoprotection System v1.1.0
Autor: Gonzalo Emir Durante - TAD EX-2026-18792778

Centralized configuration for the FastAPI service.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ========================================================================
    # API Security
    # ========================================================================
    # No production default. Set this in Render or .env.
    admin_secret: str = ""

    # Enable only temporarily when debugging deployment headers.
    enable_debug_endpoints: bool = False

    # ========================================================================
    # Core Detection
    # ========================================================================
    kappa_d: float = 0.56
    scan_timeout_seconds: int = 30
    min_text_length: int = 30

    # ========================================================================
    # Database paths
    # ========================================================================
    auth_db_path: str = "data/auth.db"
    rate_limit_db_path: str = "data/rate_limit.db"

    # Metrics database
    metrics_db_path: str = "data/metrics.db"
    metrics_retention_days: int = 90

    # Legacy compatibility. Keep if older services still read DATABASE_URL.
    database_url: str = "sqlite:///./omni_scanner.db"

    # ========================================================================
    # Rate Limiting / Plans
    # ========================================================================
    free_requests_per_day: int = 50
    pro_requests_per_month: int = 10000
    team_requests_per_month: int = 50000

    # API key hashing
    api_key_hash_pepper: str = "sas-dev-pepper-change-me"

    # Shared legacy key kept only for smoke tests / old examples.
    # This key must NOT be treated as a normal production key.
    legacy_bootstrap_api_key: str = "sas_test_key_2026"
    legacy_requests_per_day: int = 200
    legacy_deprecation_message: str = (
        "This shared legacy key is limited to 200 requests/day. "
        "Request a personal free API key at "
        "https://sas-api.onrender.com/public/request-key"
    )

    # ========================================================================
    # Ollama / local LLM backend for /v1/chat
    # ========================================================================
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct-q4_K_M"
    ollama_timeout: int = 60

    # Legacy compatibility fields.
    ollama_url: str = ""
    ollama_models_url: str = "http://localhost:11434/api/tags"

    # ========================================================================
    # Extended Modules E9-E12
    # ========================================================================
    modules_enabled: str = "E9,E10,E11,E12"
    sas_fact_kb_path: str = ""
    sas_fact_kb_flag_unknown: bool = False
    sas_topic_shift_use_st: bool = False
    sas_topic_shift_model: str = "all-MiniLM-L6-v2"

    # ========================================================================
    # CORS
    # ========================================================================
    # For production, set this to your frontend domains, e.g.:
    # CORS_ALLOW_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
    cors_allow_origins: str = "*"

    # ========================================================================
    # Logging
    # ========================================================================
    log_level: str = "INFO"

    # ========================================================================
    # Public activity / landing page
    # ========================================================================
    public_anomaly_threshold: int = 5000

    # ========================================================================
    # Email alerts
    # ========================================================================
    email_alerts_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    alert_email_to: str = "duranteg2@gmail.com"

    # ========================================================================
    # Public onboarding email delivery
    # ========================================================================
    email_from: str = ""
    resend_api_key: str = ""
    sas_api_url: str = "https://sas-api.onrender.com"
    sas_public_url: str = "https://leesintheblindmonk1999.github.io/sas-landing/"

    # ========================================================================
    # Polar billing
    # ========================================================================
    polar_sandbox: bool = False
    polar_access_token: str = ""
    polar_product_id_pro: str = ""
    polar_webhook_secret: str = ""
    polar_success_url: str = (
        "https://leesintheblindmonk1999.github.io/sas-landing/?checkout=success"
    )
    polar_return_url: str = (
        "https://leesintheblindmonk1999.github.io/sas-landing/?checkout=cancel"
    )

    # ========================================================================
    # Mercado Pago billing
    # ========================================================================
    mercadopago_access_token: str = ""
    mercadopago_public_key: str = ""
    mercadopago_webhook_secret: str = ""
    mercadopago_success_url: str = (
        "https://leesintheblindmonk1999.github.io/sas-landing/?mp=success"
    )
    mercadopago_pending_url: str = (
        "https://leesintheblindmonk1999.github.io/sas-landing/?mp=pending"
    )
    mercadopago_failure_url: str = (
        "https://leesintheblindmonk1999.github.io/sas-landing/?mp=failure"
    )

    # ========================================================================
    # SAS Identity / Metadata
    # ========================================================================
    sas_name: str = "SAS - Symbiotic Autoprotection System"
    sas_version: str = "1.1.0"
    omni_version: str = "10.1"

    registry: str = "TAD EX-2026-18792778"
    sas_doi: str = "10.5281/zenodo.19702379"
    omni_scanner_doi: str = "10.5281/zenodo.19543972"

    # Legacy name kept so older code that reads settings.zenodo_doi still works.
    zenodo_doi: str = "10.5281/zenodo.19702379"

    repo_url: str = "https://github.com/Leesintheblindmonk1999/SAS"
    hosted_api: str = "https://sas-api.onrender.com"

    ledger_hash: str = (
        "5a434d7234fd55cb45829d539eee34a5ea05a3c594e26d76bb41695c46b2a996"
    )
    ots_date: str = "2026-04-11"
    ots_chain: str = "Bitcoin (OpenTimestamps)"

    # ========================================================================
    # Optional Routers
    # ========================================================================
    enable_external_audit: bool = False

    # ========================================================================
    # Pydantic configuration
    # ========================================================================
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ========================================================================
    # Properties / helpers
    # ========================================================================

    @property
    def enabled_modules(self) -> list[str]:
        """Return enabled thermic modules as normalized uppercase codes."""
        if not self.modules_enabled.strip():
            return []

        return [
            module.strip().upper()
            for module in self.modules_enabled.split(",")
            if module.strip()
        ]

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS_ALLOW_ORIGINS into a FastAPI-compatible list."""
        value = self.cors_allow_origins.strip()

        if value == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in value.split(",")
            if origin.strip()
        ]

    @property
    def ollama_api_url(self) -> str:
        """
        Resolve the Ollama chat endpoint.

        Priority:
        1. ollama_host + /api/chat
        2. legacy ollama_url
        3. localhost default
        """
        if self.ollama_host:
            base = self.ollama_host.rstrip("/")
            if base.endswith("/api/chat"):
                return base
            return f"{base}/api/chat"

        return self.ollama_url or "http://localhost:11434/api/chat"

    @property
    def ollama_tags_url(self) -> str:
        """Resolve the Ollama tags/models endpoint."""
        if self.ollama_host:
            base = self.ollama_host.rstrip("/")
            if base.endswith("/api/tags"):
                return base
            return f"{base}/api/tags"

        return self.ollama_models_url or "http://localhost:11434/api/tags"

    @property
    def has_admin_secret(self) -> bool:
        """Return True when an admin secret is configured."""
        return bool(self.admin_secret.strip())


settings = Settings()
