"""The page, run by Streamlit's AppTest with a scripted model: no browser, no network."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from expense_agent import config, llm
from expense_agent.llm import Call, Reply

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def page(monkeypatch, script, store):
    """The page after "Delete my last coffee.": the delete waits for a Yes or No click."""
    model = script(
        Reply("r1", calls=[Call("c1", "delete_expense", {"id": 5})]),
        Reply("r2", text="Please confirm the delete."),
        Reply("r3", text="OK."),  # for a message typed next
    )
    monkeypatch.setattr(config, "API_KEY", "not-used")
    monkeypatch.setattr(config, "DATA_FILE", store.path)
    monkeypatch.setattr(llm, "make_model", lambda declarations: model)
    at = AppTest.from_file(APP, default_timeout=30).run()  # 30 s: the first run imports a lot
    at.chat_input[0].set_value("Delete my last coffee.").run()
    return at


def test_yes_deletes(page, store):
    page.button(key="yes0").click().run()

    assert store.get(5) is None
    assert not page.warning  # the question is gone


def test_no_deletes_nothing(page, store):
    page.button(key="no0").click().run()

    assert store.get(5) is not None
    assert not page.warning


def test_a_typed_message_drops_the_question(page, store):
    page.chat_input[0].set_value("Yes, delete it.").run()

    assert not page.warning  # no old button is left to delete later
    assert store.get(5) is not None
