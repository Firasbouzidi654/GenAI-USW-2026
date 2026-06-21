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
    # Moodle Web Services (HTW). Token im Moodle unter Einstellungen → Sicherheitsschlüssel erstellen.
    moodle_url: str = "https://moodle.htw-berlin.de"
    moodle_token: str = ""
    # Stellensuche: Adzuna (kostenloser Key auf developer.adzuna.com) für echte Suche + Gehalt.
    # Ohne Key fällt der Job-Service auf Arbeitnow (frei, ohne Key) zurück.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "de"
    job_location: str = "Berlin"
    # App wird von Studierenden genutzt → standardmäßig nur Werkstudentenstellen.
    job_student_only: bool = True


settings = Settings()
