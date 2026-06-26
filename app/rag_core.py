"""
rag_core.py - The importable core of our tiny Retrieval-Augmented Generation app.

This module holds the whole RAG pipeline as plain, importable functions so it can
be shared by more than one front-end: the command-line app (app/cli.py) today,
and a FastAPI web layer later. Nothing here reads from stdin, prints a banner, or
exits the process - those are a caller's job. Keeping the core free of I/O side
effects is what lets the same logic power both a terminal loop and an HTTP handler.

The big picture of RAG:
  1. RETRIEVE - find the passages in YOUR documents most relevant to a question.
  2. GENERATE - hand only those passages to a language model and ask it to
     answer using just that context.
We point the OpenAI SDK at Groq's API, so the same `openai` library talks to a
Groq-hosted model. The key is read from the environment (loaded from a local
.env file), never hardcoded.
"""

import os
import re
from pathlib import Path

# Third-party libraries (install with: pip install scikit-learn openai numpy).
import numpy as np
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Configuration (the "knobs" you can tune). Keeping them at the top, in one
# place, means you never have to hunt through the code to change behavior.
# ---------------------------------------------------------------------------

DATA_DIR = "data"        # folder that holds our .txt knowledge base
TOP_K = 3                # how many chunks to retrieve for each question
SNIPPET_LEN = 120        # how many characters of a chunk to show in previews

# --- LLM / generation settings (Stage 3) ---
MODEL = "openai/gpt-oss-20b"                  # a Groq-hosted model id
BASE_URL = "https://api.groq.com/openai/v1"   # Groq's OpenAI-compatible endpoint

# If even the BEST retrieved chunk scores below this, we treat the question as
# "not covered by the documents" and refuse WITHOUT calling the LLM. TF-IDF
# scores are low in absolute terms (a strong match here is only ~0.2-0.4), so
# keep this small: it is meant to catch total misses (~0.0), not weak matches.
# This is the main knob to tune - raise it to make the app refuse more eagerly.
SCORE_THRESHOLD = 0.05

# The EXACT sentence we must return when the answer is not in the documents.
# Defined once, here, so the threshold guard and the LLM use identical wording
# (the assignment requires this string verbatim).
NO_ANSWER = "I don't know based on the provided course documents."

# Instructions sent to the model on every call. This is where we FORCE the
# model to stay grounded: answer only from the provided context, never guess,
# and fall back to the exact NO_ANSWER sentence when the context falls short.
SYSTEM_PROMPT = (
    "You are a careful assistant that answers questions about puppy care. "
    "Answer the user's question using ONLY the context provided in their message. "
    "The context is a set of excerpts from course documents. "
    "Do not use any outside knowledge, and do not guess or make anything up. "
    "If the answer cannot be found in the context, reply with EXACTLY this "
    "sentence and nothing else:\n"
    f"{NO_ANSWER}"
)


class MissingAPIKeyError(RuntimeError):
    """Raised when GROQ_API_KEY is not set.

    The core never decides HOW to report a missing key - a CLI may print a
    friendly hint and exit, while a web server may want to fail startup or
    return an HTTP error. So we raise, and let each caller choose.
    """


# ---------------------------------------------------------------------------
# STAGE 1: Loading + chunking
# ---------------------------------------------------------------------------

def load_documents(data_dir=DATA_DIR):
    """Read every .txt file in `data_dir` from disk.

    Returns a list of (filename, full_text) pairs, e.g.
        [("feeding.txt", "Puppies need..."), ("grooming.txt", "...")]

    Why keep the filename? Later, when we retrieve a chunk, we want to tell the
    user WHICH document it came from (its "source"). If we throw the filename
    away now, we can't show it later.
    """
    documents = []

    # Path(...).glob("*.txt") finds every file ending in .txt inside the folder.
    # We sort() the results so the order is identical on every run. Deterministic
    # order makes debugging far easier - the same input always looks the same.
    for path in sorted(Path(data_dir).glob("*.txt")):
        # Always pass encoding="utf-8". Without it, Python falls back to the OS
        # default encoding, which differs between machines and can corrupt
        # characters like curly quotes or accents.
        text = path.read_text(encoding="utf-8")

        # path.name is just the filename ("feeding.txt"), without the folder.
        documents.append((path.name, text))

    return documents


