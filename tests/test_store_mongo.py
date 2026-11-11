"""The MongoDB store, against a real database: only with MONGODB_URI set, so CI skips it."""

import os

import pytest

from expense_agent.store import MongoStore

URI = os.getenv("MONGODB_URI", "")
DATABASE = "expense_agent_test"  # emptied before and after: never the app's own database
pytestmark = pytest.mark.skipif(not URI, reason="MONGODB_URI is not set")


def clear(store):
    for name in ("expenses", "ids"):  # a collection drop: Atlas's read-write role cannot drop a database
        store.client[DATABASE].drop_collection(name)


@pytest.fixture
def mongo():
    clear(MongoStore(URI, DATABASE))  # what an earlier run left
    store = MongoStore(URI, DATABASE)
    yield store
    clear(store)


def test_a_database_used_for_the_first_time_holds_the_six_examples(mongo):
    assert [row["id"] for row in mongo.all()] == [1, 2, 3, 4, 5, 6]


def test_a_new_expense_never_gets_a_deleted_expenses_id(mongo):
    mongo.delete(6)

    row = mongo.add({"amount": 2.0, "category": "food", "date": "2026-10-01", "description": "tea"})

    assert row["id"] == 7
    assert mongo.get(7) == row and mongo.get(6) is None
