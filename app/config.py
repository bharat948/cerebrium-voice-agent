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
    twilio_account_sid: str = ''
    twilio_auth_token: str = ''
    twilio_phone_number: str = ''
    twilio_validate_signatures: bool = True
    twilio_allow_inbound: bool = True
    allowed_outbound_numbers: str = ''
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o-mini'
    openai_max_output_tokens: int = 220
    deepgram_api_key: str = ''
    deepgram_stt_model: str = 'nova-3'
    deepgram_tts_model: str = 'aura-2-thalia-en'
    max_call_seconds: int = 300
    max_concurrent_calls: int = 2
    max_calls_per_hour: int = 10
    transcript_retention_days: int = 30

    @property
    def outbound_allowlist(self) -> set[str]:
        return {n.strip() for n in self.allowed_outbound_numbers.split(',') if n.strip()}

    @property
    def base_url(self) -> str:
        return self.public_base_url.rstrip('/')

    def ready_for_calls(self) -> bool:
        return bool(self.base_url.startswith('https://') and self.twilio_account_sid and self.twilio_auth_token
                    and self.twilio_phone_number and self.openai_api_key and self.deepgram_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
