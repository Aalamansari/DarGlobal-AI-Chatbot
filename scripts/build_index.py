import numpy as np

from app.backend import data, retrieval
from app.backend.config import INDEX_DIR

INDEX_DIR.mkdir(parents=True, exist_ok=True)

texts = [chunk["text"] for chunk in data.chunks]
vectors = retrieval.embed(texts)
np.save(INDEX_DIR / "vectors.npy", vectors)

print(f"Saved {len(vectors)} vectors to {INDEX_DIR}")
