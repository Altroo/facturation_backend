"""Repair neutral-history label bias without importing held-out answers into SFT."""
from collections import Counter, defaultdict
from copy import deepcopy
import calendar
import hashlib
import json
from pathlib import Path
import re

from build_dialogue_v1 import reframe, encode, digest, write_dataset
from build_shared_v5r3 import key

ROOT = Path(__file__).resolve().parents[2]
NEUTRAL = ("Hello", "Bonjour", "Hello, thanks for your help.", "Bonjour, merci pour votre aide.")
ARMS = ("", *NEUTRAL)
MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
}


def recover_rows(original, frozen, augmentation):
    """Recover authoritative roles from the parent, never parse user text as framing."""
    recovered = deepcopy(original)
    for entry in augmentation:
        row = deepcopy(original[entry["source_index"]])
        if len(row["messages"]) != 3 or entry["history"] not in NEUTRAL:
            raise ValueError("Unexpected original augmentation")
        row["messages"].insert(1, {"role": "user", "content": entry["history"]})
        recovered.append(row)
    if [{**row, "messages": reframe(row["messages"])} for row in recovered] != frozen:
        raise ValueError("Recovered roles do not reproduce frozen input")
    return recovered


def neutral_history(row):
    messages = row["messages"]
    if (len(messages) < 3 or messages[0]["role"] != "system"
            or messages[-1]["role"] != "assistant"
            or any(m["role"] != "user" for m in messages[1:-1])):
        raise ValueError("Unexpected planner roles")
    history = messages[1:-2]
    return not history or all(m["content"] in NEUTRAL for m in history)


