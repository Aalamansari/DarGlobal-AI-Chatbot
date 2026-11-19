import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "index"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Free OpenRouter models that support tool calling, tried in order.
# If one is rate-limited or down, the agent falls through to the next.
MODELS = [
    m.strip()
    for m in os.getenv(
        "OPENROUTER_MODELS",
        "google/gemma-4-31b-it:free,"
        "nvidia/nemotron-3-ultra-550b-a55b:free,"
        "google/gemma-4-26b-a4b-it:free,"
        "nvidia/nemotron-3.5-super-vl:free",
    ).split(",")
    if m.strip()
]

# Small (~67 MB quantised) so the container fits free 512 MB instances. Arabic questions
# still work: the LLM writes tool arguments/search queries in English, and BM25 indexes
# Arabic tokens. Swap to a multilingual model when memory allows.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

MAX_TOOL_ROUNDS = 6
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "8"))
