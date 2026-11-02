"""The loop: one message, a scripted model, and a run_tool that runs nothing."""

import pytest

from expense_agent import agent
from expense_agent.llm import Call, Reply, ToolResult


def run_tool(name, arguments):
    return {"ran": name}


def test_a_reply_without_calls_is_the_answer(script):
    model = script(Reply("r1", text="You spent 18.70 euros on food."))

    turn = agent.ask(model, "How much on food?", None, run_tool, max_rounds=8)

    assert turn.reply == "You spent 18.70 euros on food."
    assert turn.log == []


def test_each_call_runs_in_order_and_its_result_goes_back(script):
    calls = [Call("c1", "add_expense", {"amount": 4}), Call("c2", "list_expenses", {})]
    # Text next to calls is not the answer: the calls decide.
    model = script(Reply("r1", calls=calls, text="Adding it."), Reply("r2", text="Done."))

    turn = agent.ask(model, "Add 4 euros, then list.", None, run_tool, max_rounds=8)

    assert model.sent[1] == [
        ToolResult(calls[0], {"ran": "add_expense"}),
        ToolResult(calls[1], {"ran": "list_expenses"}),
    ]
    assert turn.reply == "Done."


def test_the_round_cap_stops_a_model_that_keeps_calling(script):
    again = Reply("r1", calls=[Call("c1", "list_expenses", {})])
    model = script(again, again, again)

    turn = agent.ask(model, "List them.", None, run_tool, max_rounds=2)

    assert turn.outcome == "round_cap"
    assert len(turn.log) == 2  # the third call did not run
    assert turn.reply is None


@pytest.mark.parametrize(
    ("text", "status"),
    [("I have deleted your last co", "incomplete"), ("", "refusal"), ("", "completed")],
)
def test_a_reply_cut_short_refused_or_empty_is_no_answer(script, text, status):
    model = script(Reply("r1", text=text, status=status))

    turn = agent.ask(model, "Delete my last coffee.", None, run_tool, max_rounds=8)

    assert turn.outcome == "no_answer"
    assert turn.reply is None  # a cut sentence can claim what never happened
