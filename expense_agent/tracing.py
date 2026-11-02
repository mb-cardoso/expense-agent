"""Tracing with the Langfuse SDK, the only module that imports it: one trace per message."""

import contextlib
from collections.abc import Iterator
from typing import Any

from langfuse import (
    Langfuse,
    LangfuseAgent,
    LangfuseGeneration,
    LangfuseTool,
    get_client,
    propagate_attributes,
)

from expense_agent import config


def setup() -> None:
    """At start: the process's one Langfuse client, which get_client() returns from now on.
    A second call, with the same key, gets the same one."""
    Langfuse(
        # Stand-in keys when there are none: without a key, every get_client() warns.
        public_key=config.LANGFUSE_PUBLIC_KEY or "none",
        secret_key=config.LANGFUSE_SECRET_KEY or "none",
        base_url=config.LANGFUSE_BASE_URL,
        environment=config.LANGFUSE_ENVIRONMENT,
        tracing_enabled=config.TRACING,
    )


def _content(value: Any) -> Any:
    return value if config.TRACE_CONTENT else None  # None: the SDK leaves the field out


@contextlib.contextmanager
def agent_turn(message: str, conversation_id: str | None) -> Iterator[LangfuseAgent]:
    """The root of one message's trace: every model and tool observation nests in it."""
    with (
        get_client().start_as_current_observation(
            as_type="agent", name="expense_agent", input=_content(message)
        ) as turn,
        propagate_attributes(session_id=conversation_id),  # this one and every child
    ):
        yield turn


def end_turn(turn: LangfuseAgent, outcome: str | None, rounds: int, reply: str | None) -> None:
    """How the turn ended. Anything but an answer marks it ERROR: a filter on level finds it."""
    failed = outcome not in (None, "answer")  # None: an exception ended it, and it is recorded
    turn.update(
        output=_content(reply or ""),
        metadata={"outcome": outcome, "rounds": rounds},
        level="ERROR" if failed else None,
        status_message=outcome if failed else None,
    )


def model_call(
    name: str, model: str, sent: Any
) -> contextlib.AbstractContextManager[LangfuseGeneration]:
    """One request to the model, as a generation: what was sent, only with content on."""
    return get_client().start_as_current_observation(
        as_type="generation", name=name, model=model, input=_content(sent)
    )


def model_result(
    generation: LangfuseGeneration,
    model: str | None,
    text: str,
    calls: list[Any],
    tokens_in: int,
    tokens_out: int,
) -> None:
    """The model that answered, which prices it, and the tokens billed. Output only with content
    on: the text, and the calls when there are any."""
    output = {"text": text, "calls": calls} if calls else text
    usage = {"input": tokens_in, "output": tokens_out}
    generation.update(model=model, output=_content(output), usage_details=usage)


def tool_call(
    name: str, call_id: str, arguments: dict[str, Any]
) -> contextlib.AbstractContextManager[LangfuseTool]:
    return get_client().start_as_current_observation(
        as_type="tool", name=name, input=_content(arguments), metadata={"call_id": call_id}
    )


def tool_result(span: LangfuseTool, result: dict[str, Any]) -> None:
    span.update(output=_content(result))


def tool_failed(reason: str | Exception) -> None:
    """Mark the running tool's observation failed: a short fixed name, or the exception's type."""
    kind = reason if isinstance(reason, str) else type(reason).__name__
    get_client().update_current_span(level="ERROR", status_message=kind)


def confirmation(question: str, approved: bool | None) -> None:
    """The user's answer to a tool's question, on that tool's observation. None: not yet."""
    answer = "waiting" if approved is None else "approved" if approved else "declined"
    get_client().update_current_span(
        metadata={"confirmation": answer, "question": _content(question)}
    )


def trace_id(turn: LangfuseAgent) -> str | None:
    """The trace id in hex, as Langfuse searches for it. None when nothing is recorded."""
    return turn.trace_id if turn.trace_id.strip("0") else None
