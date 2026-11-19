"""Pre-compute chunk embeddings so the container starts fast. Run at Docker build time."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.config import INDEX_DIR  # noqa: E402
from app.data import chunks  # noqa: E402
from app.retrieval import build_vectors, corpus_hash  # noqa: E402

INDEX_DIR.mkdir(parents=True, exist_ok=True)
vecs = build_vectors()
np.save(INDEX_DIR / "vectors.npy", vecs)
(INDEX_DIR / "meta.json").write_text(json.dumps({"hash": corpus_hash(), "n": len(chunks())}))
print(f"Indexed {len(chunks())} chunks -> {vecs.shape}")
