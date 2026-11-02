"""What the model may call, run only here. Never talks to the user: it asks through confirm()."""

import datetime
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from expense_agent import tracing
from expense_agent.schemas import AddExpense, DeleteExpense, ListExpenses, NoArguments, check
from expense_agent.store import ExpenseStore

Result = dict[str, Any]
Confirm = Callable[[str], bool | None]  # None: the user answers later


def add_expense(store: ExpenseStore, args: AddExpense) -> Result:
    if problems := check(args, datetime.date.today()):
        return {  # the last sentence stops the model "fixing" a date and saving that
            "saved": False,
            "problems": problems,
            "what_to_do": "Nothing was saved. Tell the user why. Do not change the amount "
            "or the date they gave to make it pass.",
        }
    return {"saved": store.add(args.model_dump(mode="json"))}


def list_expenses(store: ExpenseStore, args: ListExpenses) -> Result:
    rows = [
        row
        for row in store.all()
        if (args.category is None or row["category"] == args.category)
        and (args.since is None or row["date"] >= str(args.since))
    ]
    return {"expenses": rows}


def total_by_category(store: ExpenseStore, args: NoArguments) -> Result:
    totals: dict[str, float] = {}
    for row in store.all():
        totals[row["category"]] = round(totals.get(row["category"], 0) + row["amount"], 2)
    return {"totals": totals}


def delete_expense(store: ExpenseStore, args: DeleteExpense, confirm: Confirm) -> Result:
    if (row := store.get(args.id)) is None:
        tracing.tool_failed("not_found")
        return {
            "error": f"No expense has id {args.id}. Nothing was deleted. "
            "Call list_expenses to find the right id."
        }
    question = (  # asked in code: nothing the model writes can skip it
        f"Delete expense {row['id']}: {row['description']}, "
        f"{row['amount']:.2f} euros on {row['date']}?"
    )
    approved = confirm(question)
    tracing.confirmation(question, approved)
    if approved is None:  # the user has not answered yet
        return {
            "deleted": False,
            "reason": "Waiting for the user's answer. Nothing was deleted yet.",
        }
    if not approved:
        return {  # "do not ask again": without it, the model asks again more often
            "deleted": False,
            "reason": "The user declined. Nothing was deleted. "
            "Do not ask again unless the user asks you to.",
        }
    store.delete(args.id)
    return {"deleted": row}


# name: (argument model, function, description). The declarations are built from it.
TOOLS: dict[str, tuple[type[BaseModel], Callable[..., Any], str]] = {
    "add_expense": (AddExpense, add_expense, "Record one new expense the student made."),
    "list_expenses": (
        ListExpenses,
        list_expenses,
        (
            "List recorded expenses with their ids, optionally only one category "
            "or only from a day onwards."
        ),
    ),
    "total_by_category": (
        NoArguments,
        total_by_category,
        "Total amount spent in each category, over all recorded expenses.",
    ),
    "delete_expense": (
        DeleteExpense,
        delete_expense,
        (
            "Ask the user to delete one recorded expense, by its id. The user answers "
            "outside this conversation; the result says whether it was deleted."
        ),
    ),
}
ASK_FIRST = {"delete_expense"}  # tools that get confirm() and must have a yes before acting
DECLARATIONS = [
    {"type": "function", "name": name, "description": text, "parameters": model.model_json_schema()}
    for name, (model, _, text) in TOOLS.items()
]


def run_tool(name: str, arguments: dict[str, Any], store: ExpenseStore, confirm: Confirm) -> Result:
    """Run one call the model asked for. Every failure comes back as a result; nothing raises."""
    if name not in TOOLS:
        tracing.tool_failed("unknown_tool")
        return {"error": f"There is no tool called {name}. The tools are: {', '.join(TOOLS)}."}
    model, function, _ = TOOLS[name]
    try:
        args = model.model_validate(arguments)
    except ValidationError as error:
        tracing.tool_failed("invalid_arguments")
        problem = error.errors()[0]
        field = ".".join(str(part) for part in problem["loc"]) or "arguments"
        return {"error": f"Invalid {field}: {problem['msg']}. Fix it and call again."}
    try:
        result = function(store, args, confirm) if name in ASK_FIRST else function(store, args)
    except Exception as error:  # noqa: BLE001 - the contract: a tool failure is a result
        tracing.tool_failed(error)
        return {  # a write that failed half-way may have changed the data: say so
            "error": f"{name} failed: {str(error).rstrip('.')}. If it writes, it may or may not "
            "have changed the data: read the data again before repeating it."
        }
    # The APIs take a dict of JSON values: wrap anything else; dates become text.
    if not isinstance(result, dict):
        result = {"result": result}
    return json.loads(json.dumps(result, default=str))
