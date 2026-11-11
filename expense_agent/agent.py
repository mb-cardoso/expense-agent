"""The service: one user message through the loop, one Turn out. No print, no input."""

import datetime
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from expense_agent import prompts, tracing
from expense_agent.llm import Model, ToolResult

RunTool = Callable[[str, dict[str, Any]], dict[str, Any]]
OnLog = Callable[[str], object]  # what it returns is not used


@dataclass
class Turn:
    """The tool log, and the reply or a note. Passed in, it keeps the log when ask() raises."""

    log: list[str] = field(default_factory=list)
    reply: str | None = None
    note: str | None = None
    last_id: str | None = None
    outcome: str | None = None  # "answer", "no_answer" or "round_cap"
    rounds: int = 0
    trace_id: str | None = None  # the id a trace viewer searches for, when tracing is on


def ask(
    model: Model,
    message: str,
    previous_id: str | None,
    run_tool: RunTool,
    max_rounds: int,
    turn: Turn | None = None,
    on_log: OnLog | None = None,
    conversation_id: str | None = None,
    instruction: str | None = None,
) -> Turn:
    """One message through the loop, as one trace. on_log gets each tool line as it happens.
    instruction replaces the expense agent's: an example with other tools passes its own."""
    turn = turn if turn is not None else Turn()
    with tracing.agent_turn(message, conversation_id) as span:
        turn.trace_id = tracing.trace_id(span)
        try:
            _loop(model, message, previous_id, run_tool, max_rounds, turn, on_log, instruction)
        finally:
            tracing.end_turn(span, turn.outcome, turn.rounds, turn.reply)
    return turn


def _loop(
    model: Model,
    message: str,
    previous_id: str | None,
    run_tool: RunTool,
    max_rounds: int,
    turn: Turn,
    on_log: OnLog | None,
    instruction: str | None,
) -> None:
    if instruction is None:  # sent with every request
        instruction = prompts.INSTRUCTION.format(today=datetime.date.today())
    reply = model.send_text(prompts.USER_MESSAGE.format(text=message), previous_id, instruction)
    while True:
        turn.last_id = reply.id
        if not reply.calls:
            if reply.status == "completed" and reply.text:
                turn.outcome = "answer"
                turn.reply = reply.text
            else:  # cut short, refused, or empty
                turn.outcome = "no_answer"
                turn.note = (
                    f"No answer from the model ({reply.status}): the tool log is what was done."
                )
            return
        if turn.rounds == max_rounds:
            turn.outcome = "round_cap"
            turn.note = f"Stopped after {max_rounds} tool rounds: the tool log is what was done."
            return
        turn.rounds += 1
        results = []
        for call in reply.calls:  # in the order given: a read must see the writes before it
            with tracing.tool_call(call.name, call.id, call.arguments) as span:
                result = run_tool(call.name, call.arguments)
                tracing.tool_result(span, result)
                line = f"[{call.name}] {json.dumps(call.arguments)} -> {json.dumps(result)[:110]}"
                turn.log.append(line)
            if on_log is not None:
                on_log(line)
            results.append(ToolResult(call, result))
        reply = model.send_results(results, reply.id, instruction)
