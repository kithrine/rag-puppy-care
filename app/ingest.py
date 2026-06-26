"""
ingest.py - Multi-format loading + chunking (Stage 1 of the RAG pipeline).

This module is the one place that knows how to turn FILES on disk into the flat
list of chunk records the rest of the app retrieves over. It handles four
formats - .txt, .md, .json, .pdf - and normalizes them all to the SAME shape:

    {"source": "feeding.txt", "text": "Puppies need...", "title": "Feeding"}

(`title` is optional - only some formats carry one.) Because every format
collapses to this identical record, retrieval and grounding never have to learn
that formats exist: they just score one flat list of chunks.

Design note: this module imports nothing from rag_core. Keeping it a "leaf"
(rag_core depends on ingest, not the other way around) means there is no circular
import - so the chunking contract can live here, in one place, and be reused by
every loader.
"""

import json
import re
from pathlib import Path


# The "chunking contract": one self-contained idea per paragraph, paragraphs
# separated by a blank line. This single splitter is shared by the txt, md, and
# pdf loaders so the contract is defined exactly once.
def split_paragraphs(text):
    """Split text into paragraph-sized chunks on blank lines.

    Our documents separate paragraphs with a blank line, so a blank line is a
    natural place to cut. Each resulting chunk is one self-contained idea -
    exactly the unit we want to retrieve later.
    """
    # The regex r"\n\s*\n" means: a newline, then any amount of whitespace, then
    # another newline - i.e. "a blank line". Using \s* (rather than nothing)
    # makes us tolerant of lines that contain stray spaces or tabs but otherwise
    # look blank.
    raw_chunks = re.split(r"\n\s*\n", text)

    # .strip() trims ragged whitespace from each chunk, and `if chunk.strip()`
    # drops empties (e.g. a trailing blank line at the end of a file).
    return [chunk.strip() for chunk in raw_chunks if chunk.strip()]


# ---------------------------------------------------------------------------
# Markdown helpers: front-matter parsing + header stripping
# ---------------------------------------------------------------------------

def _parse_front_matter(text):
    """Pull a simple YAML-style front-matter block off the top of a document.

    Front matter looks like this, fenced by lines that are exactly '---':

        ---
        title: Feeding Your Puppy
        topic: nutrition
        ---
        # Feeding Your Puppy
        ...

    Returns (meta, body): `meta` is a dict of the key/value pairs, `body` is the
    remaining document text. If there is no front matter we return ({}, text).

    This is a tiny hand-rolled parser (like load_env_file in rag_core) rather
    than a full YAML library: it handles flat `key: value` lines, which is all
    our corpus needs, and keeps the deploy dependency-free.
    """
    lines = text.splitlines()
    # Front matter must start on the very first line with a bare '---' fence.
    if not lines or lines[0].strip() != "---":
        return {}, text

    # Find the closing '---' fence.
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = {}
            for raw in lines[1:i]:
                if ":" in raw:
                    key, value = raw.split(":", 1)
                    # Strip whitespace and optional surrounding quotes, the same
                    # way rag_core.load_env_file treats .env values.
                    meta[key.strip()] = value.strip().strip('"').strip("'")
            body = "\n".join(lines[i + 1:])
            return meta, body

    # No closing fence - treat the whole thing as body, not front matter.
    return {}, text


def _strip_md_headers(text):
    """Remove ATX header markers (#, ##, ...) while KEEPING the heading words.

    "## How often to feed" becomes "How often to feed". We keep the words on
    purpose: heading text ("vaccination schedule", "toxic foods") is often the
    most retrieval-relevant part of a section, so dropping it would hurt search.
    We only strip the leading `#` markup noise.
    """
    cleaned = []
    for line in text.splitlines():
        # Up to 3 leading spaces, then 1-6 '#', then required whitespace is the
        # CommonMark rule for an ATX heading.
        cleaned.append(re.sub(r"^\s{0,3}#{1,6}\s+", "", line))
    return "\n".join(cleaned)


