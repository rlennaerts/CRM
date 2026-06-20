from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from loguru import logger

from app.api import vehicles, work_orders, checklists, notifications, sync
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

# API routes
app.include_router(vehicles.router, prefix="/api")
app.include_router(work_orders.router, prefix="/api")
app.include_router(checklists.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(sync.router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "scheduler_running": scheduler.running}
