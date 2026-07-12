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


async def _warmup_models() -> None:
    """Preload the LLM + embedding models into Ollama's RAM so the FIRST real
    user doesn't pay the ~1 min cold-start load. Runs in the background and is
    best-effort: if Ollama is slow or down the service still starts and the
    models simply load on first use. keep_alive then keeps them resident.
    """
    from langchain_core.messages import HumanMessage

    from app.llm.client import get_llm
    from app.rag.embeddings import get_embedding_function

    try:
        await asyncio.to_thread(get_embedding_function().embed_one, "warmup")
        await get_llm().ainvoke([HumanMessage(content="warmup")])
        logger.info("Model warm-up complete — LLM + embeddings resident in RAM.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model warm-up skipped (will load on first request): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    background.start()
    if settings.warmup_on_startup:
        # Fire-and-forget: don't block startup on the ~1 min cold load.
        asyncio.create_task(_warmup_models())
        logger.info("%s started (warming models in background).", settings.app_name)
    else:
        logger.info("%s started (model warm-up disabled).", settings.app_name)
    yield
    await background.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
