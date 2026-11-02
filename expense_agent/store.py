"""The expenses: the only code that reads or writes where they are kept, here a JSON file."""

import datetime
import json
from pathlib import Path
from typing import Any

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
