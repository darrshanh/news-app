"""Contextual Multi-Armed Bandit (LinUCB) preference ranker.

Learns user topic preferences sample-efficiently from explicit Likes (+1.0) and
Dislikes (-0.5) using ridge regression over 384-D normalized MiniLM embeddings:

    A = lambda * I_d + sum(x_i * x_i^T)
    b = sum(r_i * x_i)
    theta = A^{-1} * b
    UCB(x) = x^T * theta + alpha * sqrt(x^T * A^{-1} * x)
"""

import logging
import threading
from typing import Optional

import numpy as np

from backend.app.core.database import (
    get_all_feedback_map,
    get_feedback_with_embeddings,
    upsert_article_feedback,
)
from backend.app.core.settings_store import get_runtime_settings
from backend.app.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
LAMBDA_REG = 1.0
REWARD_MAP = {
    "up": 1.0,
    "down": -0.5,
}

TOPIC_ANCHORS = (
    (
        "AI & Local LLMs",
        "Artificial intelligence, large language models, local inference, neural networks, and AI agents",
    ),
    (
        "Cybersecurity & Systems",
        "Cybersecurity vulnerabilities, zero-day exploits, ransomware campaigns, Linux systems, and security",
    ),
    (
        "Semiconductors & Hardware",
        "Semiconductors, Nvidia GPUs, chips, silicon manufacturing, data center compute, and hardware",
    ),
    (
        "Startups & Tech Markets",
        "Startups, venture capital, corporate governance, executive leadership, stocks, and tech business",
    ),
    (
        "Science & Space",
        "Astronomy, space telescopes, biotech, physics, clean energy transitions, and scientific research",
    ),
)


