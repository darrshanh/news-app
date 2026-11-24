"""Multi-agent LangGraph pipeline for Retrospective Historical Context.

Graph Architecture:
    START -> planner -> historian -> stitcher -> critic
                                        ^           |
                                        | (revise)  +--> END (if passed or max revisions)

Each node reads from and writes partial updates to a shared `ContextState`:
1. `planner_node`:   Extracts named entities and short keyword search queries.
2. `historian_node`: Runs hybrid retrieval (CPU semantic embeddings + SQLite keyword search).
3. `stitcher_node`:  Synthesizes the overarching story arc and chronological milestones.
4. `critic_node`:    Validates structure and strips any hallucinated URLs/IDs, routing back
                     to `stitcher_node` at most once if required fields are missing.
"""

from email.utils import parsedate_to_datetime
import json
import logging
import re
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.core.database import search_articles_by_keywords
from backend.app.core.settings_store import get_runtime_settings
from backend.app.services.embeddings import get_embedding_service
from backend.app.services.synthesizer import get_synthesizer

logger = logging.getLogger(__name__)


class ContextState(TypedDict):
    article_id: int
    title: str
    content: str
    summary: str
    published_at: str
    url: str
    entities: list[str]
    search_queries: list[str]
    retrieved_articles: list[dict]
    story_arc: str
    milestones: list[dict]
    critique: str
    passed: bool
    revision_count: int


def _extract_json_block(raw_text: str) -> Optional[dict]:
    """Strip optional markdown code fences and parse the first JSON object."""
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", (raw_text or "").strip(), flags=re.IGNORECASE
    ).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


_STOP_ENTITIES = {
    "investors", "investor", "users", "user", "company", "companies",
    "market", "markets", "tech", "technology", "report", "news",
    "ceo", "board", "ai", "government", "officials", "startup",
    "industry", "analysts", "customers", "employees", "shares",
}


def _parse_pub_date(date_str: str) -> float:
    """Convert RFC 2822 / ISO date string into a sortable UTC timestamp."""
    if not date_str:
        return 0.0
    try:
        return parsedate_to_datetime(date_str.strip()).timestamp()
    except Exception:
        return 0.0


def _format_display_date(date_str: str, fallback: str = "Recent") -> str:
    """Format RFC 2822 or ISO date strings cleanly as 'Nov 12, 2026'."""
    if not date_str or not date_str.strip():
        return fallback
    try:
        return parsedate_to_datetime(date_str.strip()).strftime("%b %d, %Y")
    except Exception:
        return date_str.strip()[:16]


def _first_sentences(text: str, max_chars: int = 220) -> str:
    """Return concise sentence-bounded snippet for timeline milestone cards."""
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars]
    last_dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    if last_dot > 60:
        return cut[: last_dot + 1]
    return cut.rstrip(" ,;:-") + "..."


