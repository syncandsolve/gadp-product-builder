#!/usr/bin/env python3
"""
gadp_update_contract.py — Update mutable fields on a single contract in contracts.yaml.

Usage:
    echo '<JSON>' | python scripts/gadp_update_contract.py

Input (JSON on stdin):
    {
        "id":             "OC-001",           # required — contract to update
        "status":         "passing",          # optional — new status
        "sprint":         2,                  # optional — reassign to sprint (requires /approve-decisions)
        "blocked_on":     "Waiting for X",   # optional — set or clear (null to clear)
        "implemented_at": "2025-01-01T00:00:00Z"  # optional — ISO-8601 timestamp
    }

Mutable fields:   status, blocked_on, implemented_at
Restricted field: sprint (allowed here but must only be called after /approve-decisions)
Immutable fields: id, title, scope, intent_ref, contract_type, given, when, then,
                  test_file, threat_refs, full_stack_pair — reject if included in input

Exit codes:
    0 — success
    1 — validation error or contract not found
    2 — file not found
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Field policy ─────────────────────────────────────────────────────────────

MUTABLE_FIELDS = {"status", "blocked_on", "implemented_at"}
RESTRICTED_FIELDS = {"sprint"}          # allowed but flagged — needs /approve-decisions upstream
IMMUTABLE_FIELDS = {
    "id", "title", "scope", "intent_ref", "contract_type",
    "given", "when", "then", "test_file", "threat_refs", "full_stack_pair"
}

VALID_STATUSES = {
    "pending", "in_review", "passing", "failing",
    "deferred", "rolled_back", "blocked"
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_contracts_yaml() -> Path:
    candidates = [
        Path("./outcomes/contracts.yaml"),
        Path("outcomes/contracts.yaml"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    print(
        "ERROR: contracts.yaml not found.\n"
        "       Looked in: ./outcomes/contracts.yaml",
        file=sys.stderr,
    )
    sys.exit(2)


def validate_iso8601(value: str, field: str) -> None:
    """Accept any ISO-8601 datetime string. Strict but forgiving of timezone variants."""
    try:
        # Handle trailing Z
        normalised = value.replace("Z", "+00:00")
        datetime.fromisoformat(normalised)
    except ValueError:
        print(
            f"ERROR: '{field}' must be an ISO-8601 datetime string "
            f"(e.g. '2025-01-15T14:30:00Z'). Got: {value!r}",
            file=sys.stderr,
        )
        sys.exit(1)


def read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No input provided on stdin.", file=sys.stderr)
        print("       Usage: echo '<JSON>' | python scripts/gadp_update_contract.py", file=sys.stderr)
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


def atomic_write(path: Path, doc: dict) -> None:
    """Write YAML atomically via a temp file, then replace."""
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
    update = read_stdin_json()

    # ── Require 'id' ──────────────────────────────────────────────────────────
    contract_id = update.get("id")
    if not contract_id:
        print("ERROR: 'id' field is required.", file=sys.stderr)
        sys.exit(1)
    if not isinstance(contract_id, str) or not contract_id.startswith("OC-"):
        print(
            f"ERROR: 'id' must be a string in the format 'OC-NNN'. Got: {contract_id!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Check for immutable field writes ──────────────────────────────────────
    input_fields = set(update.keys()) - {"id"}
    attempted_immutable = input_fields & IMMUTABLE_FIELDS
    if attempted_immutable:
        print(
            f"ERROR: Cannot modify immutable fields: {sorted(attempted_immutable)}\n"
            "       These fields require a new contract via /approve-decisions and Planner.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Validate individual field values ──────────────────────────────────────
    if "status" in update:
        if update["status"] not in VALID_STATUSES:
            print(
                f"ERROR: Invalid status '{update['status']}'.\n"
                f"       Valid values: {sorted(VALID_STATUSES)}",
                file=sys.stderr,
            )
            sys.exit(1)

    if "implemented_at" in update and update["implemented_at"] is not None:
        validate_iso8601(update["implemented_at"], "implemented_at")

    if "sprint" in update:
        if not isinstance(update["sprint"], int) or update["sprint"] < 0:
            print(
                f"ERROR: 'sprint' must be a non-negative integer. Got: {update['sprint']!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        # Warn — sprint reassignment should only follow /approve-decisions
        print(
            "WARN:  'sprint' is a restricted field. Ensure /approve-decisions was "
            "completed before calling this script with a sprint change.",
            file=sys.stderr,
        )

    # ── Load contracts.yaml ───────────────────────────────────────────────────
    contracts_path = find_contracts_yaml()
    try:
        with open(contracts_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except Exception as exc:
        print(f"ERROR: Failed to read {contracts_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(doc, dict) or "contracts" not in doc:
        print(
            f"ERROR: {contracts_path} is malformed — missing top-level 'contracts' key.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Find target contract ──────────────────────────────────────────────────
    contracts = doc.get("contracts", [])
    target = next((c for c in contracts if c.get("id") == contract_id), None)
    if target is None:
        known_ids = [c.get("id", "?") for c in contracts]
        print(
            f"ERROR: Contract '{contract_id}' not found in {contracts_path}.\n"
            f"       Known IDs: {known_ids}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Apply updates ─────────────────────────────────────────────────────────
    changed = {}
    for field, value in update.items():
        if field == "id":
            continue
        old_value = target.get(field)
        target[field] = value
        changed[field] = {"from": old_value, "to": value}

    if not changed:
        print(f"OK:    {contract_id} — no fields changed (input contained only 'id').")
        return

    # ── Write back atomically ─────────────────────────────────────────────────
    atomic_write(contracts_path, doc)

    # ── Confirmation output ───────────────────────────────────────────────────
    change_summary = ", ".join(
        f"{k}: {v['from']!r} → {v['to']!r}" for k, v in changed.items()
    )
    print(f"OK:    {contract_id} updated — {change_summary}")


if __name__ == "__main__":
    main()
