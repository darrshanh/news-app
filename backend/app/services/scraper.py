"""Scraper service for RSS feeds and web article content extraction.

Phase 1 Responsibilities:
- Parse RSS feeds via `feedparser` to extract metadata (title, URL, publication date, summary).
- Extract cleaned main article text from source URLs using `trafilatura`.
"""

from typing import Dict, List, Optional
import feedparser
import trafilatura
import re
import logging

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TRAF_CONFIG = trafilatura.settings.use_config()
TRAF_CONFIG.set("DEFAULT", "USER_AGENT", BROWSER_USER_AGENT)

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    clean_text = re.sub(r"<[^>]+>", "", raw_html)
    clean_text = " ".join(clean_text.split())

    if clean_text.lower().strip() in ["comments", "read more", ""] or len(clean_text) < 20:
        return ""
    return clean_text

def fetch_feed_entries(feed_url: str, limit: int = 5) -> List[Dict[str, str]]:
    """Parse an RSS or Atom feed and return normalized entry metadata.

    Args:
        feed_url: URL to the RSS or Atom feed.
        limit: Maximum number of recent articles to extract.

    Returns:
        List of dicts containing keys: title, link, published, summary.
    """
    # TODO: Implement feed parsing using feedparser
    logger.info(f"[*] Fetching RSS feed: {feed_url}")
    feed = feedparser.parse(feed_url)
    top_results = []
    for entry in feed.entries[:limit]:
        top_results.append({
            "title": entry.get("title", "Untitled"),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "summary": clean_html(entry.get("summary", ""))
        })
    logger.info(f"[*] Found {len(top_results)} entries from {feed_url}")
    return top_results


def extract_article_content(url: str) -> Optional[str]:
    """Fetch raw HTML from url and extract clean body text using trafilatura.

    Args:
        url: The web link to the target article.

    Returns:
        Cleaned markdown/plain text without ads, navbars, or boilerplate.
    """
    # TODO: Implement article extraction using trafilatura.fetch_url and trafilatura.extract
    logger.info(f"[*] Extracting article content from: {url}")
    downloaded = trafilatura.fetch_url(url, config=TRAF_CONFIG)
    # downloaded_response = trafilatura.fetch_response(url)
    if not downloaded:
        return None
    article_text = trafilatura.extract(downloaded, output_format="markdown", config=TRAF_CONFIG)
    if article_text:
        logger.info(f"[+] Extracted {len(article_text)} characters")
    else:
        logger.warning(f"[-] Could not extract content from {url}")
    return article_text

