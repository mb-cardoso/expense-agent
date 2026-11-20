"""AI access: the only module that imports a provider's SDK. The interface the loop uses, one
adapter per provider, make_model() and explain(). Tests script a Model."""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
from anthropic.types import ContentBlockParam, MessageParam, ToolParam
from google import genai
from google.genai import errors
from google.genai import interactions as gi

from expense_agent import config, tracing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Call:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    id: str
    calls: list[Call] = field(default_factory=list)
    text: str = ""
    status: str = "completed"  # "requires_action" for calls, or why it stopped: incomplete, refusal


@dataclass(frozen=True)
class ToolResult:
    call: Call
    result: dict[str, Any]


class Model(Protocol):
    def send_text(self, text: str, previous_id: str | None, instruction: str) -> Reply: ...
    def send_results(
        self, results: Sequence[ToolResult], previous_id: str, instruction: str
    ) -> Reply: ...


def _log_request(
    previous_id: str | None, instruction: str, tools: int, sent: str | Sequence[ToolResult]
) -> None:
    """One line for --trace: the text sent, or which calls the results answer."""
    if isinstance(sent, str):
        what = repr(sent[:80])
    else:
        what = ", ".join(f"result of {r.call.name} ({r.call.id})" for r in sent)
    logger.debug(
        "request  previous=%s instruction=%d chars tools=%d input=%s",
        previous_id[-8:] if previous_id else None,
        len(instruction),
        tools,
        what,
    )


def _log_reply(reply: Reply) -> None:
    logger.debug(
        "reply    id=%s status=%s calls=%s text=%r",
        reply.id[-8:],
        reply.status,
        [f"{call.name} {json.dumps(call.arguments)}" for call in reply.calls] or "none",
        reply.text[:80],
    )


class GeminiModel:
    """The Interactions API. The conversation is kept on the server, by id."""

    def __init__(self, client: genai.Client, model: str, declarations: list[dict[str, Any]]):
        self.client = client
        self.model = model
        self.declarations = declarations

    def send_text(self, text: str, previous_id: str | None, instruction: str) -> Reply:
        _log_request(previous_id, instruction, len(self.declarations), text)
        return self._create(text, previous_id, instruction)

    def send_results(
        self, results: Sequence[ToolResult], previous_id: str, instruction: str
    ) -> Reply:
        _log_request(previous_id, instruction, len(self.declarations), results)
        items = [
            {
                "type": "function_result",
                "call_id": r.call.id,
                "name": r.call.name,
                "result": r.result,
            }
            for r in results
        ]
        return self._create(items, previous_id, instruction)

    def _create(self, input: Any, previous_id: str | None, instruction: str) -> Reply:
        with tracing.model_call("interactions.create", self.model, input) as generation:
            interaction = self.client.interactions.create(  # the settings go with every request
                model=self.model,
                system_instruction=instruction,
                tools=self.declarations,
                input=input,
                previous_interaction_id=previous_id,
            )
            if not isinstance(interaction, gi.Interaction) or interaction.id is None:
                raise TypeError(f"Expected a stored interaction, got {type(interaction).__name__}")
            # The calls come from the steps, never from output_text; steps is None on a cut reply.
            calls = [
                Call(id=step.id, name=step.name, arguments=dict(step.arguments))
                for step in interaction.steps or []
                if isinstance(step, gi.FunctionCallStep)
            ]
            text = (interaction.output_text or "").strip()
            reply = Reply(id=interaction.id, calls=calls, text=text, status=interaction.status)
            usage = interaction.usage or gi.Usage()
            thought = usage.total_thought_tokens or 0  # counted apart, and billed as output
            output = (usage.total_output_tokens or 0) + thought
            tracing.model_result(
                generation, interaction.model, text, calls, usage.total_input_tokens or 0, output
            )
        _log_reply(reply)
        return reply


MAX_TOKENS = 16_000  # Claude requires it; the thinking counts toward it
STATUS = {"end_turn": "completed", "tool_use": "requires_action", "refusal": "refusal"}
NOT_RUN = {"error": "Not run: the turn ended before this call ran."}
# What a Claude reply id names: the system prompt, the messages, the calls still without a result.
Saved = tuple[str, list[MessageParam], list[str]]


