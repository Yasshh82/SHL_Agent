"""
catalog_store.py
Loads shl_catalog.json and provides keyword-based retrieval using BM25.
No GPU, no embeddings model — fits comfortably in 8 GB RAM.
"""
from __future__ import annotations

import json
import math
import re
import string
from pathlib import Path
from typing import Optional

CATALOG_PATH = Path(__file__).parent / "shl_catalog.json"

# --------------------------------------------------------------------------- #
# Simple BM25 implementation (no external library needed)                     #
# --------------------------------------------------------------------------- #
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "be", "by", "this", "that", "it",
    "as", "from", "have", "has", "had", "will", "would", "can", "could",
    "do", "does", "did", "not", "no", "i", "we", "you", "they", "he", "she",
}

def tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t not in STOPWORDS and len(t) > 1]
    return tokens


class BM25:
    """Okapi BM25 over a list of documents."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.n = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / max(self.n, 1)

        # Build inverted index
        self.df: dict[str, int] = {}
        self.tf: list[dict[str, int]] = []
        for doc in corpus:
            freq: dict[str, int] = {}
            for token in doc:
                freq[token] = freq.get(token, 0) + 1
            self.tf.append(freq)
            for token in freq:
                self.df[token] = self.df.get(token, 0) + 1

    def score(self, query_tokens: list[str], doc_index: int) -> float:
        tf = self.tf[doc_index]
        dl = len(self.corpus[doc_index])
        score = 0.0
        for token in query_tokens:
            if token not in tf:
                continue
            idf = math.log((self.n - self.df.get(token, 0) + 0.5)
                           / (self.df.get(token, 0) + 0.5) + 1)
            tf_val = tf[token]
            score += idf * (tf_val * (self.k1 + 1)) / (
                tf_val + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            )
        return score

    def get_top_k(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        tokens = tokenize(query)
        scores = [(i, self.score(tokens, i)) for i in range(self.n)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in scores[:k] if s > 0]


# --------------------------------------------------------------------------- #
# CatalogStore                                                                 #
# --------------------------------------------------------------------------- #
class CatalogStore:
    """Loads the scraped catalog and wraps BM25 retrieval."""

    def __init__(self, catalog_path: Path = CATALOG_PATH):
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.products: list[dict] = raw
        self._build_index()

    def _build_index(self):
        corpus = []
        for p in self.products:
            doc_text = " ".join([
                p.get("name", ""),
                p.get("description", ""),
                " ".join(p.get("test_type_labels", [])),
            ])
            corpus.append(tokenize(doc_text))
        self.bm25 = BM25(corpus)

    def search(
        self,
        query: str,
        k: int = 10,
        type_filter: Optional[list[str]] = None,
        remote_only: bool = False,
    ) -> list[dict]:
        """Return up to k products matching the query, with optional filters."""
        hits = self.bm25.get_top_k(query, k=min(k * 3, len(self.products)))
        results = []
        for idx, _score in hits:
            p = self.products[idx]
            if remote_only and not p.get("remote_testing"):
                continue
            if type_filter:
                if not any(t in p.get("test_types", []) for t in type_filter):
                    continue
            results.append(p)
            if len(results) >= k:
                break
        return results

    def get_by_name(self, name: str) -> Optional[dict]:
        """Find a product by name — exact substring first, then token overlap."""
        name_lower = name.lower().strip()
        if not name_lower:
            return None
        # Pass 1: exact substring match
        for p in self.products:
            if name_lower in p["name"].lower():
                return p
        # Pass 2: reverse — catalog name is substring of query name
        for p in self.products:
            if p["name"].lower() in name_lower:
                return p
        # Pass 3: token overlap (>=50% of catalog name tokens found in query)
        import re as _re
        query_tokens = set(_re.sub(r"[^a-z0-9]", " ", name_lower).split())
        best_p, best_score = None, 0.0
        for p in self.products:
            cat_tokens = set(_re.sub(r"[^a-z0-9]", " ", p["name"].lower()).split())
            cat_tokens -= {"new", "a", "an", "the", "and", "or"}
            if not cat_tokens:
                continue
            overlap = len(query_tokens & cat_tokens) / len(cat_tokens)
            if overlap > best_score:
                best_score, best_p = overlap, p
        if best_score >= 0.6:
            return best_p
        return None

    def get_by_url_slug(self, url: str) -> Optional[dict]:
        """Try to match a hallucinated URL by its path slug."""
        import re as _re
        slug = url.rstrip("/").split("/")[-1].lower()
        if not slug:
            return None
        # Direct slug match
        for p in self.products:
            p_slug = p["url"].rstrip("/").split("/")[-1].lower()
            if slug == p_slug:
                return p
        # Partial slug (LLM may shorten/alter it)
        for p in self.products:
            p_slug = p["url"].rstrip("/").split("/")[-1].lower()
            if slug in p_slug or p_slug in slug:
                return p
        return None

    def get_all(self) -> list[dict]:
        return self.products

    def summary_for_llm(self, products: list[dict]) -> str:
        """Format a list of products as compact text for LLM context."""
        lines = []
        for p in products:
            types = ", ".join(p.get("test_type_labels") or p.get("test_types", []))
            desc = p.get("description", "")[:200]
            lines.append(
                f"- {p['name']} | Types: {types} | URL: {p['url']}\n"
                f"  {desc}"
            )
        return "\n".join(lines)


# Singleton — loaded once at import time
_store: Optional[CatalogStore] = None


def get_store() -> CatalogStore:
    global _store
    if _store is None:
        _store = CatalogStore()
    return _store