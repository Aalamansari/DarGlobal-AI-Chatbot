"""Tiny end-to-end eval: does the agent pick the right tool and ground its answer?

Usage:  python eval/run_eval.py [base_url]      (default http://localhost:7860)
Each case checks (a) which tools were called and (b) facts that must appear in the answer.
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7860"

CASES = [
    {"q": "Which Dar Global projects are in Qatar?",
     "tools": ["list_darglobal_projects"], "must": ["Les Vagues"]},
    {"q": "Show 3-bedroom apartments for sale in Riyadh under 1,000,000 SAR",
     "tools": ["search_listings"], "must": ["SAR", "wasalt.sa"]},
    {"q": "Compare median villa sale prices across Saudi cities",
     "tools": ["market_stats"], "must": ["Riyadh"]},
    {"q": "Which Dar Global project is a collaboration with Pagani?",
     "tools": ["list_darglobal_projects", "search_knowledge"], "must": ["Pagani"]},
    {"q": "أرخص الشقق للإيجار في جدة",
     "tools": ["search_listings"], "must": ["wasalt.sa"]},
    {"q": "What's the weather in London tomorrow?",
     "tools": [], "must": []},  # out of scope: should decline, not invent
]


def ask(q):
    req = urllib.request.Request(f"{BASE}/api/chat", data=json.dumps({"message": q}).encode(),
                                 headers={"Content-Type": "application/json"})
    tools, answer = [], None
    with urllib.request.urlopen(req, timeout=180) as r:
        for line in r:
            line = line.decode().strip()
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            if ev["type"] == "tool":
                tools.append(ev["name"])
            elif ev["type"] in ("answer", "error"):
                answer = ev
    return tools, answer


passed = 0
for c in CASES:
    t0 = time.time()
    tools, ans = ask(c["q"])
    text = (ans or {}).get("text", "")
    ok_tool = not c["tools"] or any(t in tools for t in c["tools"])
    ok_facts = all(m.lower() in text.lower() for m in c["must"])
    ok = ans and ans["type"] == "answer" and ok_tool and ok_facts
    passed += bool(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {time.time()-t0:5.1f}s  tools={tools}  model={ans.get('model') if ans else None}")
    print(f"      Q: {c['q']}\n      A: {text[:160].replace(chr(10), ' ')}…\n")
    time.sleep(3)
print(f"{passed}/{len(CASES)} passed")
