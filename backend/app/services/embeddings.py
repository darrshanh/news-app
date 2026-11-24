"""CPU-lightweight semantic embedding service for historical context retrieval.

Uses sentence-transformers (all-MiniLM-L6-v2) on CPU so 100% of GPU VRAM stays
dedicated to Qwen 2.5 3B and Kokoro TTS.
"""

import logging
import os
import threading
from typing import Optional

import numpy as np

from backend.app.core.database import (
    get_articles_for_embedding,
    save_article_embedding,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Singleton wrapper around SentenceTransformer for article similarity search."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self._load_attempted = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> bool:
        if self.model is not None:
            return True
        if self._load_attempted:
            return False

        with self._lock:
            if self.model is not None:
                return True
            if self._load_attempted:
                return False
            self._load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"[*] Loading CPU embedding model ({self.model_name})...")
                prev_offline = os.environ.get("HF_HUB_OFFLINE")
                try:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    self.model = SentenceTransformer(
                        self.model_name, device="cpu", local_files_only=True
                    )
                except Exception:
                    if prev_offline is None:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    else:
                        os.environ["HF_HUB_OFFLINE"] = prev_offline
                    self.model = SentenceTransformer(self.model_name, device="cpu")
                finally:
                    if prev_offline is None:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    else:
                        os.environ["HF_HUB_OFFLINE"] = prev_offline
                logger.info("[+] Embedding model ready on CPU.")
                return True
            except Exception as e:
                logger.warning(
                    f"[-] Failed to load embedding model '{self.model_name}': {e}. "
                    "Semantic similarity disabled; falling back to keyword search."
                )
                return False

    def embed(self, text: str) -> Optional[np.ndarray]:
        """Return an L2-normalized float32 embedding vector for text."""
        if not text or not text.strip():
            return None
        if not self._ensure_loaded():
            return None
        with self._lock:
            vec = self.model.encode(
                text.strip(),
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return np.asarray(vec, dtype=np.float32)

    @staticmethod
    def to_bytes(vec: np.ndarray) -> bytes:
        return np.asarray(vec, dtype=np.float32).tobytes()

    @staticmethod
    def from_bytes(blob: bytes) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32)

    def embed_and_store_article(
        self,
        article_id: int,
        title: str,
        summary: str = "",
        content: str = "",
    ) -> Optional[np.ndarray]:
        """Compute and persist embedding vector for a single article."""
        body = summary.strip() or (content or "")[:600].strip()
        combined = f"{title}. {body}".strip()
        vec = self.embed(combined)
        if vec is not None:
            save_article_embedding(article_id, self.to_bytes(vec))
        return vec

    def find_similar_articles(
        self,
        query_text: str,
        exclude_id: Optional[int] = None,
        top_k: int = 5,
        min_score: float = 0.35,
    ) -> list[dict]:
        """Return top-k semantically similar articles using cosine similarity.

        Lazily backfills any DB rows missing stored embeddings.
        """
        query_vec = self.embed(query_text)
        if query_vec is None:
            return []

        rows = get_articles_for_embedding(exclude_id=exclude_id)
        scored: list[dict] = []

        for row in rows:
            blob = row.get("embedding")
            row_vec: Optional[np.ndarray] = None
            if blob:
                row_vec = self.from_bytes(blob)
            else:
                row_vec = self.embed_and_store_article(
                    article_id=row["id"],
                    title=row.get("title", ""),
                    summary=row.get("summary") or "",
                    content=row.get("content") or "",
                )

            if row_vec is None or len(row_vec) != len(query_vec):
                continue

            score = float(np.dot(query_vec, row_vec))
            if score >= min_score:
                scored.append({
                    "id": row["id"],
                    "title": row.get("title", ""),
                    "url": row.get("url", ""),
                    "published_at": row.get("published_at", ""),
                    "summary": row.get("summary") or (row.get("content") or "")[:400],
                    "score": round(score, 4),
                })

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]


_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Singleton getter for EmbeddingService."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
