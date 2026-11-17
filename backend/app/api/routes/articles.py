from fastapi import APIRouter, HTTPException, Response
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from backend.app.core.database import get_article_by_id, get_articles
from backend.app.services.ingestion import sync_feed, sync_all_feeds, iter_sync_all_feeds
from backend.app.services.tts import get_tts
from typing import Optional
import json
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/articles", tags=["articles"])

@router.get("")
def list_articles(limit: int = 20, since_id: Optional[int] = None):
    """Retrieve the latest articles from the database"""
    articles = get_articles(limit=limit, since_id=since_id)
    if not articles and since_id is None:
        sync_all_feeds()
        articles = get_articles(limit=limit)
    return articles

@router.post("/sync")
def trigger_sync():
    result = sync_all_feeds()
    return result

@router.get("/sync/stream")
def stream_sync():
    def event_generator():
        new_count = 0
        try:
            for article in iter_sync_all_feeds():
                new_count += 1
                yield f"data: {json.dumps({'type': 'article_ready', 'article': article})}\n\n"
            yield f"data: {json.dumps({'type': 'sync_complete', 'new_count': new_count})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'sync_error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/{article_id}/audio")
def stream_article_audio(article_id: int):
    article = get_article_by_id(article_id=article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    body_text = (article.get("summary") or article.get("content") or "")[:300]
    title = article.get("title", "")
    text_to_speak = article.get("audio_script") or f"{title}. {body_text}"
    audio_buffer = get_tts().synthesize_to_bytes(text=text_to_speak)
    audio_bytes = audio_buffer.getvalue()
    
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Length": str(len(audio_bytes)),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",
        }
    )
