from typing import Optional
import asyncio
import aiohttp
import aiosqlite
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/data/silo.db")
RAINDROP_TOKEN = os.getenv("RAINDROP_TOKEN", "")
GOTIFY_URL = os.getenv("GOTIFY_URL", "http://192.168.1.10:8088")
GOTIFY_TOKEN = os.getenv("GOTIFY_TOKEN", "")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_MINUTES", "30")) * 60
RAINDROP_COLLECTION_NAME = "Silo"


async def _get_or_create_raindrop_collection(session: aiohttp.ClientSession) -> int:
    headers = {"Authorization": f"Bearer {RAINDROP_TOKEN}"}
    async with session.get("https://api.raindrop.io/rest/v1/collections", headers=headers) as resp:
        data = await resp.json()
        for col in data.get("items", []):
            if col["title"] == RAINDROP_COLLECTION_NAME:
                return col["_id"]

    # Create it
    async with session.post(
        "https://api.raindrop.io/rest/v1/collection",
        headers=headers,
        json={"title": RAINDROP_COLLECTION_NAME}
    ) as resp:
        data = await resp.json()
        return data["item"]["_id"]


async def _send_gotify(message: str, title: str = "Silo Sync", priority: int = 3):
    if not GOTIFY_TOKEN:
        return
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{GOTIFY_URL}/message",
                params={"token": GOTIFY_TOKEN},
                json={"title": title, "message": message, "priority": priority}
            )
    except Exception as e:
        logger.warning(f"Gotify notification failed: {e}")


async def _find_raindrop_by_url(session: aiohttp.ClientSession, col_id: int, url: str) -> Optional[int]:
    """Search Raindrop collection for an existing raindrop with the same URL. Returns raindrop _id or None."""
    headers = {"Authorization": f"Bearer {RAINDROP_TOKEN}"}
    try:
        params = {"search": url, "collectionId": col_id}
        async with session.get(
            "https://api.raindrop.io/rest/v1/raindrops/{col_id}".format(col_id=col_id),
            headers=headers,
            params={"search": url}
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                for item in data.get("items", []):
                    if item.get("link") == url:
                        return item["_id"]
    except Exception:
        pass
    return None


async def sync_link_to_raindrop(link_id: int):
    """Sync a single link immediately after creation."""
    if not RAINDROP_TOKEN:
        return
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM links WHERE id = ? AND synced_to_raindrop = 0", (link_id,)
            ) as cur:
                link = await cur.fetchone()
            if not link:
                return

            async with aiohttp.ClientSession() as session:
                col_id = await _get_or_create_raindrop_collection(session)
                headers = {"Authorization": f"Bearer {RAINDROP_TOKEN}"}

                # Check if URL already exists in Raindrop to avoid duplicates
                existing_id = await _find_raindrop_by_url(session, col_id, link["url"])
                if existing_id:
                    logger.info(f"Link {link_id} already in Raindrop (id={existing_id}), marking as synced")
                    await db.execute(
                        "UPDATE links SET synced_to_raindrop = 1, raindrop_id = ? WHERE id = ?",
                        (existing_id, link_id)
                    )
                    await db.commit()
                    return

                payload = {
                    "link": link["url"],
                    "title": link["title"] or link["url"],
                    "collection": {"$id": col_id},
                }
                async with session.post(
                    "https://api.raindrop.io/rest/v1/raindrop",
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raindrop_id = data["item"]["_id"]
                        await db.execute(
                            "UPDATE links SET synced_to_raindrop = 1, raindrop_id = ? WHERE id = ?",
                            (raindrop_id, link_id)
                        )
                        await db.commit()
                        logger.info(f"Link {link_id} synced to Raindrop")
                    else:
                        logger.warning(f"Raindrop sync failed for link {link_id}: {resp.status}")
    except Exception as e:
        logger.error(f"Error syncing link {link_id} to Raindrop: {e}")


async def sync_pending_to_raindrop():
    """Sync all unsynced links (cron backup)."""
    if not RAINDROP_TOKEN:
        return 0, "skipped"

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM links WHERE synced_to_raindrop = 0"
            ) as cur:
                pending = await cur.fetchall()

            if not pending:
                return 0, "ok"

            synced = 0
            failed = 0
            async with aiohttp.ClientSession() as session:
                col_id = await _get_or_create_raindrop_collection(session)
                headers = {"Authorization": f"Bearer {RAINDROP_TOKEN}"}

                for link in pending:
                    try:
                        payload = {
                            "link": link["url"],
                            "title": link["title"] or link["url"],
                            "collection": {"$id": col_id},
                        }
                        async with session.post(
                            "https://api.raindrop.io/rest/v1/raindrop",
                            headers=headers,
                            json=payload
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                raindrop_id = data["item"]["_id"]
                                await db.execute(
                                    "UPDATE links SET synced_to_raindrop = 1, raindrop_id = ? WHERE id = ?",
                                    (raindrop_id, link["id"])
                                )
                                synced += 1
                            else:
                                failed += 1
                    except Exception:
                        failed += 1

                await db.commit()

            status = "ok" if failed == 0 else "partial"
            # Log sync
            await db.execute(
                "INSERT INTO sync_log (synced_count, status, message) VALUES (?, ?, ?)",
                (synced, status, f"Synced {synced}, failed {failed}")
            )
            await db.commit()

            msg = f"✅ Sincronización con Raindrop\nEnlaces sincronizados: {synced}"
            if failed:
                msg += f"\nFallidos: {failed}"
            await _send_gotify(msg, priority=4 if failed else 3)
            return synced, status

    except Exception as e:
        logger.error(f"Raindrop bulk sync error: {e}")
        await _send_gotify(f"❌ Error en sync con Raindrop: {e}", priority=7)
        return 0, "error"


async def start_sync_scheduler():
    """Background task: run periodic Raindrop sync."""
    logger.info(f"Raindrop sync scheduler started (every {SYNC_INTERVAL}s)")
    while True:
        await asyncio.sleep(SYNC_INTERVAL)
        logger.info("Running scheduled Raindrop sync...")
        synced, status = await sync_pending_to_raindrop()
        logger.info(f"Scheduled sync done: {synced} links, status={status}")
