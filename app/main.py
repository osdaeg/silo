import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import links, collections, dashboard, auth
from app.routers.auth import require_token
from app.sync import start_sync_scheduler, sync_pending_to_raindrop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(start_sync_scheduler())
    yield
    task.cancel()


app = FastAPI(title="Silo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(links.router)
app.include_router(collections.router)
app.include_router(dashboard.router)


@app.post("/sync", dependencies=[Depends(require_token)])
async def manual_sync():
    synced, status = await sync_pending_to_raindrop()
    return {"synced": synced, "status": status}
