"""The expenses: the only code that reads or writes where they are kept, a JSON file or MongoDB."""

import datetime
import json
from pathlib import Path
from typing import Any, Protocol

from pymongo import MongoClient, ReturnDocument

from expense_agent import config

Expense = dict[str, Any]


def seed(today: datetime.date) -> list[Expense]:
    """Six expenses from the past week, dated from today so the examples never go stale."""
    rows = [
        (3.20, "food", 6, "coffee"),
        (1.80, "transport", 6, "metro ticket"),
        (45.00, "education", 5, "statistics textbook"),
        (12.50, "food", 4, "lunch with friends"),
        (3.00, "food", 2, "coffee"),
        (9.00, "leisure", 1, "cinema"),
    ]
    return [
        {
            "id": i,
            "amount": amount,
            "category": category,
            "date": str(today - datetime.timedelta(days=days)),
            "description": text,
        }
        for i, (amount, category, days, text) in enumerate(rows, start=1)
    ]


class Store(Protocol):
    """What the tools ask of the data, wherever it is kept."""

    def all(self) -> list[Expense]: ...
    def get(self, expense_id: int) -> Expense | None: ...
    def add(self, fields: Expense) -> Expense: ...
    def delete(self, expense_id: int) -> None: ...


class ExpenseStore:
    """The expenses and the next id, in one JSON file. A missing file starts from the examples."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            rows = seed(datetime.date.today())
            self._write({"next_id": len(rows) + 1, "expenses": rows})
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def all(self) -> list[Expense]:
        return self._read()["expenses"]

    def get(self, expense_id: int) -> Expense | None:
        return next((row for row in self.all() if row["id"] == expense_id), None)

    def add(self, fields: Expense) -> Expense:
        data = self._read()
        row = {"id": data["next_id"], **fields}  # never reused: a stale id cannot hit a newer row
        self._write({"next_id": row["id"] + 1, "expenses": [*data["expenses"], row]})
        return row

    def delete(self, expense_id: int) -> None:
        data = self._read()
        kept = [row for row in data["expenses"] if row["id"] != expense_id]
        self._write({**data, "expenses": kept})


class MongoStore:
    """The expenses in MongoDB, one document each, and the next id in a counter document. A
    database used for the first time starts from the examples."""

    def __init__(self, uri: str, database: str = "expense_agent") -> None:
        # One client per store: it pools connections. 5 s to find the server, not the default 30.
        self.client: MongoClient[Expense] = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.expenses = self.client[database]["expenses"]
        self.ids = self.client[database]["ids"]  # the next id, kept apart: an id is never reused
        if self.ids.find_one({"_id": "expenses"}) is None:  # first use ever, not just empty
            rows = seed(datetime.date.today())
            self.expenses.insert_many([dict(row) for row in rows])  # copies: inserting adds _id
            self.ids.insert_one({"_id": "expenses", "next": len(rows) + 1})

    def all(self) -> list[Expense]:
        return list(self.expenses.find({}, {"_id": 0}).sort("id"))

    def get(self, expense_id: int) -> Expense | None:
        return self.expenses.find_one({"id": expense_id}, {"_id": 0})

    def add(self, fields: Expense) -> Expense:
        counter = self.ids.find_one_and_update(
            {"_id": "expenses"}, {"$inc": {"next": 1}}, return_document=ReturnDocument.BEFORE
        )
        assert counter is not None  # __init__ made it
        row = {"id": counter["next"], **fields}
        self.expenses.insert_one(dict(row))
        return row

    def delete(self, expense_id: int) -> None:
        self.expenses.delete_one({"id": expense_id})


def make_store() -> Store:
    """MongoDB when MONGODB_URI is set, the JSON file otherwise. The tools never know which."""
    if config.MONGODB_URI:
        return MongoStore(config.MONGODB_URI)
    return ExpenseStore(config.DATA_FILE)
