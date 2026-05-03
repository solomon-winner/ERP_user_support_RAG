"""
ERP Guide API — FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router as guide_router
from app.api.websocket import router as ws_router
from app.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="ERP Guide Assistant API",
        description="AI-powered step-by-step guide assistant for ERP systems",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(guide_router, prefix="/api/guide", tags=["Guide"])
    app.include_router(ws_router, tags=["WebSocket"])

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "environment": settings.APP_ENV}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.APP_ENV == "development",
    )
