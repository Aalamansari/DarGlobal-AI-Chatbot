import json
import time

from openai import OpenAI

from app.backend import data
from app.backend import observability as obs
from app.backend.config import MAX_STEPS, MODELS, OPENROUTER_API_KEY, OPENROUTER_URL
from app.backend.guardrails import find_urls, is_blocked, remove_unknown_links
from app.backend.prompts import REFUSAL_MESSAGE, SYSTEM_PROMPT
from app.backend.tools import TOOL_SCHEMAS, TOOLS

client = OpenAI(base_url=OPENROUTER_URL, api_key=OPENROUTER_API_KEY, timeout=60, max_retries=0)

failed_models = {}


def call_model(messages, trace, run):
    available = []
    for model in MODELS:
        if time.time() - failed_models.get(model, 0) > 90:
            available.append(model)
    if not available:
        available = MODELS

    last_error = None

    for model in available:
        step = obs.start_step(trace, "llm-call", "generation", input=messages, model=model)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=1200,
            )
            if not response.choices:
                raise Exception("empty response")
        except Exception as e:
            print(f"Model {model} failed: {str(e)[:200]}")
            obs.end_step(step, error=e)
            failed_models[model] = time.time()
            run["fallbacks"] += 1
            last_error = e
            continue

        usage = {}
        if response.usage:
            usage = {"input": response.usage.prompt_tokens or 0, "output": response.usage.completion_tokens or 0}
            run["input_tokens"] += usage["input"]
            run["output_tokens"] += usage["output"]

        message = response.choices[0].message
        output = {"content": message.content}
        if message.tool_calls:
            output["tool_calls"] = [{"name": c.function.name, "arguments": c.function.arguments}
                                    for c in message.tool_calls]
        obs.end_step(step, output=output, usage=usage)
        return response, model

    raise Exception(f"All models failed: {last_error}")


def run_tool(name, args, trace, run):
    step = obs.start_step(trace, name, "tool", input=args)
    run["tools"].append(name)

    if name not in TOOLS:
        result = {"error": "unknown tool " + name}
        obs.end_step(step, output=result, error="unknown tool")
        return result

    try:
        result = TOOLS[name](**args)
        obs.end_step(step, output=result)
        return result
    except Exception as e:
        print(f"Tool {name} failed: {e}")
        obs.end_step(step, error=e)
        return {"error": str(e)}


def remember_listings(result, found_listings):
    if not isinstance(result, dict):
        return

    for item in result.get("results", []):
        found_listings[item["id"]] = item

    if "id" in result and "url" in result:
        found_listings[result["id"]] = result


def make_cards(answer, found_listings):
    cards = []

    for listing_id in found_listings:
        if str(listing_id) in answer:
            listing = dict(data.listings_by_id.get(listing_id, found_listings[listing_id]))
            listing.pop("description", None)
            cards.append(listing)

    return cards[:6]


def run_agent(history, question):
    # wraps one agent run with a trace, metrics and a log line
    trace = obs.start_trace(question)
    run = {
        "trace_id": obs.get_trace_id(trace),
        "outcome": "unknown",
        "model": None,
        "tools": [],
        "steps": 0,
        "fallbacks": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "links_removed": 0,
    }
    start = time.time()
    final_text = None

    try:
        for event in agent_steps(history, question, trace, run):
            if event["type"] in ["answer", "error"]:
                final_text = event["text"]
            if event["type"] == "answer":
                event["trace_id"] = run["trace_id"]
            yield event
    finally:
        if trace is not None:
            trace.update(output=final_text, metadata={"outcome": run["outcome"], "model": run["model"],
                                                      "tools": run["tools"], "fallbacks": run["fallbacks"]})
            trace.end()
        obs.record_run(run, time.time() - start)


def agent_steps(history, question, trace, run):
    check = obs.start_step(trace, "input-guardrail", "guardrail", input=question)
    blocked = is_blocked(question)
    obs.end_step(check, output={"blocked": blocked})

    if blocked:
        run["outcome"] = "blocked"
        yield {"type": "answer", "text": REFUSAL_MESSAGE, "cards": [], "model": "guardrail", "seconds": 0}
        return

    system_prompt = SYSTEM_PROMPT.replace("{snapshot_date}", data.snapshot_date)
    messages = [{"role": "system", "content": system_prompt}]

    for msg in history[-8:]:
        if msg.get("role") in ["user", "assistant"] and msg.get("content"):
            messages.append({"role": msg["role"], "content": str(msg["content"])[:2000]})
    messages.append({"role": "user", "content": question})

    found_listings = {}
    start = time.time()

    # links from earlier answers are still fine to use in follow up answers
    allowed_urls = set()
    for msg in messages:
        if msg["role"] == "assistant":
            for url in find_urls(msg["content"]):
                allowed_urls.add(url)

    for _ in range(MAX_STEPS):
        run["steps"] += 1
        try:
            response, model = call_model(messages, trace, run)
        except Exception as e:
            print(e)
            run["outcome"] = "error"
            yield {"type": "error", "text": "The free AI models are busy right now. Please try again in a minute."}
            return

        run["model"] = model
        message = response.choices[0].message

        # no tool calls means the model is giving its final answer
        if not message.tool_calls:
            answer = message.content or "I couldn't produce an answer. Please rephrase."

            check = obs.start_step(trace, "link-guardrail", "guardrail", input=answer)
            answer, removed = remove_unknown_links(answer, allowed_urls)
            obs.end_step(check, output={"removed_links": removed})
            run["links_removed"] = len(removed)
            if removed:
                print("Removed unknown links:", removed)

            run["outcome"] = "answer"
            yield {
                "type": "answer",
                "text": answer,
                "cards": make_cards(answer, found_listings),
                "model": model,
                "seconds": round(time.time() - start, 1),
            }
            return

        tool_calls = [call.model_dump() for call in message.tool_calls]
        messages.append({"role": "assistant", "content": message.content or "", "tool_calls": tool_calls})

        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            clean_args = {}
            for key, value in args.items():
                if value is not None and value != "":
                    clean_args[key] = value

            yield {"type": "tool", "name": name, "args": clean_args}

            result = run_tool(name, clean_args, trace, run)
            remember_listings(result, found_listings)
            full_text = json.dumps(result, ensure_ascii=False, default=str)
            for url in find_urls(full_text):
                allowed_urls.add(url)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": full_text[:6000]})

    run["outcome"] = "error"
    yield {"type": "error", "text": "That needed too many steps. Try a more specific question."}
