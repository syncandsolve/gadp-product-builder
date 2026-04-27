#!/usr/bin/env python3
"""
gadp_append_audit.py — Append a new event to outcomes/audit-log.yaml.

This script is APPEND-ONLY. It never modifies or deletes existing events.
The audit log is an immutable ledger — every significant project event lives here.

Usage:
    echo '<JSON>' | python scripts/gadp_append_audit.py

Input (JSON on stdin). 'type' and 'actor' are always required.
Additional fields vary by event type — see EVENT TYPES below.

All events automatically receive:
    timestamp   — current UTC ISO-8601 (cannot be overridden)

EVENT TYPES and their required fields:

  bootstrap
    { "type": "bootstrap", "actor": "project-setup",
      "note": "Project scaffolded by GADP." }

  intent_confirmed
    { "type": "intent_confirmed", "actor": "intent-architect",
      "intent_id": "CI-001", "label": "User can register",
      "scope": "core" }

  direction_selected
    { "type": "direction_selected", "actor": "outcome-resolver",
      "direction": "Self-Serve SaaS",
      "note": "Selected over Sales-Assisted: ICP-1 is self-serve buyer." }

  contracts_generated
    { "type": "contracts_generated", "actor": "outcome-resolver",
      "contract_count": 28, "sprint_1_count": 14 }

  sprint_planned
    { "type": "sprint_planned", "actor": "planner",
      "sprint": 1, "contract_count": 14,
      "goal": "Complete auth and primary journey end-to-end" }

  contract_passed
    { "type": "contract_passed", "actor": "builder",
      "contract_id": "OC-001", "title": "User registration",
      "sprint": 1 }

  contract_failed
    { "type": "contract_failed", "actor": "builder",
      "contract_id": "OC-001", "title": "User registration",
      "sprint": 1, "reason": "Cookie not set in test environment" }

  contract_rolled_back
    { "type": "contract_rolled_back", "actor": "governor",
      "contract_id": "OC-001", "title": "User registration",
      "reason": "Violated INV-S-001 — JWT not in httpOnly cookie" }

  audit_run
    { "type": "audit_run", "actor": "auditor",
      "sprint": 1, "result": "clean",
      "violations": [], "contracts_checked": 7 }

  audit_violation
    { "type": "audit_violation", "actor": "auditor",
      "invariant_id": "INV-S-001", "description": "JWT not in httpOnly cookie",
      "contract_id": "OC-003", "severity": "critical" }

  decisions_approved
    { "type": "decisions_approved", "actor": "planner",
      "change_summary": "Database changed from SQLite to PostgreSQL",
      "affected_contracts": ["OC-005", "OC-006"],
      "note": "User accepted /approve-decisions" }

  intent_promoted
    { "type": "intent_promoted", "actor": "planner",
      "intent_id": "CI-012", "from_scope": "extension", "to_scope": "core",
      "sprint": 3 }

  threat_mitigated
    { "type": "threat_mitigated", "actor": "auditor",
      "threat_id": "T-004", "stride_category": "information_disclosure",
      "contract_id": "OC-009" }

  sprint_gate_passed
    { "type": "sprint_gate_passed", "actor": "auditor",
      "sprint": 1, "contracts_passing": 14, "contracts_total": 14 }

  sprint_gate_failed
    { "type": "sprint_gate_failed", "actor": "auditor",
      "sprint": 1, "reason": "OC-011 still failing — rate limiting incomplete",
      "blocked_contract": "OC-011" }

  deploy_approved
    { "type": "deploy_approved", "actor": "governor",
      "target": "production", "note": "All gate conditions met." }

  custom
    { "type": "custom", "actor": "[agent name]",
      "note": "[description of event]" }

Exit codes:
    0 — success
    1 — validation error
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

# ── Schema ────────────────────────────────────────────────────────────────────

KNOWN_EVENT_TYPES = {
    "bootstrap", "intent_confirmed", "direction_selected", "contracts_generated",
    "sprint_planned", "contract_passed", "contract_failed", "contract_rolled_back",
    "audit_run", "audit_violation", "decisions_approved", "intent_promoted",
    "threat_mitigated", "sprint_gate_passed", "sprint_gate_failed",
    "deploy_approved", "custom"
}

KNOWN_ACTORS = {
    "governor", "intent-architect", "outcome-resolver", "project-setup",
    "builder", "auditor", "planner"
}

# Required extra fields per event type (beyond type, actor, timestamp)
EVENT_REQUIRED_FIELDS: dict[str, set[str]] = {
    "intent_confirmed":     {"intent_id", "label", "scope"},
    "direction_selected":   {"direction"},
    "contracts_generated":  {"contract_count"},
    "sprint_planned":       {"sprint", "contract_count", "goal"},
    "contract_passed":      {"contract_id", "title", "sprint"},
    "contract_failed":      {"contract_id", "title", "sprint", "reason"},
    "contract_rolled_back": {"contract_id", "title", "reason"},
    "audit_run":            {"sprint", "result", "contracts_checked"},
    "audit_violation":      {"invariant_id", "description", "severity"},
    "decisions_approved":   {"change_summary"},
    "intent_promoted":      {"intent_id", "from_scope", "to_scope", "sprint"},
    "threat_mitigated":     {"threat_id", "stride_category"},
    "sprint_gate_passed":   {"sprint", "contracts_passing", "contracts_total"},
    "sprint_gate_failed":   {"sprint", "reason"},
    "deploy_approved":      {"target"},
    "bootstrap":            set(),
    "custom":               {"note"},
}

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_AUDIT_RESULTS = {"clean", "violations_found", "incomplete"}
VALID_SCOPES = {"core", "extension", "future"}
VALID_DEPLOY_TARGETS = {"dev", "staging", "production"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_audit_log() -> Path:
    candidates = [
        Path("./outcomes/audit-log.yaml"),
        Path("outcomes/audit-log.yaml"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    print(
        "ERROR: audit-log.yaml not found.\n"
        "       Looked in: ./outcomes/audit-log.yaml\n"
        "       Create it first via project-setup S0-T001 or gadp_init_project.py.",
        file=sys.stderr,
    )
    sys.exit(2)


def read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No input provided on stdin.", file=sys.stderr)
        print(
            "       Usage: echo '<JSON>' | python scripts/gadp_append_audit.py",
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


def validate_event(data: dict) -> list[str]:
    errors = []
    event_type = data.get("type", "")
    actor = data.get("actor", "")

    if not event_type:
        errors.append("'type' field is required.")
    elif event_type not in KNOWN_EVENT_TYPES:
        errors.append(
            f"Unknown event type: {event_type!r}.\n"
            f"         Known types: {sorted(KNOWN_EVENT_TYPES)}\n"
            "         Use type: 'custom' with a 'note' field for one-off events."
        )

    if not actor:
        errors.append("'actor' field is required.")
    elif actor not in KNOWN_ACTORS:
        errors.append(
            f"Unknown actor: {actor!r}.\n"
            f"         Known actors: {sorted(KNOWN_ACTORS)}"
        )

    # Reject manual timestamp — we always set it
    if "timestamp" in data:
        errors.append(
            "'timestamp' is set automatically. Remove it from your input — "
            "the current UTC time will be used."
        )

    # Check required extra fields for the event type
    if event_type in EVENT_REQUIRED_FIELDS:
        required_extra = EVENT_REQUIRED_FIELDS[event_type]
        missing = required_extra - set(data.keys())
        if missing:
            errors.append(
                f"Event type '{event_type}' is missing required fields: {sorted(missing)}"
            )

    # Type-specific value checks
    if event_type == "audit_violation":
        sev = data.get("severity")
        if sev and sev not in VALID_SEVERITIES:
            errors.append(
                f"'severity' must be one of {sorted(VALID_SEVERITIES)}. Got: {sev!r}"
            )

    if event_type == "audit_run":
        result = data.get("result")
        if result and result not in VALID_AUDIT_RESULTS:
            errors.append(
                f"'result' must be one of {sorted(VALID_AUDIT_RESULTS)}. Got: {result!r}"
            )

    if event_type == "intent_promoted":
        from_scope = data.get("from_scope")
        to_scope = data.get("to_scope")
        if from_scope and from_scope not in VALID_SCOPES:
            errors.append(f"'from_scope' must be one of {sorted(VALID_SCOPES)}. Got: {from_scope!r}")
        if to_scope and to_scope not in VALID_SCOPES:
            errors.append(f"'to_scope' must be one of {sorted(VALID_SCOPES)}. Got: {to_scope!r}")

    if event_type == "deploy_approved":
        target = data.get("target")
        if target and target not in VALID_DEPLOY_TARGETS:
            errors.append(
                f"'target' must be one of {sorted(VALID_DEPLOY_TARGETS)}. Got: {target!r}"
            )

    if event_type in {"contract_passed", "contract_failed", "contract_rolled_back"}:
        contract_id = data.get("contract_id", "")
        if contract_id and not contract_id.startswith("OC-"):
            errors.append(f"'contract_id' must start with 'OC-'. Got: {contract_id!r}")

    if event_type in {"sprint_planned", "sprint_gate_passed", "sprint_gate_failed",
                       "audit_run", "contract_passed", "contract_failed"}:
        sprint = data.get("sprint")
        if sprint is not None and (not isinstance(sprint, int) or sprint < 0):
            errors.append(f"'sprint' must be a non-negative integer. Got: {sprint!r}")

    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    data = read_stdin_json()

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = validate_event(data)
    if errors:
        print("ERROR: Event validation failed:", file=sys.stderr)
        for e in errors:
            print(f"       - {e}", file=sys.stderr)
        sys.exit(1)

    # ── Inject timestamp (always UTC, always now) ─────────────────────────────
    data["timestamp"] = datetime.now(timezone.utc).isoformat()

    # ── Normalise key order: type, timestamp, actor, then rest ────────────────
    ordered = {
        "type":      data.pop("type"),
        "timestamp": data.pop("timestamp"),
        "actor":     data.pop("actor"),
    }
    ordered.update(data)   # remaining fields in input order

    # ── Load audit-log.yaml ───────────────────────────────────────────────────
    log_path = find_audit_log()
    try:
        with open(log_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except Exception as exc:
        print(f"ERROR: Failed to read {log_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(doc, dict):
        print(f"ERROR: {log_path} is malformed — expected a YAML mapping at root.", file=sys.stderr)
        sys.exit(1)

    if "events" not in doc:
        doc["events"] = []

    if not isinstance(doc["events"], list):
        print(
            f"ERROR: {log_path} is malformed — 'events' must be a list.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Append event ──────────────────────────────────────────────────────────
    doc["events"].append(ordered)

    # ── Write back atomically ─────────────────────────────────────────────────
    atomic_write(log_path, doc)

    event_count = len(doc["events"])
    event_type = ordered["type"]
    print(f"OK:    '{event_type}' event appended to {log_path} — total events: {event_count}")


if __name__ == "__main__":
    main()
