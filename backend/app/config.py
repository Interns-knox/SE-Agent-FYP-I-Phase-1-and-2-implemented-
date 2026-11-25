from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Overridable development defaults. Real deployments set these via
    # environment variables or a .env file (see .env.example).
    DATABASE_URL: str = "postgresql+psycopg2://se_agent@localhost:5432/se_agent"
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    LLM_PROVIDER: str = "ollama"
    # Comma-separated browser origins allowed to call the API.
    CORS_ORIGINS: str = "http://localhost:5173"
    # Seconds to wait for one LLM call. Requirements and diagrams are much larger than features.
    LLM_TIMEOUT_SECONDS: float = 60.0
    # PlantUML executable used to check UML syntax and render diagrams locally.
    PLANTUML_COMMAND: str = "plantuml"
    # Optional Ollama context window (tokens). Artifact prompts are long and the Ollama
    # default (often 4096) can truncate them silently. None keeps Ollama's default.
    OLLAMA_NUM_CTX: int | None = None
    # Set false to disable Qwen3 'thinking' output (much faster; None keeps Ollama's default).
    OLLAMA_THINK: bool | None = None

    # `.env` in backend/ or in the repository root (the root file is read first, backend/ wins)
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


settings = Settings()
