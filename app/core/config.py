from datetime import date
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Retail Insight Agent"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:8501"

    llm_provider: str = "deepseek_anthropic"
    llm_model: str = "deepseek-v4-pro"
    llm_base_url: str = "https://api.deepseek.com/anthropic"
    llm_api_key: str = Field(default="", repr=False)

    langsmith_tracing: bool = False
    langsmith_api_key: str = Field(default="", repr=False)
    langsmith_project: str = "retail-insight-agent-dev"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_max_string_length: int = Field(default=2_000, ge=200, le=20_000)
    langsmith_policy_excerpt_length: int = Field(default=600, ge=100, le=5_000)

    # OCR is deliberately opt-in because scanned pages are sent to the configured
    # vision service only when native PDF text extraction has no usable result.
    ocr_enabled: bool = False
    ocr_provider: str = "qwen_openai_compatible"
    ocr_model: str = "qwen3.7-plus"
    ocr_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ocr_api_key: str = Field(default="", repr=False)
    ocr_max_pages: int = Field(default=20, ge=1, le=100)
    ocr_max_tokens: int = Field(default=2_000, ge=100, le=8_000)
    ocr_timeout_seconds: float = Field(default=60.0, gt=0, le=300)

    database_url: str = (
        "mysql+aiomysql://retail_readonly:readonly-local-dev@localhost:3307/retail_insight"
    )
    session_database_url: str = "sqlite+aiosqlite:///./data/runtime/sessions.db"
    history_result_rows: int = Field(default=100, ge=1, le=500)
    evaluation_runs_path: str = "./data/runtime/evaluation_runs"
    report_output_path: str = "./data/runtime/reports"
    report_tool_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    report_max_tool_calls: int = Field(default=2, ge=1, le=4)

    vector_store: str = "chroma"
    policy_documents_path: str = "./data/documents"
    vector_store_path: str = "./data/vector_store"
    lexical_corpus_path: str = "./data/runtime/bm25_corpus.json"
    model_cache_path: str = ""
    model_local_files_only: bool = False
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    rag_retrieval_top_k: int = 12
    rag_vector_top_k: int = 20
    rag_bm25_top_k: int = 20
    rag_rrf_k: int = 60
    rag_rerank_top_k: int = 5
    rag_min_relevance_score: float = 0.1

    max_sql_retries: int = 2
    max_result_rows: int = 500
    sql_query_timeout_seconds: int = 15
    data_as_of_date: date = date(2026, 6, 30)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def langsmith_enabled(self) -> bool:
        return self.langsmith_tracing and bool(self.langsmith_api_key)

    @property
    def ocr_available(self) -> bool:
        return self.ocr_enabled and bool(self.ocr_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
