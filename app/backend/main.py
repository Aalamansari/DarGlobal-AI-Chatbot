import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend import data, retrieval
from app.backend import observability as obs
from app.backend.agent import run_agent
from app.backend.config import BASE_DIR, REQUESTS_PER_MINUTE

STATIC_DIR = BASE_DIR / "app" / "web" / "static"


@asynccontextmanager
async def lifespan(app):
    # load data, search index and tracing once at startup
    data.load()
    retrieval.load()
    obs.setup()
    print(f"Loaded {len(data.listings)} listings, {len(data.projects)} projects, {len(data.chunks)} chunks")
    yield
    obs.flush()


app = FastAPI(title="DarGlobal Property Assistant", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# answers to first questions are cached to save the free model quota
answer_cache = {}
request_times = {}


class ChatRequest(BaseModel):
    message: str
    history: list = []


class FeedbackRequest(BaseModel):
    trace_id: str | None = None
    helpful: bool
    comment: str | None = None


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/stats")
def stats():
    cities = set()
    
    for listing in data.listings:
        if listing["city"]:
            cities.add(listing["city"])
    
    return {
        "snapshot": data.snapshot_date,
        "wasalt_listings": len(data.listings),
        "cities": len(cities),
        "darglobal_projects": len(data.projects),
        "chunks": len(data.chunks),
    }


@app.get("/api/metrics")
def metrics():
    return obs.get_metrics()


@app.post("/api/feedback")
def feedback(body: FeedbackRequest):
    if body.helpful:
        obs.count("thumbs_up")
        value = 1
    else:
        obs.count("thumbs_down")
        value = 0

    comment = None
    if body.comment:
        comment = body.comment[:500]

    obs.save_feedback(body.trace_id, value, comment)
    return {"ok": True}


def too_many_requests(ip):
    now = time.time()
    recent = [t for t in request_times.get(ip, []) if now - t < 60]
    
    if len(recent) >= REQUESTS_PER_MINUTE:
        request_times[ip] = recent
        return True
    
    recent.append(now)
    request_times[ip] = recent
    
    return False


def get_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    if request.client:
        return request.client.host
    
    return "unknown"


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request):
    question = body.message.strip()
    
    if not question or len(question) > 1000:
        return JSONResponse({"error": "Please send a question under 1000 characters."}, status_code=400)
    
    if too_many_requests(get_ip(request)):
        obs.count("rate_limited")
        return JSONResponse({"error": "Too many requests, please wait a minute."}, status_code=429)

    cache_key = question.lower()
    use_cache = len(body.history) == 0

    def stream():
        if use_cache and cache_key in answer_cache:
            obs.count("cached_answers")
            event = dict(answer_cache[cache_key])
            event["cached"] = True
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            return

        for event in run_agent(body.history, question):
            if event["type"] == "answer" and use_cache:
                if len(answer_cache) > 200:
                    answer_cache.clear()
                answer_cache[cache_key] = event
            yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
