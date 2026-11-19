import json
import time

from app.backend.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

# set by setup() when the app starts
langfuse = None


def setup():
    global langfuse

    if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
        from langfuse import Langfuse

        langfuse = Langfuse(public_key=LANGFUSE_PUBLIC_KEY, secret_key=LANGFUSE_SECRET_KEY, base_url=LANGFUSE_HOST)
        print("Langfuse tracing is on")
    else:
        print("Langfuse keys not set, tracing is off")

# every function below does nothing when Langfuse is off, so the app works without it

def start_trace(question):
    if langfuse is None:
        return None
    return langfuse.start_observation(name="property-agent", as_type="agent", input=question)


def start_step(parent, name, kind, input=None, model=None):
    # kind is "generation" for model calls, "tool" for tool calls, "guardrail" for checks
    if parent is None:
        return None
    return parent.start_observation(name=name, as_type=kind, input=input, model=model)


def end_step(step, output=None, error=None, usage=None, metadata=None):
    if step is None:
        return
    
    if error:
        step.update(output=output, level="ERROR", status_message=str(error)[:300], metadata=metadata)
    else:
        step.update(output=output, usage_details=usage, metadata=metadata)
    step.end()


def get_trace_id(trace):
    if trace is None:
        return None
    
    return trace.trace_id


def save_feedback(trace_id, value, comment=None):
    if langfuse is None or not trace_id:
        return
    
    langfuse.create_score(name="user_feedback", value=value, trace_id=trace_id,
                          data_type="NUMERIC", comment=comment)


def flush():
    if langfuse is not None:
        langfuse.flush()


metrics = {
    "started_at": time.time(),
    "runs": 0,
    "answers": 0,
    "errors": 0,
    "cached_answers": 0,
    "rate_limited": 0,
    "guardrail_blocks": 0,
    "links_removed": 0,
    "model_fallbacks": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "thumbs_up": 0,
    "thumbs_down": 0,
    "tool_calls": {},
    "models_used": {},
}
latencies = []


def count(name, amount=1):
    metrics[name] = metrics[name] + amount


def record_run(run, seconds):
    count("runs")
    
    if run["outcome"] == "answer":
        count("answers")
    
    if run["outcome"] == "error":
        count("errors")
    
    if run["outcome"] == "blocked":
        count("guardrail_blocks")
    
    count("links_removed", run["links_removed"])
    count("model_fallbacks", run["fallbacks"])
    count("input_tokens", run["input_tokens"])
    count("output_tokens", run["output_tokens"])

    for tool in run["tools"]:
        metrics["tool_calls"][tool] = metrics["tool_calls"].get(tool, 0) + 1
    
    if run["model"]:
        metrics["models_used"][run["model"]] = metrics["models_used"].get(run["model"], 0) + 1

    latencies.append(seconds)
    
    if len(latencies) > 500:
        latencies.pop(0)

    # one structured log line per run, easy to search in Render logs
    log = {
        "event": "agent_run",
        "trace_id": run["trace_id"],
        "outcome": run["outcome"],
        "model": run["model"],
        "tools": run["tools"],
        "steps": run["steps"],
        "fallbacks": run["fallbacks"],
        "input_tokens": run["input_tokens"],
        "output_tokens": run["output_tokens"],
        "links_removed": run["links_removed"],
        "seconds": round(seconds, 2),
    }
    print(json.dumps(log))


def get_metrics():
    result = dict(metrics)
    result["uptime_minutes"] = round((time.time() - metrics["started_at"]) / 60, 1)
    result.pop("started_at")
    result["tracing"] = "langfuse" if langfuse is not None else "off"

    if latencies:
        ordered = sorted(latencies)
        result["latency_avg_seconds"] = round(sum(ordered) / len(ordered), 2)
        index = int(len(ordered) * 0.95)
        if index >= len(ordered):
            index = len(ordered) - 1
        result["latency_p95_seconds"] = round(ordered[index], 2)
    else:
        result["latency_avg_seconds"] = None
        result["latency_p95_seconds"] = None

    return result
