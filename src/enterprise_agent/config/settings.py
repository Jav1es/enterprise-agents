"""应用配置 — pydantic-settings 环境变量读取。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置（从环境变量 / .env 读取）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    api_port: int = Field(default=8080, alias="API_PORT")

    # LLM
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.openai.com/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    llm_fallback_models: str = Field(default="qwen-max,deepseek-chat", alias="LLM_FALLBACK_MODELS")
    llm_max_calls: int = Field(default=10, alias="LLM_MAX_CALLS")

    # 记忆层
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_short_term_ttl: int = Field(default=1800, alias="REDIS_SHORT_TERM_TTL")
    database_url: str = Field(default="", alias="DATABASE_URL")

    # 知识层
    vector_store: str = Field(default="chroma", alias="VECTOR_STORE")
    chroma_persist_dir: str = Field(default="./data/chroma", alias="CHROMA_PERSIST_DIR")
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL")
    reranker_model: str = Field(default="BAAI/bge-reranker-base", alias="RERANKER_MODEL")

    # 接入层
    dingtalk_app_key: str = Field(default="", alias="DINGTALK_APP_KEY")
    dingtalk_app_secret: str = Field(default="", alias="DINGTALK_APP_SECRET")
    wecom_corp_id: str = Field(default="", alias="WECOM_CORP_ID")
    wecom_agent_id: str = Field(default="", alias="WECOM_AGENT_ID")
    wecom_secret: str = Field(default="", alias="WECOM_SECRET")

    # API 安全
    api_key: str = Field(default="", alias="API_KEY")
    jwt_secret: str = Field(default="", alias="JWT_SECRET")

    @property
    def fallback_model_list(self) -> list[str]:
        """备用模型列表。"""
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例。"""
    return Settings()
