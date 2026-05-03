"""
Application lifespan — startup and shutdown events.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.services.knowledge_base import kb_service
from app.services.cache_service import cache_service
from app.knowledge.embedding_store import embedding_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # ─── Startup ───
    print("=== ERP Guide API Starting ===")
    kb_service.initialize()
    await cache_service.initialize()
    try:
        await embedding_store.initialize()
    except Exception as e:
        print(f"[Startup] Embedding store init failed (DB not available?): {e}")

    print("=== ERP Guide API Ready ===")
    yield

    # ─── Shutdown ───
    print("=== ERP Guide API Shutting Down ===")
