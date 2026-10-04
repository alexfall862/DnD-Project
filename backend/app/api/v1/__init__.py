from fastapi import APIRouter

from app.api.v1 import debug, generation, health, journal, perspective, play

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(perspective.router)
router.include_router(play.router)
router.include_router(journal.router)
router.include_router(generation.router)
router.include_router(debug.router)
