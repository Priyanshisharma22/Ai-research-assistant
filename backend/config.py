from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    mistral_api_key: str = ""        # ← add this
    tavily_api_key: str = ""         # ← add this
    hf_token: str = ""               # ← add this too (you have it in .env)
    redis_url: str = "redis://localhost:6379"
    chroma_persist_dir: str = "./chroma_db"
    upload_dir: str = "./uploads"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()