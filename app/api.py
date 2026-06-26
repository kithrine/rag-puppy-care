"""
api.py - FastAPI backend that puts an HTTP face on the RAG core.

It builds the TF-IDF index ONCE at startup, then answers questions over HTTP via
`POST /api/ask`, reusing the exact same grounding the CLI uses (the score guard +
verbatim refusal live in rag_core.answer_question, so there is one source of truth
for "answer only from the documents").

This is a single-service backend: in production it also serves the built React app
from web/dist (mounted last so it never shadows the API). In development the Vite
dev server proxies /api here, so the same /api/ask call works in both - no CORS.

Run it (dev):
    python -m uvicorn app.api:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import rag_core


# ---------------------------------------------------------------------------
# Request / response schemas. Pydantic gives us validation for free (a bad body
# becomes a clean 422) plus an auto-generated OpenAPI spec at /docs.
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str


class Source(BaseModel):
    source: str   # the filename a chunk came from, e.g. "toxic_foods.txt"
    score: float  # TF-IDF cosine similarity to the question
    snippet: str  # a short preview of the chunk, for the UI's source cards


class AskResponse(BaseModel):
    answer: str
    refused: bool
    sources: list[Source]


# ---------------------------------------------------------------------------
# Startup: build the index exactly once and keep it on app.state.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load env + client + knowledge base once, before serving any request.

    Building the TF-IDF index per request would be wasteful; the index never
    changes between questions, so we do it here at startup. If the API key is
    missing we fail fast with a clear error rather than starting a server that
    can never answer.
    """
    # Honor a local .env in development; in production the host sets the env var
    # directly and this is a no-op.
    rag_core.load_env_file()

    try:
        app.state.client = rag_core.make_client()
    except rag_core.MissingAPIKeyError as exc:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Set it in the environment "
            "(or a local .env file) before starting the server."
        ) from exc

    chunks = rag_core.load_chunks()
    app.state.chunks = chunks
    app.state.vectorizer, app.state.tfidf_matrix = rag_core.build_index(chunks)

    yield  # ---- the app serves requests here ----
    # Nothing to tear down.


app = FastAPI(title="Puppy Care RAG API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# API routes. These are registered BEFORE the static mount below so the SPA
# catch-all can never shadow them.
# ---------------------------------------------------------------------------

def _snippet(text: str, limit: int = rag_core.SNIPPET_LEN) -> str:
    """Shorten a chunk to a single-line preview for a source card."""
    snippet = text[:limit].replace("\n", " ").strip()
    return snippet + "…" if len(text) > limit else snippet


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request) -> AskResponse:
    """Answer one question, grounded in the knowledge base.

    A plain `def` (not `async def`) on purpose: the Groq call inside
    answer_question is blocking, so FastAPI runs this in a threadpool and the
    event loop stays free for other requests.
    """
    state = request.app.state
    result = rag_core.answer_question(
        req.question,
        state.vectorizer,
        state.tfidf_matrix,
        state.chunks,
        state.client,
    )
    sources = [
        Source(source=chunk["source"], score=score, snippet=_snippet(chunk["text"]))
        for chunk, score in result["results"]
    ]
    return AskResponse(answer=result["answer"], refused=result["refused"], sources=sources)


@app.get("/api/health")
def health(request: Request) -> dict:
    """Cheap readiness check (no LLM call) - handy for deploy probes."""
    chunks = request.app.state.chunks
    return {
        "status": "ok",
        "chunks": len(chunks),
        "files": len({chunk["source"] for chunk in chunks}),
    }


# ---------------------------------------------------------------------------
# Static SPA, mounted LAST. Registering it after the API routes means Starlette
# (which matches routes in order) checks /api/* first, so the "/" catch-all only
# handles everything else. Skipped until web/dist exists (built in Phase 4/6).
# ---------------------------------------------------------------------------

_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
