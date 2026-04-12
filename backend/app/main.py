"""ClubResolve — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables. Shutdown: cleanup."""
    await init_db()
    yield


app = FastAPI(
    title="ClubResolve",
    description="Case organization, governance research, and parent advocacy support for BC sports club disputes",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
app.include_router(api_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
