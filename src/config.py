from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    things_agent_api_key: str
    things_mcp_url: str = "http://127.0.0.1:8100/mcp"
    things_agent_host: str = "0.0.0.0"
    things_agent_port: int = 8200

    # Bot settings
    telegram_bot_token: str = ""
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    things_agent_base_url: str = "http://127.0.0.1:8200/api/v1"

    # Sherlock-HQ integration
    sherlock_hq_url: str = "http://127.0.0.1:8300"
    sherlock_dashboard_token: str = ""
    rick_chat_id: int = 0


settings = Settings()
