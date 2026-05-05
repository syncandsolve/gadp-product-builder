#!/usr/bin/env python3
"""
gadp_validate.py — Validate all GADP YAML files against schema.

Usage:
    python scripts/gadp_validate.py

Validates:
    ./intents/intent-store.yaml
    ./intents/design-language.yaml  (if has_ui: true)
    ./outcomes/contracts.yaml
    ./outcomes/audit-log.yaml       (if present)
    ./decisions/decisions.yaml
    ./decisions/invariants.yaml
    ./decisions/threat-model.yaml

Reports each file PASS / FAIL with field-level errors.
Also runs cross-file consistency checks (project_id, ID references, etc.)

Exit codes:
    0 — all files pass
    1 — one or more validation failures
    2 — required file not found
"""

import sys
from pathlib import Path
from uuid import UUID

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Colour helpers (no dependencies) ─────────────────────────────────────────

def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"

def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"

def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"

def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"

# ── YAML load helpers ─────────────────────────────────────────────────────────

def load_yaml(path: Path) -> tuple[dict | None, str | None]:
    """Return (doc, error_message). doc is None on parse error."""
    if not path.exists():
        return None, f"File not found: {path}"
    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if not isinstance(doc, dict):
            return None, f"Expected a YAML mapping at root, got {type(doc).__name__}"
        return doc, None
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"

def is_valid_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False

# ── Collector ─────────────────────────────────────────────────────────────────

class FileResult:
    def __init__(self, label: str, path: Path):
        self.label = label
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.skipped = False
        self.skip_reason = ""

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def skip(self, reason: str) -> None:
        self.skipped = True
        self.skip_reason = reason

    @property
    def passed(self) -> bool:
        return not self.errors and not self.skipped

# ── Validators ────────────────────────────────────────────────────────────────

VALID_PRODUCT_TYPES = {
    "Web SaaS", "Internal tool", "Marketing site", "API product",
    "Chrome extension", "Desktop app", "Mobile-first PWA", "CLI tool", "Composite"
}

VALID_REGULATORY = {"none", "GDPR", "HIPAA", "PCI-DSS", "SOC2"}

VALID_CONTRACT_TYPES = {"functional", "security", "performance", "deletion", "accessibility"}
VALID_SCOPES = {"core", "extension", "future"}
VALID_CONTRACT_STATUSES = {
    "pending", "in_review", "passing", "failing",
    "deferred", "rolled_back", "blocked"
}

VALID_INV_CATEGORIES = {
    "architecture", "security", "data", "performance", "design_quality", "quality"
}
VALID_INV_VIOLATION_ACTIONS = {"hard_stop", "audit_flag"}

VALID_STRIDE = {
    "spoofing", "tampering", "repudiation",
    "information_disclosure", "denial_of_service", "elevation_of_privilege"
}

VALID_THREAT_SEVERITIES = {"Critical", "High", "Medium", "Low"}
VALID_THREAT_STATUSES = {"open", "mitigated", "accepted", "transferred"}


