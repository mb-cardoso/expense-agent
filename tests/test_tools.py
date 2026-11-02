"""The contracts in docs/TOOLS.md: what run_tool() returns, and what it leaves in the data."""

import datetime

from expense_agent import tools


def no(question):
    return False


def test_an_unknown_tool_is_an_error_result(store):
    result = tools.run_tool("refund", {}, store, no)

    assert result["error"].startswith("There is no tool called refund.")


def test_invalid_arguments_are_an_error_that_names_the_field(store):
    result = tools.run_tool("add_expense", {"amount": 3, "category": "gifts"}, store, no)

    assert result["error"].startswith("Invalid category")


def test_an_exception_in_a_tool_becomes_a_result(store):
    store.path.write_text("not JSON")  # a broken data file: reading it raises

    result = tools.run_tool("list_expenses", {}, store, no)

    assert result["error"].startswith("list_expenses failed")


def test_an_expense_dated_in_the_future_is_not_saved(store):
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    expense = {"amount": 10, "category": "health", "date": str(tomorrow), "description": "gym"}

    result = tools.run_tool("add_expense", expense, store, no)

    assert result["problems"] == ["date is in the future"]
    assert len(store.all()) == 6  # still the six examples


def test_a_delete_asks_the_user_and_a_yes_deletes(store):
    questions = []

    def yes(question):
        questions.append(question)
        return True

    tools.run_tool("delete_expense", {"id": 5}, store, yes)

    assert questions[0].startswith("Delete expense 5: coffee, 3.00 euros on")
    assert store.get(5) is None


def test_a_declined_delete_changes_nothing(store):
    before = store.all()

    result = tools.run_tool("delete_expense", {"id": 5}, store, no)

    assert result["deleted"] is False
    assert store.all() == before
