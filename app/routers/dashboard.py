import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, db=Depends(get_db)):
    async with db.execute(
        "SELECT id, name FROM collections ORDER BY name"
    ) as cur:
        collections = [dict(r) for r in await cur.fetchall()]

    async with db.execute("SELECT COUNT(*) as total FROM links") as cur:
        total = (await cur.fetchone())["total"]

    async with db.execute(
        "SELECT COUNT(*) as pending FROM links WHERE synced_to_raindrop = 0"
    ) as cur:
        pending = (await cur.fetchone())["pending"]

    async with db.execute(
        "SELECT synced_count, status, message, created_at FROM sync_log ORDER BY created_at DESC LIMIT 1"
    ) as cur:
        last_sync = await cur.fetchone()
        last_sync = dict(last_sync) if last_sync else None

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "collections": collections,
        "total_links": total,
        "pending_sync": pending,
        "last_sync": last_sync,
        "api_token": os.getenv("SILO_API_TOKEN", "changeme"),
    })
