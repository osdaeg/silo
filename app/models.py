from pydantic import BaseModel, HttpUrl
from typing import Optional


class CollectionCreate(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: int
    name: str
    created_at: str


class LinkCreate(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    collection_id: Optional[int] = None


class LinkUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    collection_id: Optional[int] = None


class LinkOut(BaseModel):
    id: int
    url: str
    title: Optional[str]
    description: Optional[str]
    collection_id: Optional[int]
    collection_name: Optional[str]
    synced_to_raindrop: bool
    created_at: str
