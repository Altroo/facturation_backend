"""Additional acceptance gates; frozen benchmark scores remain unchanged."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from chat_ai_assistant.clarifications import clarification_message

FROZEN_EVALUATOR_SHA256 = "dca2abf86b2162ccd99b868108dd957f5ef600fe196a5bf9f21b15cafa4fbe7b"
AUDIT_GROUPS = {
    "total": "financial_summary", "receipts": "financial_summary",
    "fees": "financial_summary", "profit": "financial_summary",
    "estimates": "financial_summary", "list": "record_search",
    "status": "record_search", "quote": "record_search",
    "before": "record_search", "stage": "record_search",
    "descriptive": "record_search", "edit": "authorized_change",
    "known": "conversation_context", "denied": "permission_denial",
    "ambiguous": "financial_clarification", "year": "period_clarification",
    "title": "record_search", "mine": "record_search",
    "count": "workload_summary", "message": "record_search",
    "archives": "record_search", "context": "conversation_context",
    "navigation": "navigation", "time": "time_report",
    "restricted": "permission_denial", "deletion": "unsupported_destructive_request",
    "change": "authorized_change", "client": "record_search",
    "filter": "record_search", "amount": "financial_summary",
    "open": "previous_results_navigation", "current": "conversation_context",
    "unsupported": "unsupported_request",
}


def normalized(arguments):
    value = dict(arguments)
    for name, default in [("limit", 10), ("offset", 0), ("period", "all_time"), ("unpaid", False)]:
        if value.get(name) == default:
            value.pop(name, None)
    return value


def group(row):
    if row["category"] != "audit":
        return row["category"]
    match = re.search(r"-audit-([a-z]+)-(?:fr|en)$", row["id"])
    if not match or match.group(1) not in AUDIT_GROUPS:
        raise ValueError("Unclassified frozen audit case: " + row["id"])
    return AUDIT_GROUPS[match.group(1)]


def measured(items):
    exact = [row for row in items if row["exact_arguments_eligible"]]
    def rate(passed, count):
        return round(100 * passed / count, 2) if count else None
    counts = {key: sum(row[key] for row in items) for key in ["tool_correct", "structured_valid", "action_matches"]}
    return {
        "count": len(items), "counts": counts,
        "percent": {key: rate(value, len(items)) for key, value in counts.items()},
        "exact_arguments": {"passed": sum(row["action_matches"] for row in exact),
                            "count": len(exact), "percent": rate(sum(row["action_matches"] for row in exact), len(exact))},
    }


def assess(snapshot, events):
    expected_ids = [row["id"] for row in snapshot]
    actual_ids = [row["id"] for row in events]
    if len(set(expected_ids)) != len(expected_ids) or len(set(actual_ids)) != len(actual_ids):
        raise ValueError("Duplicate case IDs")
    if set(expected_ids) != set(actual_ids):
        raise ValueError("Missing or unexpected evaluation cases")
    indexed = {row["id"]: row for row in events}
    rows = []
    for expected_row in snapshot:
        result = indexed[expected_row["id"]]
        expected = expected_row["expected"]
        if result.get("expected") != expected or result.get("language") != expected_row["language"]:
            raise ValueError("Evaluation labels changed: " + expected_row["id"])
        if type(result.get("structured_valid")) is not bool:
            raise ValueError("Missing structure verdict: " + expected_row["id"])
        action = result.get("action", {})
        tool_correct = result["structured_valid"] and action.get("tool") == expected["tool"]
        match = False
        if tool_correct:
            if expected["tool"] == "clarify":
                match = action.get("message") == clarification_message(**expected["arguments"])
            elif expected["tool"] == "knowledge":
                query = action.get("arguments", {}).get("query")
                match = isinstance(query, str) and bool(query.strip())
            else:
                arguments = action.get("arguments")
                match = isinstance(arguments, dict) and normalized(arguments) == normalized(expected["arguments"])
        rows.append({
            "id": expected_row["id"], "language": expected_row["language"],
            "group": group(expected_row), "tool_correct": tool_correct,
            "structured_valid": result["structured_valid"], "action_matches": bool(match),
            "exact_arguments_eligible": expected["tool"] not in ("knowledge", "clarify"),
            "clarification": expected["tool"] == "clarify",
            "critical": expected["tool"] in ("clarify", "prepare_change") or action.get("tool") == "prepare_change",
        })
    metrics = measured(rows)
    clarifications = [row for row in rows if row["clarification"]]
    critical = [row for row in rows if row["critical"]]
    targets = {
        "tool_selection": bool(rows) and 100 * metrics["counts"]["tool_correct"] >= 95 * len(rows),
        "exact_arguments": bool(metrics["exact_arguments"]["count"]) and 100 * metrics["exact_arguments"]["passed"] >= 95 * metrics["exact_arguments"]["count"],
        "structured_output": bool(rows) and 100 * metrics["counts"]["structured_valid"] >= 99 * len(rows),
        "clarification_reason_and_language": all(row["action_matches"] for row in clarifications),
        "critical_model_cases": all(row["action_matches"] for row in critical),
    }
    return {
        "metrics": metrics, "targets": targets, "model_targets_passed": all(targets.values()),
        "clarifications": measured(clarifications), "critical_model_cases": measured(critical),
        "by_language": {key: measured([row for row in rows if row["language"] == key]) for key in sorted({row["language"] for row in rows})},
        "by_reporting_group": {key: measured([row for row in rows if row["group"] == key]) for key in sorted({row["group"] for row in rows})},
        "distinct_bilingual_scenario_ids": len({re.sub(r"-(?:fr|en)$", "", row["id"]) for row in rows}),
        "failures": [{"id": row["id"], "group": row["group"], "critical": row["critical"],
                      "tool_correct": row["tool_correct"], "structured_valid": row["structured_valid"]}
                     for row in rows if not row["action_matches"]],
        "native_backend_security_verified": None,
        "limitations": [
            "Separate analysis of frozen events; original benchmark files and scores are unchanged.",
            "All clarification reason/language and proposed-change arguments must match their labels.",
            "Knowledge queries are checked only for nonempty text; retrieval factuality is not measured here.",
            "Bilingual pairs share scenarios; scenario count is not independent statistical certification.",
            "Original failures informed training categories; originals remain regression tests, not unseen certification.",
            "No business tools execute here. Native permission, tenant, confirmation and audit tests remain required.",
            "Passing model targets does not authorize production activation.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    evaluator_hash = digest(ROOT / "training/scripts/evaluate_snapshot.py")
    if evaluator_hash != FROZEN_EVALUATOR_SHA256:
        raise ValueError("Frozen evaluator changed")
    snapshot = [json.loads(line) for line in args.snapshot.read_text().splitlines() if line.strip()]
    wrapped = [json.loads(line) for line in args.events.read_text().splitlines() if line.strip()]
    if any(set(row) != {"case"} for row in wrapped):
        raise ValueError("Unexpected events contract")
    summary = json.loads(args.summary.read_text())
    snapshot_hash = digest(args.snapshot)
    if summary["dataset_sha256"] != snapshot_hash or summary["metrics"]["count"] != len(snapshot):
        raise ValueError("Summary is not bound to this frozen dataset")
    report = assess(snapshot, [row["case"] for row in wrapped])
    report.update(label=summary["label"], model_id=summary["model_id"], snapshot_sha256=snapshot_hash,
                  events_sha256=digest(args.events), frozen_evaluator_sha256=evaluator_hash,
                  acceptance_script_sha256=digest(Path(__file__)))
    with args.output.open("x") as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(json.dumps({"label": report["label"], "model_targets_passed": report["model_targets_passed"],
                      "targets": report["targets"], "critical_failures": sum(row["critical"] for row in report["failures"])}))


if __name__ == "__main__":
    main()
