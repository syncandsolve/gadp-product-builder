# GADP — Session Handoff
## Version 3.2 — Updated after the v3.2 improvement session

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
gadp-handoff.md                   ← This file — design rationale and improvement history
gadp/
  agents/
    intent-architect.md
    outcome-resolver.md
    project-setup.md
    builder.md
    auditor.md
    planner.md
  config/
    framework-globs.yaml
    qi-mandatory.yaml
    invariant-defaults.yaml
  scripts/                        ← canonical script implementations (added in v3.1)
    gadp_init_project.py
    gadp_update_contract.py
    gadp_append_contract.py
    gadp_append_intent.py
    gadp_update_intent_status.py
    gadp_append_audit.py
    gadp_validate.py
```

---

## How we got here — the full arc

### v2 — Three-prompt manual-paste workflow

GADP v2 was three enormous prompts the user pasted one at a time. Prompt A (intent-architect), Prompt B (outcome-resolver), Prompt C (project-setup). Each was ~1500 lines of embedded instructions, reference tables, format rules, and YAML schemas. No resume, no orchestration, no development phase governance.

### v3.0 — Governor + six agents

v3.0 replaced the three prompts with `AGENTS.md` (the Governor) and six sub-agent files in `gadp/agents/`. The Governor reads `RESUME.md`, detects project state, dispatches the right agent, and communicates in plain language. Key additions: `RESUME.md` checkpoint system, Builder + Auditor + Planner for the development phase, `/approve-decisions` gate, `/approve-deploy-prod` gate.

What was preserved from v2: the intent store, outcome contracts, STRIDE threat modelling, auto-detectable invariants, the audit log, Sprint 0 separation, data lifecycle and deletion contracts.

### v3.1 — Eight targeted fixes from real-world use

Eight specific problems identified in real-world use were analysed rigorously and addressed with targeted structural changes. Full details in the v3.1 section below.

### v3.2 — Setup agent execution model corrected

One problem identified after v3.1 shipped: the DISPATCH BOUNDARY added in v3.1 to stop the Governor from running agent steps inline did not work for setup agents, because there is no tooling in the environment that actually enforces a stop. The v3.1 fix was correct for development agents (Builder, Auditor, Planner) where a real subprocess or Task tool provides process isolation — but for setup agents it left the model in a contradictory state: instructed to stop and wait for an external response that was never going to arrive. Full details in the v3.2 section below.

---

## What was changed in v3.1 — comprehensive synopsis

### Problem 1: Hardcoded output formatting was fighting the TUI

**What was wrong.** The three init agents (intent-architect, outcome-resolver, project-setup) had approximately 40 hardcoded display templates embedded in the prompt text: blockquote cards, `===` section dividers, inline markdown tables. These consumed tokens on every dispatch, produced output the opencode/claudecode TUI could not render cleanly, and coupled presentation logic to agent logic. Every agent output had two natural components — structured data (what was decided) and narrative explanation (why) — that were entangled.

**What changed.** All hardcoded display blocks removed from all three init agent files. Replaced with a single `gadp_output` YAML envelope that every agent output that requires user review now follows:

```yaml
gadp_output:
  agent: "[agent name]"
  checkpoint: "[STEP-ID or PHASE-ID]"
  narrative: |
    [Plain prose — what happened and what the user needs to decide.]
  data:
    type: "[typed payload type]"
    payload: [structured YAML — rendered natively by TUI]
  action_required: "[confirm | approve | choose | none]"
  prompt: "[Single question — one sentence]"
