import json
import logging
import time
from collections import OrderedDict, defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, retrieval
from .config import RATE_LIMIT_PER_MIN, ROOT
from .data import chunks, darglobal_projects, listings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="Property Assistant")
STATIC = ROOT / "app" / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Free models have tight daily quotas, so repeated first-turn questions are served from cache.
_cache: "OrderedDict[str, dict]" = OrderedDict()
_hits: "defaultdict[str, deque]" = defaultdict(deque)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[dict] = []


@app.on_event("startup")
def warm():
    t = time.time()
    retrieval.search("warm up", k=1)
    log.info("Loaded %d listings, %d projects, %d chunks in %.1fs",
             len(listings()), len(darglobal_projects()), len(chunks()), time.time() - t)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/stats")
def stats():
    ls = listings()
    return {"snapshot": agent.SNAPSHOT, "wasalt_listings": len(ls),
            "cities": len({l["city"] for l in ls if l["city"]}),
            "darglobal_projects": len(darglobal_projects()), "chunks": len(chunks())}


def _rate_limited(ip):
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        return True
    q.append(now)
    return False


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    if _rate_limited(ip):
        return JSONResponse({"error": "Too many requests, please wait a minute."}, status_code=429)

    key = body.message.strip().lower()
    cacheable = not body.history

    def stream():
        if cacheable and key in _cache:
            _cache.move_to_end(key)
            yield f"data: {json.dumps({**_cache[key], 'cached': True})}\n\n"
            return
        for ev in agent.run(body.history, body.message.strip()):
            if ev["type"] == "answer" and cacheable:
                _cache[key] = ev
                if len(_cache) > 200:
                    _cache.popitem(last=False)
            if ev["type"] == "tool":
                log.info("tool %s %s", ev["name"], ev["args"])
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
