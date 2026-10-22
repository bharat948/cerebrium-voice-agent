from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    app_name: str = 'Voice Foundry'
    app_env: str = 'development'
    app_api_key: str = 'dev-local-only-change-me'
    demo_mode: bool = True
    public_base_url: str = ''
    db_path: str = '/data/voice_foundry.db'
    database_url: str = ''
    auth_mode: str = 'api_key'  # google or api_key; production should use google
    google_client_id: str = ''
    google_client_secret: str = ''
    google_owner_sub: str = ''
    session_secret: str = ''
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    enable_background_worker: bool = True
    worker_poll_seconds: int = 10
    brave_search_api_key: str = ''
    twilio_account_sid: str = ''
    twilio_auth_token: str = ''
    twilio_phone_number: str = ''
    twilio_validate_signatures: bool = True
    twilio_allow_inbound: bool = True
    allowed_outbound_numbers: str = ''
    owner_phone: str = ''
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o-mini'
    # Selectable per call. Existing deployments without VOICE_ENGINE automatically use Live.
    voice_engine: str = 'openai_live'
    openai_live_model: str = 'gpt-live-1'
    openai_live_voice: str = 'marin'
    openai_live_backend_model: str = 'gpt-4o-mini'
    # Optional explicit fallback for recoverable Responses configuration errors.
    # Empty preserves model selection; never switch models without configuration.
    openai_live_fallback_backend_model: str = ''
    live_barge_in_rms: int = 900
    live_barge_in_frames: int = 5
    openai_max_output_tokens: int = 220
    deepgram_api_key: str = ''
    deepgram_stt_model: str = 'nova-3'
    deepgram_tts_model: str = 'aura-2-thalia-en'
    max_call_seconds: int = 300
    max_concurrent_calls: int = 2
    max_calls_per_hour: int = 10
    transcript_retention_days: int = 30
    integration_encryption_key: str = ''
    monthly_budget_usd: float = 15.0
    agent_monthly_budget_usd: float = 5.0
    enable_postcall_processor: bool = True
    google_import_enabled: bool = False
    twelve_data_api_key: str = ''

    @property
    def outbound_allowlist(self) -> set[str]:
        return {n.strip() for n in self.allowed_outbound_numbers.split(',') if n.strip()}

    @property
    def base_url(self) -> str:
        return self.public_base_url.rstrip('/')

    def ready_for_calls(self, engine: str | None = None) -> bool:
        engine = engine or self.voice_engine
        transport = bool(self.base_url.startswith('https://') and self.twilio_account_sid
                         and self.twilio_auth_token and self.twilio_phone_number)
        if engine == 'openai_live':
            return transport and bool(self.openai_api_key)
        if engine == 'deepgram':
            return transport and bool(self.openai_api_key and self.deepgram_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
