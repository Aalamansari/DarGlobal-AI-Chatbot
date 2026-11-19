import json
import time

from openai import OpenAI

from app.backend import data
from app.backend.config import MAX_STEPS, MODELS, OPENROUTER_API_KEY, OPENROUTER_URL
from app.backend.guardrails import find_urls, is_blocked, remove_unknown_links
from app.backend.prompts import REFUSAL_MESSAGE, SYSTEM_PROMPT
from app.backend.tools import TOOL_SCHEMAS, TOOLS

client = OpenAI(base_url=OPENROUTER_URL, api_key=OPENROUTER_API_KEY, timeout=60, max_retries=0)

failed_models = {}


def call_model(messages):
    available = []
    for model in MODELS:
        if time.time() - failed_models.get(model, 0) > 90:
            available.append(model)
    if not available:
        available = MODELS

    last_error = None

    for model in available:
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
            return response, model
        except Exception as e:
            print(f"Model {model} failed: {str(e)[:200]}")
            failed_models[model] = time.time()
            last_error = e

    raise Exception(f"All models failed: {last_error}")


def run_tool(name, args):
    if name not in TOOLS:
        return {"error": "unknown tool " + name}
    
    try:
        return TOOLS[name](**args)
    except Exception as e:
        print(f"Tool {name} failed: {e}")
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
    if is_blocked(question):
        yield {"type": "answer", "text": REFUSAL_MESSAGE, "cards": [], "model": "guardrail", "seconds": 0}
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
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

    for step in range(MAX_STEPS):
        try:
            response, model = call_model(messages)
        except Exception as e:
            print(e)
            yield {"type": "error", "text": "The free AI models are busy right now. Please try again in a minute."}
            return

        message = response.choices[0].message

        # no tool calls means the model is giving its final answer
        if not message.tool_calls:
            answer = message.content or "I couldn't produce an answer. Please rephrase."
            answer = remove_unknown_links(answer, allowed_urls)
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

            result = run_tool(name, clean_args)
            remember_listings(result, found_listings)
            result_text = json.dumps(result, ensure_ascii=False, default=str)[:6000]
            for url in find_urls(json.dumps(result, ensure_ascii=False, default=str)):
                allowed_urls.add(url)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result_text})

    yield {"type": "error", "text": "That needed too many steps. Try a more specific question."}
