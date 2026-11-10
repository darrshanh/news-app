import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.app.models.article import ArticleCreate
from typing import Optional

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
    table_create_stmt = "CREATE TABLE IF NOT EXISTS articles(" \
    "id INTEGER PRIMARY KEY AUTOINCREMENT," \
    "title TEXT NOT NULL," \
    "url TEXT UNIQUE NOT NULL," \
    "published_at TEXT," \
    "summary TEXT," \
    "content TEXT," \
    "takeaways TEXT," \
    "audio_script TEXT," \
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
    conn.execute(table_create_stmt)
    conn.commit()
    conn.close()

def save_article(article: ArticleCreate) -> Optional[int]:
    table_insert_stmt = "INSERT OR IGNORE INTO articles (title, url, published_at, summary, content, takeaways, audio_script) VALUES (?, ?, ?, ?, ?, ?, ?)"
    conn = get_db_connection()
    cursor = conn.execute(
        table_insert_stmt,
        (article.title, article.url, article.published_at, article.summary, article.content, article.takeaways, article.audio_script)
    )
    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()

    return inserted_id if inserted_id else None

def get_articles(limit: int = 20) -> list[dict]:
    conn = get_db_connection()
    table_query_stmt = "SELECT * FROM articles ORDER BY id DESC LIMIT ?"
    cursor = conn.execute(
        table_query_stmt,
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def get_article_by_id(article_id: int) -> Optional[dict]:
    conn = get_db_connection()
    table_query_stmt = "SELECT * FROM articles WHERE id = ?"
    cursor = conn.execute(
        table_query_stmt,
        (article_id,)
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None

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