```

Fourteen typed payload types defined: `intent_batch`, `design_tokens`, `screen_inventory`, `contract_summary`, `architecture_decisions`, `api_design`, `entity_model`, `data_lifecycle`, `threat_summary`, `sprint_plan`, `verification_result`, `status_report`. Each type has an explicit field schema.

The Governor now reads the `narrative` field and presents it in plain language, while passing `payload` directly to the TUI for native rendering. The Governor never reformats payload data. All agents produce envelopes — Builder, Auditor, Planner, all three init agents.

**Files changed:** AGENTS.md (READING SUB-AGENT OUTPUT section), intent-architect.md (all Steps), outcome-resolver.md (all Phases), project-setup.md (Phase 0, all S0-T0xx summaries, Sprint 0 verification), builder.md (Step 9), auditor.md (final report), planner.md (all Flows).

---

### Problem 2: Governor was executing sub-agent steps inline

**What was wrong.** AGENTS.md said "dispatch that sub-agent" but provided no mechanism to actually stop execution and wait. The model continued inline as the sub-agent. This was especially damaging for the three init agents — the Governor would start Phase 1, finish Phase 2, proceed through Phase 3, and never return to Governor mode. The user's notes about sub-agents not spawning and the Governor starting to execute steps itself were a direct result of this.

**What changed.** A formal **DISPATCH BOUNDARY** added to AGENTS.md. When dispatching any sub-agent, the Governor executes exactly three steps and then stops:

- **Step A** — Write checkpoint to RESUME.md (`phase_progress.active_agent`, `status: in_progress`)
- **Step B** — Output the dispatch block as the final content of this turn
- **Step C** — Stop. Do not begin executing the agent's steps

When sub-agent output arrives in the next turn, the Governor reads the `gadp_output` envelope, presents narrative to the user, renders payload via TUI, updates RESUME.md checkpoint, clears `active_agent`, and asks for user response if `action_required` is not `none`.

An `OPERATING MODE` section was added to the top of every sub-agent file explicitly stating: "You run as a sub-agent. When you reach a step that requires user input, output a `gadp_output` envelope and stop."

**Files changed:** AGENTS.md (DISPATCH BOUNDARY section), all six agent files (OPERATING MODE section).

---

### Problem 3: Phase 3 and Phase 4 output was collapsing to a single line

**What was wrong.** Outcome Resolver Phase 3 (Data Architecture) and Phase 4 (API Design) had no explicit user-review gate and no structured output format. The model would generate entity models and API designs inline, sometimes serialising the YAML without proper indentation or collapsing it entirely. Both phases also had no confirm gate — the model would derive and immediately continue without giving the user a chance to review.

**What changed.** Phase 3 split into two separate phases with individual confirm gates:

- **Phase 3A** — Entity model with `entity_model` payload. Fields, types, indexes, relationships, sensitivity flags. Confirm gate: "Does this data model match your design?"
- **Phase 3B** — Data lifecycle with `data_lifecycle` payload. Retention periods, deletion triggers, cascade rules, backup strategy. Confirm gate: "Does the retention plan match your legal obligations?"

Phase 4 (API Design) now has an explicit `api_design` payload with a confirm gate. The payload covers auth strategy, RBAC, endpoint list with auth requirements and rate limits, error contract, and API lifecycle rules.

The structured payload types force the model to write each field explicitly — it cannot compress them into a single line because the schema requires distinct named fields at each level.

**Files changed:** outcome-resolver.md (Phase 3 split into 3A/3B, Phase 4 redesigned). Checkpoint IDs updated throughout: `PHASE-3` → `PHASE-3A` + `PHASE-3B`.

---

### Problem 4: Python mutation scripts were generated fresh per project, causing variance and bugs

**What was wrong.** Project Setup S0-T001 said "generate these 6 Python scripts" based on a high-level description. Every project got a slightly different implementation. Scripts had bugs. The model would improvise different function signatures, different error handling, different path resolution. Script errors were reported across multiple real sessions.

**What changed.** All seven mutation scripts moved to `gadp/scripts/` as canonical, version-controlled implementations. They are now part of the GADP repository — not generated per project.

Project Setup S0-T001 now copies them: `cp ./gadp/scripts/gadp_*.py ./scripts/`. If `./gadp/scripts/` is missing, the agent checks for pre-generated scripts at the project root and moves them. If neither is found, it hard stops with a clear message.

A new script `gadp_init_project.py` was added — it generates all nine GADP YAML files (intent-store, design-language, contracts, audit-log, decisions, invariants, threat-model, openapi, diagram stub) from a `project-init.json` config file. This directly addresses the "can I place pre-generated scripts at the root and use them for a new project" question — yes, combined with a config file, you can bootstrap a new project without running the full Governor + Intent Architect flow.

The canonical scripts are precise and tested:
- **gadp_update_contract.py** — separates mutable fields (status, blocked_on, implemented_at), restricted fields (sprint — warns that /approve-decisions must have happened), and immutable fields (title, given, when, then — hard rejected). Atomic write via temp file + `os.replace`.
- **gadp_append_contract.py** — validates all required fields, rejects unknown fields (typo protection), validates OC-NNN format, validates test_file path prefix, updates type-specific counts.
- **gadp_append_intent.py** — handles CI-*, SI-*, QI-* with type-specific validation. Security intents must have `security_surface: true`. Extension/future intents must have `deferral_reason` and `inclusion_trigger`.
- **gadp_update_intent_status.py** — accepts only `id` and `status`. Per-type status enums. Rejects any other field with an explicit message.
- **gadp_append_audit.py** — seventeen named event types, each with required field validation. Timestamp injected automatically and rejected if caller includes it. Normalised key order.
- **gadp_validate.py** — validates all seven GADP files independently, then cross-file consistency: `project_id` matches, invariant IDs declared in decisions exist in invariants.yaml, T-* IDs in contracts exist in threat-model.yaml. Coloured PASS/FAIL/SKIP/WARN output.
- **gadp_init_project.py** — generates all project YAML files from config, runs gadp_validate.py as self-test before exiting.

**Files changed:** gadp/scripts/ (all 7 new files), project-setup.md (S0-T001 completely rewritten), AGENTS.md (file_map schema updated with `gadp_scripts` and `tmp_dir` entries).

---

### Problem 5: Mid-phase resume lost model reasoning context

**What was wrong.** `RESUME.md confirmed_data` captured user-approved values but not the model's reasoning. If a session ended after the regulatory exposure was classified as GDPR (a non-trivial inference), a new session would re-derive it — probably correctly, but not guaranteed. The `assumptions` block in intent-store.yaml was written only once at phase completion, not incrementally.

**What changed.** A `derived_context` sub-block added to `phase_progress.confirmed_data` in RESUME.md. It is append-only — new entries are added, existing entries are never overwritten.

Agents write to `derived_context` after each non-trivial reasoning step:
- Intent Architect writes after STEP-1 (`product_type_rationale`), STEP-2A (`blast_rationale`), STEP-3 (`competitor_confidence`), STEP-4 batches (`capability_derivation_notes` per intent), STEP-5 (`regulatory_exposure_rationale`), STEP-6A (`design_token_source`, `design_direction_words`, `token_derivation_notes`)
- Outcome Resolver writes after PHASE-1.5 (`direction_selection_rationale`) and PHASE-2 (`stack_rationale` per dimension)

A resuming agent reads `derived_context` before re-deriving anything. If an entry exists for a field, it is used as the starting point rather than re-derived from scratch.

**Files changed:** AGENTS.md (RESUME.MD SCHEMA — `confirmed_data.derived_context` block with full comments), intent-architect.md (CHECKPOINT PROTOCOL — derived_context writes at each step), outcome-resolver.md (CHECKPOINT PROTOCOL — derived_context writes at PHASE-1.5 and PHASE-2).

---

### Problem 6: File references were inconsistent across agent files

**What was wrong.** Several agents referenced the wrong path for T-* threat IDs. `decisions.yaml` contains only a `threat_model_ref` pointer, but agents would search there for T-* data. The dispatch context in AGENTS.md did not include `threat_model_path`. The `file_map` schema was missing `gadp_scripts` and `tmp_dir`. Builder's `relevant_files` list in dispatch wasn't pre-populated.

**What changed.**
- `threat_model_path: "./decisions/threat-model.yaml"` added to the standard dispatch input block in AGENTS.md
- `gadp_scripts: "./gadp/scripts/"`, `tmp_dir: "./tmp/"`, `builder_progress: "./tmp/builder-progress.yaml"` added to `file_map` schema
- Builder dispatch `relevant_files` pre-populated with the standard set
- Explicit note added to Builder Step 1, Auditor Step 1, and Planner CORE RULES: "T-* threat IDs live exclusively in `./decisions/threat-model.yaml`. `decisions.yaml` contains only a `threat_model_ref` pointer."
- Same note added to WHAT THE BUILDER/AUDITOR/PLANNER NEVER DOES in each respective file

**Files changed:** AGENTS.md (dispatch block, file_map schema), builder.md (Step 1, NEVER DOES), auditor.md (Step 1, NEVER DOES), planner.md (CORE RULES, NEVER DOES).

---

### Problem 7: No hard stops between setup phases and implementation phases

**What was wrong.** The Governor would complete project setup tasks S0-T001 through S0-T010 and then dispatch Project Setup for Sprint 0 verification in the same session. Or Sprint 0 verification would pass and Builder would be dispatched for Sprint 1 in the same session. Context windows were deep and saturated at these points. In one reported case, a sub-agent started implementing S-01 tasks immediately after finishing S-00, blowing up its context window.

**What changed.** Three enforced hard stops added to AGENTS.md:

**HARD STOP 1 — Before Sprint 0 verification:** If `setup_progress.last_completed_task == S0-T010` AND `sprint_0.status == not_run` AND the current session ran any S0-T0xx task, the Governor refuses to dispatch Sprint 0 verification. It tells the user to start a new session and updates `focus.next_action`. If the session opened fresh into an already-completed setup state, the stop does not apply.

**HARD STOP 2 — Before Sprint 1 implementation:** If Sprint 0 just passed AND the current session ran Sprint 0 verification steps, the Planner produces the sprint plan and the Governor waits for `/approve-sprint-1`. On approval, it tells the user to start a new session before Builder is dispatched.

**HARD STOP 3 — Builder context pressure:** After three contracts pass in a session, soft recommendation for 1-2 remaining contracts, hard stop for more than 2 remaining.

Project Setup S0-T010 now explicitly writes to `focus.next_action` and `session_notes` with language the Governor will detect. The Planner's Flow 4 completion envelope now includes `session_boundary_required: true` when HARD STOP 2 applies.

**Files changed:** AGENTS.md (HARD STOPS section — entire new section), project-setup.md (S0-T010 step — strengthened session boundary language and HARD STOP envelope), planner.md (Flow 4 — `session_boundary_required` field in completion envelope).

---

### Problem 8: Sub-agent progress was not persisted, causing resume failures

**What was wrong.** The reported scenario: OC-001 implemented, test failing, session quit, resume. Governor dispatches Builder. Builder does not check if OC-001's test was passing — it sees `status: in_review` and starts implementing OC-002. The Builder had marked `in_review` before quitting but had no record of what work was done or what state the test was in.

**What changed.**

**Builder now writes `./tmp/builder-progress.yaml` after every atomic sub-task.** Not at the end. Not as a batch. After each: schema migration, repository layer, service layer, API handler, test run (with passing/failing counts and exact error text), invariant checks, contract marked passing. The file is overwritten at the start of each new contract (status: starting) and updated in-place as sub-tasks complete.

The progress file is **not gitignored** — it must survive session ends. The `.gitignore` pattern is `tmp/*` + `!tmp/builder-progress.yaml`.

**Governor now runs PRE-DISPATCH BUILDER VALIDATION before every Builder dispatch.** Four cases handled:
- Progress file exists, matches current contract, `session_status: test_failing` → do NOT dispatch Builder immediately, dispatch with explicit instruction to re-run test first
- Progress file exists, matches current contract, `session_status: in_progress` → dispatch with instruction to run test before adding new code
- Progress file exists, `session_status: complete`, but contracts.yaml still shows `in_review` → the marking step failed last session; fix the status before dispatching
- Progress file missing, contract is `in_review` → session interrupted before any write; dispatch with instruction to check test before adding code

**Auditor reads `./tmp/builder-progress.yaml` in Step 1** and notes mid-flight contract state in its report envelope (`builder_progress_note` field).

**Files changed:** AGENTS.md (PRE-DISPATCH BUILDER VALIDATION — entire new section), builder.md (OPERATING MODE, RESUMPTION, Step 3, Steps 4/5 atomic writes, Step 6 test result write, Step 8 complete write, NEVER DOES), auditor.md (Step 1 — reads progress file, report envelope — `builder_progress_note`), project-setup.md (S0-T001 — creates `./tmp/` directory, S0-T003 — gitignore rules for builder-progress.yaml).

---

## What was changed in v3.2

### Problem 9: DISPATCH BOUNDARY did not work for setup agents

**What was wrong.** The v3.1 DISPATCH BOUNDARY ("Step C — Stop. Do not continue. Do not begin executing the agent's steps yourself.") was observed failing for setup agents in two separate new-project sessions. The Governor would issue the DISPATCHING block for Intent Architect, then immediately continue executing Intent Architect's steps inline in the same turn — the opposite of what the instruction required.

The root cause: the stop in the DISPATCH BOUNDARY is purely aspirational. There is no tool call, no subprocess, no process boundary that actually enforces it. The model reads `intent-architect.md` to "operate as that agent" and then keeps going, because nothing in the environment creates a real pause. The v3.1 fix worked on the correct diagnosis (Governor running agent steps inline) but applied the wrong remedy (a text instruction to stop, with no enforcement mechanism).

This failure mode is specific to setup agents. Development agents (Builder, Auditor, Planner) dispatch correctly because Claude Code's `Task` tool or an equivalent parallel sub-agent mechanism provides genuine process isolation — the DISPATCHING block hands off to a real subprocess, and there is an actual boundary the model cannot cross. That path remains unchanged and correct.

**The deeper insight.** Setup agents and development agents have fundamentally different execution characteristics:

- Setup agents run once per project. They are interactive conversations — eight confirmation steps in Intent Architect, seven phases with an `/approve-decisions` gate in Outcome Resolver. There is no engineering work being isolated; there is a back-and-forth dialogue. The dispatch-and-wait model adds overhead with no payoff.
- Development agents run repeatedly across sprints. Builder implements contracts with real tool calls, file writes, test runs, and sub-task state. True isolation prevents context bleed between contracts. Dispatch-and-wait is the right model here.

Applying the dispatch protocol uniformly across all six agents confused the model about what it was supposed to be doing during setup: it was instructed to stop and wait for an external agent response that was never going to arrive.

**What changed.** Two execution modes formalised:

**Inline execution** — for Intent Architect, Outcome Resolver, and Project Setup. The Governor reads the agent file and executes it directly. No DISPATCHING block is issued. No stop-and-wait. The `gadp_output` envelope format is preserved for all user communication. Checkpoints still write to RESUME.md after every confirmed step. All resumption, validation, and checkpoint protocol rules in each agent file still apply in full.

**Dispatch protocol** — for Builder, Auditor, and Planner. Full DISPATCH BOUNDARY, DISPATCHING block, stop-and-wait. Unchanged from v3.1.

The Governor persona (IDENTITY section, COMMUNICATION RULES, authority model) is untouched. The change is exclusively in execution mechanics.

**Files changed:**

| File | Change |
|---|---|
| `AGENTS.md` | SUB-AGENT REGISTRY split into two labeled tables (setup inline / development dispatch). STATE DETECTION action lines for INTENT_ARCHITECT, OUTCOME_RESOLVER, PROJECT_SETUP updated from "Dispatch X" to "Execute X inline". MID_PHASE resume logic split by agent type. BOOTSTRAP Step 4 updated. DISPATCH section scoped to development agents with note. DISPATCH BOUNDARY scoped with note. New INLINE EXECUTION section added. WHAT THE GOVERNOR NEVER DOES: two new items added. |
| `gadp/agents/intent-architect.md` | OPERATING MODE rewritten: inline execution, no DISPATCHING block, explicit prohibition on skipping confirmation gates. |
| `gadp/agents/outcome-resolver.md` | OPERATING MODE rewritten: same pattern, "phases" language. |
| `gadp/agents/project-setup.md` | OPERATING MODE rewritten: same pattern, "tasks" language. |
| All 7 agent files + `gadp_init_project.py` | Version tag bumped: `3.1` → `3.2`. |
| `README.md` | "How it works" updated to describe the two agent groups. Version bumped. |
| `gadp-handoff.md` | This entry added. Version bumped. |

**What was not changed:** builder.md, auditor.md, planner.md (beyond version tag), all config files, all scripts (beyond version strings in gadp_init_project.py), all YAML schemas embedded in agent files (beyond gadp_version strings).

---

## Key design decisions to preserve

These were established in v3.0 and remain unchanged:

- **Governor never implements.** It orchestrates and communicates. Never writes code, never touches contracts directly.
- **Auditor owns counters and audit log.** No other agent updates `status` counters in RESUME.md or writes to `audit-log.yaml`.
- **Builder owns contract status.** Only Builder marks contracts `passing`. Only Auditor marks them `failing` (regression).
- **Planner owns governance changes.** Only Planner modifies `decisions.yaml`, `invariants.yaml`, or contract `when/then` fields — always after `/approve-decisions`.
- **INV-DQ-001 is canonical.** All design token enforcement. INV-U-* is retired — never generate it.
- **INV-P-005 is intentionally null.** The only invariant where `detection_command: null` is correct — N+1 queries cannot be detected via grep.
- **Full-stack pairs never split.** UI contract and its API contract always in the same sprint.
- **sprint1_chain is the minimum viable journey.** Set by Intent Architect Step 6C, enforced by Outcome Resolver Phase 6, verified by Project Setup S0-T010 and the First Run Standard gate.
- **`threat-model.yaml` does not require `/approve-decisions`.** Threat model updates are operational, not architectural. Only `decisions.yaml` and `invariants.yaml` require the gate.
- **`./decisions/decisions.yaml` never contains T-* IDs.** It contains `threat_model_ref: "./decisions/threat-model.yaml"` as a pointer. All T-* data lives in `threat-model.yaml` exclusively.

Added in v3.1:

- **`./tmp/builder-progress.yaml` is not gitignored.** It must survive session ends. The `tmp/*` + `!tmp/builder-progress.yaml` gitignore pattern is the correct implementation.
- **Canonical scripts live in `./gadp/scripts/`.** They are copied to `./scripts/` at S0-T001. If a script errors, check the canonical version before attempting inline fixes.
- **`derived_context` in RESUME.md is append-only.** New entries are added, existing entries are never overwritten. A resuming agent reads it before re-deriving anything.
- **`gadp_output` envelopes are the only user-facing output format.** Agents never produce freeform presentation blocks. The Governor never reformats payload data — it passes it to the TUI as-is.
- **Session boundaries are enforced by the Governor, not advisory.** The three hard stops are state-machine checks, not notes in a prompt.

Added in v3.2:

- **Setup agents execute inline. Development agents use dispatch.** Intent Architect, Outcome Resolver, and Project Setup are executed directly by the Governor — no DISPATCHING block, no stop-and-wait. Builder, Auditor, and Planner use the full dispatch protocol with process isolation.
- **The DISPATCH BOUNDARY applies to development agents only.** Do not apply it to setup agents. The enforcement mechanism (Task tool / subprocess) does not exist in the setup context.
- **`gadp_output` envelopes are still required during inline execution.** Inline does not mean freeform. Every user-facing output during setup must follow the envelope format. Every confirmation gate must be observed.

---

## The v3.2 file manifest

Files changed from v3.1:

| File | Change type | Key changes |
|---|---|---|
| `AGENTS.md` | Updated | SUB-AGENT REGISTRY split, STATE DETECTION updated, BOOTSTRAP Step 4 updated, DISPATCH and DISPATCH BOUNDARY scoped, new INLINE EXECUTION section, WHAT NEVER DOES extended |
| `gadp/agents/intent-architect.md` | Updated | OPERATING MODE rewritten for inline execution, version tag |
| `gadp/agents/outcome-resolver.md` | Updated | OPERATING MODE rewritten for inline execution, version tag |
| `gadp/agents/project-setup.md` | Updated | OPERATING MODE rewritten for inline execution, version tag |
| `gadp/agents/builder.md` | Version tag only | No functional changes |
| `gadp/agents/auditor.md` | Version tag only | No functional changes |
| `gadp/agents/planner.md` | Version tag only | No functional changes |
| `gadp/scripts/gadp_init_project.py` | Version strings only | gadp_version "3.1" → "3.2" |
| `README.md` | Updated | "How it works" reflects two agent groups, version bumped |
| `gadp-handoff.md` | Updated | v3.2 entry added, arc updated, design decisions updated, version bumped |

---

## Improvement areas identified but not yet implemented

These were discussed or noted but not addressed. Good candidates for the next round.

1. **`gadp status` shortcut** — a one-liner the Governor recognises that prints current phase, sprint, passing/failing counts, and the next action. Useful for re-orienting without triggering a full session start.

2. **Sub-agent output logs in `./gadp/logs/`** — one completion record per dispatch. Governor reads logs to construct status reports rather than re-reading all YAML on every session start. Partially superseded by `./tmp/builder-progress.yaml` for Builder state, but a broader log would reduce context usage on mature projects.

3. **Per-intent checkpoint granularity inside capability batches** — currently confirmed batches are written as whole batches. If a session ends mid-batch (user confirmed 3 of 5 intents in batch 2), those 3 are not individually persisted. The `derived_context.capability_derivation_notes` added in v3.1 partially addresses this, but fine-grained per-intent confirmation tracking would be more resilient.

4. **Prototype mode contracts** — mentioned in Planner Flow 6 but not fully specified. A lightweight contract variant that explicitly skips typechecks and coverage for time-boxed exploration, then converts to full contracts or gets discarded. Needs a clear entry path and governance rules to prevent prototype mode from becoming a backdoor around invariants.

5. **Explicit disagreement flow** — currently when a user wants to change a derived decision, the path is: user describes change → Governor detects conflict → Planner does impact analysis → `/approve-decisions`. The Governor's CONFLICT DETECTION section handles this, but a dedicated "I disagree with X" flow that prompts the user through the Planner more smoothly would reduce friction.

6. **`project-init.json` schema documentation** — the schema is documented in `gadp_init_project.py`'s docstring, but a standalone `gadp/config/project-init-schema.json` with JSON Schema validation would be cleaner and allow IDE autocompletion when writing the config file.

---

## How to continue

Clone the repo, read the files, then propose and implement improvements one at a time. The owner will validate each change before the next one is made.

```bash
git clone https://github.com/syncandsolve/gadp-product-builder.git
```

Start by reading `AGENTS.md` and `gadp-handoff.md` in full. Then propose what you want to improve, explain the change and why, and wait for approval before generating anything.
