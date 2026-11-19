import json
import sys
import time
import urllib.request

# for running the evals do 'python eval/run_eval.py [base_url]'
if len(sys.argv) > 1:
    BASE_URL = sys.argv[1]
else:
    BASE_URL = "http://localhost:7860"

TEST_CASES = [
    {"question": "Which Dar Global projects are in Qatar?",
     "tools": ["list_darglobal_projects"], "must_contain": ["Les Vagues"]},
    {"question": "Show 3-bedroom apartments for sale in Riyadh under 1,000,000 SAR",
     "tools": ["search_listings"], "must_contain": ["SAR", "wasalt.sa"]},
    {"question": "Compare median villa sale prices across Saudi cities",
     "tools": ["market_stats"], "must_contain": ["Riyadh"]},
    {"question": "Which Dar Global project is a collaboration with Pagani?",
     "tools": ["list_darglobal_projects", "search_knowledge"], "must_contain": ["Pagani"]},
    {"question": "أرخص الشقق للإيجار في جدة",
     "tools": ["search_listings"], "must_contain": ["wasalt.sa"]},

    # out of scope, the bot should say it can't help instead of making something up
    {"question": "What's the weather in London tomorrow?",
     "tools": [], "must_contain": []},
]


def ask(question):
    body = json.dumps({"message": question}).encode()
    request = urllib.request.Request(BASE_URL + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
    tools_used = []
    final_event = None

    with urllib.request.urlopen(request, timeout=180) as response:
        for line in response:
            line = line.decode().strip()
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            if event["type"] == "tool":
                tools_used.append(event["name"])
            if event["type"] in ["answer", "error"]:
                final_event = event

    return tools_used, final_event


passed = 0
for case in TEST_CASES:
    start = time.time()
    tools_used, event = ask(case["question"])
    answer = event["text"] if event else ""

    right_tool = len(case["tools"]) == 0 or any(tool in tools_used for tool in case["tools"])
    has_facts = all(word.lower() in answer.lower() for word in case["must_contain"])
    ok = event is not None and event["type"] == "answer" and right_tool and has_facts

    if ok:
        passed += 1
    status = "PASS" if ok else "FAIL"
    model = event.get("model") if event else None
    print(f"{status}  {time.time() - start:.1f}s  tools={tools_used}  model={model}")
    print("   Q:", case["question"])
    print("   A:", answer[:160].replace("\n", " "), "\n")
    time.sleep(3)

print(f"{passed}/{len(TEST_CASES)} passed")
