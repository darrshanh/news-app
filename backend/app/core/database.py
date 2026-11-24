import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.app.models.article import ArticleCreate
from typing import Optional

ARTICLE_PUBLIC_COLUMNS = (
    "id, title, url, published_at, summary, content, "
    "takeaways, audio_script, historical_context, created_at"
)


def get_db_connection():
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    db_file = data_dir / "news_agent.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = get_db_connection()
    table_create_stmt = (
        "CREATE TABLE IF NOT EXISTS articles("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "title TEXT NOT NULL,"
        "url TEXT UNIQUE NOT NULL,"
        "published_at TEXT,"
        "summary TEXT,"
        "content TEXT,"
        "takeaways TEXT,"
        "audio_script TEXT,"
        "embedding BLOB,"
        "historical_context TEXT,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
    )
    conn.execute(table_create_stmt)

    # Safely migrate existing tables lacking embedding / historical_context columns
    existing_cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    if "embedding" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN embedding BLOB")
    if "historical_context" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN historical_context TEXT")

    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_settings("
        "key TEXT PRIMARY KEY,"
        "value TEXT NOT NULL);"
    )

    conn.commit()
    conn.close()


def save_article(article: ArticleCreate) -> Optional[int]:
    table_insert_stmt = (
        "INSERT OR IGNORE INTO articles "
        "(title, url, published_at, summary, content, takeaways, audio_script) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    conn = get_db_connection()
    cursor = conn.execute(
        table_insert_stmt,
        (
            article.title,
            article.url,
            article.published_at,
            article.summary,
            article.content,
            article.takeaways,
            article.audio_script,
        ),
    )
    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()

    return inserted_id if inserted_id else None


def get_articles(limit: int = 20, since_id: Optional[int] = None) -> list[dict]:
    conn = get_db_connection()
    if since_id is not None:
        table_query_stmt = (
            f"SELECT {ARTICLE_PUBLIC_COLUMNS} FROM articles "
            "WHERE id > ? ORDER BY id DESC LIMIT ?"
        )
        cursor = conn.execute(table_query_stmt, (since_id, limit))
    else:
        table_query_stmt = (
            f"SELECT {ARTICLE_PUBLIC_COLUMNS} FROM articles "
            "ORDER BY id DESC LIMIT ?"
        )
        cursor = conn.execute(table_query_stmt, (limit,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_article_by_id(article_id: int) -> Optional[dict]:
    conn = get_db_connection()
    table_query_stmt = f"SELECT {ARTICLE_PUBLIC_COLUMNS} FROM articles WHERE id = ?"
    cursor = conn.execute(table_query_stmt, (article_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def save_article_embedding(article_id: int, embedding_bytes: bytes) -> None:
    """Persist serialized float32 embedding vector for an article."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE articles SET embedding = ? WHERE id = ?",
        (sqlite3.Binary(embedding_bytes), article_id),
    )
    conn.commit()
    conn.close()


def get_articles_for_embedding(exclude_id: Optional[int] = None) -> list[dict]:
    """Fetch article text metadata and optional embedding BLOB for vector search/backfill."""
    conn = get_db_connection()
    if exclude_id is not None:
        cursor = conn.execute(
            "SELECT id, title, url, published_at, summary, content, embedding "
            "FROM articles WHERE id != ? ORDER BY id DESC",
            (exclude_id,),
        )
    else:
        cursor = conn.execute(
            "SELECT id, title, url, published_at, summary, content, embedding "
            "FROM articles ORDER BY id DESC"
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_article_context(article_id: int, context_json: str) -> None:
    """Persist cached LangGraph historical context JSON on an article row."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE articles SET historical_context = ? WHERE id = ?",
        (context_json, article_id),
    )
    conn.commit()
    conn.close()


def search_articles_by_keywords(
    keywords: list[str],
    exclude_id: Optional[int] = None,
    limit: int = 8,
) -> list[dict]:
    """Parameterized keyword search across title, summary, and content."""
    clean_terms = []
    seen = set()
    for kw in keywords:
        term = str(kw).strip()
        if len(term) >= 2 and term.lower() not in seen:
            seen.add(term.lower())
            clean_terms.append(term)
    if not clean_terms:
        return []

    like_clauses = []
    params: list[object] = []
    for term in clean_terms[:8]:
        pattern = f"%{term}%"
        like_clauses.append("(title LIKE ? OR summary LIKE ? OR content LIKE ?)")
        params.extend([pattern, pattern, pattern])

    where_sql = "(" + " OR ".join(like_clauses) + ")"
    if exclude_id is not None:
        where_sql = f"id != ? AND {where_sql}"
        params.insert(0, exclude_id)

    params.append(limit)
    sql = (
        f"SELECT {ARTICLE_PUBLIC_COLUMNS} FROM articles "
        f"WHERE {where_sql} ORDER BY id DESC LIMIT ?"
    )
    conn = get_db_connection()
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_setting_raw(key: str) -> Optional[str]:
    """Read a JSON/string setting value by key from SQLite."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def save_setting_raw(key: str, value: str) -> None:
    """Insert or update a JSON/string setting value in SQLite."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def article_exists(url: str) -> bool:
    conn = get_db_connection()
    table_query_stmt = "SELECT 1 FROM ARTICLES WHERE url = ?"
    cursor = conn.execute(
        table_query_stmt,
        (url,)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None