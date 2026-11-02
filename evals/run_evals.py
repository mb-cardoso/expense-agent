"""Run the labelled cases against the real model, in sets, and grade the data each run leaves."""

import argparse
import datetime
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from expense_agent import agent, config, llm, tools, tracing
from expense_agent.store import ExpenseStore

CASES = Path(__file__).with_name("cases.jsonl")
RESULTS = config.ROOT / "data" / "evals"


def grade(
    expect: dict[str, Any], before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> bool:
    if expect.get("unchanged"):
        return after == before
    if "deleted" in expect:
        gone = sorted({r["id"] for r in before} - {r["id"] for r in after})
        return gone == expect["deleted"] and len(after) == len(before) - len(gone)
    added = [r for r in after if r["id"] not in {b["id"] for b in before}]
    if len(added) != 1 or len(after) != len(before) + 1:
        return False
    want, row = expect["added"], added[0]
    day = datetime.date.today() - datetime.timedelta(days=want["days_ago"])
    return (
        abs(row["amount"] - want["amount"]) < 0.005
        and row["category"] == want["category"]
        and row["date"] == str(day)
    )


def changes(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    gone = sorted({r["id"] for r in before} - {r["id"] for r in after})
    added = [r for r in after if r["id"] not in {b["id"] for b in before}]
    return f"deleted {gone}, added {[(r['amount'], r['category'], r['date']) for r in added]}"


def trial(case: dict[str, Any], model: llm.Model, set_number: int, number: int) -> dict[str, Any]:
    """One run of a case. Its grade is None when the API failed: nothing to grade."""
    with tempfile.TemporaryDirectory() as folder:
        store = ExpenseStore(Path(folder) / "expenses.json")
        before = store.all()
        answer = bool(case["confirm"])

        def run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return tools.run_tool(name, arguments, store, lambda question: answer)

        turn = agent.Turn()
        passed: bool | None = None
        try:
            agent.ask(model, case["message"], None, run_tool, config.MAX_ROUNDS, turn)
        except Exception as error:  # noqa: BLE001 - explain() re-raises anything that is a bug
            print(f"    {case['id']}: {llm.explain(error)}")
            explanation = "not graded: the API failed"
        else:
            after = store.all()
            passed = grade(case["expect"], before, after)
            explanation = f"expected {json.dumps(case['expect'])}; {changes(before, after)}"
        return {
            "set": set_number,
            "case": case["id"],
            "trial": number,
            "grade": passed,
            "explanation": explanation,
            "outcome": turn.outcome,
            "rounds": turn.rounds,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sets", type=int, default=2)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--cases", type=Path, default=CASES, help="a JSONL file of labelled cases")
    options = parser.parse_args()
    if not config.API_KEY:
        print(f"No API key. Copy .env.example to .env and fill in {config.KEY_NAME}.")
        return 1
    tracing.setup()
    model = llm.make_model(tools.DECLARATIONS)
    text = options.cases.read_text(encoding="utf-8")
    cases = [json.loads(line) for line in text.splitlines() if line]
    started = datetime.datetime.now()
    rows: list[dict[str, Any]] = []
    for number in range(1, options.sets + 1):
        print(f"set {number}, {config.MODEL}, {datetime.datetime.now():%H:%M}")
        for case in cases:
            results = [trial(case, model, number, n) for n in range(1, options.trials + 1)]
            rows += results
            graded = [row["grade"] for row in results if row["grade"] is not None]
            failed = len(results) - len(graded)
            note = f"  ({failed} not graded: the API failed)" if failed else ""
            print(f"  {case['id']:<22} {sum(graded)}/{len(graded)}{note}")
    path = RESULTS / f"{started:%Y-%m-%d_%H%M%S}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"model": config.MODEL, **row}) + "\n" for row in rows]
    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"results: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
