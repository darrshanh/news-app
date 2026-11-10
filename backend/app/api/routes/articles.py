from fastapi import APIRouter, HTTPException, Response
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from backend.app.core.database import get_article_by_id, get_articles
from backend.app.services.ingestion import sync_feed, sync_all_feeds
from backend.app.services.tts import get_tts

router = APIRouter(prefix="/articles", tags=["articles"])

@router.get("")
def list_articles(limit: int = 20):
    """Retrieve the latest articles from the database"""
    articles = get_articles(limit=limit)
    if not articles:
        sync_all_feeds()
        articles = get_articles(limit=limit)
    return articles

@router.post("/sync")
def trigger_sync():
    result = sync_all_feeds()
    return result

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
