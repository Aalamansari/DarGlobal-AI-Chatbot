import json
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend import data, retrieval
from app.backend.agent import run_agent
from app.backend.config import BASE_DIR, REQUESTS_PER_MINUTE

STATIC_DIR = BASE_DIR / "app" / "web" / "static"

app = FastAPI(title="Property Assistant")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# answers to first questions are cached to save the free model quota
answer_cache = {}
request_times = {}


class ChatRequest(BaseModel):
    message: str
    history: list = []


@app.on_event("startup")
def startup():
    retrieval.search("test", k=1)
    print(f"Loaded {len(data.listings)} listings, {len(data.projects)} projects, {len(data.chunks)} chunks")


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
        return JSONResponse({"error": "Too many requests, please wait a minute."}, status_code=429)

    cache_key = question.lower()
    use_cache = len(body.history) == 0

    def stream():
        if use_cache and cache_key in answer_cache:
            event = dict(answer_cache[cache_key])
            event["cached"] = True
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            return

        for event in run_agent(body.history, question):
            if event["type"] == "tool":
                print("Tool call:", event["name"], event["args"])
            if event["type"] == "answer" and use_cache:
                if len(answer_cache) > 200:
                    answer_cache.clear()
                answer_cache[cache_key] = event
            yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