def _first_h1(text):
    """Return the text of the first level-1 (`# `) heading, or None."""
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#\s+(.*)", line)
        if match:
            return match.group(1).strip() or None
    return None


# ---------------------------------------------------------------------------
# Per-format loaders. Each returns a list of chunk records for ONE file.
# ---------------------------------------------------------------------------

def _load_txt(path):
    """Plain text: split into paragraphs. No title. (The original behavior.)"""
    text = path.read_text(encoding="utf-8")
    return [{"source": path.name, "text": para} for para in split_paragraphs(text)]


def _load_md(path):
    """Markdown: optional front matter for the title, headers stripped from text."""
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(raw)

    # Prefer an explicit front-matter title; fall back to the first H1 heading.
    title = meta.get("title") or _first_h1(body)

    # Strip header markup AFTER finding the title, so the title still reads
    # nicely while the chunk text loses the noisy '#' markers.
    body = _strip_md_headers(body)

    records = []
    for para in split_paragraphs(body):
        record = {"source": path.name, "text": para}
        if title:
            record["title"] = title
        records.append(record)
    return records


def _load_json(path, text_field="text", title_field="title"):
    """JSON: a list of records, each contributing one chunk.

    Two shapes are accepted, in document (list) order:
      - a list of strings: each string IS the chunk text.
      - a list of objects: the chunk text comes from `text_field` ("text"), and
        an optional `title_field` ("title") becomes the chunk title.

    Authoring a JSON knowledge-base file (Phase 5) therefore looks like:
        [{"title": "Grapes and raisins", "text": "Grapes and raisins can ..."}]
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: expected a JSON list of records")

    records = []
    for item in data:
        if isinstance(item, str):
            text, title = item, None
        elif isinstance(item, dict):
            text, title = item.get(text_field), item.get(title_field)
        else:
            # Skip anything that is neither a string nor an object.
            continue

        # Skip records with no usable text rather than indexing empty chunks.
        if not text or not str(text).strip():
            continue

        record = {"source": path.name, "text": str(text).strip()}
        if title:
            record["title"] = str(title).strip()
        records.append(record)
    return records


def _load_pdf(path):
    """PDF: extract text with pypdf, then chunk by paragraph.

    pypdf is imported lazily so the app still loads .txt/.md/.json even if pypdf
    is not installed - only PDFs need it. The document title, if pypdf can read
    it from the PDF metadata, becomes the chunk title.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - exercised only without pypdf
        raise RuntimeError(
            "pypdf is required to read PDF files (pip install pypdf)"
        ) from exc

    reader = PdfReader(str(path))

    title = None
    try:
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title.strip() or None
    except Exception:
        # Metadata is best-effort; never let a missing/odd title block ingestion.
        title = None

    # Join each page's extracted text with a blank line, then apply the same
    # paragraph splitter. PDF extraction is imperfect, but this keeps the
    # chunking contract identical to the other formats.
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages)

    records = []
    for para in split_paragraphs(text):
        record = {"source": path.name, "text": para}
        if title:
            record["title"] = title
        records.append(record)
    return records


# Dispatch table: file extension -> loader. Adding a format is one entry here.
LOADERS = {
    ".txt": _load_txt,
    ".md": _load_md,
    ".json": _load_json,
    ".pdf": _load_pdf,
}


def load_chunks(data_dir="data"):
    """Load every supported file in `data_dir` into one flat list of chunk records.

    Files are processed in sorted filename order, and chunks keep document order
    within each file, so the same inputs always produce the same list - which
    matters for a stable TF-IDF index and reproducible retrieval. Files with an
    unsupported extension (e.g. .DS_Store) are simply ignored.
    """
    paths = [
        path
        for path in Path(data_dir).glob("*")
        if path.is_file() and path.suffix.lower() in LOADERS
    ]

    chunks = []
    for path in sorted(paths, key=lambda p: p.name):
        chunks.extend(LOADERS[path.suffix.lower()](path))
    return chunks
