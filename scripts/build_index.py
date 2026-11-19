import numpy as np

from app.backend import data, retrieval
from app.backend.config import INDEX_DIR

INDEX_DIR.mkdir(parents=True, exist_ok=True)
index_file = INDEX_DIR / "vectors.npy"

# remove the old index so load() always builds a fresh one
if index_file.exists():
    index_file.unlink()

data.load()
retrieval.load()
np.save(index_file, retrieval.vectors)

print(f"Saved {len(retrieval.vectors)} vectors to {INDEX_DIR}")