def chunk_text(text):
    """Split ONE document's text into paragraph-sized chunks.

    Our files separate paragraphs with a blank line, so a blank line is a
    natural place to cut. Each resulting chunk is one self-contained idea -
    exactly the unit we want to retrieve later.

    Why chunk at all? If we treated a whole file as one block, a question about
    rabies timing would match the ENTIRE vaccinations file - including unrelated
    paragraphs about side effects. Smaller chunks = sharper, more focused
    retrieval.
    """
    # The regex r"\n\s*\n" means: a newline, then any amount of whitespace, then
    # another newline - i.e. "a blank line". Using \s* (rather than nothing)
    # makes us tolerant of lines that contain stray spaces or tabs but otherwise
    # look blank.
    raw_chunks = re.split(r"\n\s*\n", text)

    # Two cleanups in one line:
    #   1. .strip() trims leading/trailing whitespace and newlines from each
    #      chunk so we don't carry around ragged edges.
    #   2. `if chunk.strip()` drops empty chunks. Every file ends with a blank
    #      line, which would otherwise leave an empty string at the end.
    chunks = [chunk.strip() for chunk in raw_chunks if chunk.strip()]

    return chunks


def build_chunks(documents):
    """Turn loaded documents into a flat list of chunk records.

    Each record is a small dictionary:
        {"source": "feeding.txt", "text": "Puppies need..."}

    We use a dictionary (instead of a bare tuple) because `chunk["source"]` and
    `chunk["text"]` are self-explanatory when you re-read the code later. And we
    keep ONE flat list - rather than lists grouped by file - because the
    retrieval step scores every chunk together, regardless of its source file.
    """
    chunks = []

    for filename, text in documents:
        for chunk in chunk_text(text):
            chunks.append({"source": filename, "text": chunk})

    return chunks


# ---------------------------------------------------------------------------
# STAGE 2: Vectorize + retrieve
# ---------------------------------------------------------------------------

def build_index(chunks):
    """Turn the chunk texts into a TF-IDF matrix we can search.

    Returns (vectorizer, tfidf_matrix):
      - vectorizer:   the FITTED TfidfVectorizer. We keep it because the exact
                      same vocabulary and word-weights must later be applied to
                      the user's question.
      - tfidf_matrix: a sparse matrix with one ROW per chunk and one COLUMN per
                      word in the vocabulary.

    What is TF-IDF? It scores each word in a chunk by combining:
      TF  (term frequency)         - how often the word appears in THIS chunk.
      IDF (inverse document freq)  - how RARE the word is across ALL chunks.
    Multiplying them means filler words (like "the", which is everywhere) get
    low weight, while distinctive words (like "rabies" or "crate") get high
    weight. Matching then focuses on the words that actually carry meaning.
    """
    # Pull just the text out of each chunk record; the vectorizer only needs the
    # words. We keep the parallel `chunks` list to recover the source filename
    # for any row later, because row i in the matrix corresponds to chunks[i].
    texts = [chunk["text"] for chunk in chunks]

    # fit_transform does three things at once:
    #   1. Builds the vocabulary (every unique word across all chunks).
    #   2. Lowercases and tokenizes the text (sensible defaults).
    #   3. Computes the TF-IDF weight for every (chunk, word) pair.
    # Tip: TfidfVectorizer(stop_words="english") would drop filler words
    # entirely - an easy upgrade. We leave it off so you see the plain baseline.
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(texts)

    return vectorizer, tfidf_matrix


def retrieve(question, vectorizer, tfidf_matrix, chunks, top_k=TOP_K):
    """Find the `top_k` chunks most relevant to `question`.

    Returns a list of (chunk, score) pairs, best match first, e.g.
        [({"source": "vaccinations.txt", "text": "..."}, 0.41), ...]
    """
    # Convert the question into a vector with the SAME fitted vectorizer. Note we
    # call transform, NOT fit_transform: the vocabulary is already locked in from
    # the chunks, and the question must be described in that same vocabulary for
    # the numbers to be comparable. Any word in the question that never appeared
    # in the documents is simply ignored.
    query_vector = vectorizer.transform([question])

    # cosine_similarity measures the ANGLE between vectors, not their length. Two
    # texts are "similar" if they use the same important words in similar
    # proportions, no matter how long they are. It returns a 2D array shaped
    # (num_questions, num_chunks); we passed one question, so row [0] gives us a
    # flat array with one score per chunk.
    scores = cosine_similarity(query_vector, tfidf_matrix)[0]

    # np.argsort returns the INDEXES that would sort scores from low to high.
    # [::-1] reverses that to high-to-low, and [:top_k] keeps the best few.
    top_indices = np.argsort(scores)[::-1][:top_k]

    # Pair each winning chunk with its score. float(...) turns numpy's number
    # type into a plain Python float so it prints and compares cleanly.
    results = [(chunks[i], float(scores[i])) for i in top_indices]

    return results


