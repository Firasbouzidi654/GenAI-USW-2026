from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    gemini_api_key: str
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    postgres_url: str
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "documents"
    embedding_model: str = "gemini-embedding-001"
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150
    rag_top_k: int = 4
    # Paste the n8n Production Webhook URL here (see README for setup instructions)
    n8n_job_agent_webhook_url: str = ""
    # Comma-separated fallback chain, tried in order (see app.agents.base.run_with_model_fallback)
    gemini_models: str = (
        "gemini-2.5-flash,gemini-2.0-flash,gemini-2.0-flash-lite,"
        "gemini-1.5-flash,gemini-1.5-pro"
    )

    @property
    def gemini_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]


settings = Settings()