def validate_intent_store(path: Path, result: FileResult) -> dict | None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return None

    # ── Top-level keys ────────────────────────────────────────────────────────
    for key in ("gadp_version", "project", "intents"):
        if key not in doc:
            result.err(f"Missing required top-level key: '{key}'")

    # ── project block ─────────────────────────────────────────────────────────
    project = doc.get("project", {}) or {}
    if not isinstance(project, dict):
        result.err("'project' must be a mapping")
    else:
        pid = project.get("id")
        if not pid:
            result.err("project.id is required")
        elif not is_valid_uuid(str(pid)):
            result.err(f"project.id must be a valid UUID. Got: {pid!r}")

        ptype = project.get("type")
        if not ptype:
            result.err("project.type is required")
        elif ptype not in VALID_PRODUCT_TYPES:
            result.warn(f"project.type '{ptype}' is not a recognised product type. "
                        f"Known: {sorted(VALID_PRODUCT_TYPES)}")

        for flag in ("has_ui", "has_backend", "has_database", "has_auth"):
            if flag not in project:
                result.err(f"project.{flag} is required (must be true or false)")
            elif not isinstance(project[flag], bool):
                result.err(f"project.{flag} must be a boolean. Got: {project[flag]!r}")

        reg = project.get("regulatory_exposure")
        if reg is None:
            result.err("project.regulatory_exposure is required")
        else:
            if isinstance(reg, list):
                for r in reg:
                    if r not in VALID_REGULATORY:
                        result.warn(f"Unrecognised regulatory_exposure value: {r!r}. "
                                    f"Known: {sorted(VALID_REGULATORY)}")
            elif isinstance(reg, str) and reg not in VALID_REGULATORY:
                result.warn(f"Unrecognised regulatory_exposure: {reg!r}. "
                            f"Known: {sorted(VALID_REGULATORY)}")

    has_ui = project.get("has_ui", False)

    # ── intents block ─────────────────────────────────────────────────────────
    intents = doc.get("intents", {}) or {}

    # Capability intents
    caps = intents.get("capabilities", []) or []
    core_caps = [c for c in caps if c.get("scope") == "core"]
    if len(core_caps) < 4:
        result.err(f"At least 4 core capability intents required. Found: {len(core_caps)}")

    ci_ids: set[str] = set()
    for i, cap in enumerate(caps):
        ctx = f"intents.capabilities[{i}] (id={cap.get('id', '?')})"
        cap_id = cap.get("id")
        if not cap_id:
            result.err(f"{ctx}: 'id' is required")
        elif not str(cap_id).startswith("CI-"):
            result.err(f"{ctx}: 'id' must start with 'CI-'. Got: {cap_id!r}")
        else:
            if cap_id in ci_ids:
                result.err(f"Duplicate capability intent id: {cap_id}")
            ci_ids.add(cap_id)

        for field in ("label", "scope", "security_surface"):
            if field not in cap:
                result.err(f"{ctx}: missing required field '{field}'")

        scope = cap.get("scope")
        if scope and scope not in VALID_SCOPES:
            result.err(f"{ctx}: 'scope' must be one of {sorted(VALID_SCOPES)}. Got: {scope!r}")

        if scope in ("extension", "future"):
            if not cap.get("deferral_reason"):
                result.err(f"{ctx}: 'deferral_reason' required when scope='{scope}'")
            if not cap.get("inclusion_trigger"):
                result.err(f"{ctx}: 'inclusion_trigger' required when scope='{scope}'")

        if cap.get("security_surface") is True:
            if not cap.get("security_concern_type"):
                result.err(f"{ctx}: 'security_concern_type' required when security_surface=true")

    # Quality intents
    qis = intents.get("quality", []) or []
    hard_qis = [q for q in qis if q.get("constraint_level") == "hard"]
    if len(qis) < 3:
        result.err(f"At least 3 quality intents required. Found: {len(qis)}")
    if not hard_qis:
        result.err("At least 1 quality intent must have constraint_level: hard")

    qi_ids = {q.get("id") for q in qis}
    if has_ui:
        for mandatory in ("QI-LCP", "QI-CLS", "QI-INP", "QI-BUNDLE"):
            if not any(q.get("id") == mandatory for q in qis):
                result.err(f"has_ui=true requires quality intent {mandatory}")
        for qi in qis:
            qi_id = qi.get("id", "?")
            for field in ("scale_trigger", "measurement_method"):
                if not qi.get(field):
                    result.err(f"Quality intent {qi_id}: '{field}' is required")

    # Security intents
    security = intents.get("security", []) or []
    si_ids: set[str] = set()
    for i, si in enumerate(security):
        ctx = f"intents.security[{i}] (id={si.get('id', '?')})"
        si_id = si.get("id")
        if si_id:
            if si_id in si_ids:
                result.err(f"Duplicate security intent id: {si_id}")
            si_ids.add(si_id)
            if not str(si_id).startswith("SI-"):
                result.err(f"{ctx}: 'id' must start with 'SI-'. Got: {si_id!r}")
        for field in ("threat_id", "stride_category", "label"):
            if not si.get(field):
                result.err(f"{ctx}: missing required field '{field}'")
        stride = si.get("stride_category")
        if stride and stride not in VALID_STRIDE:
            result.err(f"{ctx}: 'stride_category' must be one of {sorted(VALID_STRIDE)}")

    return doc


