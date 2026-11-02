"""The argument models the model fills in, and check(): shape in the schema, rules in code."""

import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["food", "transport", "housing", "education", "health", "leisure", "other"]

# The rules for choosing a category, with examples, where the model reads them: the argument's
# description.
HOUSE_RULES = """Anything bought for university is education, whatever it is. \
Transport is only the daily commute; trips taken for fun or social events are leisure.
Examples:
<example>Headphones for online lectures, 50 euros. -> education</example>
<example>Taxi to a friend's party, 9 euros. -> leisure</example>
<example>Metro ticket to class, 1.80. -> transport</example>
<example>Lunch at the faculty canteen, 4 euros. -> food</example>
<example>Yoga class, 10 euros. -> health</example>"""


class AddExpense(BaseModel):
    amount: float = Field(description="Amount in euros")
    category: Category = Field(description=HOUSE_RULES)
    date: datetime.date = Field(description="Day the money was spent")
    description: str = Field(description="What was bought, in a few words")


class ListExpenses(BaseModel):
    category: Category | None = None
    since: datetime.date | None = Field(None, description="Only expenses on or after this day")


class NoArguments(BaseModel):
    pass


class DeleteExpense(BaseModel):
    id: int = Field(description="The id of the expense, as returned by list_expenses")


# Ranges and dates are checked here, not as schema bounds: a bound bends the answer to fit.
def check(expense: AddExpense, today: datetime.date) -> list[str]:
    """Business rules. An empty list means the expense may be saved."""
    problems = []
    if expense.amount <= 0:
        problems.append("amount is not positive")
    if expense.amount > 5000:
        problems.append("amount is implausibly large")
    if expense.date > today:
        problems.append("date is in the future")
    elif (today - expense.date).days > 90:
        problems.append(f"date {expense.date} is more than 90 days old")
    return problems
