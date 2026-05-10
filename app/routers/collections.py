from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.models import CollectionCreate, CollectionOut
from app.routers.auth import require_token
from typing import List

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=List[CollectionOut], dependencies=[Depends(require_token)])
async def list_collections(db=Depends(get_db)):
    async with db.execute("SELECT id, name, created_at FROM collections ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=CollectionOut, dependencies=[Depends(require_token)])
async def create_collection(data: CollectionCreate, db=Depends(get_db)):
    try:
        async with db.execute(
            "INSERT INTO collections (name) VALUES (?) RETURNING id, name, created_at",
            (data.name,)
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail="Collection already exists")
    return dict(row)


@router.delete("/{collection_id}", dependencies=[Depends(require_token)])
async def delete_collection(collection_id: int, db=Depends(get_db)):
    await db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    await db.commit()
    return {"ok": True}
