#!/usr/bin/env python3
"""
gadp_append_contract.py — Append a new OC-* contract to contracts.yaml.

Usage:
    echo '<JSON>' | python scripts/gadp_append_contract.py

Input (JSON on stdin) — all fields required unless marked optional:
    {
        "id":            "OC-029",                    # must match OC-NNN format, no duplicates
        "title":         "User can register",
        "intent_ref":    "CI-001",
        "contract_type": "functional",                # functional|security|performance|deletion|accessibility
        "sprint":        1,
        "scope":         "core",                      # core|extension|future
        "given":         "the user is on /register",
        "when":          "they submit a valid email and password",
        "then":          "an account is created and a 201 response returned",
        "test_file":     "tests/contracts/OC-029-user-registration.test.ts",
        "status":        "pending",                   # almost always pending on append
        "threat_refs":   ["T-001", "T-004"],          # optional — list of T-* IDs
        "full_stack_pair": "OC-030",                  # optional — paired UI contract ID
        "blocked_on":    null,                        # optional
        "implemented_at": null                        # optional
    }

Exit codes:
    0 — success
    1 — validation error or duplicate ID
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

# ── Schema ────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "id", "title", "intent_ref", "contract_type", "sprint",
    "scope", "given", "when", "then", "test_file", "status"
}

OPTIONAL_FIELDS = {"threat_refs", "full_stack_pair", "blocked_on", "implemented_at"}

VALID_CONTRACT_TYPES = {"functional", "security", "performance", "deletion", "accessibility"}
VALID_SCOPES = {"core", "extension", "future"}
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
        "       Looked in: ./outcomes/contracts.yaml\n"
        "       Run gadp_init_project.py first to create the initial file.",
        file=sys.stderr,
    )
    sys.exit(2)


def read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No input provided on stdin.", file=sys.stderr)
        print("       Usage: echo '<JSON>' | python scripts/gadp_append_contract.py", file=sys.stderr)
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


def validate_contract(data: dict) -> list[str]:
    """Return list of validation error messages. Empty list means valid."""
    errors = []

    # Required fields
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    # Unknown fields
    known = REQUIRED_FIELDS | OPTIONAL_FIELDS
    unknown = set(data.keys()) - known
    if unknown:
        errors.append(f"Unknown fields (remove or check spelling): {sorted(unknown)}")

    # ID format
    contract_id = data.get("id", "")
    if contract_id and not (
        isinstance(contract_id, str)
        and contract_id.startswith("OC-")
        and contract_id[3:].isdigit()
        and len(contract_id) >= 5
    ):
        errors.append(f"'id' must match pattern OC-NNN (e.g. OC-001). Got: {contract_id!r}")

    # intent_ref format
    intent_ref = data.get("intent_ref", "")
    if intent_ref and isinstance(intent_ref, str):
        if not (intent_ref.startswith(("CI-", "SI-", "QI-"))):
            errors.append(
                f"'intent_ref' must start with CI-, SI-, or QI-. Got: {intent_ref!r}"
            )

    # Enum fields
    if "contract_type" in data and data["contract_type"] not in VALID_CONTRACT_TYPES:
        errors.append(
            f"'contract_type' must be one of {sorted(VALID_CONTRACT_TYPES)}. "
            f"Got: {data['contract_type']!r}"
        )

    if "scope" in data and data["scope"] not in VALID_SCOPES:
        errors.append(
            f"'scope' must be one of {sorted(VALID_SCOPES)}. Got: {data['scope']!r}"
        )

    if "status" in data and data["status"] not in VALID_STATUSES:
        errors.append(
            f"'status' must be one of {sorted(VALID_STATUSES)}. Got: {data['status']!r}"
        )

    # sprint
    sprint = data.get("sprint")
    if sprint is not None and (not isinstance(sprint, int) or sprint < 0):
        errors.append(f"'sprint' must be a non-negative integer. Got: {sprint!r}")

    # test_file path sanity
    test_file = data.get("test_file", "")
    if test_file and not test_file.startswith("tests/"):
        errors.append(
            f"'test_file' must be under tests/ (e.g. tests/contracts/OC-001.test.ts). "
            f"Got: {test_file!r}"
        )

    # threat_refs must be a list
    threat_refs = data.get("threat_refs")
    if threat_refs is not None:
        if not isinstance(threat_refs, list):
            errors.append(f"'threat_refs' must be a list. Got: {type(threat_refs).__name__}")
        else:
            bad = [r for r in threat_refs if not (isinstance(r, str) and r.startswith("T-"))]
            if bad:
                errors.append(f"All 'threat_refs' must start with 'T-'. Bad values: {bad}")

    # full_stack_pair format
    pair = data.get("full_stack_pair")
    if pair is not None and not (isinstance(pair, str) and pair.startswith("OC-")):
        errors.append(f"'full_stack_pair' must be an OC-NNN ID. Got: {pair!r}")

    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = read_stdin_json()

    # ── Validate input ────────────────────────────────────────────────────────
    errors = validate_contract(data)
    if errors:
        print("ERROR: Contract validation failed:", file=sys.stderr)
        for e in errors:
            print(f"       - {e}", file=sys.stderr)
        sys.exit(1)

    contract_id = data["id"]

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

    contracts = doc.get("contracts", [])

    # ── Duplicate check ───────────────────────────────────────────────────────
    existing_ids = [c.get("id") for c in contracts]
    if contract_id in existing_ids:
        print(
            f"ERROR: Contract '{contract_id}' already exists in {contracts_path}.\n"
            "       Use gadp_update_contract.py to modify an existing contract.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Normalise optional fields ─────────────────────────────────────────────
    # Ensure optional fields have consistent defaults if absent
    data.setdefault("threat_refs", [])
    data.setdefault("full_stack_pair", None)
    data.setdefault("blocked_on", None)
    data.setdefault("implemented_at", None)

    # Remove None values from top-level (yaml.safe_dump writes them as 'null' which is fine,
    # but explicit None keys add noise — keep them so schema is consistent)

    # ── Append and update counts ──────────────────────────────────────────────
    contracts.append(data)
    doc["contracts"] = contracts
    doc["contract_count"] = len(contracts)

    # Update type-specific counts
    count_keys = {
        "functional":    "core_count",
        "security":      "security_count",
        "performance":   "performance_count",
        "deletion":      "deletion_count",
        "accessibility": "accessibility_count",
    }
    count_key = count_keys.get(data["contract_type"])
    if count_key:
        doc[count_key] = doc.get(count_key, 0) + 1

    # ── Write back atomically ─────────────────────────────────────────────────
    atomic_write(contracts_path, doc)

    print(
        f"OK:    {contract_id} appended to {contracts_path} — "
        f"total contracts: {doc['contract_count']}"
    )


if __name__ == "__main__":
    main()
