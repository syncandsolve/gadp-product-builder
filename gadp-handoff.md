# GADP — Session Handoff
## For the next agent continuing this work

---

## What GADP is

GADP (Governed Agentic Development Protocol) is a protocol for building production-ready software with an AI coding tool. It prevents context loss across sessions, enforces architecture governance, and produces a self-describing project that any new session can resume without conversation history.

The core idea: every feature is a **contract** (a precise, machine-testable definition of done), every decision is **locked** with rationale, every session resumes from **RESUME.md** on disk. The project knows what it is, what has been decided, what is passing, and what is next — independently of any AI conversation.

---

## Where the files live

**GitHub:** https://github.com/syncandsolve/gadp-product-builder

```
AGENTS.md                         ← Governor instructions (entry point)
README.md                         ← Plain-English overview
gadp/
  agents/
    intent-architect.md           ← Was Prompt A — idea intake through design language
    outcome-resolver.md           ← Was Prompt B — contracts, decisions, threat model
    project-setup.md              ← Was Prompt C — scaffold, CI/CD, Sprint 0
    builder.md                    ← NEW — contract implementation
    auditor.md                    ← NEW — invariants, regressions, sprint gates
    planner.md                    ← NEW — new features, changes, sprint planning
  config/
    framework-globs.yaml          ← Bundle size globs per framework
    qi-mandatory.yaml             ← Mandatory quality intents by product type
    invariant-defaults.yaml       ← INV-A/S/P/DQ/D/Q templates for Outcome Resolver
```

You can read any file with:
```
https://raw.githubusercontent.com/syncandsolve/gadp-product-builder/main/AGENTS.md
```

---

## How we got here — the full arc

### Where it started

GADP v2 was a three-prompt, manual-paste workflow. The user would:
1. Paste **Prompt A** (intent-architect) — run the full idea-to-design-language session in one shot
2. Paste **Prompt B** (outcome-resolver) — run the full architecture-to-contracts session
3. Paste **Prompt C** (project-setup) — scaffold the project and verify Sprint 0

Each prompt was ~1500 lines of embedded instructions, reference tables, format rules, and YAML schemas. If a session ended mid-prompt, there was no way to resume without re-pasting and manually explaining where things stopped. The three prompts were the only things keeping the project governed.

### What was strong in v2 and kept

- The **intent store** as single source of truth for everything the project is building
- **Outcome contracts** as the executable definition of done — `when / given / then`
- **STRIDE threat modelling** baked into the architecture phase
- **Invariants** with auto-detectable `detection_command` fields — governance that runs in CI
- The **audit log** as append-only record of every significant event
- **Sprint 0** separation — verify the scaffold before writing any product code
- **Idempotent task recovery** — tasks can be re-run safely if they fail
- The **data lifecycle** system — finite retention, deletion contracts per SENSITIVE entity
- The `/approve-decisions` gate for locked architecture decisions
- The `/approve-deploy-prod` gate with a hard production checklist

### What was broken and fixed

**Problem: No orchestration layer.** The model had to infer which "mode" it was in from conversation context. There was no Governor — the user was the Governor. Fixed by making `AGENTS.md` the Governor's instruction file. The Governor is always the entry point. It reads `RESUME.md`, detects state, dispatches agents, receives output, and communicates in plain language. The user never talks to agents directly.

**Problem: Cannot resume mid-phase.** Prompts A and B had no checkpoint system — if a session ended after confirming 2 of 4 capability intent batches, those confirmations were lost. Fixed by adding `phase_progress.confirmed_data` to `RESUME.md`. Every user confirmation is written to disk before continuing. Resumption reads confirmed data and skips re-asking.

**Problem: Three prompts, manual paste.** Fixed by replacing the three prompts with six sub-agent files in `gadp/agents/`. The Governor reads `AGENTS.md`, detects which phase the project is in, and dispatches the right agent automatically. The user says "hi" — that's it.

**Problem: Output format fighting the tool.** v2 enforced `=== block ===` formatting and `HARD STOP` directives to compensate for tools that barrel through gates. v3 removes all of this. The tool handles turn-taking natively. Agents use whatever format renders best — markdown tables, prose, grouped lists. No protocol syntax in user-facing output.

**Problem: Human-hostile language.** Capability intents were presented as `CI-001 core : A user can register`. Fixed by removing all ID codes from user-facing output. The Governor and agents speak in plain language. IDs live in YAML files, not in conversation.

**Problem: Hardcoded model routing.** `RESUME.md` had a `model_routing` block. Removed entirely. The tool operator configures the model. GADP does not route.

**Problem: Reference tables embedded in prompts.** Framework bundle size globs, mandatory quality intents, invariant templates — all were markdown tables inside Prompt B and C, adding hundreds of lines to files that had to be re-read every session. Moved to `gadp/config/` as YAML files read by the relevant agent only.

