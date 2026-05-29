from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    postgres_url: str
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()