class ClaudeModel:
    """The Messages API keeps nothing, so this class keeps what Gemini's server keeps: each
    reply's conversation, by the reply's id. Every request sends all of it."""

    def __init__(self, client: anthropic.Anthropic, model: str, declarations: list[dict[str, Any]]):
        self.client = client
        self.model = model
        self.tools: list[ToolParam] = [
            {"name": d["name"], "description": d["description"], "input_schema": d["parameters"]}
            for d in declarations
        ]
        self.saved: dict[str, Saved] = {}

    def send_text(self, text: str, previous_id: str | None, instruction: str) -> Reply:
        _log_request(previous_id, instruction, len(self.tools), text)
        waiting = self.saved[previous_id][2] if previous_id else []
        # A call left without a result (the round cap, a cut reply) is a 400: answer it first.
        blocks: list[ContentBlockParam] = [_result_block(call_id, NOT_RUN) for call_id in waiting]
        blocks.append({"type": "text", "text": text})
        return self._create(blocks, previous_id, instruction)

    def send_results(
        self, results: Sequence[ToolResult], previous_id: str, instruction: str
    ) -> Reply:
        _log_request(previous_id, instruction, len(self.tools), results)
        blocks: list[ContentBlockParam] = [_result_block(r.call.id, r.result) for r in results]
        return self._create(blocks, previous_id, instruction)

    def _create(
        self, blocks: list[ContentBlockParam], previous_id: str | None, instruction: str
    ) -> Reply:
        system, history, _ = self.saved[previous_id] if previous_id else (instruction, [], [])
        messages: list[MessageParam] = [*history, {"role": "user", "content": blocks}]
        with tracing.model_call("messages.create", self.model, blocks) as generation:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,  # the conversation's first: a new one voids the thinking sent back
                tools=self.tools,
                messages=messages,
                output_config={"effort": config.EFFORT},  # thinking is on by default: how much
            )
            content = response.content
            status = STATUS.get(response.stop_reason or "", "incomplete")
            calls = [Call(b.id, b.name, dict(b.input)) for b in content if b.type == "tool_use"]
            text = "".join(b.text for b in content if b.type == "text").strip()
            usage = response.usage  # output_tokens is what is billed, the thinking included
            tracing.model_result(
                generation, response.model, text, calls, usage.input_tokens, usage.output_tokens
            )
        if content and status != "refusal":  # sent back as it came, thinking blocks included
            answer: MessageParam = {"role": "assistant", "content": content}
            self.saved[response.id] = (system, [*messages, answer], [call.id for call in calls])
        else:  # a refused or empty reply is never sent back: the API joins the user turns around it
            self.saved[response.id] = (system, messages, [])  # a refused message stays until /clear
        reply = Reply(response.id, calls if status == "requires_action" else [], text, status)
        _log_reply(reply)
        return reply


def _result_block(call_id: str, value: dict[str, Any]) -> ContentBlockParam:
    content = json.dumps(value, ensure_ascii=False)
    is_error = "error" in value
    return {"type": "tool_result", "tool_use_id": call_id, "content": content, "is_error": is_error}


def make_model(declarations: list[dict[str, Any]]) -> Model:
    """The adapter of config.PROVIDER. The loop, the tools and the interfaces never know which."""
    if config.PROVIDER == "anthropic":
        # False: _create records each request, as Gemini's; the SDK's own span would be a second.
        client = anthropic.Anthropic(api_key=config.API_KEY, open_telemetry=False)
        return ClaudeModel(client, config.MODEL, declarations)
    return GeminiModel(genai.Client(api_key=config.API_KEY), config.MODEL, declarations)


def explain(error: Exception) -> str:
    """A sentence for the user about a failed request. Re-raises what is a bug, not an API error."""
    # Interactions can answer in several requests; one failed after the first.
    if isinstance(error, errors.ContinuationInterruptedError):
        return "The model's reply was cut by a failed request: send the message again."
    # Gemini's API errors all have a status_code, None without a connection; Anthropic's
    # connection errors have none.
    if not hasattr(error, "status_code") and not isinstance(error, anthropic.APIConnectionError):
        raise error
    status = getattr(error, "status_code", None)
    if status is None:
        return "Could not reach the API: no connection, or the request timed out."
    if status == 429:
        return "Rate limit reached, even after the SDK's own retries. Wait a minute."
    if status >= 500:
        return f"The API is having problems ({status}). Try again shortly."
    if status == 402:
        return "Tjhe API key has no credits left. Trying again will not help."
    return f"The API rejected the request ({status}): {str(error)[:200]}"
