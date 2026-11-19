# Property Assistant: an agentic chatbot over Dar Global & Wasalt data

A tool-using AI agent that answers questions about **Dar Global's international luxury developments** and **Wasalt's Saudi property listings**. It cites a source link for every claim, works in English and Arabic, and runs on free OpenRouter models.

**Live demo:** _<your Space URL>_

Try:
- *Which Dar Global projects are in Oman?*
- *3-bedroom apartments for sale in Riyadh under 1M SAR*
- *Compare median villa prices across Saudi cities*
- *Which Dar Global developments are branded with luxury partners?*
- *أرخص الشقق للإيجار في جدة*

## Architecture

```mermaid
flowchart LR
    subgraph Collect["1 · Collect (offline)"]
        A[darglobal.co.uk<br/>38 projects, 72 pages] --> R[(data/raw/*.json)]
        B[wasalt.sa sitemap<br/>random sample of 320 listings] --> R
    end
    subgraph Build["2 · Build (docker build)"]
        R --> S[(SQLite<br/>structured listings)]
        R --> C[Text chunks] --> E[Multilingual embeddings<br/>+ BM25]
    end
    subgraph Serve["3 · Serve (FastAPI)"]
        U[Chat UI] -->|SSE| G[Agent loop]
        G <-->|tool calls| T{Tools}
        T --> S
        T --> E
        G <--> M[OpenRouter free models<br/>with fallback chain]
    end
```

### Why it is built this way

| Decision | Reason |
|---|---|
| **Agent with tools rather than plain RAG** | "3-bed under 1M in Riyadh" is a filter query, and vector search is poor at numbers. The model chooses between structured SQL search, market statistics and semantic search, and can chain several calls. |
| **Two stores** | Listings (price, beds, city) go in SQLite. Free text (project pages, FAQs, descriptions) goes in a hybrid BM25 + embedding index merged with reciprocal rank fusion. BM25 catches exact names like "Les Vagues"; embeddings catch meaning and Arabic. |
| **Small local embeddings** (`bge-small-en-v1.5`, quantised ONNX through fastembed) | No paid API, and it fits a free 512 MB instance. Corpus embeddings are computed at image build time. Arabic questions still work because the LLM writes tool arguments in English and BM25 indexes Arabic tokens. |
| **Plain agent loop, no framework** | It is about 100 lines and every step is easy to trace. The UI shows each tool call live. |
| **Model fallback + circuit breaker** | Free models get rate-limited upstream. The agent falls through a list of free tool-calling models and skips a failed model for 90 s. |
| **Answer cache + per-IP rate limit** | Free-tier quotas are small, so repeated questions are answered from cache. |
| **Snapshot, not live scraping** | Answers are fast and reproducible, and the app adds no load to the source sites. Re-running collection refreshes the data. |

### Tools the agent can call

| Tool | Backed by | Use |
|---|---|---|
| `search_listings` | SQLite | Filter Wasalt listings by purpose, city, district, type, price, bedrooms, area |
| `get_listing` | SQLite | Full details of one listing |
| `market_stats` | SQLite | Median, min and max price and price per m², grouped by city, district or type |
| `list_darglobal_projects` | JSON | Dar Global projects by country or keyword (partner brand, type) |
| `search_knowledge` | BM25 + vectors | Open questions over project pages, partners, FAQs, press and listing descriptions |

## Data collection

| Source | What | How |
|---|---|---|
| darglobal.co.uk | 38 projects (name, location, country, type, bedrooms, completion) + 72 pages (projects, partners, about, FAQ, press) | Structured project data read from each page's embedded Next.js JSON, plus page text |
| wasalt.sa | 320 listings (227 sale, 93 rent) across 20 cities + home/corporate pages | Random sample of URLs from Wasalt's public sitemap; fields read from schema.org JSON-LD and page data |

Responsible collection:
- Only paths that robots.txt allows. Wasalt's `/search` is disallowed and was not touched.
- Low request rates (about one page every 1.2–1.5 s) and a small sample.
- Both sites put a bot check in front of automated clients, and **nothing here bypasses it**. Pages were read through a normal browser session.
- **No personal data is stored.** Agent and broker names and phone numbers are dropped; only company or agency names are kept.

Data snapshot: **19 Nov 2026**. Wasalt figures come from a sample and are not market-wide statistics, and the assistant says so in its answers.

## Run locally

```bash
cp .env.example .env               # add your OPENROUTER_API_KEY
docker build -t property-assistant .
docker run -p 7860:7860 --env-file .env property-assistant
# open http://localhost:7860
```

Without Docker: `pip install -r requirements.txt && python -m scripts.build_index && uvicorn app.backend.main:app --port 7860`

## Guardrails

| Layer | Guardrail |
|---|---|
| Input | Questions are limited to 1,000 characters and 8 requests per minute per IP. Common prompt-injection phrases ("ignore previous instructions", "system prompt", "jailbreak"...) are refused before the model is called, which also saves quota. |
| Prompt | The assistant only helps with real estate, treats tool results and page text as data rather than instructions, refuses to change its rules or reveal its prompt, and never invents facts or URLs. |
| Tools | Parameterised SQL, an allow-list for `group_by`, results capped at 10, tool errors caught, tool output truncated. |
| Output | Every markdown link in the answer is checked against the URLs the tools actually returned, and unknown links are reduced to plain text. The UI sanitises the answer's HTML with DOMPurify. |
| Agent loop | At most 6 tool rounds, limited history, capped answer length, low temperature. |
| Data | No personal data is stored. |

## Evaluation

`python eval/run_eval.py [base_url]` runs end-to-end cases. Each one checks that the right tool was chosen, that the expected facts appear in the answer, and that forbidden content does not. The cases cover structured search, statistics, Dar Global lookup, an Arabic query, and guardrail cases: off-topic requests (weather, coding), a prompt-extraction attempt and a role-change attempt. Run only the guardrail cases with `python eval/run_eval.py http://localhost:7860 guardrails`.

## Project layout

```
app/
  backend/
    main.py        FastAPI: SSE chat endpoint, cache, rate limit
    agent.py       tool-calling loop, model fallback, circuit breaker
    prompts.py     system prompt
    guardrails.py  input check, link check
    tools.py       5 tools + JSON schemas
    retrieval.py   BM25 + embeddings, reciprocal rank fusion
    data.py        normalisation, SQLite, chunking
    config.py      settings and paths
  web/
    static/        single-file chat UI
data/raw/        scraped snapshot (JSON)
scripts/         build_index.py (runs during docker build)
eval/            end-to-end eval
```

## What I'd do next in production

- Scheduled re-collection (daily diff of the sitemap) with change tracking and stale-listing removal
- Postgres + pgvector instead of in-memory stores; a geo-search tool using listing coordinates
- A paid or self-hosted model for reliability, streaming tokens, and tracing every tool call (Langfuse/OpenTelemetry)
- A larger eval set with LLM-as-judge for faithfulness, run in CI
- Lead capture: hand off to a sales agent or CRM when a user shows buying intent
- Keep chat history on the server (per session) instead of trusting the history the browser sends, so it can't be faked
- Rate limit per signed session or with the platform's trusted client IP, since `X-Forwarded-For` can be spoofed
- An LLM-based classifier for injection and off-topic requests instead of a phrase list, plus a moderation check on outputs

_Built as a technical assignment. Not affiliated with Dar Global or Wasalt; all data is publicly available and may be out of date._
