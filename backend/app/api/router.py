"""Aggregate all API routers."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.keys import router as keys_router
from app.api.cases import router as cases_router
from app.api.chat import router as chat_router
from app.api.evidence import router as evidence_router
from app.api.wizard import router as wizard_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(keys_router)
api_router.include_router(cases_router)
api_router.include_router(chat_router)
api_router.include_router(evidence_router)
api_router.include_router(wizard_router)