# ---------------------------------------------------------------------------
# STAGE 3: Secrets, context formatting, and the LLM call
# ---------------------------------------------------------------------------

def load_env_file(path=".env"):
    """Load KEY=VALUE pairs from a local .env file into the environment.

    This is a tiny, dependency-free version of what the popular `python-dotenv`
    package does. If the file does not exist we silently do nothing - the key
    might already be set directly in your shell environment instead.

    We skip blank lines and comments (lines starting with '#'), and we use
    os.environ.setdefault so a value already present in the real environment
    WINS over the file. That is the conventional, least-surprising behavior.
    """
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Strip whitespace and optional surrounding quotes: KEY="abc" -> abc.
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_client():
    """Build the OpenAI client, pointed at Groq, after checking the API key.

    The OpenAI SDK is "OpenAI-compatible" and Groq exposes a matching endpoint,
    so we keep the familiar OpenAI() client but swap in Groq's base_url. The key
    comes from the environment (which load_env_file may have just populated). If
    it is missing we raise MissingAPIKeyError rather than printing or exiting -
    the core has no business killing the process. The caller (CLI or web server)
    catches this and reports it however suits that front-end.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise MissingAPIKeyError("GROQ_API_KEY is not set")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def format_context(results):
    """Combine the retrieved chunks into one labeled context string for the LLM.

    Each chunk is tagged with its source filename. Labeling does two jobs: it
    helps the model keep facts straight, and it lets a curious reader trace any
    statement in the answer back to the document it came from.
    """
    blocks = []
    for chunk, score in results:
        blocks.append(f"[Source: {chunk['source']}]\n{chunk['text']}")
    # A blank line between blocks keeps them clearly separated for the model.
    return "\n\n".join(blocks)


def generate_answer(question, results, client):
    """Ask the LLM to answer `question` using ONLY the retrieved chunks.

    This is the "generate" half of RAG. We use Groq's Responses API:
      - instructions: our SYSTEM_PROMPT (the grounding rules).
      - input:        the retrieved context followed by the user's question.
    The model's text comes back on response.output_text.
    """
    context = format_context(results)
    user_input = f"Context:\n{context}\n\nQuestion: {question}"

    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=user_input,
    )
    return response.output_text.strip()


# ---------------------------------------------------------------------------
# Orchestration: one entry point that ties retrieve + the two guards + generate
# together, so every front-end gets IDENTICAL grounding behavior.
# ---------------------------------------------------------------------------

def answer_question(question, vectorizer, tfidf_matrix, chunks, client, top_k=TOP_K):
    """Answer one `question` end-to-end, applying the grounding guards.

    Returns a dict:
        {
          "answer":  str,   # the model's answer, OR the verbatim NO_ANSWER text
          "refused": bool,  # True when the score guard refused (no API call)
          "results": [(chunk, score), ...],  # what retrieval found, best first
        }

    Why centralize this here (rather than in each caller)? The grounding rules -
    the score-threshold guard and the verbatim refusal string - are a graded
    requirement and must behave identically in the CLI and the web API. Putting
    the sequence in ONE place means there is a single source of truth; callers
    only decide how to PRESENT the result.

    We return the raw `results` (not a pre-formatted snippet) so each front-end
    can render sources its own way: the CLI builds a 120-char preview, while the
    web API will derive {source, score, snippet} from the same data.
    """
    # RETRIEVE first - we always want the sources, even when we end up refusing,
    # so a caller can show what (little) the documents had to offer.
    results = retrieve(question, vectorizer, tfidf_matrix, chunks, top_k=top_k)

    # GUARD 1 (cheap, local): if even the best chunk is a weak match, the
    # documents almost certainly do not cover this question. Refuse here, with
    # NO API call, returning the exact NO_ANSWER sentence.
    best_score = results[0][1] if results else 0.0
    if best_score < SCORE_THRESHOLD:
        return {"answer": NO_ANSWER, "refused": True, "results": results}

    # GUARD 2 (semantic): otherwise let the model answer. Its instructions force
    # it to use only the chunks above, and to return the same NO_ANSWER sentence
    # if they do not actually contain the answer.
    answer = generate_answer(question, results, client)
    return {"answer": answer, "refused": False, "results": results}
