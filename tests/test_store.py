"""The data."""


def test_a_new_expense_never_gets_a_deleted_expenses_id(store):
    store.delete(6)

    row = store.add({"amount": 2.0, "category": "food", "date": "2026-10-01", "description": "tea"})

    assert row["id"] == 7  # not 6: an id the model saw earlier can never hit a newer row
