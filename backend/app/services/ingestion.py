import sys
from pathlib import Path
# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from backend.app.services.scraper import fetch_feed_entries, extract_article_content
from backend.app.services.tts import KokoroTTS
from backend.app.models.article import ArticleCreate
from backend.app.core.database import (
    article_exists,
    get_article_by_id,
    get_enabled_feed_urls,
    list_rss_feeds,
    save_article,
)
from backend.app.core.settings_store import get_runtime_settings
from backend.app.services.embeddings import get_embedding_service
from backend.app.services.synthesizer import get_synthesizer, EditorialDigest
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json

synthesizer = get_synthesizer()
_sync_lock = threading.Lock()

DEFAULT_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/feed/",
]

def iter_sync_feed(feed_url: str, limit_per_feed: int = 5) -> int:
    """Ingest a single RSS feed, extract article content, and save new items to the DB."""
    # 1. Call scraper.fetch_feed_entries(feed_url, limit)
    # 2. For each entry, check if already in DB (or try extract_article_content)
    # 3. Create ArticleCreate model
    # 4. Call database.save_article(...)
    # 5. Return count of newly saved articles
    new_saved_count = 0
    fetch_results = fetch_feed_entries(feed_url=feed_url, limit=limit_per_feed)
    pending_entries = []
    for entry in fetch_results:
        article_url = entry.get("link")
        if not article_url or article_exists(article_url):
            continue
        pending_entries.append(entry)
    if not pending_entries:
        return

    scraped_items = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_entry = {
            executor.submit(extract_article_content, entry["link"]): entry
            for entry in pending_entries
        }
        for future in as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                extracted_text = future.result()
            except Exception:
                extracted_text = None
            scraped_items.append((entry, extracted_text))

    for entry, extracted_text in scraped_items:
        content = extracted_text or entry.get("summary") or entry.get("title", "untitled")
        digest = synthesizer.synthesize(title=entry.get("title", "untitled"), content=content)
        article_data = ArticleCreate(
            title=entry["title"],
            url=entry["link"],
            published_at=entry["published"],
            summary=digest.summary or entry.get("summary", ""),
            content=content,
            takeaways=json.dumps(digest.takeaways),
            audio_script=digest.audio_script,
        )
        saved_id = save_article(article=article_data)
        if saved_id:
            try:
                get_embedding_service().embed_and_store_article(
                    article_id=saved_id,
                    title=article_data.title,
                    summary=article_data.summary or "",
                    content=article_data.content or "",
                )
            except Exception:
                pass
            saved_article = get_article_by_id(saved_id)
            if saved_article:
                yield saved_article
        # if save_article(article=article_data):
        #     new_saved_count += 1
        # extracted_text = extract_article_content(article_url)
        # content = extracted_text or entry.get("summary") or entry.get("title", "untitled")
        # digest = synthesizer.synthesize(title=entry.get("title", "untitled"), content=content)
        # article_data = ArticleCreate(title=entry["title"], url=entry["link"], published_at=entry["published"], summary=digest.summary or entry.get("summary", ""), content=content, takeaways=json.dumps(digest.takeaways), audio_script=digest.audio_script)
        # if save_article(article=article_data):
        #     new_saved_count += 1
    return new_saved_count

def sync_feed(feed_url: str, limit_per_feed: int = 5) -> int:
    return sum(1 for _ in iter_sync_feed(feed_url=feed_url, limit_per_feed=limit_per_feed))

def _resolve_active_feeds(feed_urls: list[str] = None) -> list[str]:
    """Resolve explicit feed list, enabled DB feeds, or built-in defaults if uninitialized."""
    if feed_urls is not None:
        return feed_urls
    configured = list_rss_feeds()
    if configured:
        return get_enabled_feed_urls()
    return DEFAULT_FEEDS


def iter_sync_all_feeds(feed_urls: list[str] = None):
    feeds = _resolve_active_feeds(feed_urls)
    limit = get_runtime_settings().articles_per_feed
    with _sync_lock:
        for url in feeds:
            yield from iter_sync_feed(url, limit_per_feed=limit)

def sync_all_feeds(feed_urls: list[str] = None) -> dict:
    """Ingest all configured feeds and return summary stats."""
    # Loops over feeds, aggregates counts, and returns e.g. {"new_articles": 7}
    feeds = _resolve_active_feeds(feed_urls)
    limit = get_runtime_settings().articles_per_feed
    newly_synced_feed_count = 0
    with _sync_lock:
        for url in feeds:
            newly_synced_feed_count += sync_feed(url, limit_per_feed=limit)
    return {"status": "success", "new_articles": newly_synced_feed_count}