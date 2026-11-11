"""The terminal interface: reads what the user types, prints each tool line and the reply."""

import argparse
import io
import json
import logging
import sys
import uuid

from expense_agent import agent, config, llm, tools, tracing
from expense_agent.store import make_store

COMMANDS = {
    "/help": "show this list",
    "/data": "show the data the tools keep",
    "/clear": "start a new conversation (the data stays)",
    "/quit": "leave",
}


def confirm(question: str) -> bool:
    """Put a tool's question to the user before it acts. The model cannot answer this."""
    try:
        answer = input(f"  {question} [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def show(turn: agent.Turn) -> None:
    if turn.note:
        print(f"  [{turn.note}]")
    if turn.reply:
        print("\nai  >", turn.reply)


def utf8_stdout() -> None:
    """Piped or redirected output on Windows is cp1252: an emoji would crash print()."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="expense-agent", description="The expense agent.")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="print every request to the model and every reply, and each message's trace id",
    )
    options = parser.parse_args(argv)
    utf8_stdout()
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="  %(message)s")
    if options.trace:  # only this logger: the SDK's and the HTTP library's stay quiet
        llm.logger.setLevel(logging.DEBUG)
    if not config.API_KEY:
        print(f"No API key. Copy .env.example to .env and fill in {config.KEY_NAME}.")
        return 1
    tracing.setup()
    store = make_store()
    model = llm.make_model(tools.DECLARATIONS)
    previous_id: str | None = None
    # The interface keeps the conversation, so it names it: the id groups its traces.
    conversation_id = uuid.uuid4().hex
    print("Agent ready. Model:", config.MODEL)
    print("Type /help for commands.")
    while True:
        try:
            message = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not message:
            continue
        if message.startswith("/"):
            command = message.split()[0]
            if command == "/quit":
                return 0
            if command == "/help":
                for name, description in COMMANDS.items():
                    print(f"  {name:<7} {description}")
            elif command == "/data":
                try:
                    rows = store.all()
                except Exception as error:  # noqa: BLE001 - a broken file, or no database
                    rows = []
                    print(f"  The data could not be read: {error}")
                for row in rows:
                    print("  " + json.dumps(row, ensure_ascii=False))
            elif command == "/clear":
                previous_id = None
                conversation_id = uuid.uuid4().hex
                print("  new conversation; the data is unchanged")
            else:
                print(f"  unknown command: {command}. Type /help.")
            continue
        turn = agent.Turn()
        try:
            agent.ask(
                model,
                message,
                previous_id,
                lambda name, arguments: tools.run_tool(name, arguments, store, confirm),
                config.MAX_ROUNDS,
                turn,
                on_log=lambda line: print(f"  {line}"),
                conversation_id=conversation_id,
            )
        except Exception as error:  # noqa: BLE001 - explain() re-raises anything that is a bug
            print(f"  {llm.explain(error)}")
            if options.trace and turn.trace_id:
                print(f"  trace {turn.trace_id}")
            if getattr(error, "status_code", None) == 404 and previous_id is not None:
                previous_id = None
                conversation_id = uuid.uuid4().hex
                print(
                    "  The stored conversation is gone, or the model name is unknown: "
                    "the next message starts a new one."
                )
            print("  Any tool lines above already happened. Check /data before sending it again.")
            continue
        show(turn)
        if options.trace and turn.trace_id:
            print(f"  trace {turn.trace_id}")
        previous_id = turn.last_id
