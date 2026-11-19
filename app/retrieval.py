"""Hybrid retrieval: BM25 (exact words like project names) + multilingual embeddings
(meaning, and Arabic queries), merged with reciprocal rank fusion.

Embeddings are computed once at Docker build time (scripts/build_index.py) and loaded
from disk, so the container starts fast and never re-embeds at runtime.
"""
import hashlib
import json
import logging
import re
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from .config import EMBED_MODEL, INDEX_DIR
from .data import chunks

log = logging.getLogger(__name__)


def _tok(text):
    return re.findall(r"[\w؀-ۿ]+", text.lower())


def corpus_hash():
    h = hashlib.sha1()
    for c in chunks():
        h.update(c["text"].encode("utf-8"))
    return h.hexdigest()[:16]


@lru_cache
def _bm25():
    return BM25Okapi([_tok(c["text"] + " " + (c.get("title") or "")) for c in chunks()])


@lru_cache
def _embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(EMBED_MODEL, cache_dir=str(INDEX_DIR / "models"))


@lru_cache
def _vectors():
    path, meta = INDEX_DIR / "vectors.npy", INDEX_DIR / "meta.json"
    if path.exists() and meta.exists():
        if json.loads(meta.read_text())["hash"] == corpus_hash():
            return np.load(path)
        log.warning("Index is stale; rebuilding in memory")
    try:
        return build_vectors()
    except Exception as e:  # retrieval still works on BM25 alone
        log.error("Embeddings unavailable, using BM25 only: %s", e)
        return None


def build_vectors():
    texts = [c["text"] for c in chunks()]
    vecs = np.array(list(_embedder().embed(texts)), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    return vecs


def search(query, k=6, sources=None):
    docs = chunks()
    if not docs:
        return []
    allowed = [i for i, c in enumerate(docs) if not sources or c["source"] in sources]
    if not allowed:
        return []
    allowed_set = set(allowed)

    rankings = []
    bm = _bm25().get_scores(_tok(query))
    rankings.append(sorted(allowed, key=lambda i: -bm[i])[:50])

    vecs = _vectors()
    if vecs is not None:
        q = np.array(list(_embedder().embed([query]))[0], dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sims = vecs @ q
        rankings.append(sorted(allowed, key=lambda i: -sims[i])[:50])

    fused = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking):
            if i in allowed_set:
                fused[i] = fused.get(i, 0) + 1 / (60 + rank)
    top = sorted(fused, key=lambda i: -fused[i])[:k]
    return [docs[i] for i in top]
