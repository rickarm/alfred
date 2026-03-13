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


settings = Settings()
