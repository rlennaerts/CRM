from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from loguru import logger

from app.api import vehicles, work_orders, checklists, notifications, sync, portal
from app.config import settings
from app.database import engine
from app.models import Base
from app.tasks.scheduler import setup_scheduler, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database tabellen aanmaken
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tabellen aangemaakt")

    # Taakplanner starten
    setup_scheduler()
    scheduler.start()
    logger.info("Taakplanner gestart")

    yield

    scheduler.shutdown()
    logger.info("Taakplanner gestopt")


app = FastAPI(
    title="CRM Hub",
    description="Integratie-hub voor VWE, Gaston, SAM en werkplaatsplanbord",
    version="1.0.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="app/templates")

# CORS zodat de Sales Portal (aparte dev-server / origin) de API mag aanroepen.
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(vehicles.router, prefix="/api")
app.include_router(work_orders.router, prefix="/api")
app.include_router(checklists.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(portal.router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "scheduler_running": scheduler.running}