def _call_qwen(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Invoke the shared warm Qwen 2.5 3B GGUF singleton via its thread-safe chat helper."""
    synth = get_synthesizer()
    return synth.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )


def _fallback_entities(title: str, text: str) -> list[str]:
    """Extract capitalized multi-word names or strong title terms when JSON fails."""
    phrases = re.findall(r"\b[A-Z][a-zA-Z0-9-]+(?:\s+[A-Z][a-zA-Z0-9-]+)*\b", title)
    if not phrases:
        phrases = re.findall(r"\b[A-Z][a-zA-Z0-9-]{2,}\b", text[:500])
    seen = set()
    unique: list[str] = []
    stop_words = {"The", "This", "That", "With", "From", "How", "Why", "What", "Who"}
    for phrase in phrases:
        if phrase in stop_words or phrase.lower() in seen:
            continue
        seen.add(phrase.lower())
        unique.append(phrase)
        if len(unique) >= 5:
            break
    return unique or [title[:40]]


def planner_node(state: ContextState) -> dict:
    """Node 1: Extract key entities and keyword queries for retrieval."""
    body_preview = state.get("summary") or state.get("content", "")[:1200]
    system_prompt = (
        "You extract key entities and concise search keywords from a news article. "
        "Output strictly valid JSON with keys 'entities' (3 to 5 specific people, organizations, "
        "products, or topics) and 'search_queries' (2 to 4 short 1-to-2 word database search terms)."
    )
    user_prompt = f"Title: {state['title']}\n\nText:\n{body_preview[:1200]}"

    entities: list[str] = []
    search_queries: list[str] = []

    try:
        raw = _call_qwen(system_prompt, user_prompt, max_tokens=120, temperature=0.2)
        parsed = _extract_json_block(raw)
        if parsed:
            raw_entities = parsed.get("entities") or []
            raw_queries = parsed.get("search_queries") or []
            entities = [str(e).strip() for e in raw_entities if str(e).strip()][:5]
            search_queries = [str(q).strip() for q in raw_queries if str(q).strip()][:4]
    except Exception as e:
        logger.warning(f"[-] Planner node fallback triggered: {e}")

    if not entities:
        entities = _fallback_entities(state["title"], body_preview)
    if not search_queries:
        search_queries = entities[:3]

    return {"entities": entities, "search_queries": search_queries}


def historian_node(state: ContextState) -> dict:
    """Node 2: Retrieve related historical articles using vector similarity + keywords."""
    cfg = get_runtime_settings()
    article_id = state["article_id"]
    query_text = f"{state['title']}. {state.get('summary') or state.get('content', '')[:600]}"

    semantic_hits = get_embedding_service().find_similar_articles(
        query_text=query_text,
        exclude_id=article_id,
        top_k=max(5, cfg.context_max_precedents + 1),
        min_score=cfg.context_min_score,
    )
    raw_terms = [*state.get("entities", []), *state.get("search_queries", [])]
    keyword_terms = [
        t for t in dict.fromkeys(raw_terms)
        if t.strip().lower() not in _STOP_ENTITIES and len(t.strip()) >= 3
    ][:3]
    keyword_hits = search_articles_by_keywords(
        keywords=keyword_terms,
        exclude_id=article_id,
        limit=6,
    )

    merged_by_id: dict[int, dict] = {}
    for item in semantic_hits:
        merged_by_id[item["id"]] = {
            "id": item["id"],
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "published_at": item.get("published_at") or "",
            "summary": item.get("summary") or "",
            "score": item.get("score", 0.0),
            "match_type": "semantic",
        }

    for item in keyword_hits:
        aid = item["id"]
        if aid in merged_by_id:
            merged_by_id[aid]["match_type"] = "semantic+keyword"
        else:
            merged_by_id[aid] = {
                "id": aid,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "published_at": item.get("published_at") or "",
                "summary": item.get("summary") or (item.get("content") or "")[:400],
                "score": 0.30,
                "match_type": "keyword",
            }

    ranked = sorted(merged_by_id.values(), key=lambda x: x["score"], reverse=True)[:6]
    # Order retrieved precedents chronologically using parsed UTC timestamps (oldest -> newest)
    chronological = sorted(
        ranked,
        key=lambda x: (_parse_pub_date(x.get("published_at") or ""), x["id"]),
    )
    return {"retrieved_articles": chronological}


def _build_verified_milestones(state: ContextState) -> list[dict]:
    """Build strictly grounded chronological milestones from archive hits + current story."""
    limit = get_runtime_settings().context_max_precedents
    precedents = state.get("retrieved_articles", [])
    milestones: list[dict] = []
    for item in precedents[:limit]:
        milestones.append({
            "date": _format_display_date(item.get("published_at") or "", fallback="Earlier"),
            "headline": item.get("title", "Related Dispatch"),
            "summary": _first_sentences(item.get("summary") or item.get("title", "")),
            "source_url": item.get("url", ""),
            "article_id": item.get("id"),
        })

    milestones.append({
        "date": _format_display_date(state.get("published_at") or "", fallback="Latest"),
        "headline": state["title"],
        "summary": _first_sentences(state.get("summary") or state.get("content", "")),
        "source_url": state.get("url", ""),
        "article_id": state["article_id"],
    })
    return milestones


def _build_fallback_context(state: ContextState) -> tuple[str, list[dict]]:
    """Construct clean timeline directly from retrieved articles and current dispatch."""
    precedents = state.get("retrieved_articles", [])
    milestones = _build_verified_milestones(state)

    entities_str = ", ".join(state.get("entities", [])[:3]) or "this development"
    if precedents:
        story_arc = (
            f"This story connects to {len(precedents)} related prior dispatches involving {entities_str}, "
            f"tracing how earlier reporting led up to today's update: {state['title']}."
        )
    else:
        story_arc = (
            f"Today's report on {entities_str} marks an emerging development in our archive. "
            f"Future dispatches on these entities will automatically link into this chronological timeline."
        )
    return story_arc, milestones


def _clean_prose_arc(raw_text: str) -> str:
    """Strip markdown fences or accidental braces from plain-prose story arc."""
    cleaned = re.sub(
        r"^```(?:text|markdown|json)?\s*|\s*```$", "", (raw_text or "").strip(), flags=re.IGNORECASE
    ).strip()
    return cleaned.strip('"\' \n')


def stitcher_node(state: ContextState) -> dict:
    """Node 3: Build verified chronological milestones and synthesize cohesive story arc prose."""
    precedents = state.get("retrieved_articles", [])
    milestones = _build_verified_milestones(state)

    critique_note = ""
    if state.get("critique"):
        critique_note = (
            f"\n\nREVISION REQUIRED:\n{state['critique']}\n"
            "Write plain prose sentences only (no JSON, no braces, no bullet lists).\n"
        )

    if precedents:
        limit = get_runtime_settings().context_max_precedents
        timeline_notes = "\n".join(
            f"- [{_format_display_date(p.get('published_at') or '', 'Earlier')}] {p['title']}: "
            f"{_first_sentences(p.get('summary') or '', max_chars=200)}"
            for p in precedents[:limit]
        )
        system_prompt = (
            "You are an investigative news editor. Synthesize the chronological news progression below into "
            "2 to 3 concise, analytical plain-prose sentences explaining how prior events led to today's story "
            "and what is at stake next. Do NOT output JSON, markdown headings, or bullet points—just plain sentences."
        )
        user_prompt = (
            f"PRIOR COVERAGE:\n{timeline_notes}\n\n"
            f"LATEST STORY ({_format_display_date(state.get('published_at') or '', 'Latest')}):\n"
            f"{state['title']}: {_first_sentences(state.get('summary') or state.get('content', ''), max_chars=360)}"
            f"{critique_note}"
        )
        max_toks = 180
    else:
        system_prompt = (
            "You are an investigative news editor. Write 2 to 3 concise, plain-prose sentences explaining the "
            "broader background context leading up to this story and why it matters next. "
            "Do NOT output JSON, markdown headings, or bullet points—just plain sentences."
        )
        user_prompt = (
            f"TITLE: {state['title']}\n"
            f"TEXT: {(state.get('summary') or state.get('content', ''))[:1600]}"
            f"{critique_note}"
        )
        max_toks = 220

    story_arc = ""
    try:
        raw = _call_qwen(system_prompt, user_prompt, max_tokens=max_toks, temperature=0.3)
        story_arc = _clean_prose_arc(raw)
    except Exception as e:
        logger.warning(f"[-] Stitcher node error: {e}")

    if not story_arc:
        story_arc, _ = _build_fallback_context(state)

    return {"story_arc": story_arc, "milestones": milestones}


def critic_node(state: ContextState) -> dict:
    """Node 4: Verify timeline structure, strip hallucinated URLs/IDs, and trigger <=1 revision."""
    issues: list[str] = []
    story_arc = (state.get("story_arc") or "").strip()
    if len(story_arc) < 40:
        issues.append("'story_arc' must be at least 2 complete sentences.")
    if "{" in story_arc or "```" in story_arc:
        issues.append("'story_arc' must be plain prose without JSON braces or markdown fences.")

    allowed_urls = {state.get("url", "")} | {
        a.get("url", "") for a in state.get("retrieved_articles", []) if a.get("url")
    }
    allowed_urls.discard("")
    allowed_ids = {state["article_id"]} | {a["id"] for a in state.get("retrieved_articles", [])}

    sanitized: list[dict] = []
    for item in state.get("milestones", []):
        if not isinstance(item, dict):
            continue
        date = str(item.get("date", "")).strip()
        headline = str(item.get("headline", "")).strip()
        summary = str(item.get("summary", "")).strip()
        if not (date and headline and summary):
            continue

        raw_url = str(item.get("source_url") or "").strip()
        clean_url = raw_url if raw_url in allowed_urls else ""

        raw_aid = item.get("article_id")
        clean_aid = raw_aid if isinstance(raw_aid, int) and raw_aid in allowed_ids else None

        sanitized.append({
            "date": date,
            "headline": headline,
            "summary": summary,
            "source_url": clean_url,
            "article_id": clean_aid,
        })

    if not sanitized:
        issues.append("'milestones' must contain at least 1 valid milestone.")

    revision_count = state.get("revision_count", 0)
    if issues and revision_count < 1:
        return {
            "passed": False,
            "critique": " ".join(issues),
            "revision_count": revision_count + 1,
        }

    # Final safety fallback after max revision attempts
    if not sanitized or len(story_arc) < 20 or "{" in story_arc or "```" in story_arc:
        fallback_arc, fallback_milestones = _build_fallback_context(state)
        story_arc = fallback_arc
        sanitized = sanitized or fallback_milestones

    return {
        "story_arc": story_arc,
        "milestones": sanitized,
        "critique": "",
        "passed": True,
    }


def should_continue(state: ContextState) -> str:
    """Conditional edge router: loop back to stitcher at most once on critic rejection."""
    if not state.get("passed", True) and state.get("revision_count", 0) <= 1:
        return "stitcher"
    return END


def _compile_context_graph():
    builder = StateGraph(ContextState)
    builder.add_node("planner", planner_node)
    builder.add_node("historian", historian_node)
    builder.add_node("stitcher", stitcher_node)
    builder.add_node("critic", critic_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "historian")
    builder.add_edge("historian", "stitcher")
    builder.add_edge("stitcher", "critic")
    builder.add_conditional_edges(
        "critic",
        should_continue,
        {"stitcher": "stitcher", END: END},
    )
    return builder.compile()


_context_graph = _compile_context_graph()


def build_historical_context(article: dict) -> dict:
    """Run the 4-node LangGraph workflow to generate historical context for an article."""
    initial_state: ContextState = {
        "article_id": article["id"],
        "title": article.get("title", ""),
        "content": article.get("content") or "",
        "summary": article.get("summary") or "",
        "published_at": article.get("published_at") or "",
        "url": article.get("url") or "",
        "entities": [],
        "search_queries": [],
        "retrieved_articles": [],
        "story_arc": "",
        "milestones": [],
        "critique": "",
        "passed": False,
        "revision_count": 0,
    }

    final_state = _context_graph.invoke(initial_state)
    return {
        "article_id": article["id"],
        "story_arc": final_state.get("story_arc", ""),
        "entities": final_state.get("entities", []),
        "milestones": final_state.get("milestones", []),
        "related_count": len(final_state.get("retrieved_articles", [])),
        "revisions": final_state.get("revision_count", 0),
    }
