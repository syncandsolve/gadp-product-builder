#!/usr/bin/env python3
"""
gadp_append_intent.py — Append a new CI-* or SI-* intent to intent-store.yaml.

Usage:
    echo '<JSON>' | python scripts/gadp_append_intent.py

Supported intent types and their required fields:

  Capability intent (CI-*):
    {
        "id":                  "CI-015",
        "label":               "User can export data to CSV",
        "scope":               "extension",           # core|extension|future
        "security_surface":    false,
        "deferral_reason":     "complexity",          # required if scope != core
        "inclusion_trigger":   "Sprint 3 complete",   # required if scope != core
        "inferred":            false,                 # optional, default false
        "source":              "user",                # user|inferred|derived — optional
        "notes":               "Requested in ICP-1"   # optional
    }

  Security intent (SI-*):
    {
        "id":                  "SI-005",
        "threat_id":           "T-007",
        "stride_category":     "information_disclosure",
        "label":               "Encrypt PII at rest",
        "scope":               "core",
        "security_surface":    true,
        "security_concern_type": "data_protection"
    }

  Quality intent (QI-*):
    {
        "id":                  "QI-EXPORT-001",
        "label":               "CSV export completes within 3 seconds for 10k rows",
        "type":                "soft",                # soft|hard
        "scale_trigger":       "> 50k rows",
        "measurement_method":  "Jest timer + test dataset"
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

# ── Schema constants ──────────────────────────────────────────────────────────

VALID_SCOPES = {"core", "extension", "future"}
VALID_STRIDE = {
    "spoofing", "tampering", "repudiation",
    "information_disclosure", "denial_of_service", "elevation_of_privilege"
}
VALID_SECURITY_CONCERN_TYPES = {
    "auth", "data_protection", "injection", "access_control",
    "rate_limiting", "session_management", "csrf", "xss", "other"
}
VALID_QI_TYPES = {"soft", "hard"}
VALID_SOURCES = {"user", "inferred", "derived"}

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
        print("       Usage: echo '<JSON>' | python scripts/gadp_append_intent.py", file=sys.stderr)
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


def detect_intent_type(intent_id: str) -> str:
    """Return 'capability', 'security', or 'quality' based on ID prefix."""
    if intent_id.startswith("CI-"):
        return "capability"
    if intent_id.startswith("SI-"):
        return "security"
    if intent_id.startswith("QI-"):
        return "quality"
    return "unknown"


# ── Validators ────────────────────────────────────────────────────────────────

def validate_capability_intent(data: dict) -> list[str]:
    errors = []

    required = {"id", "label", "scope", "security_surface"}
    missing = required - set(data.keys())
    if missing:
        errors.append(f"Missing required fields for CI-*: {sorted(missing)}")

    scope = data.get("scope")
    if scope and scope not in VALID_SCOPES:
        errors.append(f"'scope' must be one of {sorted(VALID_SCOPES)}. Got: {scope!r}")

    if scope in ("extension", "future"):
        if not data.get("deferral_reason"):
            errors.append(
                f"'deferral_reason' is required when scope is '{scope}'. "
                "Explain why this capability is deferred."
            )
        if not data.get("inclusion_trigger"):
            errors.append(
                f"'inclusion_trigger' is required when scope is '{scope}'. "
                "Describe the condition that would bring this in."
            )

    if "security_surface" in data and not isinstance(data["security_surface"], bool):
        errors.append("'security_surface' must be a boolean (true or false).")

    if data.get("security_surface") is True:
        if not data.get("security_concern_type"):
            errors.append(
                "'security_concern_type' is required when security_surface is true. "
                f"Valid values: {sorted(VALID_SECURITY_CONCERN_TYPES)}"
            )
        elif data["security_concern_type"] not in VALID_SECURITY_CONCERN_TYPES:
            errors.append(
                f"'security_concern_type' must be one of {sorted(VALID_SECURITY_CONCERN_TYPES)}. "
                f"Got: {data['security_concern_type']!r}"
            )

    source = data.get("source")
    if source is not None and source not in VALID_SOURCES:
        errors.append(f"'source' must be one of {sorted(VALID_SOURCES)}. Got: {source!r}")

    return errors


def validate_security_intent(data: dict) -> list[str]:
    errors = []

    required = {"id", "threat_id", "stride_category", "label", "scope",
                "security_surface", "security_concern_type"}
    missing = required - set(data.keys())
    if missing:
        errors.append(f"Missing required fields for SI-*: {sorted(missing)}")

    stride = data.get("stride_category")
    if stride and stride not in VALID_STRIDE:
        errors.append(
            f"'stride_category' must be one of {sorted(VALID_STRIDE)}. Got: {stride!r}"
        )

    threat_id = data.get("threat_id", "")
    if threat_id and not (isinstance(threat_id, str) and threat_id.startswith("T-")):
        errors.append(f"'threat_id' must start with 'T-'. Got: {threat_id!r}")

    scope = data.get("scope")
    if scope and scope not in VALID_SCOPES:
        errors.append(f"'scope' must be one of {sorted(VALID_SCOPES)}. Got: {scope!r}")

    concern = data.get("security_concern_type")
    if concern and concern not in VALID_SECURITY_CONCERN_TYPES:
        errors.append(
            f"'security_concern_type' must be one of {sorted(VALID_SECURITY_CONCERN_TYPES)}. "
            f"Got: {concern!r}"
        )

    if data.get("security_surface") is not True:
        errors.append("'security_surface' must be true for all SI-* intents.")

    return errors


def validate_quality_intent(data: dict) -> list[str]:
    errors = []

    required = {"id", "label", "type", "scale_trigger", "measurement_method"}
    missing = required - set(data.keys())
    if missing:
        errors.append(f"Missing required fields for QI-*: {sorted(missing)}")

    qi_type = data.get("type")
    if qi_type and qi_type not in VALID_QI_TYPES:
        errors.append(f"'type' must be one of {sorted(VALID_QI_TYPES)}. Got: {qi_type!r}")

    return errors


def validate_intent(data: dict) -> list[str]:
    intent_id = data.get("id", "")
    intent_type = detect_intent_type(intent_id)

    if intent_type == "capability":
        return validate_capability_intent(data)
    if intent_type == "security":
        return validate_security_intent(data)
    if intent_type == "quality":
        return validate_quality_intent(data)

    return [
        f"'id' must start with CI-, SI-, or QI-. Got: {intent_id!r}\n"
        "       CI- = capability intent\n"
        "       SI- = security intent\n"
        "       QI- = quality intent"
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = read_stdin_json()

    intent_id = data.get("id", "")
    if not intent_id:
        print("ERROR: 'id' field is required.", file=sys.stderr)
        sys.exit(1)

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = validate_intent(data)
    if errors:
        print("ERROR: Intent validation failed:", file=sys.stderr)
        for e in errors:
            print(f"       - {e}", file=sys.stderr)
        sys.exit(1)

    intent_type = detect_intent_type(intent_id)

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

    # ── Map intent type to its list key ──────────────────────────────────────
    list_key_map = {
        "capability": "capabilities",
        "security":   "security",
        "quality":    "quality",
    }
    list_key = list_key_map[intent_type]

    if list_key not in intents:
        intents[list_key] = []

    existing_ids = [i.get("id") for i in intents[list_key]]

    # ── Duplicate check ───────────────────────────────────────────────────────
    if intent_id in existing_ids:
        print(
            f"ERROR: Intent '{intent_id}' already exists in {store_path} under intents.{list_key}.\n"
            "       Use gadp_update_intent_status.py to modify an existing intent.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Append ────────────────────────────────────────────────────────────────
    intents[list_key].append(data)
    doc["intents"] = intents

    # ── Write back atomically ─────────────────────────────────────────────────
    atomic_write(store_path, doc)

    print(
        f"OK:    {intent_id} ({intent_type}) appended to {store_path} "
        f"under intents.{list_key} — "
        f"total in list: {len(intents[list_key])}"
    )


if __name__ == "__main__":
    main()
