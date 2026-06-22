"""FastAPI entrypoint for the Toti Cakery chatbot service."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.conversation import background
from app.core.config import settings
from app.core.database import init_db
from app.webhook.routes import router as webhook_router

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _prewarm() -> None:
    """Load the chat + embedding models into Ollama so the first real user isn't
    hit by a ~70s cold start. Runs in the background; failures are non-fatal."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.llm.client import get_llm
        from app.llm.prompt import SYSTEM_PROMPT
        from app.rag.embeddings import get_embedding_function
        from app.tools.registry import ALL_TOOLS

        get_embedding_function().embed_one("warmup")
        # Warm the EXACT prefix (system prompt + tool schemas) so Ollama caches it
        # and the first real user gets a warm, fast response.
        llm = get_llm().bind_tools(ALL_TOOLS)
        await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content="halo")])
        logger.info("Model pre-warm complete.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model pre-warm skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    background.start()
    if settings.llm_prewarm_on_startup:
        asyncio.create_task(_prewarm())
    logger.info("%s started.", settings.app_name)
    yield
    await background.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
