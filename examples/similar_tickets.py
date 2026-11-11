"""Tickets like this one: a tool the model calls, answered by MongoDB Atlas Vector Search.
The 30 past tickets are embedded once with Gemini and stored with their vectors, in the
expenses' database; a vector index on the collection ranks them in one query.
Needs MONGODB_URI, and GOOGLE_API_KEY for the embeddings whatever PROVIDER says. From the
project folder:
    uv run python examples/similar_tickets.py"""

import json
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from expense_agent import agent, config, llm, tracing

DIMENSIONS = 768
FIELDS = ("id", "category", "text", "resolution")
INSTRUCTION = (
    "You help a support team. For a new ticket, call similar_tickets with its text and answer "
    "from the result: which past tickets are like it, by id, and how each was resolved."
)
NEW_TICKET = "I was charged twice for my subscription this month. Please give me my money back."
DECLARATIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "similar_tickets",
        "description": "The past tickets most like a new ticket's text, with how each was resolved.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The new ticket's text"}},
            "required": ["text"],
        },
    }
]
if not config.MONGODB_URI:
    raise SystemExit("Set MONGODB_URI in .env: the tickets live in MongoDB Atlas.")
gemini = genai.Client()  # GOOGLE_API_KEY from the environment, which config.py filled from .env
tickets = MongoClient[dict[str, Any]](config.MONGODB_URI).expense_agent.tickets


def embed(texts: list[str]) -> list[list[float]]:
    """gemini-embedding-2 at 768 dimensions. One Content per text, or the list comes back as
    one embedding. The prefixes are the documented ones: what is stored, and what is searched."""
    result = gemini.models.embed_content(
        model="gemini-embedding-2",
        contents=[types.Content(parts=[types.Part(text=text)]) for text in texts],
        config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
    )
    return [embedding.values or [] for embedding in result.embeddings or []]


def store(rows: list[dict[str, Any]]) -> None:
    """Once: the tickets with their vectors, and the index, which Atlas builds on its side."""
    vectors = embed([f"title: none | text: {row['text']}" for row in rows])
    tickets.insert_many([{**row, "embedding": v} for row, v in zip(rows, vectors)])
    field = {
        "type": "vector",
        "path": "embedding",
        "numDimensions": DIMENSIONS,
        "similarity": "cosine",
    }
    tickets.create_search_index(  # a free cluster allows three search indexes in all
        SearchIndexModel(name="vector_index", type="vectorSearch", definition={"fields": [field]})
    )
    while not all(index.get("queryable") for index in tickets.list_search_indexes("vector_index")):
        time.sleep(2)


def similar(text: str, k: int) -> list[dict[str, Any]]:
    """The k nearest tickets: the database ranks them, in one query."""
    [vector] = embed([f"task: search result | query: {text}"])
    # $vectorSearch must be the first stage; numCandidates about 20 times the limit (Atlas docs).
    search = {"index": "vector_index", "path": "embedding", "queryVector": vector, "limit": k}
    shown = {"_id": 0, **{f: 1 for f in FIELDS}, "score": {"$meta": "vectorSearchScore"}}
    stages = [{"$vectorSearch": {**search, "numCandidates": 20 * k}}, {"$project": shown}]
    return [{**hit, "score": round(hit["score"], 3)} for hit in tickets.aggregate(stages)]


def run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"tickets": similar(arguments["text"], 5)}


if tickets.estimated_document_count() == 0:
    rows = json.loads(Path(__file__).with_name("tickets.json").read_text(encoding="utf-8"))
    store(rows["historical_tickets"])
    print(f"stored {tickets.estimated_document_count()} tickets with their embeddings")
tracing.setup()
turn = agent.ask(
    llm.make_model(DECLARATIONS),
    f"New ticket: {NEW_TICKET}",
    None,
    run_tool,
    config.MAX_ROUNDS,
    on_log=lambda line: print(f"  {line}"),
    instruction=INSTRUCTION,
)
print(f"ai  > {turn.reply}")
print(f"  trace {turn.trace_id}")
