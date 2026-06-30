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
    # Optional Groq fallback. If GROQ_API_KEY is missing, the app stays Gemini-only.
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    # HTW Berlin IMAP mailbox (see app.services.imap_email_service)
    htw_email_address: str = ""
    htw_email_password: str = ""
    htw_imap_host: str = ""
    htw_imap_port: int = 993
    # Moodle Web Services (HTW). Token im Moodle unter Einstellungen → Sicherheitsschlüssel erstellen.
    moodle_url: str = "https://moodle.htw-berlin.de"
    moodle_token: str = ""
    moodle_user_id: str = ""
    # Stellensuche: Adzuna (kostenloser Key auf developer.adzuna.com) für echte Suche + Gehalt.
    # Ohne Key fällt der Job-Service auf Arbeitnow (frei, ohne Key) zurück.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "de"
    job_location: str = "Berlin"
    # App wird von Studierenden genutzt → standardmäßig nur Werkstudentenstellen.
    job_student_only: bool = True

    @property
    def gemini_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]


settings = Settings()
