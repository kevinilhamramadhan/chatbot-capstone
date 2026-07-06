"""ChatOllama LLM with tool calling enabled."""

import logging
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def get_llm():
    from langchain_ollama import ChatOllama  # lazy: heavy import

    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        num_ctx=settings.llm_num_ctx,
        num_predict=settings.llm_num_predict,  # cap runaway generations (CPU latency tail)
    )
