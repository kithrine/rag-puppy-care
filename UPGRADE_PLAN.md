# RAG Puppy Care — Upgrade Roadmap

From a Python CLI to a deployable web app (React + Vite + Tailwind frontend), without throwing away the RAG core you already built.

---

## 1. Where you are today

`rag.py` is a single-file, well-documented RAG pipeline:

- **Ingest:** load every `.txt` in `data/`, split into paragraph-sized chunks.
- **Retrieve:** TF-IDF vectorizer + cosine similarity, top 3 chunks (`scikit-learn`).
- **Generate:** Groq model `openai/gpt-oss-20b` via the OpenAI-compatible SDK.
- **Grounding:** a system prompt that forbids outside knowledge, a verbatim refusal string (`I don't know based on the provided course documents.`), and a cheap TF-IDF score guard (`SCORE_THRESHOLD = 0.05`) that refuses before the API call.
- **Sources:** prints retrieved filename + score + preview before each answer.
- **Secrets:** `GROQ_API_KEY` from `.env`, gitignored, with a committed `.env.example`.

**Rubric check — you already pass the core:**

| Rubric item | Status today |
|---|---|
| Custom knowledge base (md/txt/json/pdf) | Content built out (19 `.txt` files, ~207 chunks); format variety still pending |
| Retrieval | Done (TF-IDF) |
| AI-generated answer | Done (Groq) |
| Grounded answer (context only) | Done (prompt + refusal + guard) |
| Source display | Done (CLI) |
| Stretch: deployed | Not yet |

So this upgrade is really three jobs: **(A) wrap the core in a web UI, (B) widen the knowledge base in both depth and file formats, (C) deploy it.** None of it requires rewriting the RAG logic.

---

## 2. Recommended architecture

**Keep Python. Wrap it, don't rewrite it.** Your RAG core works and is rubric-complete; the win is exposing it over HTTP and putting a React chat UI on top.

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  React + Vite + Tailwind     │  fetch  │  FastAPI backend             │
│  chat UI + answer + source   │ ──────▶ │  POST /api/ask               │
│  cards w/ filename & score   │ ◀────── │   → reuses your rag.py funcs │
└─────────────────────────────┘  JSON   │   → calls Groq               │
   dev: Vite dev server (5173)           │   → serves built web/dist    │
   prod: built to web/dist               └──────────────┬───────────────┘
                                                         │ reads at startup
                                                  ┌──────▼───────┐
                                                  │  data/ (kb)  │
                                                  │ txt md json  │
                                                  │ + pdf loader │
                                                  └──────────────┘