**Problem: No development-phase governance.** v2 ended after setup. There was no Builder, no Auditor, no Planner — development was ungoverned. Fixed by adding three new agents that handle the full development lifecycle with the same rigour as setup.

### The architecture that resulted

```
You
 │
 ▼
Governor (AGENTS.md)
 │  reads RESUME.md on every session start
 │  detects state → dispatches agent → receives output → reports in plain language
 │
 ├── Intent Architect    setup phase — idea to intent-store.yaml + design-language.yaml
 ├── Outcome Resolver    setup phase — intents to contracts + decisions + invariants + OpenAPI
 ├── Project Setup       setup phase — scaffold + CI/CD + Sprint 0 verification
 ├── Builder             dev phase   — contract implementation + auto-retry
 ├── Auditor             dev phase   — invariant checks + regressions + sprint gates
 └── Planner             dev phase   — new features + changes + sprint planning
```

**State machine in AGENTS.md** (first match):
1. `BOOTSTRAP` — no RESUME.md → create minimal RESUME.md → ask what we're building
2. `MID_PHASE` — phase in progress → ask user if they want to resume
3. `INTENT_ARCHITECT` → `OUTCOME_RESOLVER` → `PROJECT_SETUP` → `SPRINT_0` → `DEVELOPMENT`

**RESUME.md** is the only file the Governor writes directly. All other GADP YAML mutations go through `./scripts/gadp_*.py` — mutation scripts generated at S0-T001 that validate schema and write atomically.

---

## Key design decisions to preserve

- **Governor never implements.** It orchestrates and communicates. Never writes code, never touches contracts directly.
- **Auditor owns counters and audit log.** No other agent updates `status` counters in RESUME.md or writes to `audit-log.yaml`.
- **Builder owns contract status.** Only Builder marks contracts `passing`. Only Auditor marks them `failing` (regression).
- **Planner owns governance changes.** Only Planner modifies `decisions.yaml`, `invariants.yaml`, or contract `when/then` fields — always after `/approve-decisions`.
- **INV-DQ-001 is canonical.** All design token enforcement. INV-U-* is retired — never generate it.
- **INV-P-005 is intentionally null.** The only invariant where `detection_command: null` is correct — N+1 queries cannot be detected via grep.
- **Full-stack pairs never split.** UI contract and its API contract always in the same sprint.
- **sprint1_chain is the minimum viable journey.** Set by Intent Architect Step 6C, enforced by Outcome Resolver Phase 6, verified by Project Setup S0-T010 and the First Run Standard gate.
- **`threat-model.yaml` does not require `/approve-decisions`.** Threat model updates are operational, not architectural. Only `decisions.yaml` and `invariants.yaml` require the gate.

---

## Improvement areas identified but not yet implemented

These were noted during the build and are good candidates for the next session:

1. **`gadp status` shortcut** — a one-liner the Governor recognises that prints current phase, sprint, passing/failing counts, and the single next action. Useful for re-orienting mid-day without triggering a full session.

2. **Sub-agent output logs** — `./gadp/logs/` with one completion record per dispatch. Governor reads logs to construct status reports rather than re-reading all YAML on every session. Keeps context usage low on mature projects.

3. **Explicit disagreement flow** — currently if the user wants to change a derived decision (e.g. "I want a different database"), the flow is: user describes change → Governor detects it needs Planner → Planner does impact analysis → `/approve-decisions`. This works but the Governor's conflict detection in AGENTS.md could be more explicit about the entry path for "I disagree with X".

4. **Checkpoint granularity inside capability intent batches** — currently confirmed batches are written to `confirmed_data` as whole batches. If a session ends mid-batch (user confirmed 3 of 5 intents in batch 2), those 3 confirmations are not individually persisted. Fine-grained per-intent checkpointing would be more resilient.

5. **Prototype mode contracts** — mentioned in Planner but not fully specified. A lightweight contract variant that explicitly skips typechecks and coverage for time-boxed exploration sessions, then gets converted to full contracts or discarded.

6. **The README is written for someone adopting GADP cold.** It may need a shorter "TL;DR" section at the very top for developers who just cloned the repo and want to know if this is worth reading in 30 seconds.

---

## How to continue

Read the files from the repo, then propose and implement improvements one at a time. The owner will validate each change before the next one is made — the same discipline the protocol itself enforces.

Start by fetching:
- `https://raw.githubusercontent.com/syncandsolve/gadp-product-builder/main/AGENTS.md`
- `https://raw.githubusercontent.com/syncandsolve/gadp-product-builder/main/README.md`

Then propose what you want to improve, explain the change and why, and wait for approval before generating anything.
