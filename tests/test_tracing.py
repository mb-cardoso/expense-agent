"""The traces, offline: the spans the Langfuse SDK would send, read from memory."""

import os
import subprocess
import sys

import pytest
from opentelemetry.trace import StatusCode

from expense_agent import agent, config, tools
from expense_agent.llm import Call, Reply


def run_nothing(name, arguments):
    return {}


def test_a_message_is_one_trace_with_its_tool_calls_inside(script, spans):
    model = script(Reply("r1", calls=[Call("c1", "list_expenses", {})]), Reply("r2", text="Done."))

    turn = agent.ask(model, "How much?", None, run_nothing, max_rounds=8)

    tool, root = spans()  # in the order they ended
    assert root.parent is None  # the message starts a trace of its own
    assert tool.parent == root.context  # the tool call is a step inside it
    assert turn.trace_id == format(root.context.trace_id, "032x")  # the id --trace prints


@pytest.mark.parametrize("content", [False, True])
def test_what_was_written_is_traced_only_when_turned_on(monkeypatch, script, store, spans, content):
    monkeypatch.setattr(config, "TRACE_CONTENT", content)
    model = script(
        Reply("r1", calls=[Call("c1", "delete_expense", {"id": 5})]), Reply("r2", text="Kept.")
    )

    def run_tool(name, arguments):  # the user answers no
        return tools.run_tool(name, arguments, store, lambda question: False)

    agent.ask(model, "Delete my last coffee.", None, run_tool, max_rounds=8)

    exported = "".join(span.to_json() for span in spans())  # all that would leave the machine
    assert ("coffee" in exported) is content  # in the message and in the tool's question


def test_a_message_without_an_answer_is_marked_as_an_error(script, spans):
    model = script(Reply("r1", text="I have deleted your last co", status="incomplete"))

    agent.ask(model, "Delete my last coffee.", None, run_nothing, max_rounds=8)

    (root,) = spans()
    assert root.status.status_code is StatusCode.ERROR  # Langfuse shows level ERROR
    assert root.status.description == "no_answer"


def test_without_langfuse_keys_nothing_is_sent_or_said():
    code = (
        "from expense_agent import tracing\n"
        "tracing.setup()\n"
        "with tracing.agent_turn('Hi', None): pass"
    )
    # The two key lines of .env.example, empty. Set here, they win over .env. A fresh Python:
    # this one already has the test client.
    env = {**os.environ, "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}

    ran = subprocess.run([sys.executable, "-c", code], check=False, env=env, capture_output=True)

    assert ran.stderr == b""  # no warning, no failed upload, no traceback
