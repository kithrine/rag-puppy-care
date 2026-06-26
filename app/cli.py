"""
cli.py - The interactive command-line front-end for the Puppy Care RAG app.

All the RAG logic lives in app/rag_core.py; this file only handles the terminal:
reading questions, printing the banner and retrieved sources, and reporting a
missing API key in a friendly way. Run it with:

    python -m app.cli

(after `pip install -r requirements.txt` and putting your key in a .env file).
This behaves exactly like the old `python rag.py` did.
"""

import sys

from app import rag_core


def main():
    """Run the interactive question-and-answer loop.

    Each turn: read a question -> retrieve the top chunks -> show their
    sources/scores -> refuse if nothing relevant, otherwise ask the LLM to
    answer using only those chunks.
    """
    # On Windows the console often defaults to a legacy encoding (cp1252) that
    # cannot print every character an LLM may return (curly quotes, em dashes,
    # thin spaces, ...). Switch our output stream to UTF-8 so answers always
    # print cleanly instead of crashing with a UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Make the API key available (.env -> environment), then build the client.
    # We do this FIRST so we fail fast with a clear message if the key is
    # missing, before spending time building the index. The core raises on a
    # missing key; the friendly hint + exit is the CLI's responsibility.
    rag_core.load_env_file()
    try:
        client = rag_core.make_client()
    except rag_core.MissingAPIKeyError:
        print("ERROR: GROQ_API_KEY is not set.")
        print("Create a file named '.env' in this folder containing one line:")
        print("    GROQ_API_KEY=gsk_your_key_here")
        print("(Tip: copy .env.example to .env and paste your real key in.)")
        sys.exit(1)

    # Build the knowledge base once at startup (load -> chunk -> TF-IDF index).
    # Doing this a single time (not per question) matters: fitting the vectorizer
    # is the expensive part, and the index never changes between questions.
    documents = rag_core.load_documents()
    chunks = rag_core.build_chunks(documents)
    vectorizer, tfidf_matrix = rag_core.build_index(chunks)

    # Friendly startup banner so the user knows what is loaded and how to quit.
    print("=" * 64)
    print("  Puppy Care RAG - ask questions about caring for your puppy")
    print(f"  Knowledge base: {len(chunks)} chunks from {len(documents)} files")
    print(f"  Model: {rag_core.MODEL} (via Groq)")
    print("  Type a question, or 'quit' to exit.")
    print("=" * 64)

    # The main loop. Each pass through handles exactly one question.
    while True:
        try:
            question = input("\nAsk a question (or 'quit'): ").strip()
        except (EOFError, KeyboardInterrupt):
            # EOFError = the input stream ended (e.g. piped input ran out);
            # KeyboardInterrupt = Ctrl-C. Either way, leave cleanly.
            print("\nGoodbye!")
            break

        if question.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break
        if not question:
            continue  # empty line: just show the prompt again

        # Hand the question to the shared core: it retrieves, applies the
        # score-threshold guard (refusing with NO_ANSWER and no API call when
        # nothing relevant turns up), and otherwise asks the model to answer.
        result = rag_core.answer_question(
            question, vectorizer, tfidf_matrix, chunks, client
        )

        # Show the sources behind every answer, so they are always visible.
        print("\nRetrieved sources:")
        for rank, (chunk, score) in enumerate(result["results"], start=1):
            preview = chunk["text"][:rag_core.SNIPPET_LEN].replace("\n", " ")
            print(f"  {rank}. [{chunk['source']}]  score={score:.3f}")
            print(f"     {preview}...")

        # The answer is either the model's reply or the verbatim NO_ANSWER text
        # when the guard refused - either way, print it the same way.
        print(f"\nAnswer: {result['answer']}\n")


if __name__ == "__main__":
    main()
