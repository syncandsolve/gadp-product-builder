#!/usr/bin/env python3
"""
gadp_init_project.py — Generate initial GADP project YAML files for a new project.

This script replaces the manual writing of GADP files during project bootstrap.
It is the FIRST script to run — before any other gadp_*.py scripts.

Usage:
    python gadp/scripts/gadp_init_project.py --config project-init.json [--out .]

The --config file is a JSON document produced by the Intent Architect and Outcome
Resolver agents. Its structure is documented below.

This script generates:
    ./intents/intent-store.yaml
    ./intents/design-language.yaml          (if has_ui: true)
    ./outcomes/contracts.yaml
    ./outcomes/audit-log.yaml
    ./decisions/decisions.yaml              (stub — Outcome Resolver fills this)
    ./decisions/invariants.yaml             (stub — Outcome Resolver fills this)
    ./decisions/threat-model.yaml           (stub — Outcome Resolver fills this)
    ./decisions/openapi.yaml                (stub — Outcome Resolver fills this, if has_backend)
    ./diagrams/primary-value-loop.mmd       (stub — Intent Architect fills this)

It also:
    - Creates all required directories
    - Writes an initial audit-log.yaml with a bootstrap event
    - Validates the generated files using the same checks as gadp_validate.py

After running, validate by running:
    python scripts/gadp_validate.py

project-init.json structure:
{
  "project_id":           "UUID — generate a new v4 if absent",
  "project_name":         "My Product",
  "product_type":         "Web SaaS",
  "has_ui":               true,
  "has_backend":          true,
  "has_database":         true,
  "has_auth":             true,
  "regulatory_exposure":  "GDPR",
  "data_sensitivity":     "SENSITIVE",

  "product": {
    "name":               "My Product",
    "tagline":            "One sentence value proposition",
    "solution_map": {
      "problem":          "what problem it solves",
      "for_whom":         "who it is for",
      "severity":         "high"
    }
  },

  "stack_preferences": {
    "language":           "TypeScript",
    "framework":          "Next.js",
    "database":           "PostgreSQL",
    "orm":                "Prisma",
    "auth_strategy":      "Custom JWT"
  },

  "capabilities": [
    {
      "id":               "CI-001",
      "label":            "User can register with email and password",
      "scope":            "core",
      "security_surface": true,
      "security_concern_type": "auth_credential",
      "inferred":         false
    }
  ],

  "quality_intents": [
    {
      "id":               "QI-LCP",
      "label":            "LCP <= 2.5s on median hardware",
      "type":             "hard",
      "scale_trigger":    "p75 LCP exceeds 2.5s",
      "measurement_method": "Lighthouse CI"
    }
  ],

  "security_intents": [],

  "constraints": [],

  "kpis": [
    {
      "id":     "KPI-001",
      "label":  "100 active users within 90 days of launch",
      "north_star": true
    }
  ],

  "assumptions": [],

  "contracts": [],    // Can be empty at init — Outcome Resolver populates these

  "design": {         // Optional — set if has_ui: true and design tokens are known
    "source":         "described",
    "tokens": {
      "component_library": "shadcn/ui",
      "css_approach":      "Tailwind CSS",
      "colors": {
        "primary": "#4F46E5"
      }
    }
  }
}

Exit codes:
    0 — success
    1 — validation error in config or generated files
    2 — file system error
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Directories ───────────────────────────────────────────────────────────────

REQUIRED_DIRS = [
    "intents",
    "outcomes",
    "decisions",
    "diagrams",
    "scripts",
    "tests/contracts",
    "docs/runbooks",
    "docs/postmortems",
    "artifacts",
    "tmp",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        sys.exit(2)


def validate_config(cfg: dict) -> list[str]:
    errors = []
    required = [
        "project_name", "product_type", "has_ui",
        "has_backend", "has_database", "has_auth"
    ]
    for field in required:
        if field not in cfg:
            errors.append(f"Missing required field: '{field}'")

    product_type = cfg.get("product_type", "")
    valid_types = {
        "Web SaaS", "Internal tool", "Marketing site", "API product",
        "Chrome extension", "Desktop app", "Mobile-first PWA", "CLI tool", "Composite"
    }
    if product_type and product_type not in valid_types:
        errors.append(
            f"'product_type' must be one of {sorted(valid_types)}. Got: {product_type!r}"
        )

    for flag in ("has_ui", "has_backend", "has_database", "has_auth"):
        if flag in cfg and not isinstance(cfg[flag], bool):
            errors.append(f"'{flag}' must be a boolean. Got: {cfg[flag]!r}")

    caps = cfg.get("capabilities", [])
    if not isinstance(caps, list):
        errors.append("'capabilities' must be a list")
    else:
        core_caps = [c for c in caps if c.get("scope") == "core"]
        if caps and len(core_caps) < 1:
            errors.append("At least 1 core capability intent required in 'capabilities'")

    return errors


# ── File generators ───────────────────────────────────────────────────────────

def generate_intent_store(cfg: dict, out_dir: Path) -> None:
    project_id = cfg.get("project_id") or str(uuid.uuid4())

    doc = {
        "gadp_version": "3.1",
        "project": {
            "id": project_id,
            "name": cfg["project_name"],
            "type": cfg["product_type"],
            "has_ui": cfg["has_ui"],
            "has_backend": cfg["has_backend"],
            "has_database": cfg["has_database"],
            "has_auth": cfg["has_auth"],
            "regulatory_exposure": cfg.get("regulatory_exposure", "none"),
            "data_sensitivity": cfg.get("data_sensitivity", "none"),
            "created_at": now_iso(),
            "status": "locked",
        },
        "product": cfg.get("product", {
            "name": cfg["project_name"],
            "tagline": "Add tagline here",
            "solution_map": {
                "problem": "Define the problem",
                "for_whom": "Define the audience",
                "severity": "high",
            }
        }),
        "intents": {
            "capabilities": cfg.get("capabilities", []),
            "quality": cfg.get("quality_intents", []),
            "design": cfg.get("design", {"source": "N/A"}),
            "constraint": cfg.get("constraints", []),
            "security": cfg.get("security_intents", []),
        },
        "stack_preferences": cfg.get("stack_preferences", {}),
        "kpis": cfg.get("kpis", []),
        "assumptions": cfg.get("assumptions", []),
    }

    # Store project_id back into cfg for other generators to use
    cfg["_project_id"] = project_id

    path = out_dir / "intents" / "intent-store.yaml"
    atomic_write(path, doc)
    print(f"  OK  intents/intent-store.yaml  (project_id: {project_id})")


def generate_design_language(cfg: dict, out_dir: Path) -> None:
    if not cfg.get("has_ui"):
        return

    design = cfg.get("design", {})
    tokens = design.get("tokens", {})

    doc = {
        "gadp_version": "3.1",
        "project_id": cfg.get("_project_id", ""),
        "source": design.get("source", "described"),
        "component_library": tokens.get("component_library", "shadcn/ui"),
        "css_approach": tokens.get("css_approach", "Tailwind CSS"),
        "icon_library": tokens.get("icon_library", "lucide-react"),
        "colors": tokens.get("colors", {
            "primary": "#4F46E5",
            "secondary": "#7C3AED",
            "accent": "#06B6D4",
            "neutrals": {
                "50": "#F9FAFB", "100": "#F3F4F6", "200": "#E5E7EB",
                "400": "#9CA3AF", "600": "#4B5563", "900": "#111827"
            },
            "semantic": {
                "error": "#EF4444",
                "warning": "#F59E0B",
                "success": "#10B981",
                "info": "#3B82F6"
            }
        }),
        "typography": tokens.get("typography", {
            "heading": "Inter",
            "body": "Inter",
            "mono": "JetBrains Mono"
        }),
        "dark_mode": tokens.get("dark_mode", False),
        "generated_at": now_iso(),
        "note": (
            "Token values above are stubs derived from config. "
            "Intent Architect must confirm or update these before project-setup begins."
        ),
    }

    path = out_dir / "intents" / "design-language.yaml"
    atomic_write(path, doc)
    print(f"  OK  intents/design-language.yaml")


def generate_contracts(cfg: dict, out_dir: Path) -> None:
    contracts = cfg.get("contracts", [])
    project_id = cfg.get("_project_id", "")

    core_count = sum(1 for c in contracts if c.get("contract_type") == "functional")
    sec_count = sum(1 for c in contracts if c.get("contract_type") == "security")
    perf_count = sum(1 for c in contracts if c.get("contract_type") == "performance")
    del_count = sum(1 for c in contracts if c.get("contract_type") == "deletion")
    a11y_count = sum(1 for c in contracts if c.get("contract_type") == "accessibility")

    doc = {
        "gadp_version": "3.1",
        "project_id": project_id,
        "generated_at": now_iso(),
        "contract_count": len(contracts),
        "core_count": core_count,
        "security_count": sec_count,
        "performance_count": perf_count,
        "deletion_count": del_count,
        "accessibility_count": a11y_count,
        "contracts": contracts,
    }

    path = out_dir / "outcomes" / "contracts.yaml"
    atomic_write(path, doc)
    count_note = f"{len(contracts)} contracts" if contracts else "empty — Outcome Resolver will populate"
    print(f"  OK  outcomes/contracts.yaml  ({count_note})")


def generate_audit_log(cfg: dict, out_dir: Path) -> None:
    project_id = cfg.get("_project_id", "")

    doc = {
        "gadp_version": "3.1",
        "project_id": project_id,
        "events": [
            {
                "type": "bootstrap",
                "timestamp": now_iso(),
                "actor": "project-setup",
                "note": (
                    f"Project '{cfg['project_name']}' scaffolded by GADP "
                    f"gadp_init_project.py. project_id: {project_id}"
                ),
            }
        ],
    }

    path = out_dir / "outcomes" / "audit-log.yaml"
    atomic_write(path, doc)
    print(f"  OK  outcomes/audit-log.yaml  (bootstrap event written)")


def generate_decisions_stub(cfg: dict, out_dir: Path) -> None:
    project_id = cfg.get("_project_id", "")

    doc = {
        "gadp_version": "3.1",
        "project_id": project_id,
        "generated_at": now_iso(),
        "locked": False,
        "selected_direction": None,
        "threat_model_ref": "./decisions/threat-model.yaml",
        "decisions": [],
        "_stub": (
            "This file is a stub. Outcome Resolver Phase 2 will populate "
            "decisions and set locked: true after /approve-decisions."
        ),
    }

    path = out_dir / "decisions" / "decisions.yaml"
    atomic_write(path, doc)
    print(f"  OK  decisions/decisions.yaml  (stub — Outcome Resolver will populate)")


def generate_invariants_stub(cfg: dict, out_dir: Path) -> None:
    project_id = cfg.get("_project_id", "")

    doc = {
        "gadp_version": "3.1",
        "project_id": project_id,
        "generated_at": now_iso(),
        "invariants": [],
        "_stub": (
            "This file is a stub. Outcome Resolver Phase 7 will derive invariants "
            "from decisions and intent-store using gadp/config/invariant-defaults.yaml."
        ),
    }

    path = out_dir / "decisions" / "invariants.yaml"
    atomic_write(path, doc)
    print(f"  OK  decisions/invariants.yaml  (stub — Outcome Resolver will populate)")


def generate_threat_model_stub(cfg: dict, out_dir: Path) -> None:
    project_id = cfg.get("_project_id", "")

    doc = {
        "gadp_version": "3.1",
        "project_id": project_id,
        "generated_at": now_iso(),
        "components": [],
        "trust_boundaries": [],
        "stride": {cat: [] for cat in (
            "spoofing", "tampering", "repudiation",
            "information_disclosure", "denial_of_service", "elevation_of_privilege"
        )},
        "_stub": (
            "This file is a stub. Outcome Resolver Phase 5 will derive the STRIDE "
            "threat model from security intents and the architecture decisions."
        ),
    }

    path = out_dir / "decisions" / "threat-model.yaml"
    atomic_write(path, doc)
    print(f"  OK  decisions/threat-model.yaml  (stub — Outcome Resolver will populate)")


def generate_openapi_stub(cfg: dict, out_dir: Path) -> None:
    if not cfg.get("has_backend"):
        return

    eligible_types = {"Web SaaS", "Internal tool", "API product", "Mobile-first PWA"}
    if cfg.get("product_type") not in eligible_types:
        return

    project_id = cfg.get("_project_id", "")
    project_name = cfg.get("project_name", "Project")

    doc = {
        "openapi": "3.1.0",
        "info": {
            "title": project_name,
            "version": "1.0.0",
            "description": f"Generated by GADP gadp_init_project.py. project_id: {project_id}",
        },
        "paths": {},
        "_stub": (
            "This file is a stub. Outcome Resolver Phase 4 will derive all "
            "endpoints from capability intents and the architecture decisions."
        ),
    }

    path = out_dir / "decisions" / "openapi.yaml"
    atomic_write(path, doc)
    print(f"  OK  decisions/openapi.yaml  (stub — Outcome Resolver will populate)")


def generate_diagram_stub(cfg: dict, out_dir: Path) -> None:
    project_name = cfg.get("project_name", "Project")

    content = (
        f"%%{{init: {{'theme': 'default'}}}}%%\n"
        "flowchart LR\n"
        f"    A[User] --> B[{project_name}]\n"
        "    B --> C[Primary Value]\n"
        "    %% Stub — Intent Architect will replace this with the\n"
        "    %% primary value loop diagram after Phase 4.\n"
    )

    path = out_dir / "diagrams" / "primary-value-loop.mmd"
    tmp = path.with_suffix(".mmd.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        print(f"ERROR: Failed to write {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"  OK  diagrams/primary-value-loop.mmd  (stub)")


# ── Directory setup ───────────────────────────────────────────────────────────

def create_directories(out_dir: Path) -> None:
    for d in REQUIRED_DIRS:
        target = out_dir / d
        target.mkdir(parents=True, exist_ok=True)
    print(f"  OK  directories created: {', '.join(REQUIRED_DIRS)}")


# ── Self-validation after generation ─────────────────────────────────────────

def run_self_validation(out_dir: Path) -> bool:
    """Run gadp_validate.py from the out_dir. Return True if all pass."""
    import subprocess
    validate_script = out_dir / "gadp" / "scripts" / "gadp_validate.py"
    if not validate_script.exists():
        validate_script = out_dir / "scripts" / "gadp_validate.py"
    if not validate_script.exists():
        print(
            "\nWARN: gadp_validate.py not found — skipping self-validation.\n"
            "      Run: python scripts/gadp_validate.py manually to validate generated files."
        )
        return True

    result = subprocess.run(
        [sys.executable, str(validate_script)],
        cwd=str(out_dir),
        capture_output=False,
    )
    return result.returncode == 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate initial GADP project YAML files from a project-init.json config."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to project-init.json produced by Intent Architect / Outcome Resolver.",
    )
    parser.add_argument(
        "--out",
        default=".",
        help="Project root directory where files will be written (default: current directory).",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip self-validation after generation.",
    )
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in {config_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Validate config ───────────────────────────────────────────────────────
    errors = validate_config(cfg)
    if errors:
        print("ERROR: project-init.json validation failed:", file=sys.stderr)
        for e in errors:
            print(f"       - {e}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out).resolve()

    print(f"\nGADP Init — {cfg['project_name']}")
    print(f"Output:   {out_dir}")
    print(f"Type:     {cfg['product_type']}")
    print(f"Flags:    ui={cfg['has_ui']} backend={cfg['has_backend']} "
          f"db={cfg['has_database']} auth={cfg['has_auth']}")
    print("─" * 60)

    # ── Create directories ────────────────────────────────────────────────────
    try:
        create_directories(out_dir)
    except Exception as exc:
        print(f"ERROR: Failed to create directories: {exc}", file=sys.stderr)
        sys.exit(2)

    # ── Generate files ────────────────────────────────────────────────────────
    generate_intent_store(cfg, out_dir)
    generate_design_language(cfg, out_dir)
    generate_contracts(cfg, out_dir)
    generate_audit_log(cfg, out_dir)
    generate_decisions_stub(cfg, out_dir)
    generate_invariants_stub(cfg, out_dir)
    generate_threat_model_stub(cfg, out_dir)
    generate_openapi_stub(cfg, out_dir)
    generate_diagram_stub(cfg, out_dir)

    print("─" * 60)

    # ── Self-validation ───────────────────────────────────────────────────────
    if not args.no_validate:
        print("\nRunning gadp_validate.py on generated files...\n")
        passed = run_self_validation(out_dir)
        if not passed:
            print(
                "\nERROR: Validation failed on generated files.\n"
                "       Fix the errors above, then re-run gadp_init_project.py.\n"
                "       You may also edit project-init.json and re-run — "
                "all files will be overwritten.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print("\nWARN: Self-validation skipped (--no-validate). "
              "Run: python scripts/gadp_validate.py manually.")

    print(f"\nDone. Next step:")
    print(f"  The Governor will dispatch Intent Architect and Outcome Resolver")
    print(f"  to complete the GADP files before project setup begins.")
    print(f"  Or if you have pre-built GADP files, copy them into the generated")
    print(f"  directory structure and run: python scripts/gadp_validate.py\n")


if __name__ == "__main__":
    main()
