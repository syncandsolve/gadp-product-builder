#!/usr/bin/env python3
"""
gadp_update_intent_status.py — Update the status field of a single intent in intent-store.yaml.

Usage:
    echo '<JSON>' | python scripts/gadp_update_intent_status.py

Input (JSON on stdin):
    {
        "id":     "CI-001",      # required — intent to update (CI-*, SI-*, or QI-*)
        "status": "active"       # required — new status value
    }

Valid status values by intent type:

  CI-* (capability):
    active     — intent is confirmed in scope
    deferred   — moved to extension/future (requires scope change separately)
    deprecated — no longer relevant, not removed for audit trail
    promoted   — was extension/future, now promoted to core sprint

  SI-* (security):
    active     — threat mitigation is in scope
    mitigated  — corresponding contract is passing
    accepted   — risk accepted with documentation
    deprecated — no longer applies (e.g. threat was invalidated)

  QI-* (quality):
    active     — quality intent is being tracked
    met        — measurement confirms the target is being hit
    at_risk    — current measurements are trending toward breach
    breached   — measurement confirms the target is not being hit

Only 'status' may be updated through this script. To modify label, scope,
threat_id, or any other field, use /approve-decisions and Planner.

Exit codes:
    0 — success
    1 — validation error or intent not found
    2 — file not found
"""

import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Status enums per intent type ──────────────────────────────────────────────

VALID_STATUSES = {
    "CI": {"active", "deferred", "deprecated", "promoted"},
    "SI": {"active", "mitigated", "accepted", "deprecated"},
    "QI": {"active", "met", "at_risk", "breached"},
}

ALL_VALID_STATUSES = {s for ss in VALID_STATUSES.values() for s in ss}

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_intent_store() -> Path:
    candidates = [
        Path("./intents/intent-store.yaml"),
        Path("intents/intent-store.yaml"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    print(
        "ERROR: intent-store.yaml not found.\n"
        "       Looked in: ./intents/intent-store.yaml",
        file=sys.stderr,
    )
    sys.exit(2)


def read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No input provided on stdin.", file=sys.stderr)
        print(
            "       Usage: echo '<JSON>' | python scripts/gadp_update_intent_status.py",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print("ERROR: Input must be a JSON object.", file=sys.stderr)
        sys.exit(1)
    return data


def detect_prefix(intent_id: str) -> str | None:
    for prefix in ("CI", "SI", "QI"):
        if intent_id.startswith(f"{prefix}-"):
            return prefix
    return None


def list_key_for_prefix(prefix: str) -> str:
    return {"CI": "capabilities", "SI": "security", "QI": "quality"}[prefix]


def atomic_write(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(".yaml.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        os.replace(tmp, path)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        print(f"ERROR: Failed to write {path}: {exc}", file=sys.stderr)
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = read_stdin_json()

    # ── Basic input checks ────────────────────────────────────────────────────
    intent_id = data.get("id")
    new_status = data.get("status")

    if not intent_id:
        print("ERROR: 'id' field is required.", file=sys.stderr)
        sys.exit(1)

    if not new_status:
        print("ERROR: 'status' field is required.", file=sys.stderr)
        sys.exit(1)

    # ── Check for disallowed extra fields ─────────────────────────────────────
    extra = set(data.keys()) - {"id", "status"}
    if extra:
        print(
            f"ERROR: This script only accepts 'id' and 'status'. "
            f"Unexpected fields: {sorted(extra)}\n"
            "       To modify other intent fields, use /approve-decisions and Planner.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Detect intent type and validate status ────────────────────────────────
    prefix = detect_prefix(intent_id)
    if prefix is None:
        print(
            f"ERROR: 'id' must start with CI-, SI-, or QI-. Got: {intent_id!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    valid_for_type = VALID_STATUSES[prefix]
    if new_status not in valid_for_type:
        print(
            f"ERROR: '{new_status}' is not a valid status for {prefix}-* intents.\n"
            f"       Valid values for {prefix}-*: {sorted(valid_for_type)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Load intent-store.yaml ────────────────────────────────────────────────
    store_path = find_intent_store()
    try:
        with open(store_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except Exception as exc:
        print(f"ERROR: Failed to read {store_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(doc, dict) or "intents" not in doc:
        print(
            f"ERROR: {store_path} is malformed — missing top-level 'intents' key.",
            file=sys.stderr,
        )
        sys.exit(1)

    intents = doc["intents"]
    list_key = list_key_for_prefix(prefix)

    if list_key not in intents:
        print(
            f"ERROR: intents.{list_key} block not found in {store_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Find the intent ───────────────────────────────────────────────────────
    intent_list = intents[list_key]
    target = next((i for i in intent_list if i.get("id") == intent_id), None)

    if target is None:
        known = [i.get("id", "?") for i in intent_list]
        print(
            f"ERROR: Intent '{intent_id}' not found in intents.{list_key}.\n"
            f"       Known IDs in this list: {known}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Apply update ──────────────────────────────────────────────────────────
    old_status = target.get("status")

    if old_status == new_status:
        print(f"OK:    {intent_id} — status already '{new_status}', no change made.")
        return

    target["status"] = new_status

    # ── Write back atomically ─────────────────────────────────────────────────
    atomic_write(store_path, doc)

    print(f"OK:    {intent_id} status updated — {old_status!r} → {new_status!r}")


if __name__ == "__main__":
    main()
