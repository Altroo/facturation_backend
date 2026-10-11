"""Rebind existing synthetic SFT rows to current approved native metadata.

Preserves user messages and action labels. This is dataset preparation only:
no inference, optimization, database access, or frozen evaluation changes.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLICATIONS = ("facturation", "management_projet", "design_workflow")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--application", choices=APPLICATIONS, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    args = parser.parse_args()
    app = args.application
    source = ROOT / "training/datasets" / (app.replace("_", "-") + "-refinement-v1-en-fr")
    output = ROOT / "training/datasets" / (app.replace("_", "-") + "-metadata-v2-en-fr")
    if output.exists():
        raise ValueError("Never overwrite a frozen preparation")
    source_manifest = json.loads((source / "manifest.json").read_text())
    assert source_manifest["generator_sha256"] == digest(ROOT / "training/scripts/build_refinement_v1.py")
    sys.path.insert(0, str(args.backend))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", app + "_backend.settings_ai_test" if app in ("facturation", "management_projet") else app + "_backend.settings_test")
    from django.db.backends.base.base import BaseDatabaseWrapper
    def deny(*args, **kwargs):
        raise RuntimeError("Training metadata preparation must not access any database")
    BaseDatabaseWrapper.ensure_connection = deny
    import django
    django.setup()
    from chat_ai import tools as native_tools
    from chat_ai_assistant.calendar_context import with_calendar_context
    from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
    from training_contracts import CLARIFICATION_DESCRIPTION
    from jsonschema import validate
    if app == "facturation":
        from chat_ai_assistant.orchestrator import SYSTEM
        from chat_ai_assistant.routing import shortlist
        from chat_ai.shortcut_catalog import shortcut_search_hint
        from build_dataset_v4 import PROFILES, validate_business_action
    else:
        from chat_ai.planner import SYSTEM, shortlist
    native = native_tools.registry()
    clarify = {"type": "function", "function": {"name": "clarify", "description": CLARIFICATION_DESCRIPTION, "parameters": CLARIFICATION_SCHEMA}}
    payloads, counts, repairs = {}, {}, []
    for split in ("train", "valid"):
        path = source / (split + ".eval.jsonl")
        assert digest(path) == source_manifest["files"][path.name]
        originals = list(map(json.loads, path.read_text().splitlines()))
        diagnostic, training = [], []
        for original in originals:
            row = copy.deepcopy(original)
            context = json.loads(row["messages"][0]["content"].split("Trusted context: ", 1)[1])
            text = row["messages"][-1]["content"]
            expected = row["expected"]
            caps = row.get("capabilities", context.get("capabilities"))
            if app == "facturation":
                # V4 kept the exact profile key; later refinement additions used member_edit.
                profile = row.get("capability_profile")
                if profile is None:
                    assert row["id"].startswith("facturation-refinement-v1-")
                    profile = "member_edit"
                caps = PROFILES[profile]
                hint = shortcut_search_hint(text)
                if hint != text:
                    context["shortcut_search_hint"] = hint
            else:
                assert caps is not None
                context.setdefault("current_resource", None)
                context.setdefault("current_identifier", None)
            if app == "design_workflow":
                caps = sorted(set(caps) | ({"mutate"} if set(caps) & {"update", "archive"} else set()))
                context["capabilities"] = caps
            if app == "management_projet":
                count = context.get("previous_result_count", 0)
                if count and "previous_result_identifiers" not in context:
                    assert expected["tool"] == "previous_results" and 1 <= count <= 4
                    context["previous_result_identifiers"] = [6204, 871, 5309, 2406][:count]
                    repairs.append({"split": split, "id": row["id"], "change": "Synthetic saved IDs added in display order; ordinal label unchanged."})
                context.setdefault("previous_result_identifiers", [])
            selected = shortlist(context.get("shortcut_search_hint") or text, native.permitted(set(caps)), context)
            if expected["tool"] == "clarify":
                validate(expected["arguments"], CLARIFICATION_SCHEMA)
            else:
                tool = next((tool for tool in selected if tool.name == expected["tool"]), None)
                assert tool is not None, ("Native shortlist does not offer original action", row["id"])
                validate(expected["arguments"], tool.input_schema)
                if app == "facturation":
                    validate_business_action(expected["tool"], expected["arguments"], context, text)
            context = with_calendar_context(context)
            row["trusted_context"] = context
            row["offered_tools"] = [tool.name for tool in selected]
            row["offered_tool_schemas"] = [tool.schema() for tool in selected]
            row["messages"][0] = {"role": "system", "content": SYSTEM + "\nTrusted context: " + json.dumps(context, ensure_ascii=False)}
            assert row["messages"][1:] == original["messages"][1:] and row["expected"] == original["expected"]
            diagnostic.append(row)
            training.append({"messages": row["messages"] + [{"role": "assistant", "content": None, "tool_calls": [{"type": "function", "function": {"name": expected["tool"], "arguments": expected["arguments"]}}]}], "tools": row["offered_tool_schemas"] + [clarify]})
        counts[split] = len(originals)
        payloads[split + ".eval.jsonl"] = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in diagnostic)
        payloads[split + ".jsonl"] = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in training)
    for payload in payloads.values():
        if re.search(r"[\u0600-\u06ff]|BEGIN.{0,12}PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret)\s*[:=]", payload, re.I):
            raise ValueError("Sensitive or unsupported-language content")
    source_paths = [Path(native_tools.__file__)]
    source_paths += [source_paths[0].with_name(name) for name in ("planner.py", "services.py", "shortcuts.py") if source_paths[0].with_name(name).is_file()]
    manifest = {
        "version": output.name, "application": app, "languages": ["en", "fr"], "counts": counts,
        "source_dataset": source.name, "source_manifest_sha256": digest(source / "manifest.json"),
        "generator_sha256": digest(Path(__file__)),
        "native_sources": {str(path.relative_to(args.backend)): digest(path) for path in source_paths},
        "shared_sources": {name: digest(ROOT / name) for name in ("src/chat_ai_assistant/orchestrator.py", "src/chat_ai_assistant/routing.py", "src/chat_ai_assistant/calendar_context.py", "training/scripts/training_contracts.py", "training/scripts/build_dataset_v4.py")},
        "files": {name: hashlib.sha256(payload.encode()).hexdigest() for name, payload in payloads.items()},
        "context_repairs": repairs,
        "status": "Prepared only; no model training or acceptance claim.",
        "methodology": "All source user messages, action labels and split membership preserved. Current native tool schemas, planner prompt, derived calendar and documented synthetic context repairs replace historical envelopes. No held-out rows enter training or validation.",
        "security_scope": "Synthetic capability snapshots are not live role simulations. Native backend authorization and confirmed writes are tested separately. Database access prohibited.",
    }
    output.mkdir()
    for name, payload in payloads.items():
        with (output / name).open("x") as stream:
            stream.write(payload)
    with (output / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"application": app, "counts": counts, "context_repairs": len(repairs), "training": "not run"}))


if __name__ == "__main__":
    main()
