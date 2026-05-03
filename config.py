from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # OpenAI / LLM
    OPENAI_API_KEY: str = "sk-placeholder"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536
    llm_system_prompt_path: str = "./app/prompts/system_prompt.txt"

    # Mock mode — set to False when you have OpenAI credits
    LLM_MOCK_MODE: bool = True

    # Database
    DATABASE_URL: str = "postgresql://erp_guide:erp_guide_pass@localhost:5432/erp_guide"
    PGVECTOR_ENABLED: bool = True

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 3600
    CACHE_ENABLED: bool = True

    # App
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Knowledge Base
    ROUTE_REGISTRY_PATH: str = "./app/data/route_registry.json"
    PROCESS_GRAPHS_PATH: str = "./app/data/process_graphs.json"
    DOCS_DIR: str = "./app/data/sample_docs"
    CHUNK_SIZE_TOKENS: int = 500
    CHUNK_OVERLAP_TOKENS: int = 50
    SEMANTIC_SEARCH_TOP_K: int = 5

    # LLM Settings
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
