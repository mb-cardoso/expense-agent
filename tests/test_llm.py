"""ClaudeModel keeps the conversation the Messages API does not: these tests read the requests
it sends. GeminiModel has none: its server keeps the conversation, and mypy checks it."""

from types import SimpleNamespace

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from expense_agent import llm
from expense_agent.llm import ToolResult

CALL = ToolUseBlock(type="tool_use", id="c1", name="list_expenses", input={})
TEXT = TextBlock(type="text", text="Done.")


def message(id, stop, *content):
    """A reply as the SDK returns it."""
    usage = Usage(input_tokens=1, output_tokens=1)
    return Message(
        id=id,
        content=list(content),
        model="m",
        role="assistant",
        stop_reason=stop,
        type="message",
        usage=usage,
    )


def claude(*replies):
    """A ClaudeModel whose API answers with these replies; requests keeps what it sent."""
    answers, requests = list(replies), []

    def create(**request):
        requests.append(request)
        return answers.pop(0)

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return llm.ClaudeModel(client, "m", []), requests


def test_a_call_left_without_a_result_is_answered_before_the_next_message():
    # The round cap can end a turn on a call: the API wants a result for it before any text.
    model, requests = claude(message("m1", "tool_use", CALL), message("m2", "end_turn", TEXT))
    model.send_text("List them.", None, "Today is x.")

    model.send_text("Next message.", "m1", "Today is x.")

    not_run, text = requests[1]["messages"][-1]["content"]
    assert (not_run["tool_use_id"], not_run["is_error"]) == ("c1", True)
    assert text == {"type": "text", "text": "Next message."}


def test_after_a_refusal_the_call_that_ran_is_not_answered_again():
    model, requests = claude(
        message("m1", "tool_use", CALL), message("m2", "refusal"), message("m3", "end_turn", TEXT)
    )
    first = model.send_text("Add it.", None, "Today is x.")
    model.send_results([ToolResult(first.calls[0], {"saved": True})], "m1", "Today is x.")

    model.send_text("Next message.", "m2", "Today is x.")

    sent = requests[2]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user", "user"]  # no refusal
    assert sent[3]["content"] == [{"type": "text", "text": "Next message."}]  # no second result
