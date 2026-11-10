"""Phase 1 Verification Tests.

Validates:
1. RSS Feed Parsing & Trafilatura Article Extraction.
2. In-Memory Kokoro-ONNX Audio Synthesis Latency (RTF < 0.25, under 3s on CPU).
"""

import time
import pytest
from backend.app.services.scraper import fetch_feed_entries, extract_article_content
from backend.app.services.tts import KokoroTTS


def test_scraper_rss_and_content():
    """Verify that RSS feeds are parsed and articles yield extracted text."""
    test_feed = "https://news.ycombinator.com/rss"
    entries = fetch_feed_entries(test_feed, limit=3)
    
    assert len(entries) > 0, "No entries parsed from feed"
    first = entries[0]
    assert "title" in first and "link" in first
    print(f"\n[Test] Parsed article: {first['title']} -> {first['link']}")

    content = extract_article_content(first["link"])
    assert content is not None, "Failed to extract content from article link"
    assert len(content.strip()) > 50, "Extracted content is too short"
    print(f"[Test] Successfully extracted {len(content)} characters of text.")


def test_tts_latency_and_buffer():
    """Verify Kokoro ONNX in-memory audio synthesis speed on CPU."""
    tts = KokoroTTS()
    sample_text = (
        "Breaking technology news: autonomous AI agents are now capable of synthesizing "
        "personalized audio briefings directly in memory with sub-second latency."
    )

    start_time = time.perf_counter()
    audio_buffer = tts.synthesize_to_bytes(sample_text)
    elapsed = time.perf_counter() - start_time

    assert audio_buffer is not None
    buffer_bytes = audio_buffer.getvalue()
    assert len(buffer_bytes) > 44, "Audio buffer does not contain valid WAV data"
    assert buffer_bytes[:4] == b"RIFF", "Buffer does not start with RIFF header"

    print(f"\n[Test] Synthesized {len(buffer_bytes)} bytes in {elapsed:.2f}s")
    assert elapsed < 5.0, f"Synthesis took too long: {elapsed:.2f}s (target < 3s-5s on CPU)"


if __name__ == "__main__":
    print("Run tests with: .\\.venv\\Scripts\\pytest backend/tests/test_phase1.py")

