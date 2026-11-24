from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from backend.app.core.database import (
    get_article_by_id,
    get_articles_with_embeddings,
    save_article_context,
)
from backend.app.core.settings_store import get_runtime_settings
from backend.app.services.bandit import get_bandit_ranker
from backend.app.services.context_agent import build_historical_context
from backend.app.services.ingestion import sync_feed, sync_all_feeds, iter_sync_all_feeds
from backend.app.services.tts import get_tts
from typing import Literal, Optional
import json
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/articles", tags=["articles"])


class FeedbackRequest(BaseModel):
    vote: Optional[Literal["up", "down"]] = None


@router.get("")
def list_articles(
    limit: int = 20,
    since_id: Optional[int] = None,
    sort: str = "personalized",
):
    """Retrieve articles, optionally ranked by the local LinUCB preference bandit."""
    articles = get_articles_with_embeddings(limit=limit, since_id=since_id)
    if not articles and since_id is None:
        sync_all_feeds()
        articles = get_articles_with_embeddings(limit=limit)
    use_personalization = sort == "personalized" and since_id is None
    return get_bandit_ranker().rank_articles(articles, personalized=use_personalization)


@router.get("/bandit/stats")
def get_bandit_stats():
    """Return current LinUCB topic affinities and Like/Dislike totals."""
    return get_bandit_ranker().get_radar_stats()

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

@router.post("/{article_id}/feedback")
def submit_article_feedback(article_id: int, payload: FeedbackRequest):
    """Record Like/Dislike feedback, update LinUCB matrices, and return refreshed radar."""
    article = get_article_by_id(article_id=article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    radar = get_bandit_ranker().record_feedback(article_id=article_id, vote=payload.vote)
    return {"article_id": article_id, "vote": payload.vote, "radar": radar}


@router.get("/{article_id}/context")
def get_article_context(article_id: int, refresh: bool = False):
    """Return cached or freshly stitched LangGraph historical context for an article."""
    article = get_article_by_id(article_id=article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if not refresh and article.get("historical_context"):
        try:
            cached = json.loads(article["historical_context"])
            if isinstance(cached, dict):
                return cached
        except Exception:
            pass

    result = build_historical_context(article)
    save_article_context(article_id, json.dumps(result))
    return result


@router.get("/{article_id}/audio")
def stream_article_audio(article_id: int, voice: Optional[str] = None):
    article = get_article_by_id(article_id=article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    body_text = (article.get("summary") or article.get("content") or "")[:300]
    title = article.get("title", "")
    text_to_speak = article.get("audio_script") or f"{title}. {body_text}"
    selected_voice = voice or get_runtime_settings().tts_voice
    audio_buffer = get_tts().synthesize_to_bytes(text=text_to_speak, voice=selected_voice)
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
