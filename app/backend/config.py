import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
INDEX_DIR = BASE_DIR / "data" / "index"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1"

# free models that support tool calling, tried in this order
MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
]

EMBED_MODEL = "BAAI/bge-small-en-v1.5"

MAX_STEPS = 6
REQUESTS_PER_MINUTE = 8
