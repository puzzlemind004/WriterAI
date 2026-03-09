"""
Point d'entrée de l'API FastAPI.
Lancer avec : uvicorn api.main:app --reload
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.storage.database import init_db
from api.routers import projects, pipeline, content
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage : initialise la base de données
    await init_db()
    logger.info("Base de données initialisée")
    yield
    # Arrêt : rien à faire pour l'instant


app = FastAPI(
    title="WriterAI API",
    description="Moteur de rédaction de livres assisté par IA",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(pipeline.router)
app.include_router(content.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
