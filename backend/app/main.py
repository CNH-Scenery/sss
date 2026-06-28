from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.backtest import router as backtest_router
from app.api.responses import router as responses_router
from app.api.strategy import router as strategy_router
from app.api.surveys import router as surveys_router
from app.config import get_settings
from app.db import init_db


@asynccontextmanager
async def lifespan(api: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title="Tacit Trader Backend", version="0.1.0", lifespan=lifespan)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/api/health")
    def health() -> dict[str, bool | str]:
        return {"ok": True, "service": "tacit-trader-backend"}

    api.include_router(surveys_router)
    api.include_router(responses_router)
    api.include_router(strategy_router)
    api.include_router(backtest_router)

    return api


app = create_app()
