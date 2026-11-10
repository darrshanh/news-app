"""Phase 1 Deliverable CLI:
Fetches headlines from sample RSS feeds, extracts content, and speaks them aloud locally.
"""


import sys
from pathlib import Path
# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.app.services.scraper import fetch_feed_entries, extract_article_content
from backend.app.services.tts import KokoroTTS



# Sample feeds for testing
SAMPLE_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/feed/",
]


def main():
    print("=== News Intelligence Agent - Phase 1 CLI ===")
    # TODO: Fetch feed entries, extract content, and synthesize speech
    print("Available Feeds:")
    for i, feed in enumerate(SAMPLE_FEEDS, 1):
        print(f"[{i}] {feed}")
    user_selected_option = int(input("Select a feed to fetch news from(1/2/3): "))
    user_selected_feed_url = SAMPLE_FEEDS[user_selected_option - 1]
    articles = fetch_feed_entries(user_selected_feed_url)
    for index, article in enumerate(articles):
        print(f"[{index + 1}] {article["title"]}")
        print(f"[summary] {article["summary"]}")
    user_expand_option = int(input("Select an article to expand: "))
    user_selected_article_text = extract_article_content(articles[user_expand_option - 1]["link"])
    print(f"{articles[user_expand_option - 1]["title"]}")
    content = user_selected_article_text or articles[user_expand_option - 1]["summary"]
    print(content)
    text_to_speak = f"{articles[user_expand_option - 1]['title']}. {content[:350]}"
    tts_engine = KokoroTTS()
    buffer = tts_engine.synthesize_to_bytes(text_to_speak)
    with open("news_audio.wav", "wb") as f:
        f.write(buffer.getvalue())
    pass


if __name__ == "__main__":
    main()

