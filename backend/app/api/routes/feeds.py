import sqlite3
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.core.database import (
    add_rss_feed,
    delete_rss_feed,
    list_rss_feeds,
    toggle_rss_feed,
)

router = APIRouter(prefix="/feeds", tags=["feeds"])


class FeedCreateRequest(BaseModel):
    url: str
    name: Optional[str] = ""


class FeedToggleRequest(BaseModel):
    enabled: bool


@router.get("")
def get_feeds():
    """List all configured RSS feeds and their enabled status."""
    return list_rss_feeds()


@router.post("", status_code=201)
def create_feed(payload: FeedCreateRequest):
    """Validate and add a custom RSS feed URL."""
    raw_url = (payload.url or "").strip()
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid http:// or https:// RSS feed URL.",
        )

    clean_name = (payload.name or "").strip()
    if not clean_name:
        clean_name = parsed.netloc.replace("www.", "")

    try:
        return add_rss_feed(url=raw_url, name=clean_name)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="This RSS feed URL is already in your sources list.",
        )


@router.patch("/{feed_id}")
def update_feed(feed_id: int, payload: FeedToggleRequest):
    """Enable or disable a configured RSS feed."""
    updated = toggle_rss_feed(feed_id=feed_id, enabled=payload.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail="Feed not found")
    return updated


@router.delete("/{feed_id}")
def remove_feed(feed_id: int):
    """Remove a configured RSS feed."""
    if not delete_rss_feed(feed_id=feed_id):
        raise HTTPException(status_code=404, detail="Feed not found")
    return {"status": "deleted", "id": feed_id}