def input_key(row):
    # Deliberately excludes assistant labels and neutral background.
    payload = {"application": row["application"], "tools": row["tools"],
               "system": row["messages"][0], "current": row["messages"][-2]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def rebalance(rows):
    result, provenance, occurrences = [], [], Counter()
    for index, source in enumerate(rows):
        row = deepcopy(source)
        if neutral_history(row):
            identity = input_key(row)
            arm = (int(identity[:16], 16) + occurrences[identity]) % len(ARMS)
            occurrences[identity] += 1
            history = [{"role": "user", "content": ARMS[arm]}] if ARMS[arm] else []
            row["messages"] = [row["messages"][0], *history, *row["messages"][-2:]]
            provenance.append({"source_index": index, "arm": ARMS[arm] or "no_history",
                               "input_sha256": identity})
        result.append(row)
    return result, provenance


def distribution(rows):
    counts = defaultdict(Counter)
    for row in rows:
        if not neutral_history(row):
            continue
        history = row["messages"][1:-2]
        arm = " | ".join(m["content"] for m in history) or "no_history"
        function = row["messages"][-1]["tool_calls"][0]["function"]
        label = function["name"]
        if label == "clarify":
            label += ":" + function["arguments"]["reason"]
        counts[arm][label] += 1
    return {arm: dict(sorted(values.items())) for arm, values in sorted(counts.items())}


def calendar_rows(rows):
    """Expand verified positive explicit-month templates across all months and years.

    Training-only variants of existing training templates, not new independent
    validation cases. Dates use the calendar library, never model calculations.
    """
    templates = {}
    for row in rows:
        text = row["messages"][-2]["content"]
        for language, phrase in (("fr", "septembre 2031"), ("en", "September 2031")):
            if phrase in text and len(row["messages"]) == 3:
                k = row["application"], language
                if k in templates:
                    raise ValueError("Ambiguous calendar source template")
                function = row["messages"][-1]["tool_calls"][0]["function"]
                if function["arguments"].get("date_from") != "2031-09-01" or function["arguments"].get("date_to") != "2031-09-30":
                    raise ValueError("Calendar template lacks verified explicit dates")
                templates[k] = row
    apps = ("facturation", "management_projet", "design_workflow")
    if set(templates) != {(app, lang) for app in apps for lang in MONTHS}:
        raise ValueError("Incomplete calendar templates")
    additions = []
    # No February 2036, 2000 or 2100: those remain frozen diagnostics.
    for app_index, app in enumerate(apps):
        for language in MONTHS:
            template = templates[app, language]
            periods = []
            for month in range(1, 13):
                year = 2028 + ((month * 3 + app_index * 5) % 12)
                if month == 2:
                    year = (2028, 2040, 2044)[app_index]
                if month == 9 and year == 2031:
                    year = 2038
                periods.append((year, month))
            periods.extend([((2029, 2030, 2033)[app_index], 2), (2200, 2), (2400, 2)])
            for year, month in periods:
                row = deepcopy(template)
                phrase = ("septembre" if language == "fr" else "September") + " 2031"
                row["messages"][-2]["content"] = row["messages"][-2]["content"].replace(
                    phrase, MONTHS[language][month - 1] + " " + str(year))
                args = row["messages"][-1]["tool_calls"][0]["function"]["arguments"]
                args["date_from"] = f"{year:04}-{month:02}-01"
                args["date_to"] = f"{year:04}-{month:02}-{calendar.monthrange(year, month)[1]:02}"
                additions.append(row)
    return additions


def prepare():
    parent = ROOT / "training/datasets/shared-v5r4-en-fr"
    original = ROOT / "training/datasets/shared-v5r3-en-fr"
    output = ROOT / "training/datasets/shared-v5r5-en-fr"
    if output.exists():
        raise ValueError("Never overwrite a versioned dataset")
    prior = json.loads((parent / "manifest.json").read_text())
    ancestor = json.loads((original / "manifest.json").read_text())
    if digest(ROOT / "training/scripts/build_shared_v5r3.py") != ancestor["generator_sha256"]:
        raise ValueError("Normalized leakage checker source changed")
    if digest(ROOT / "training/scripts/build_dialogue_v1.py") != prior["generator_sha256"]:
        raise ValueError("Reframing source changed")
    if digest(original / "manifest.json") != prior["parent_manifest_sha256"]:
        raise ValueError("Parent manifest changed")
    if digest(ROOT / "src/chat_ai_assistant/planning_messages.py") != prior["planning_messages_sha256"]:
        raise ValueError("Native framing changed")
    held_out = set()
    for name, info in ancestor["held_out"].items():
        path = ROOT / name
        if digest(path) != info["sha256"]:
            raise ValueError("Frozen held-out data changed")
        for row in map(json.loads, path.read_text().splitlines()):
            context = json.loads(row["messages"][0]["content"].split("Trusted context: ", 1)[1])
            held_out.add(key(context["application"], row["messages"][-1]["content"]))
    payloads, audit, split_keys = {}, {}, {}
    for split in ("train", "valid"):
        name = split + ".jsonl"
        for folder, manifest in ((parent, prior), (original, ancestor)):
            if digest(folder / name) != manifest["files"][name]:
                raise ValueError("Frozen source changed")
        originals = list(map(json.loads, (original / name).read_text().splitlines()))
        frozen = list(map(json.loads, (parent / name).read_text().splitlines()))
        recovered = recover_rows(originals, frozen, prior["augmentation"][split])
        extra = calendar_rows(originals) if split == "train" else []
        repaired, provenance = rebalance(recovered + extra)
        split_keys[split] = {key(row["application"], row["messages"][-2]["content"]) for row in repaired}
        if split_keys[split] & held_out:
            raise ValueError("Held-out current request entered SFT")
        for source, fixed in zip(recovered + extra, repaired):
            if (source["messages"][0] != fixed["messages"][0]
                    or source["messages"][-2:] != fixed["messages"][-2:]
                    or source["tools"] != fixed["tools"]):
                raise ValueError("Repair changed current request, target or trusted inputs")
            if not neutral_history(source) and source != fixed:
                raise ValueError("Genuine history changed")
        payloads[name] = encode([{**row, "messages": reframe(row["messages"])} for row in repaired])
        if re.search(r"[\u0600-\u06ff]|BEGIN.{0,12}PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret)\s*[:=]", payloads[name], re.I):
            raise ValueError("Sensitive or out-of-language content")
        audit[split] = {"retained": len(recovered), "calendar_variants": len(extra), "total": len(repaired),
                        "before": distribution(recovered), "after": distribution(repaired),
                        "history_assignment": provenance}
    if split_keys["train"] & split_keys["valid"]:
        raise ValueError("Training/validation current request overlap")
    manifest = {"version": output.name, "languages": ["en", "fr"], "applications": prior["applications"],
                "generator_sha256": digest(Path(__file__)), "reframe_sha256": digest(ROOT / "training/scripts/build_dialogue_v1.py"),
                "planning_messages_sha256": prior["planning_messages_sha256"],
                "parent_manifest_sha256": digest(parent / "manifest.json"), "ancestor_manifest_sha256": digest(original / "manifest.json"),
                "source_files": prior["files"], "evaluation_manifest_sha256": prior["evaluation_manifest_sha256"],
                "held_out": ancestor["held_out"], "held_out_count": ancestor["held_out_count"], "audit": audit,
                "split_policy": "Retain all original logical scenarios and split membership. Assign neutral greetings from input-only hashes, independent of expected tool and arguments. Preserve genuine history. Add 90 training-only calendar variants from verified training templates. No held-out answers enter SFT. Variants are correlated, not independent examples; existing regression suites are not blind certification.",
                "training_policy": "PREPARED ONLY. Server-only shared model; no automatic optimization, download or activation."}
    write_dataset(output, payloads, manifest)
    return manifest


if __name__ == "__main__":
    value = prepare()
    print(json.dumps({split: {k: v for k, v in info.items() if k in ("retained", "calendar_variants", "total", "before", "after")}
                      for split, info in value["audit"].items()}, ensure_ascii=False, indent=2))
