"""The terminal: output piped on Windows, and the order of what it prints."""

import io
import sys

from expense_agent import cli, config, llm
from expense_agent.llm import Call, Reply


def test_utf8_stdout_lets_an_emoji_through_a_cp1252_pipe(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))  # Windows, piped

    cli.utf8_stdout()
    print("Saved. \U0001f600", flush=True)  # without utf8_stdout(): UnicodeEncodeError

    assert raw.getvalue().decode("utf-8").startswith("Saved. \U0001f600")


def test_the_y_n_question_comes_after_the_tool_line_before_it(monkeypatch, capsys, script, store):
    calls = [Call("c1", "list_expenses", {}), Call("c2", "delete_expense", {"id": 5})]
    model = script(Reply("r1", calls=calls), Reply("r2", text="Deleted."))
    monkeypatch.setattr(config, "API_KEY", "not-used")
    monkeypatch.setattr(config, "DATA_FILE", store.path)
    monkeypatch.setattr(llm, "make_model", lambda declarations: model)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Delete my last coffee.\ny\n"))  # typed

    cli.main([])

    screen = capsys.readouterr().out
    assert screen.index("[list_expenses]") < screen.index("Delete expense 5: coffee")
