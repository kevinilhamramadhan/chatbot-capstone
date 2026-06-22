"""Central configuration for the Toti Cakery chatbot service.

Every tunable lives here and is sourced from environment variables so nothing
operational is hardcoded in business logic (see PROMPT rules #2 and #4).
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Service ───────────────────────────────────────────────────────────────
    app_name: str = "Toti Cakery Chatbot Service"
    log_level: str = "INFO"

    # ── Backend (Nicholas's FastAPI) ──────────────────────────────────────────
    # NOTE: do NOT hardcode paths. Backend has a double-prefix routing bug; paths
    # are resolved/verified in backend_client against this base URL. See README.
    backend_base_url: str = "http://localhost:8001"
    backend_verify_paths_via_openapi: bool = True
    backend_request_timeout_seconds: float = 10.0
    # Sent as X-Service-Key on every backend call. Must match the backend's
    # SERVICE_API_KEY (require_service_key dependency). Harmless on public GETs.
    backend_service_api_key: str = ""

    # ── Ollama (LLM + embeddings) ─────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:1.7b"
    embedding_model: str = "qwen3-embedding:0.6b"
    llm_temperature: float = 0.7
    llm_top_p: float = 0.8
    llm_num_ctx: int = 32768
    # qwen3 "thinking" mode. Off by default: faster replies, no reasoning tokens,
    # and more consistent tool-call formatting for a small model.
    llm_reasoning: bool = False
    # Keep models resident in Ollama to avoid ~70s cold-start reloads. -1 = never
    # unload (Ollama expects an int or a duration like "30m"). Also set
    # OLLAMA_MAX_LOADED_MODELS=2 on the Ollama server so the chat + embedding
    # models don't evict each other (see README).
    llm_keep_alive: int = -1
    # Pre-warm LLM + embeddings on startup so the first user isn't hit by cold start.
    llm_prewarm_on_startup: bool = True

    # ── RAG / ChromaDB ────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "toti_faq"
    knowledge_base_dir: str = "./knowledge_base/faq"
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 77  # ~15% of chunk_size
    rag_top_k: int = 3
    # Scope guard: retrieval similarity below this => out-of-scope, refuse to
    # answer from the LLM's general knowledge. Start reasonable, tune later.
    rag_similarity_threshold: float = 0.40

    # ── WhatsApp gateway (wwebjs-api) ─────────────────────────────────────────
    wwebjs_base_url: str = "http://wwebjs-api:3000"
    wwebjs_api_key: str = "change-me"
    wwebjs_session_id: str = "toti"

    # ── Local chatbot DB (SQLite) ─────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./toti_chatbot.db"

    # ── Payment gateway (mock Midtrans) ───────────────────────────────────────
    payment_gateway_url: str = "http://payment-gateway:9000"
    payment_check_interval_seconds: int = 30
    payment_timeout_minutes: int = 30
    # Decision: support full payment OR 50% down-payment (DP).
    allow_down_payment: bool = True
    down_payment_percentage: float = 0.50

    # ── Checkout / identity ───────────────────────────────────────────────────
    # Decision: phone auto-fills from the sender's WhatsApp number, overridable.
    autofill_phone_from_wa: bool = True

    # ── Admin / human takeover ────────────────────────────────────────────────
    # Decision: single fixed admin number for now.
    admin_wa_number: str = ""
    takeover_expiry_days: int = 7

    # ── Store info (used in "ready for pickup/delivery" messages) ─────────────
    store_name: str = "Toti Cakery"
    store_address: str = "Jl. Contoh No. 123, Jakarta (ganti di .env)"

    # ── Owner gating for financial_report / business_analytics ────────────────
    owner_wa_numbers: str = ""  # comma-separated

    @property
    def owner_wa_list(self) -> list[str]:
        return [n.strip() for n in self.owner_wa_numbers.split(",") if n.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