def validate_contracts(path: Path, result: FileResult, project_id: str | None) -> dict | None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return None

    # project_id consistency
    if project_id and doc.get("project_id") != project_id:
        result.err(
            f"project_id mismatch: contracts.yaml has '{doc.get('project_id')}', "
            f"intent-store.yaml has '{project_id}'"
        )

    contracts = doc.get("contracts", [])
    if not isinstance(contracts, list):
        result.err("'contracts' must be a list")
        return doc

    if len(contracts) < 1:
        result.err("contracts.yaml must contain at least 1 contract")

    pending = [c for c in contracts if c.get("status") == "pending"]
    if not pending:
        result.warn("No pending contracts — ensure this is intentional (post-sprint)")

    oc_ids: set[str] = set()
    for i, contract in enumerate(contracts):
        ctx = f"contracts[{i}] (id={contract.get('id', '?')})"

        oc_id = contract.get("id")
        if not oc_id:
            result.err(f"{ctx}: 'id' is required")
        elif not str(oc_id).startswith("OC-"):
            result.err(f"{ctx}: 'id' must start with 'OC-'. Got: {oc_id!r}")
        else:
            if oc_id in oc_ids:
                result.err(f"Duplicate contract id: {oc_id}")
            oc_ids.add(oc_id)

        for field in ("title", "intent_ref", "contract_type", "sprint",
                       "scope", "given", "when", "then", "test_file", "status"):
            if field not in contract:
                result.err(f"{ctx}: missing required field '{field}'")

        ctype = contract.get("contract_type")
        if ctype and ctype not in VALID_CONTRACT_TYPES:
            result.err(f"{ctx}: 'contract_type' must be one of {sorted(VALID_CONTRACT_TYPES)}")

        scope = contract.get("scope")
        if scope and scope not in VALID_SCOPES:
            result.err(f"{ctx}: 'scope' must be one of {sorted(VALID_SCOPES)}")

        status = contract.get("status")
        if status and status not in VALID_CONTRACT_STATUSES:
            result.err(f"{ctx}: 'status' must be one of {sorted(VALID_CONTRACT_STATUSES)}")

        sprint = contract.get("sprint")
        if sprint is not None and (not isinstance(sprint, int) or sprint < 0):
            result.err(f"{ctx}: 'sprint' must be a non-negative integer. Got: {sprint!r}")

        test_file = contract.get("test_file", "")
        if test_file and not test_file.startswith("tests/"):
            result.err(f"{ctx}: 'test_file' must start with 'tests/'. Got: {test_file!r}")

        intent_ref = contract.get("intent_ref", "")
        if intent_ref and not str(intent_ref).startswith(("CI-", "SI-", "QI-")):
            result.warn(f"{ctx}: 'intent_ref' should start with CI-, SI-, or QI-. Got: {intent_ref!r}")

        threat_refs = contract.get("threat_refs")
        if threat_refs is not None:
            if not isinstance(threat_refs, list):
                result.err(f"{ctx}: 'threat_refs' must be a list")
            else:
                bad = [r for r in threat_refs if not str(r).startswith("T-")]
                if bad:
                    result.err(f"{ctx}: all 'threat_refs' must start with 'T-'. Bad: {bad}")

        depends_on = contract.get("depends_on")
        if depends_on is not None:
            if not isinstance(depends_on, list):
                result.err(f"{ctx}: 'depends_on' must be a list")
            else:
                bad = [
                    d for d in depends_on
                    if not (isinstance(d, str) and d.startswith("OC-")
                            and d[3:].isdigit() and len(d) >= 5)
                ]
                if bad:
                    result.err(f"{ctx}: all 'depends_on' entries must match OC-NNN format. Bad: {bad}")
                if oc_id and oc_id in depends_on:
                    result.err(f"{ctx}: 'depends_on' must not contain the contract's own ID ({oc_id!r})")

    # depends_on cross-reference and cycle detection
    dep_map: dict[str, list[str]] = {}
    for contract in contracts:
        cid = contract.get("id")
        deps = contract.get("depends_on") or []
        if not isinstance(deps, list) or not cid:
            continue
        dep_map[cid] = [d for d in deps if isinstance(d, str)]
        for dep_id in dep_map[cid]:
            if dep_id not in oc_ids:
                result.err(
                    f"Contract {cid}: depends_on references {dep_id!r} "
                    f"which does not exist in contracts.yaml"
                )

    # Cycle detection — DFS over the dependency graph
    visited: set[str] = set()
    in_stack: set[str] = set()

    def has_cycle(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for neighbour in dep_map.get(node, []):
            if has_cycle(neighbour):
                return True
        in_stack.discard(node)
        return False

    for node in list(dep_map):
        if node not in visited and has_cycle(node):
            result.err(
                f"Circular dependency detected in depends_on graph involving {node!r}. "
                f"Sprint planning cannot order contracts with circular dependencies — "
                f"review the depends_on chain and remove the cycle."
            )
            break  # one cycle error is sufficient; the chain will be obvious from the graph

    # Declared count consistency
    declared = doc.get("contract_count")
    if declared is not None and declared != len(contracts):
        result.warn(
            f"'contract_count' declares {declared} but {len(contracts)} contracts found. "
            "Run gadp_validate.py after any append to detect this."
        )

    return doc


def validate_decisions(path: Path, result: FileResult, project_id: str | None) -> dict | None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return None

    if project_id and doc.get("project_id") != project_id:
        result.err(
            f"project_id mismatch: decisions.yaml has '{doc.get('project_id')}', "
            f"intent-store.yaml has '{project_id}'"
        )

    if not doc.get("locked"):
        result.warn("decisions.yaml 'locked' field is not true — decisions should be locked after /approve-decisions")

    if not doc.get("selected_direction"):
        result.err("'selected_direction' is required in decisions.yaml")

    threat_ref = doc.get("threat_model_ref")
    if not threat_ref:
        result.err("'threat_model_ref' is required in decisions.yaml — must point to ./decisions/threat-model.yaml")
    elif threat_ref != "./decisions/threat-model.yaml":
        result.warn(
            f"'threat_model_ref' should be './decisions/threat-model.yaml'. Got: {threat_ref!r}. "
            "Agents look for T-* IDs in threat-model.yaml, not decisions.yaml."
        )

    decisions_list = doc.get("decisions", []) or []
    for i, dec in enumerate(decisions_list):
        ctx = f"decisions[{i}] (id={dec.get('id', '?')})"
        dec_id = dec.get("id", "")
        if not str(dec_id).startswith("DEC-"):
            result.warn(f"{ctx}: 'id' should start with 'DEC-'. Got: {dec_id!r}")

        if not dec.get("dimension"):
            result.err(f"{ctx}: 'dimension' is required")
        if not dec.get("choice"):
            result.err(f"{ctx}: 'choice' is required")
        if not dec.get("why"):
            result.err(f"{ctx}: 'why' is required — every decision must cite its intent")

        inv_gen = dec.get("invariant_generated")
        if inv_gen and not str(inv_gen).startswith("INV-"):
            result.warn(f"{ctx}: 'invariant_generated' should start with 'INV-'. Got: {inv_gen!r}")

    return doc


def validate_invariants(path: Path, result: FileResult, project_id: str | None, doc_decisions: dict | None) -> dict | None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return None

    if project_id and doc.get("project_id") != project_id:
        result.err(
            f"project_id mismatch: invariants.yaml has '{doc.get('project_id')}', "
            f"intent-store.yaml has '{project_id}'"
        )

    invariants = doc.get("invariants", []) or []
    if len(invariants) < 1:
        result.err("invariants.yaml must contain at least 1 invariant")

    inv_ids: set[str] = set()
    has_inv_a = False
    has_inv_s = False

    # Collect declared invariant IDs from decisions for cross-check
    declared_in_decisions: set[str] = set()
    if doc_decisions:
        for dec in (doc_decisions.get("decisions") or []):
            ig = dec.get("invariant_generated")
            if ig:
                declared_in_decisions.add(str(ig))

    for i, inv in enumerate(invariants):
        ctx = f"invariants[{i}] (id={inv.get('id', '?')})"
        inv_id = inv.get("id", "")

        if not inv_id:
            result.err(f"{ctx}: 'id' is required")
        else:
            if inv_id in inv_ids:
                result.err(f"Duplicate invariant id: {inv_id}")
            inv_ids.add(inv_id)
            if inv_id.startswith("INV-A-"):
                has_inv_a = True
            if inv_id.startswith("INV-S-"):
                has_inv_s = True

        if inv_id == "INV-U-001" or inv_id.startswith("INV-U-"):
            result.err(
                f"{ctx}: INV-U-* invariants are retired in GADP v3.0. "
                "Use INV-DQ-001 instead."
            )

        for field in ("category", "rule", "violation_action"):
            if not inv.get(field):
                result.err(f"{ctx}: missing required field '{field}'")

        cat = inv.get("category")
        if cat and cat not in VALID_INV_CATEGORIES:
            result.warn(
                f"{ctx}: 'category' '{cat}' is not a recognised invariant category. "
                f"Known: {sorted(VALID_INV_CATEGORIES)}"
            )

        va = inv.get("violation_action")
        if va and va not in VALID_INV_VIOLATION_ACTIONS:
            result.err(
                f"{ctx}: 'violation_action' must be one of {sorted(VALID_INV_VIOLATION_ACTIONS)}. "
                f"Got: {va!r}"
            )

        auto = inv.get("auto_detectable")
        if auto is True and not inv.get("detection_command"):
            result.warn(
                f"{ctx}: auto_detectable=true but 'detection_command' is missing or empty. "
                "Add a detection command or set auto_detectable: false."
            )

        # Source check — every invariant must have exactly one source
        has_source = bool(inv.get("source_decision")) or bool(inv.get("source_intent"))
        if not has_source:
            result.warn(
                f"{ctx}: no source found (source_decision or source_intent). "
                "Every invariant must cite the decision or intent that drove it."
            )

    if not has_inv_a:
        result.warn("No INV-A-* (architecture) invariant found. At least one is expected for most product types.")
    if not has_inv_s:
        result.warn("No INV-S-* (security) invariant found. At least one is expected when has_auth: true.")

    # Cross-check: invariants declared in decisions.yaml should exist here
    for dec_inv in declared_in_decisions:
        if dec_inv not in inv_ids:
            result.err(
                f"decisions.yaml references invariant_generated: {dec_inv} "
                f"but it was not found in invariants.yaml"
            )

    return doc


def validate_threat_model(path: Path, result: FileResult, project_id: str | None) -> dict | None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return None

    if project_id and doc.get("project_id") != project_id:
        result.err(
            f"project_id mismatch: threat-model.yaml has '{doc.get('project_id')}', "
            f"intent-store.yaml has '{project_id}'"
        )

    if "stride" not in doc:
        result.err("'stride' block is required in threat-model.yaml")
        return doc

    stride_block = doc.get("stride", {}) or {}
    if not isinstance(stride_block, dict):
        result.err("'stride' must be a mapping with STRIDE category keys")
        return doc

    # Check each STRIDE category has at least 1 entry
    for cat in VALID_STRIDE:
        entries = stride_block.get(cat, []) or []
        if not entries:
            result.warn(f"No threats in STRIDE category '{cat}'. At least 1 entry expected.")

    t_ids: set[str] = set()
    for cat, entries in stride_block.items():
        if not isinstance(entries, list):
            result.warn(f"stride.{cat} should be a list. Got: {type(entries).__name__}")
            continue
        for i, threat in enumerate(entries):
            ctx = f"stride.{cat}[{i}] (id={threat.get('id', '?')})"
            t_id = threat.get("id", "")
            if not t_id:
                result.err(f"{ctx}: 'id' is required")
            else:
                if t_id in t_ids:
                    result.err(f"Duplicate threat id: {t_id}")
                t_ids.add(t_id)
                if not str(t_id).startswith("T-"):
                    result.err(f"{ctx}: 'id' must start with 'T-'. Got: {t_id!r}")

            sev = threat.get("severity")
            if sev and sev not in VALID_THREAT_SEVERITIES:
                result.err(
                    f"{ctx}: 'severity' must be one of {sorted(VALID_THREAT_SEVERITIES)}. "
                    f"Got: {sev!r}"
                )

            status = threat.get("status")
            if status and status not in VALID_THREAT_STATUSES:
                result.err(
                    f"{ctx}: 'status' must be one of {sorted(VALID_THREAT_STATUSES)}. "
                    f"Got: {status!r}"
                )

    if not doc.get("components"):
        result.warn("'components' block is missing from threat-model.yaml")
    if not doc.get("trust_boundaries"):
        result.warn("'trust_boundaries' block is missing from threat-model.yaml")

    return doc, t_ids  # type: ignore[return-value]


def validate_audit_log(path: Path, result: FileResult, project_id: str | None) -> None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return

    if project_id and doc.get("project_id") != project_id:
        result.err(
            f"project_id mismatch: audit-log.yaml has '{doc.get('project_id')}', "
            f"intent-store.yaml has '{project_id}'"
        )

    events = doc.get("events", [])
    if not isinstance(events, list):
        result.err("'events' must be a list")
        return

    if not events:
        result.warn("audit-log.yaml has no events — expected at least a bootstrap event")
        return

    for i, ev in enumerate(events):
        ctx = f"events[{i}]"
        if not ev.get("type"):
            result.err(f"{ctx}: 'type' is required")
        if not ev.get("timestamp"):
            result.err(f"{ctx}: 'timestamp' is required")
        if not ev.get("actor"):
            result.err(f"{ctx}: 'actor' is required")


def validate_design_language(path: Path, result: FileResult) -> None:
    doc, err = load_yaml(path)
    if err:
        result.err(err)
        return

    for key in ("colors", "typography"):
        if key not in doc:
            result.warn(f"design-language.yaml: '{key}' block is missing")

    colors = doc.get("colors", {}) or {}
    for expected in ("primary", "secondary"):
        if expected not in colors:
            result.warn(f"design-language.yaml: colors.{expected} is missing")


# ── Cross-file: threat refs in contracts ─────────────────────────────────────

def cross_check_threat_refs(
    contracts_doc: dict | None,
    threat_ids: set[str],
    results: list[FileResult],
) -> list[str]:
    errors = []
    if not contracts_doc:
        return errors
    for contract in contracts_doc.get("contracts", []):
        refs = contract.get("threat_refs") or []
        oc_id = contract.get("id", "?")
        for ref in refs:
            if ref not in threat_ids:
                errors.append(
                    f"Contract {oc_id} references threat {ref!r} "
                    f"but it does not exist in threat-model.yaml"
                )
    return errors


# ── Reporter ──────────────────────────────────────────────────────────────────

def print_result(r: FileResult) -> None:
    if r.skipped:
        print(f"  {_yellow('SKIP')}  {r.label}  ({r.skip_reason})")
        return

    if r.passed and not r.warnings:
        print(f"  {_green('PASS')}  {r.label}")
    elif r.passed:
        print(f"  {_green('PASS')}  {r.label}  {_yellow(f'({len(r.warnings)} warning(s))')}")
    else:
        print(f"  {_red('FAIL')}  {r.label}  ({len(r.errors)} error(s), {len(r.warnings)} warning(s))")

    for e in r.errors:
        print(f"         {_red('✗')} {e}")
    for w in r.warnings:
        print(f"         {_yellow('△')} {w}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(_bold("\nGADP Validation Report"))
    print("─" * 60)

    results: list[FileResult] = []
    all_errors: list[str] = []

    # ── intent-store.yaml ─────────────────────────────────────────────────────
    r_intent = FileResult("intent-store.yaml", Path("./intents/intent-store.yaml"))
    results.append(r_intent)
    intent_doc = validate_intent_store(r_intent.path, r_intent)
    project_id = None
    has_ui = False
    if intent_doc:
        project_id = str(intent_doc.get("project", {}).get("id", ""))
        has_ui = intent_doc.get("project", {}).get("has_ui", False)

    # ── design-language.yaml (conditional) ───────────────────────────────────
    dl_path = Path("./intents/design-language.yaml")
    r_dl = FileResult("design-language.yaml", dl_path)
    results.append(r_dl)
    if has_ui:
        validate_design_language(dl_path, r_dl)
    else:
        r_dl.skip("has_ui is false")

    # ── contracts.yaml ────────────────────────────────────────────────────────
    r_contracts = FileResult("contracts.yaml", Path("./outcomes/contracts.yaml"))
    results.append(r_contracts)
    contracts_doc = validate_contracts(r_contracts.path, r_contracts, project_id)

    # ── decisions.yaml ────────────────────────────────────────────────────────
    r_decisions = FileResult("decisions.yaml", Path("./decisions/decisions.yaml"))
    results.append(r_decisions)
    decisions_doc = validate_decisions(r_decisions.path, r_decisions, project_id)

    # ── invariants.yaml ───────────────────────────────────────────────────────
    r_inv = FileResult("invariants.yaml", Path("./decisions/invariants.yaml"))
    results.append(r_inv)
    validate_invariants(r_inv.path, r_inv, project_id, decisions_doc)

    # ── threat-model.yaml ─────────────────────────────────────────────────────
    r_threat = FileResult("threat-model.yaml", Path("./decisions/threat-model.yaml"))
    results.append(r_threat)
    threat_result = validate_threat_model(r_threat.path, r_threat, project_id)
    threat_ids: set[str] = set()
    if isinstance(threat_result, tuple):
        _, threat_ids = threat_result

    # ── audit-log.yaml (optional) ─────────────────────────────────────────────
    audit_path = Path("./outcomes/audit-log.yaml")
    r_audit = FileResult("audit-log.yaml", audit_path)
    results.append(r_audit)
    if audit_path.exists():
        validate_audit_log(audit_path, r_audit, project_id)
    else:
        r_audit.skip("not yet created (expected after S0-T001)")

    # ── Cross-file checks ─────────────────────────────────────────────────────
    cross_errors = cross_check_threat_refs(contracts_doc, threat_ids, results)

    # ── Print per-file results ─────────────────────────────────────────────────
    for r in results:
        print_result(r)

    # ── Cross-file errors ─────────────────────────────────────────────────────
    if cross_errors:
        print()
        print(_bold("Cross-file consistency errors:"))
        for e in cross_errors:
            print(f"  {_red('✗')} {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_errors = sum(len(r.errors) for r in results) + len(cross_errors)
    total_warnings = sum(len(r.warnings) for r in results)
    failed = [r for r in results if not r.passed and not r.skipped]

    print("─" * 60)
    if total_errors == 0:
        print(_green(_bold(f"  All files valid.  {total_warnings} warning(s).")))
        sys.exit(0)
    else:
        print(_red(_bold(
            f"  {total_errors} error(s) in {len(failed)} file(s).  "
            f"{total_warnings} warning(s)."
        )))
        sys.exit(1)


if __name__ == "__main__":
    main()
