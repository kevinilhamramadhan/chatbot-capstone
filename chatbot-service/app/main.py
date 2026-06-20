"""FastAPI entrypoint for the Toti Cakery chatbot service."""

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    background.start()
    logger.info("%s started.", settings.app_name)
    yield
    await background.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
