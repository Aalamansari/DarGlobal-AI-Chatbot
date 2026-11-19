"""Tool-calling agent loop over OpenRouter free models, with model fallback.

Plain loop on purpose (no framework): every step is visible and easy to reason about.
  user question -> model picks tools -> we run them -> results go back -> repeat -> answer
"""
import json
import logging
import time

from openai import OpenAI

from .config import MAX_TOOL_ROUNDS, MODELS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, RAW_DIR
from .data import listings_by_id
from .tools import REGISTRY, SCHEMAS

log = logging.getLogger(__name__)

try:
    SNAPSHOT = json.loads((RAW_DIR / "meta.json").read_text())["collected_on"]
except Exception:
    SNAPSHOT = "unknown date"

SYSTEM_PROMPT = f"""You are a property assistant built on public data scraped on {SNAPSHOT} from two sites:
- Dar Global (darglobal.co.uk): an international luxury real-estate developer (projects in places like Dubai, London, Oman, Saudi Arabia, Spain, Qatar, Bosnia).
- Wasalt (wasalt.sa): a Saudi property marketplace with listings for sale and rent.

Rules:
1. Always use tools to get facts. Never invent prices, projects, amenities or listing details.
2. Pick tools deliberately: structured filters -> search_listings; prices/market comparisons -> market_stats;
   Dar Global developments -> list_darglobal_projects and/or search_knowledge(source="darglobal");
   open questions -> search_knowledge. You may call several tools before answering.
3. If the tools return nothing relevant, say so plainly and suggest what the user could ask instead.
4. Cite sources: link each listing or project you mention with its URL in markdown, e.g. [Villa in Al Narjis](url).
   When you mention a Wasalt listing, include its id like (ID 5841667).
5. Wasalt data is a sample of the marketplace, not every listing. Say so when giving counts or statistics.
6. Format prices with thousands separators and currency (e.g. 850,000 SAR). Rent is annual unless stated.
7. Reply in the user's language (English or Arabic). Be concise: short intro, then bullets.
8. You are not a financial advisor; for investment questions give facts, not recommendations.
"""


def _client():
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY, timeout=60,
                  max_retries=0, default_headers={"X-Title": "Property Assistant Demo"})


# Circuit breaker: a model that just failed is skipped for a while instead of
# making every request wait on it again.
_cooldown_until: dict[str, float] = {}
COOLDOWN_S = 90


def _complete(messages):
    """Try each free model in turn; return (response, model)."""
    last_err = None
    now = time.time()
    ready = [m for m in MODELS if _cooldown_until.get(m, 0) <= now]
    for model in ready or MODELS:
        try:
            resp = _client().chat.completions.create(
                model=model, messages=messages, tools=SCHEMAS, tool_choice="auto",
                temperature=0.2, max_tokens=1200,
            )
            if not resp.choices:
                raise RuntimeError("empty response")
            return resp, model
        except Exception as e:
            log.warning("model %s failed: %s", model, str(e)[:200])
            _cooldown_until[model] = time.time() + COOLDOWN_S
            last_err = e
    raise RuntimeError(f"All models failed: {last_err}")


def _run_tool(name, args):
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except Exception as e:
        log.exception("tool %s failed", name)
        return {"error": str(e)}


def run(history, question):
    """Generator of events: status / tool / answer / error."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history[-8:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:2000]})
    messages.append({"role": "user", "content": question})

    seen_listings = {}
    t0 = time.time()
    for _ in range(MAX_TOOL_ROUNDS):
        yield {"type": "status", "text": "Thinking…"}
        try:
            resp, model = _complete(messages)
        except Exception as e:
            yield {"type": "error", "text": "The free AI models are busy or rate-limited right now. "
                                            "Please try again in a minute.", "detail": str(e)[:300]}
            return
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        if not calls:
            answer = msg.content or "I couldn't produce an answer. Please rephrase."
            by_id = listings_by_id()
            cards = [{k: v for k, v in by_id.get(lid, l).items() if k != "description"}
                     for lid, l in seen_listings.items() if str(lid) in answer][:6]
            yield {"type": "answer", "text": answer, "cards": cards, "model": model,
                   "seconds": round(time.time() - t0, 1)}
            return

        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [c.model_dump() for c in calls]})
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            args = {k: v for k, v in args.items() if v not in (None, "")}
            yield {"type": "tool", "name": c.function.name, "args": args}
            result = _run_tool(c.function.name, args)
            for r in result.get("results", []) if isinstance(result, dict) else []:
                seen_listings[r["id"]] = r
            if isinstance(result, dict) and "id" in result and "url" in result:
                seen_listings[result["id"]] = result
            messages.append({"role": "tool", "tool_call_id": c.id,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:6000]})

    yield {"type": "error", "text": "That needed too many steps. Try a more specific question."}
