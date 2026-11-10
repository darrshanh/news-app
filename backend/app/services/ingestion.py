import sys
from pathlib import Path
# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from backend.app.services.scraper import fetch_feed_entries, extract_article_content
from backend.app.services.tts import KokoroTTS
from backend.app.models.article import ArticleCreate
from backend.app.core.database import save_article, article_exists
from backend.app.services.synthesizer import get_synthesizer, EditorialDigest
import json

synthesizer = get_synthesizer()

DEFAULT_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/feed/",
]

def sync_feed(feed_url: str, limit_per_feed: int = 5) -> int:
    """Ingest a single RSS feed, extract article content, and save new items to the DB."""
    # 1. Call scraper.fetch_feed_entries(feed_url, limit)
    # 2. For each entry, check if already in DB (or try extract_article_content)
    # 3. Create ArticleCreate model
    # 4. Call database.save_article(...)
    # 5. Return count of newly saved articles
    new_saved_count = 0
    fetch_results = fetch_feed_entries(feed_url=feed_url, limit=limit_per_feed)
    for entry in fetch_results:
        article_url = entry.get("link")
        if not article_url:
            continue
        if article_exists(article_url):
            continue
        extracted_text = extract_article_content(article_url)
        content = extracted_text or entry.get("summary") or entry.get("title", "untitled")
        digest = synthesizer.synthesize(title=entry.get("title", "untitled"), content=content)
        article_data = ArticleCreate(title=entry["title"], url=entry["link"], published_at=entry["published"], summary=entry["summary"], content=content, takeaways=json.dumps(digest.takeaways), audio_script=digest.audio_script)
        if save_article(article=article_data):
            new_saved_count += 1
    return new_saved_count

def sync_all_feeds(feed_urls: list[str] = None) -> dict:
    """Ingest all configured feeds and return summary stats."""
    # Loops over feeds, aggregates counts, and returns e.g. {"new_articles": 7}
    feeds = feed_urls or DEFAULT_FEEDS
    newly_synced_feed_count = 0
    for url in feeds:
        newly_synced_feed_count += sync_feed(url)
    return {"status": "success", "new_articles": newly_synced_feed_count}