```

### Stack

- **Backend: FastAPI + Uvicorn.** Minimal boilerplate, auto-generated `/docs`, and it imports your existing `rag.py` functions directly. Refactor `rag.py` so the logic (load, chunk, build index, retrieve, generate) is importable and the `while True` loop lives in a separate `cli.py`. The web layer and CLI then share one engine.
- **Frontend: React + Vite + Tailwind CSS.** Component structure (chat list, message, source card), fast dev server with hot reload, and a production build that's just static files. Use the current Tailwind + Vite setup (Tailwind v4 uses the `@tailwindcss/vite` plugin and a CSS `@import "tailwindcss";` rather than a `tailwind.config.js` + PostCSS chain — let Claude Code follow the current Tailwind docs for exact steps so it stays correct as versions move).
- **One deployed service.** Vite builds the React app to `web/dist/`; FastAPI serves that folder as static files **and** exposes the API. One repo, one deploy, no production CORS. In development you run two processes (Vite on 5173, FastAPI on 8000) and let Vite **proxy** `/api` calls to FastAPI, so the frontend code calls `/api/ask` in both dev and prod with no env switching.
- **Retrieval: stay with TF-IDF for now.** Zero extra cost, deploys light, rubric-sufficient. Groq does not currently offer an embeddings endpoint, so "real" semantic embeddings would mean adding `sentence-transformers` (heavier deploy) or a second provider. Keep that as an optional stretch (Phase 6), not a requirement.

### How dev vs. prod fit together

- **Dev:** `uvicorn app.api:app --reload` (port 8000) + `npm run dev` in `web/` (port 5173). You browse the Vite server; it proxies `/api/*` to FastAPI. Hot reload on the frontend, autoreload on the backend.
- **Prod:** `npm run build` produces `web/dist/`; FastAPI mounts it at `/` and serves the SPA, while `/api/*` routes are registered first so they aren't shadowed by the static mount. You deploy one service.

### Target repo layout after the upgrade

```
rag-puppy-care/
├── app/
│   ├── rag_core.py      # your rag.py logic, refactored to be importable
│   ├── ingest.py        # multi-format loader: txt, md, json, pdf
│   ├── api.py           # FastAPI: /api/ask + serves web/dist
│   └── cli.py           # the old interactive loop (kept working)
├── web/                 # Vite + React + Tailwind project
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── index.css        # @import "tailwindcss";
│   │   └── components/
│   │       ├── ChatBox.jsx
│   │       ├── Message.jsx
│   │       └── SourceCard.jsx
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js   # dev proxy: /api -> http://localhost:8000
│   └── dist/            # build output, served by FastAPI (gitignore-able)
├── data/                # knowledge base (expanded, multi-format)
├── requirements.txt
├── .env.example
└── README.md
```

---

## 3. The plan in phases

Do them in order; each phase leaves you with a working app, so you can stop at any point and still have something demoable.

1. **Refactor** `rag.py` → `app/rag_core.py` (importable) + `app/cli.py` (the loop). No behavior change. Confirm the CLI still runs.
2. **Multi-format ingestion** (`app/ingest.py`): handle `.txt`, `.md`, `.json`, `.pdf`. This closes the one rubric gap. Track a `source` (filename) and ideally a `title`/`section` per chunk.
3. **FastAPI backend** (`app/api.py`): `POST /api/ask` returns `{ answer, refused, sources: [{source, score, snippet}] }`. Build the index once at startup. Serve `web/dist/` (when present) and keep `/api/*` registered first.
4. **React frontend** (`web/`): scaffold Vite + React + Tailwind, build the chat UI and **source cards** (filename + score + snippet — your "source display" rubric item, now visual), and set up the dev proxy.
5. **Diversify knowledge-base formats** (Section 4 below): the content is already built out (19 `.txt` files); once the Phase 2 loader supports them, convert a few to `.md`, make toxic foods a `.json`, and add a `.pdf` handout so every rubric format is represented.
6. **Deploy** (Section 5) and write the README. *(Optional polish: answer streaming, embeddings upgrade, highlight-the-cited-sentence.)*

---

## 4. Knowledge base — status and remaining work

**Done — content is built out.** The knowledge base has been researched and expanded to **19 `.txt` files / ~207 paragraph chunks** (up from 9 thin files), grounded in current authoritative sources (AAHA, AVSAB, ASPCA, CAPC, AVMA, UC Davis, VOHC). The nine original topics were substantially deepened and fact-checked along the way (for example, leptospirosis is now noted as a core vaccine per the 2022 AAHA guidelines, and feeding now covers AAFCO growth statements, large-breed calcium limits, and the FDA grain-free/DCM caution). Ten new topics were added:

- health_warning_signs, parasite_prevention, exercise, leash_training, separation_anxiety
- dental_care, spay_neuter, puppy_proofing, toxic_foods, microchipping

Everything stays in the original blank-line-separated prose style, so the current chunker reads it unchanged. This was verified: all 207 chunks load with no empty or malformed chunks, and a TF-IDF retrieval test returns the right sources (e.g. "can my dog eat grapes" → toxic_foods, "early signs of parvo" → health_warning_signs, "puppy pulling on leash" → leash_training).

**Remaining work is format variety, not content.** The rubric calls for md/json/pdf alongside txt, and the Phase 2 ingestion loader is what unlocks them. Once that loader exists, diversify a subset of the corpus so every format is represented:

- Convert 2–3 topics to `.md` with a small title/topic front-matter block (nicer source titles, exercises the markdown path):

```markdown
---
title: Feeding Your Puppy
topic: nutrition
---

# Feeding Your Puppy

## How often to feed
...
```

- Re-express `data/toxic_foods.txt` (and/or a toxic-plants list) as a structured `.json` record set.
- Add at least one `.pdf` handout, e.g. a vaccination-schedule one-pager.

**Keep the chunking contract** whatever the format: one idea per paragraph, a blank line between paragraphs. For `.md`, strip/handle headers sensibly; for `.json`, pick a clear text field per record.

**Optional retrieval polish.** Now that the corpus is larger, adding `stop_words="english"` to the `TfidfVectorizer` sharpens matching and makes off-topic refusals fire more cleanly — an off-topic query currently clears the 0.05 score threshold on shared common words and relies on the grounded LLM to refuse.

---

## 5. Deployment (the stretch goal)

Because Vite builds to static files and FastAPI serves them, you can still deploy **one** service. Build the frontend, then deploy the Python app with `web/dist/` included.

**Recommended — single service (simplest, no CORS):**

- **Render** — "Web Service" from the GitHub repo. Build command installs Python deps *and* builds the frontend (`pip install -r requirements.txt && cd web && npm ci && npm run build`); start command `uvicorn app.api:app --host 0.0.0.0 --port $PORT`. Add `GROQ_API_KEY` as an environment secret. (Railway / Fly.io work the same way; Fly wants a small Dockerfile that does both build steps.)
- **Hugging Face Spaces (Docker)** — a Dockerfile that builds the React app then runs Uvicorn; set the key as a Space secret.

**Alternative — split deploy (more "real," more moving parts):** host the React build on Vercel/Netlify and the FastAPI API on Render. You then have to handle CORS and point the frontend at the API's URL via an env var. Only worth it if you specifically want separate frontend hosting; for "hit the rubric cleanly," the single service is the lower-risk path.

Notes: free tiers sleep when idle (first request is slow — fine for a demo). **Never commit `.env`** (your `.gitignore` already handles it); set the key in the host's secrets UI. Pin Python versions in `requirements.txt` and commit a `package-lock.json` so deployed builds match local. Add `web/node_modules/` (and optionally `web/dist/`) to `.gitignore`.

---

## 6. Prompts to hand to Claude Code

Give Claude Code the rubric and this file as context, then work **one phase per prompt** — it keeps changes reviewable and each step independently testable. Tell it to propose a plan before editing on the bigger phases.

### Kickoff (paste first)

```
This is a Python RAG app ("Puppy Care"). Read UPGRADE_PLAN.md and rag.py to
understand the current design. We're turning the CLI into a deployable web app.

Constraints:
- Keep the existing RAG approach (TF-IDF retrieval + Groq generation). Reuse the
  logic in rag.py; do not rewrite the retrieval/grounding from scratch.
- Backend: FastAPI. Frontend: React + Vite + Tailwind CSS in web/. In production,
  FastAPI serves Vite's build output (web/dist) as static files AND exposes the
  API from the same service. In development, the Vite dev server proxies /api to
  FastAPI so the frontend calls /api/ask in both dev and prod.
- Preserve the grounding behavior exactly: context-only answers, the verbatim
  refusal string, and the score-threshold guard.

Before writing code, give me a short plan and the file structure you'll create.
Then we'll do it one phase at a time.
```

### Phase 1 — Refactor for reuse

```
Refactor rag.py into app/rag_core.py containing importable functions
(load/ingest, chunk, build_index, retrieve, generate_answer, plus the config
constants and the refusal string). Move the interactive while-loop into
app/cli.py that imports rag_core. Do not change any behavior or wording. After
the change, `python -m app.cli` should behave exactly like the old `python rag.py`.
```

### Phase 2 — Multi-format ingestion

```
Create app/ingest.py that loads .txt, .md, .json, and .pdf from data/ into the
same chunk records used today ({"source": filename, "text": ...}), plus an
optional "title". For .md, parse a simple YAML front-matter block if present and
strip headers from chunk text. For .json, load a list of records and turn a
chosen text field into chunks. For .pdf, extract text with pypdf and chunk by
paragraph. Keep deterministic ordering. Add the deps to requirements.txt. Wire
rag_core to use this loader so both CLI and API benefit.
```

### Phase 3 — FastAPI backend

```
Create app/api.py: a FastAPI app that builds the index once at startup and
exposes POST /api/ask. Request: {"question": str}. Response:
{"answer": str, "refused": bool, "sources": [{"source": str, "score": float,
"snippet": str}]}. Reuse rag_core.retrieve and rag_core.generate_answer, and
apply the same score-threshold guard before calling Groq (set refused=true and
return the verbatim refusal string when it triggers). Read GROQ_API_KEY from the
environment. Register the /api routes first, then, if web/dist exists, mount it
as static files at "/" (with html=True for the SPA) so it doesn't shadow the API.
Add fastapi + uvicorn to requirements.txt and show me the dev run command.
```

### Phase 4 — React + Vite + Tailwind frontend

```
Scaffold a Vite + React app in web/ and set up Tailwind CSS using the current
recommended Vite integration. Build a chat UI as components:
- App.jsx holds conversation state.
- ChatBox: input + Send button + loading state.
- Message: renders a user or assistant message.
- SourceCard: shows a source's filename, formatted score, and snippet.
On submit, POST to /api/ask and render the answer, with the returned sources as
SourceCards beneath it. If refused=true, show the refusal clearly. Configure
vite.config.js to proxy /api to http://localhost:8000 in dev so the same
/api/ask fetch works in dev and prod. Keep it clean and responsive with Tailwind.
Tell me the two commands to run the app in dev (uvicorn + npm run dev).
```

### Phase 5 — Diversify knowledge-base formats

```
The data/ knowledge base is already researched and built out as 19 .txt files
(see Section 4 of UPGRADE_PLAN.md). Do NOT rewrite the content. After the Phase 2
ingestion loader supports multiple formats, diversify formats so the rubric's
md/json/pdf are represented:
- Convert 2-3 existing topics to .md with a title/topic YAML front-matter block.
- Re-express data/toxic_foods.txt as a structured .json record set.
- Add one .pdf handout (e.g., a vaccination-schedule one-pager).
Preserve the chunking contract: one idea per paragraph, blank line between
paragraphs. Keep the existing wording and accuracy intact.
```

### Phase 6 — Deploy + README

```
Prepare the app for single-service deployment to Render. The build must install
Python deps and build the React app (pip install -r requirements.txt && cd web
&& npm ci && npm run build); start with uvicorn app.api:app --host 0.0.0.0
--port $PORT, serving web/dist. Document the GROQ_API_KEY secret. Add
web/node_modules and (optionally) web/dist to .gitignore. Write a README with
local setup (CLI + the two-process web dev flow), the architecture, and deploy
steps. Do not commit any secrets.
```

### Optional polish prompts

```
Add answer streaming: stream the Groq response token-by-token to the React UI
(Server-Sent Events or chunked fetch) and render it progressively.
```

```
Add an optional semantic-retrieval mode using sentence-transformers embeddings +
cosine similarity, behind a config flag, falling back to TF-IDF. Compare results.
```

---

## 7. Working tips for the handoff

- **Feed Claude Code the rubric** verbatim at the start so it optimizes for grading, not generic "best practices."
- **One phase per session/commit.** Review the diff, run it, commit, then move on. Small steps are easier to debug and to explain in your write-up.
- **Ask for a plan before code** on Phases 2–4.
- **You'll need Node + npm installed** for the frontend (Phases 4 and 6). Confirm `node --version` works before starting Phase 4.
- **Protect the grounding behavior.** When in doubt, tell it: keep the refusal string and the threshold guard exactly as-is — that's a graded requirement.
- **Test the refusal path** (ask something off-topic like "how do I file taxes?") in the web UI, not just the happy path.
```