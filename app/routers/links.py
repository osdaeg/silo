from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from app.database import get_db
from app.models import LinkCreate, LinkUpdate, LinkOut
from app.routers.auth import require_token
from app.sync import sync_link_to_raindrop
from typing import List, Optional
import aiohttp
import asyncio

router = APIRouter(prefix="/links", tags=["links"])


async def fetch_page_title(url: str) -> Optional[str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Silo/1.0)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5), allow_redirects=True) as resp:
                if resp.status == 200 and 'text/html' in resp.content_type:
                    # Read only first 8KB to find <title>
                    chunk = await resp.content.read(8192)
                    text = chunk.decode('utf-8', errors='ignore')
                    start = text.lower().find('<title')
                    if start != -1:
                        end_tag = text.find('>', start)
                        close = text.lower().find('</title>', end_tag)
                        if close != -1:
                            title = text[end_tag+1:close].strip()
                            return title[:200] if title else None
    except Exception:
        pass
    return None


@router.get("", response_model=List[LinkOut], dependencies=[Depends(require_token)])
async def list_links(
    collection_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    db=Depends(get_db)
):
    query = """
        SELECT l.id, l.url, l.title, l.description, l.collection_id,
               c.name as collection_name, l.synced_to_raindrop, l.created_at
        FROM links l
        LEFT JOIN collections c ON c.id = l.collection_id
        WHERE 1=1
    """
    params = []
    if collection_id is not None:
        query += " AND l.collection_id = ?"
        params.append(collection_id)
    if q:
        query += " AND (l.url LIKE ? OR l.title LIKE ? OR l.description LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    query += " ORDER BY l.created_at DESC"

    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/fetch-title", dependencies=[Depends(require_token)])
async def get_title(url: str = Query(...)):
    title = await fetch_page_title(url)
    return {"title": title}


@router.post("", response_model=LinkOut, dependencies=[Depends(require_token)])
async def create_link(data: LinkCreate, background_tasks: BackgroundTasks, db=Depends(get_db)):
    # Auto-fetch title if not provided
    title = data.title
    if not title:
        title = await fetch_page_title(data.url)

    async with db.execute(
        """INSERT INTO links (url, title, description, collection_id)
           VALUES (?, ?, ?, ?)
           RETURNING id, url, title, description, collection_id, synced_to_raindrop, created_at""",
        (data.url, title, data.description, data.collection_id)
    ) as cur:
        row = await cur.fetchone()
    await db.commit()
    link = dict(row)

    col_name = None
    if link["collection_id"]:
        async with db.execute("SELECT name FROM collections WHERE id=?", (link["collection_id"],)) as cur2:
            col_row = await cur2.fetchone()
            if col_row:
                col_name = col_row["name"]
    link["collection_name"] = col_name

    background_tasks.add_task(sync_link_to_raindrop, link["id"])
    return link


@router.patch("/{link_id}", response_model=LinkOut, dependencies=[Depends(require_token)])
async def update_link(link_id: int, data: LinkUpdate, db=Depends(get_db)):
    fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [link_id]
    await db.execute(f"UPDATE links SET {set_clause} WHERE id = ?", params)
    await db.commit()
    async with db.execute(
        """SELECT l.id, l.url, l.title, l.description, l.collection_id,
                  c.name as collection_name, l.synced_to_raindrop, l.created_at
           FROM links l LEFT JOIN collections c ON c.id = l.collection_id
           WHERE l.id = ?""",
        (link_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Link not found")
    return dict(row)


@router.delete("/{link_id}", dependencies=[Depends(require_token)])
async def delete_link(link_id: int, db=Depends(get_db)):
    await db.execute("DELETE FROM links WHERE id = ?", (link_id,))
    await db.commit()
    return {"ok": True}
