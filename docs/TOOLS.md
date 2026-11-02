# Tools

The functions the expense agent may call. Each one is declared in `tools.py` from
its argument model in `schemas.py`, runs only through `run_tool()`, and returns a
dict. A failure is a result too: the agent reads it and acts on it, and the
conversation goes on. `tests/test_tools.py` checks an unknown tool, invalid
arguments, a tool that raises, an expense dated in the future, a delete a yes
allows, and one a no refuses.

| Tool | Reads or writes | Safe to repeat | Asks the user first |
|---|---|---|---|
| `add_expense` | writes | no: a repeat stores a second expense; if a save's answer is lost, call `list_expenses` first | no |
| `list_expenses` | reads | yes | no |
| `total_by_category` | reads | yes | no |
| `delete_expense` | writes | yes: ids are never reused, so a second delete finds nothing | yes |

Any tool can also return `{"error": "There is no tool called ..."}` or
`{"error": "Invalid <field>: ... Fix it and call again."}` from `run_tool()`,
before it runs: the agent corrects its call. An unexpected exception inside a
tool comes back as `{"error": "<tool> failed: ... If it writes, it may or may not
have changed the data: read the data again before repeating it."}`. A result
that is not a dict comes back as `{"result": ...}`, and dates as text.

## How to add a tool

1. Its argument model in `schemas.py`; a rule on the values goes in `check()`, not
   in a schema bound, because the model fakes a value to pass a bound.
2. An entry in `TOOLS` in `tools.py`: the name, the model, the function, the
   description the model reads. Add it to `ASK_FIRST` if it needs a yes.
3. A row in the table above, a test in `tests/test_tools.py`, and a case in
   `evals/cases.jsonl`.

## add_expense

**Purpose.** "Record one new expense the student made."

**Parameters.**

| Name | Type | Notes |
|---|---|---|
| `amount` | number | in euros |
| `category` | one of `food`, `transport`, `housing`, `education`, `health`, `leisure`, `other` | the rules for choosing one, with examples, are in its description, in `schemas.py` |
| `date` | date, `YYYY-MM-DD` | the day the money was spent |
| `description` | text | what was bought, in a few words |

**Returns.** `{"saved": {"id", "amount", "category", "date", "description"}}`. The
id is new: ids are never reused, even after a delete.

**Fails with.** `{"saved": false, "problems": [...], "what_to_do": ...}` when
`check()` refuses the expense: the amount is not positive or is over 5,000, or
the date is in the future or more than 90 days old. The agent tells the user
why, and does not change the amount or the date they gave to make it pass.

## list_expenses

**Purpose.** "List recorded expenses with their ids, optionally only one category
or only from a day onwards."

**Parameters.**

| Name | Type | Notes |
|---|---|---|
| `category` | one of the seven categories, optional | leave out for all |
| `since` | date, optional | only expenses on or after this day |

**Returns.** `{"expenses": [{"id", "amount", "category", "date", "description"}, ...]}`,
possibly an empty list.

**Fails with.** Nothing of its own.

## total_by_category

**Purpose.** "Total amount spent in each category, over all recorded expenses."

**Parameters.** None.

**Returns.** `{"totals": {"food": 18.7, ...}}`, in euros.

**Fails with.** Nothing of its own.

## delete_expense

**Purpose.** "Ask the user to delete one recorded expense, by its id. The user
answers outside this conversation; the result says whether it was deleted." A
delete cannot be undone.

The description says so because on the page the Yes comes after the reply.
Measured on 1 November 2026, two sets of ten turns per provider, by reading the
replies: with this wording, no reply written while the question waited claimed the
delete (0 of 20 on claude-haiku-5-5, 0 of 20 on gemini-flash-lite-latest), so the
page shows the reply as the model wrote it.

**Parameters.**

| Name | Type | Notes |
|---|---|---|
| `id` | integer | as returned by `list_expenses` |

**Returns.** `{"deleted": {"id", "amount", "category", "date", "description"}}`.

**Asks the user first.** Before anything is deleted, the tool asks through the
`confirm()` the interface supplies: "Delete expense 5: coffee, 3.00 euros on
2026-10-30?", and acts only on a yes. The model cannot answer it. The terminal
asks y/N; any answer but `y` or `yes` is a no. On the page, `confirm()` returns
`None` and the tool returns
`{"deleted": false, "reason": "Waiting for the user's answer. Nothing was deleted yet."}`;
`docs/ARCHITECTURE.md` (the confirmation) says what the click does.

**Fails with.**

- `{"error": "No expense has id N. Nothing was deleted. Call list_expenses to find the right id."}`:
  the agent lists the expenses and finds the right id, or tells the user.
- `{"deleted": false, "reason": "The user declined. Nothing was deleted. Do not ask again unless the user asks you to."}`:
  nothing was deleted. The result asks the agent to tell the user so and not to
  ask again on its own; the code guarantees only that nothing was deleted.