class LinUCBRanker:
    """Thread-safe Disjoint/Linear UCB contextual bandit backed by SQLite feedback."""

    def __init__(self, dim: int = EMBEDDING_DIM, reg_lambda: float = LAMBDA_REG):
        self.dim = dim
        self.reg_lambda = reg_lambda
        self._lock = threading.Lock()
        self._initialized = False
        self._A = self.reg_lambda * np.eye(self.dim, dtype=np.float64)
        self._A_inv = (1.0 / self.reg_lambda) * np.eye(self.dim, dtype=np.float64)
        self._b = np.zeros(self.dim, dtype=np.float64)
        self._theta = np.zeros(self.dim, dtype=np.float64)
        self._total_likes = 0
        self._total_dislikes = 0
        self._topic_vecs: Optional[list[tuple[str, np.ndarray]]] = None

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.rebuild_from_db()

    def _ensure_topic_anchors(self) -> list[tuple[str, np.ndarray]]:
        if self._topic_vecs is not None:
            return self._topic_vecs

        svc = get_embedding_service()
        vecs: list[tuple[str, np.ndarray]] = []
        for label, prompt in TOPIC_ANCHORS:
            vec = svc.embed(prompt)
            if vec is not None and len(vec) == self.dim:
                vecs.append((label, np.asarray(vec, dtype=np.float64)))
        if vecs:
            self._topic_vecs = vecs
        return vecs

    def _solve_state(
        self, A: np.ndarray, b: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute regularized inverse A^{-1} and ridge weights theta safely."""
        A_inv = np.linalg.inv(A)
        theta = A_inv @ b
        return A_inv, theta

    def rebuild_from_db(self) -> None:
        """Recompute A, A^{-1}, b, and theta from all persisted article_feedback rows."""
        rows = get_feedback_with_embeddings()
        svc = get_embedding_service()

        A = self.reg_lambda * np.eye(self.dim, dtype=np.float64)
        b = np.zeros(self.dim, dtype=np.float64)
        likes = 0
        dislikes = 0

        for row in rows:
            vote = row.get("vote")
            reward = float(row.get("reward", REWARD_MAP.get(vote, 0.0)))
            if vote == "up":
                likes += 1
            elif vote == "down":
                dislikes += 1

            blob = row.get("embedding")
            vec: Optional[np.ndarray] = None
            if blob:
                vec = svc.from_bytes(blob)
            else:
                vec = svc.embed_and_store_article(
                    article_id=row["article_id"],
                    title=row.get("title", ""),
                    summary=row.get("summary") or "",
                    content=row.get("content") or "",
                )

            if vec is None or len(vec) != self.dim:
                continue

            x = np.asarray(vec, dtype=np.float64)
            A += np.outer(x, x)
            b += reward * x

        A_inv, theta = self._solve_state(A, b)
        with self._lock:
            self._A = A
            self._A_inv = A_inv
            self._b = b
            self._theta = theta
            self._total_likes = likes
            self._total_dislikes = dislikes
            self._initialized = True

    def record_feedback(self, article_id: int, vote: Optional[str]) -> dict:
        """Persist Like ('up'), Dislike ('down'), or undo (None) and return updated radar."""
        if vote not in ("up", "down", None):
            raise ValueError("vote must be 'up', 'down', or null")

        reward = REWARD_MAP.get(vote, 0.0) if vote is not None else 0.0
        upsert_article_feedback(article_id=article_id, vote=vote, reward=reward)
        self.rebuild_from_db()
        return self.get_radar_stats()

    def _score_vector_locked(
        self, vec: np.ndarray, alpha: float
    ) -> tuple[float, float, float]:
        x = np.asarray(vec, dtype=np.float64)
        exploitation = float(np.dot(x, self._theta))
        variance = max(0.0, float(x @ self._A_inv @ x))
        exploration = float(alpha * np.sqrt(variance))
        return exploitation + exploration, exploitation, exploration

    def rank_articles(
        self,
        articles: list[dict],
        personalized: bool = True,
        alpha: Optional[float] = None,
    ) -> list[dict]:
        """Attach user_vote & UCB scores, strip BLOB embeddings, and optionally rank."""
        self._ensure_initialized()
        effective_alpha = (
            alpha if alpha is not None else get_runtime_settings().bandit_alpha
        )
        vote_map = get_all_feedback_map()
        svc = get_embedding_service()

        scored_items: list[dict] = []
        for raw in articles:
            item = dict(raw)
            blob = item.pop("embedding", None)
            aid = item["id"]
            item["user_vote"] = vote_map.get(aid)

            vec: Optional[np.ndarray] = None
            if blob:
                vec = svc.from_bytes(blob)
            elif svc._ensure_loaded():
                vec = svc.embed_and_store_article(
                    article_id=aid,
                    title=item.get("title", ""),
                    summary=item.get("summary") or "",
                    content=item.get("content") or "",
                )

            if vec is not None and len(vec) == self.dim:
                with self._lock:
                    ucb, exploit, explore = self._score_vector_locked(
                        vec, effective_alpha
                    )
            else:
                ucb, exploit, explore = 0.0, 0.0, 0.0

            item["ucb_score"] = round(ucb, 4)
            item["exploitation_score"] = round(exploit, 4)
            item["exploration_score"] = round(explore, 4)
            scored_items.append(item)

        with self._lock:
            has_votes = (self._total_likes + self._total_dislikes) > 0

        if personalized and has_votes:
            scored_items.sort(
                key=lambda x: (x["ucb_score"], x["id"]),
                reverse=True,
            )

        return scored_items

    def get_radar_stats(self, alpha: Optional[float] = None) -> dict:
        """Return live user affinity breakdown across curated editorial topics."""
        self._ensure_initialized()
        effective_alpha = (
            alpha if alpha is not None else get_runtime_settings().bandit_alpha
        )
        topic_vecs = self._ensure_topic_anchors()

        with self._lock:
            likes = self._total_likes
            dislikes = self._total_dislikes
            total_votes = likes + dislikes
            topics: list[dict] = []

            if topic_vecs:
                for label, vec in topic_vecs:
                    ucb, exploit, explore = self._score_vector_locked(
                        vec, effective_alpha
                    )
                    affinity_pct = int(
                        round(max(5.0, min(98.0, 50.0 + exploit * 60.0)))
                    )
                    topics.append({
                        "label": label,
                        "affinity_pct": affinity_pct,
                        "exploitation": round(exploit, 4),
                        "exploration": round(explore, 4),
                        "ucb_score": round(ucb, 4),
                    })
            else:
                for label, _ in TOPIC_ANCHORS:
                    topics.append({
                        "label": label,
                        "affinity_pct": 50,
                        "exploitation": 0.0,
                        "exploration": 0.0,
                        "ucb_score": 0.0,
                    })

        topics.sort(key=lambda t: t["affinity_pct"], reverse=True)
        return {
            "total_likes": likes,
            "total_dislikes": dislikes,
            "total_votes": total_votes,
            "alpha": round(float(effective_alpha), 2),
            "topics": topics,
        }


_bandit_ranker: Optional[LinUCBRanker] = None


def get_bandit_ranker() -> LinUCBRanker:
    """Singleton getter for LinUCBRanker."""
    global _bandit_ranker
    if _bandit_ranker is None:
        _bandit_ranker = LinUCBRanker()
    return _bandit_ranker
