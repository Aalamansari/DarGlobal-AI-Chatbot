import re

import numpy as np
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi

from app.backend import data
from app.backend.config import EMBED_MODEL, INDEX_DIR

# filled by load() when the app starts
embedder = None
bm25 = None
vectors = None


def tokenize(text):
    # keeping english and arabic words
    return re.findall(r"[\w؀-ۿ]+", text.lower())


def embed(texts):
    result = np.array(list(embedder.embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    
    return result / norms


def load_vectors():
    path = INDEX_DIR / "vectors.npy"
    
    if path.exists():
        saved = np.load(path)
        if len(saved) == len(data.chunks):
            return saved
    print("Index missing or out of date, building it now")
    
    return embed([chunk["text"] for chunk in data.chunks])


def load():
    global embedder, bm25, vectors

    embedder = TextEmbedding(EMBED_MODEL, cache_dir=str(INDEX_DIR / "models"))

    bm25_docs = []
    for chunk in data.chunks:
        bm25_docs.append(tokenize(chunk["text"] + " " + (chunk["title"] or "")))
    bm25 = BM25Okapi(bm25_docs)

    vectors = load_vectors()


def search(query, k=6, sources=None):
    allowed = []
    for i, chunk in enumerate(data.chunks):
        if sources is None or chunk["source"] in sources:
            allowed.append(i)
    if not allowed:
        return []

    bm25_scores = bm25.get_scores(tokenize(query))
    vector_scores = vectors @ embed([query])[0]

    bm25_top = sorted(allowed, key=lambda i: bm25_scores[i], reverse=True)[:50]
    vector_top = sorted(allowed, key=lambda i: vector_scores[i], reverse=True)[:50]

    # combine both rankings (reciprocal rank fusion)
    scores = {}
    for ranking in [bm25_top, vector_top]:
        for rank, i in enumerate(ranking):
            scores[i] = scores.get(i, 0) + 1 / (60 + rank)

    best = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
    
    return [data.chunks[i] for i in best]