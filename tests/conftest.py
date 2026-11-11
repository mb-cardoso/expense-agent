"""What the tests share. No test reaches the network: the model is scripted, and the traces
stay in memory."""

import os

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from expense_agent import config
from expense_agent.store import ExpenseStore

# The process's one Langfuse client, made before any test, keeps every trace in MEMORY.
# setup(), which the page and the terminal run, asks for the same key, so it gets this client.
os.environ.pop("LANGFUSE_TRACING_ENABLED", None)  # whatever .env says: the tests read the traces
MEMORY = InMemorySpanExporter()
LANGFUSE = Langfuse(public_key="pk-lf-test", secret_key="sk-lf-test", span_exporter=MEMORY)
config.LANGFUSE_PUBLIC_KEY = "pk-lf-test"
config.MONGODB_URI = ""  # whatever .env says: the page and the terminal tests use the file


class ScriptedModel:
    """Stands in for GeminiModel or ClaudeModel: answers with the prepared replies, in order,
    and keeps what each request sent, the user's text or the tool results."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def send_text(self, text, previous_id, instruction):
        self.sent.append(text)
        return self.replies.pop(0)

    def send_results(self, results, previous_id, instruction):
        self.sent.append(results)
        return self.replies.pop(0)


@pytest.fixture
def script():
    """script(Reply(...), Reply(...)) is a model that answers with those replies."""
    return ScriptedModel


@pytest.fixture
def store(tmp_path):
    """The six example expenses, in this test's own folder."""
    return ExpenseStore(tmp_path / "expenses.json")


@pytest.fixture
def spans():
    """spans() returns the spans this test recorded, as the Langfuse SDK would send them."""
    LANGFUSE.flush()  # what earlier tests recorded goes out before it is cleared
    MEMORY.clear()

    def recorded():
        LANGFUSE.flush()  # the SDK sends in batches
        return MEMORY.get_finished_spans()

    return recorded
