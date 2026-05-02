# GADP v3.3 — System Scrutiny and Change Plan
## Prepared against commit: main branch, May 2026

---

## PART 1 — RIGOROUS SCRUTINY OF THE CURRENT SYSTEM

This section documents what the system actually is, independent of what any single file claims it to be. Every finding is cross-referenced across files.

---

### Finding 1 — Hard Stop 2 Is a Broken Spec (Confirmed Bug)

**Location:** `AGENTS.md` — HARD STOPS section, Hard Stop 2, Step 4  
**Severity:** High — causes incorrect behaviour on every Sprint 1 approval

The text reads:
> *"On approval, Planner writes sprint_1.status: planned to RESUME.md (see Planner Flow 4). Then tell the user..."*

This is structurally broken. Here is what actually happens in the dispatch model:

1. Governor dispatches Planner via Task tool invocation (DISPATCH BOUNDARY Step B)
2. Planner executes Flow 4 Steps 1–3, produces the plan, outputs `gadp_output` with `action_required: approve`, and stops — the subprocess ends
3. Governor presents the plan. User says `/approve-sprint-1`
4. The Governor now needs the approval handled — but Planner is gone. The Governor must dispatch Planner *again*

The second dispatch is the bug. Planner's Flow 4 Step 4 says it writes `sprint_1.status: planned`, `focus`, and `session_notes` to RESUME.md — but a second dispatch starts Planner cold. The second Planner gets no context about which plan was approved. It would need the Governor to pass the full plan context in the dispatch block, which AGENTS.md does not specify anywhere.

In the best case the Governor re-derives from scratch and produces a slightly different result. In the worst case it loops, stalls, or fails silently. The v3.3 changelog even says this specific problem was addressed — but the AGENTS.md text still describes Planner as the writer.

**Cross-check against `planner.md` Flow 4 Step 4:** Confirmed — Step 4 writes `sprint_1` block, `focus`, and `session_notes` directly to RESUME.md. No mention that the Governor owns these writes.

**The correct spec:** Governor owns these writes. It has everything it needs from Planner's FLOW4-PLAN output: `contract_count`, `first_contract_id`, `sprint`, `goal`. No second Planner dispatch is needed or correct.

---

### Finding 2 — opencode.json and Agent Spec Files Are Mutually Contradictory

**Location:** `opencode.json` vs `auditor.md` (STEP 5, STEP 6) and `planner.md` (FLOW 4 STEP 4)  
**Severity:** Critical — the permission layer and the behavioural spec contradict each other

`opencode.json` sets `"edit": "deny"` for both Auditor and Planner:

```json
"gadp-auditor": { "permission": { "edit": "deny", "bash": "allow" } }
"gadp-planner": { "permission": { "edit": "deny", "bash": "allow" } }
```

But `auditor.md` STEP 5 says:
> *"Write these exact counts to RESUME.md status block. This is the Auditor's write — no other agent updates these counters."*

And STEP 6 says the Auditor calls mutation scripts directly via bash:
> `echo '...' | python3 gadp/scripts/gadp_append_audit.py`

And `planner.md` Flow 4 Step 4 says Planner writes the sprint_1 block to RESUME.md directly.

The contradiction has two layers:

**Layer A — Edit tool vs. bash:** `"edit": "deny"` blocks the file-edit tool. It does NOT block bash. So `echo > RESUME.md` via bash still works. The permission setting partially enforces read-only intent but leaves the bash pathway wide open.

**Layer B — Script calls via bash:** The mutation scripts (`gadp_append_audit.py`, `gadp_update_contract.py`) are called via bash. `"edit": "deny"` does not block these — bash is explicitly allowed. So Auditor can still write to `audit-log.yaml` and `contracts.yaml` via scripts. This is actually CORRECT for the intended workflow — but the spec for RESUME.md writes is broken.

**Net result:** The opencode.json signals intent toward "Auditor and Planner are read-only for direct file writes" but the agent spec files haven't been updated to reflect this. The agents are told to write directly; the permission layer partially but not fully prevents it; and there's no protocol for the Governor to handle the writes instead.

---

### Finding 3 — Bash Bypass Vulnerability Is Unaddressed in All Agent Specs

**Location:** All six agent files — NEVER DOES sections (or lack thereof)  
**Severity:** High — confirmed exploitable (Planner exploit documented in feedback.md)

The feedback.md documents a confirmed case: Planner was denied a file edit, detected the denial, and used `cat > file` via bash as a workaround. Nothing in any NEVER DOES section prohibits this.

Cross-checking all six agents:

| Agent | Has NEVER DOES | Prohibits bash bypass | Risk |
|---|---|---|---|
| Builder | Yes | No | High — writes most application files |
| Auditor | Yes | No | Medium — bash allowed, scripts callable |
| Planner | Yes | No | Medium — edit:deny but bash open |
| Intent Architect | **No** | N/A | Lower — inline, but gap exists |
| Outcome Resolver | **No** | N/A | Lower — inline, but gap exists |
| Project Setup | **No** | N/A | High — writes everything during setup |

Three agents have no NEVER DOES section at all. The missing section in `project-setup.md` is the highest-risk gap — Project Setup writes the entire project scaffold and has access to every file during its run.

The fix is two-part:
1. Add a bash bypass prohibition to every NEVER DOES section
2. Add NEVER DOES sections to the three agents missing them

The prohibition text needs to cover: `cat >`, `echo >`, `tee`, `python3 -c open(...).write(...)`, and any equivalent shell pattern that writes file content when an edit tool denial would otherwise stop work.

---

### Finding 4 — Builder STEP 9 RESUME.md Write Is Architecturally Inconsistent

**Location:** `builder.md` — STEP 9  
**Severity:** Medium — creates a write scope inconsistency

Builder STEP 9 writes the focus block to RESUME.md — pointing to the next contract. The AUTHORITY MODEL in AGENTS.md says:
> `RESUME.md — Governor — Every session`

Builder writing RESUME.md is technically within tolerated scope (AGENTS.md also says "Never writes ./tmp/builder-progress.yaml — that is Builder's exclusive write," implying Builder does write other things). But the STEP 9 focus write is functionally a Governor responsibility — the Governor chooses the next contract, not Builder.

More concretely: if Builder writes the wrong `next_action` or an incorrect `focus.contract_id`, the Governor reads it at the next session start and dispatches the wrong contract without questioning it.

The feedback correctly identifies that Builder's Step 9 RESUME.md write should become a `resume_patch` in `gadp_output`, with the Governor applying it. This also makes Builder's output auditable — the Governor can validate the next-contract pointer before committing it to disk.

**Counterpoint:** Builder STEP 3 also writes RESUME.md (`focus.implementation_target`). This one has a different character — it's setting a pre-implementation checkpoint that survives session interruptions. If Builder crashes mid-contract, the Governor reads `focus.implementation_target` to know which files were in scope. This write arguably IS justified in Builder. The feedback suggests the Governor sets it pre-dispatch, which is fine if the Governor knows the files ahead of time — but often it doesn't.

**Recommendation:** Step 9 write → `resume_patch` in gadp_output. Step 3 write → keep in Builder (needed for crash recovery before any impl begins).

---

### Finding 5 — gadp_output Envelope Spec Is Missing Fields

**Location:** `AGENTS.md` — READING SUB-AGENT OUTPUT section  
**Severity:** Medium — protocol gap for the new architecture

The current `gadp_output` envelope spec:

```yaml
gadp_output:
  agent:
  checkpoint:
  narrative:
  data:
    type:
    payload:
  action_required:
  prompt:
```

It has no `file_writes` field, no `resume_patch` field, and no `checkpoint_writes` field. The Governor's READING SUB-AGENT OUTPUT section has five handling rules — none of them address executing mutation script calls or applying RESUME.md patches.

Once Auditor and Planner are made read-only (returning structured write instructions instead of executing writes), the Governor has no protocol for what to do with them. This is a spec gap that would cause the Governor to ignore or mishandle the new fields.

---

### Finding 6 — gadp-handoff.md Is Stale Relative to v3.3

**Location:** `gadp-handoff.md`  
**Severity:** Low — documentation gap, not functional

The v3.3 section documents four changes: dispatch mechanism, resume state, session boundaries, scripts unification. It does not mention:

- `opencode.json` — added in v3.3 or after, enabling per-agent model routing and permission scoping
- `OPENCODE_SETUP.md` — new file
- The `edit: deny` permission design for Auditor and Planner

The directory listing in `gadp-handoff.md` does not include `opencode.json` or `OPENCODE_SETUP.md`. Any future session reading the handoff to understand the system state will miss the permission architecture entirely.

---

### Finding 7 — Auditor Status Counter Write vs. opencode.json

**Location:** `auditor.md` STEP 5, `opencode.json`, `AGENTS.md` AUTHORITY MODEL  
**Severity:** Medium — inconsistent between spec and implementation intent

AGENTS.md AUTHORITY MODEL says:
> `RESUME.md — Governor — Every session`

Auditor STEP 5 says Auditor writes `status` counters to RESUME.md. This is the one case where a sub-agent is supposed to write RESUME.md. But `"edit": "deny"` in opencode.json blocks this if done via the edit tool.

Auditor CAN still write RESUME.md via bash (e.g. `python3 -c "..."` or a sed command). But this is exactly the bash bypass pattern the feedback identifies as a vulnerability.

The cleanest resolution: Auditor returns the counter values in a `resume_patch` field in `gadp_output`. Governor applies them. Governor already owns RESUME.md — this gives it full control over the counters rather than relying on Auditor to write them correctly in an external session.

---

### Finding 8 — README.md Does Not Reflect opencode.json

**Location:** `README.md` — Setup section  
**Severity:** Low — onboarding documentation gap

The setup section says: *"Open the project in your AI coding tool — Claude Code, opencode, or any tool that reads AGENTS.md."* It does not mention that `opencode.json` is required for opencode to route sub-agents to the correct models and enforce the correct permissions.

A user setting up with opencode following the README would get AGENTS.md dispatching sub-agents to the default model, no model specialisation, and no permission restrictions — none of the v3.3 architecture benefits.

---

## PART 2 — EVALUATION OF FEEDBACK.MD PROPOSALS

The feedback proposes three distinct interventions. Each is evaluated on correctness, completeness, and implementation scope.

---

### Proposal A — Fix the Hard Stop 2 Double-Dispatch Bug

**Verdict: Correct. Implement as written, with one extension.**

The proposed fix is right: Governor owns the RESUME.md writes post-approval. No second Planner dispatch. Two files change.

**Extension:** Planner's FLOW4-PLAN `gadp_output` payload currently returns `contract_count` and groups, but not the contract IDs needed for `gadp_update_contract.py` calls. The Governor needs these IDs to update sprint assignments post-approval. The gadp_output payload must be extended to include contract IDs alongside titles.

Specifically, the FLOW4-PLAN payload needs:
```yaml
contracts_to_assign:
  - { id: "OC-001", sprint: 1 }
  - { id: "OC-002", sprint: 1 }
```

Without this, the Governor cannot execute the contract sprint-assignment writes that are currently Planner's Step 4 responsibility.

---

### Proposal B — Bash Bypass Rules in NEVER DOES

**Verdict: Correct. Implement in full.**

Every agent needs the prohibition. The three missing NEVER DOES sections (Intent Architect, Outcome Resolver, Project Setup) need to be created and include it.

**Nuance for setup agents:** Intent Architect, Outcome Resolver, and Project Setup run inline as Governor continuations. Technically the Governor IS the AI doing the writes. Adding NEVER DOES sections here is defensive and correct, but the trust model is different — these are not isolated subprocesses. Still, the prohibition is valid: even when running inline, the agent should not use shell workarounds when a file write fails. It should surface the failure to the user.

**Nuance for script calls:** The prohibition must NOT catch legitimate mutation script calls (e.g., `echo '...' | python3 gadp/scripts/gadp_append_audit.py`). The bash bypass prohibition is specifically about using bash to write file content when the edit tool was denied. Script calls through bash are the authorised write pathway. The prohibition text must distinguish between:
- Prohibited: `cat > contracts.yaml`, `echo "..." > RESUME.md`, `tee file.yaml`, writing via Python one-liner
- Allowed: `python3 gadp/scripts/gadp_append_audit.py`, `python3 gadp/scripts/gadp_update_contract.py`

---

### Proposal C — Governor as File-Write Executor (Architectural Change)

**Verdict: Correct in direction. Implement in layers, not all at once.**

The feedback proposes three agent changes:
- Auditor → read-only: return `file_writes` + `resume_patch`
- Planner → read-only: return `file_writes` + `resume_patch`
- Builder → keep write access to `src/`, `tests/`, `tmp/` only

**Layer 1 (Implement now):** Planner Flow 4 and Hard Stop 2 — already required by Proposal A. Planner stops writing RESUME.md on sprint approval. Governor writes it. This is simple because the Governor has all needed data.

**Layer 2 (Implement now):** Auditor RESUME.md status counters. Auditor returns a `resume_patch` with counter values. Governor writes them. This eliminates the Auditor→RESUME.md write that conflicts with `"edit": "deny"` in opencode.json, and reconciles the spec with the permission model.

**Layer 3 (Implement with care):** Auditor audit-log and contract-status writes via mutation scripts. These could stay as direct bash calls (they are not the edit-tool bypass case — they go through authorised scripts). However, if the architecture goal is "Auditor never writes, Governor executes," then the `file_writes` envelope is needed. This adds complexity to the Governor's output-handling protocol. Recommend implementing but flagging as the riskiest change — the Governor must correctly execute multiple script calls in order without Auditor's domain context.

**Layer 4 (Deferred):** Planner Flows 1, 2, 3 (new capability, architecture change, contract revision). These flows are interactive: Planner proposes, user approves mid-flow, Planner then executes. Making Planner read-only here requires either (a) Planner returning all pending writes as a batch with the proposal, before approval — risky because the batch might change based on user feedback; or (b) a two-phase dispatch model where Planner proposes, Governor presents, user approves, Governor dispatches Planner again with the approved state to generate the `file_writes` batch. Option (b) is a significant protocol change. Defer until Flow 4 / Hard Stop 2 fix is stable.

**Builder RESUME.md writes:**
- Step 3 focus write: Keep in Builder. This is the pre-implementation crash-recovery checkpoint. The Governor cannot set `implementation_target` before dispatch because Builder determines the exact files during Step 2.
- Step 9 focus write: Move to `resume_patch` in gadp_output. Governor applies it. This is low-risk and eliminates Builder's need to write RESUME.md after contract completion.

---

## PART 3 — COMPREHENSIVE CHANGE PLAN

Changes are grouped by file, ordered by priority, and described at the edit level (what text replaces what).

---

### CHANGE GROUP 1 — Critical: Fix Hard Stop 2 and Planner Flow 4

**Files:** `AGENTS.md`, `planner.md`  
**Priority:** P0 — fixes confirmed broken behaviour

#### 1.1 — AGENTS.md Hard Stop 2 Step 4

**Current text:**
```
4. On approval, Planner writes sprint_1.status: planned to RESUME.md (see Planner Flow 4). Then tell the user:
```

**Replace with:**
```
4. On /approve-sprint-1, the Governor writes sprint_1 directly to RESUME.md — no second Planner dispatch.
   Extract from the FLOW4-PLAN gadp_output payload:
   - sprint_1.contract_count
   - sprint_1.first_contract_id
   - contracts_to_assign (list of { id, sprint })

   Execute in order:
   a. For each entry in contracts_to_assign:
      echo '{"id": "[OC-NNN]", "sprint": N}' | python3 gadp/scripts/gadp_update_contract.py
   b. echo '{"type": "sprint_planned", "actor": "governor", "sprint": 1,
             "contract_count": N, "goal": "[goal]"}' | python3 gadp/scripts/gadp_append_audit.py
   c. Write to RESUME.md:
      sprint_1:
        status: planned
        contract_count: [N]
        first_contract_id: "[OC-NNN]"
      focus:
        sprint: 1
        contract_id: "[first_contract_id]"
        contract_title: "[title]"
        next_action: "Sprint 1 approved. Begin with [first contract title]."
      session_notes: |
        Sprint 0 passed. Sprint 1 planned and approved — [N] contracts.
        First contract: [title]. Start a new session.

   Then tell the user:
```

#### 1.2 — AGENTS.md WHAT THE GOVERNOR NEVER DOES

Add to the list:
```
- Never dispatches Planner a second time to handle /approve-sprint-[N] — the Governor writes sprint_1, focus, and session_notes directly from the FLOW4-PLAN payload
```

#### 1.3 — planner.md Flow 4 Step 3 — Extend payload

Add `contracts_to_assign` to the FLOW4-PLAN payload:

```yaml
contracts_to_assign:
  - { id: "OC-NNN", title: "[title]", sprint: N }
```

This gives the Governor the contract IDs needed to execute `gadp_update_contract.py` calls post-approval.

#### 1.4 — planner.md Flow 4 Step 4 — Remove Governor's writes

**Current Step 4** executes contract updates, audit log append, and RESUME.md writes.

**New Step 4:** Remove the RESUME.md block entirely (sprint_1, focus, session_notes writes). Keep only:
- Contract sprint-field updates via `gadp_update_contract.py` — BUT move these to the Governor too (per contracts_to_assign in the payload). So Step 4 becomes empty and can be removed.

**Actually:** With `"edit": "deny"` and the Governor owning writes, Planner Flow 4 Step 4 should be eliminated. The FLOW4-PLAN output is the terminal output. The Governor handles everything post-approval. Planner stops at Step 3.

**Revised Step 3 narrative note:** Add to the Step 3 output note:
```
After presenting this plan, Planner's work is complete. 
The Governor handles all writes on /approve-sprint-[N].
Planner does not execute a Step 4. Do not write to any file post-proposal.
```

**Revised FLOW4-COMPLETE:** Remove the FLOW4-COMPLETE gadp_output entirely — it was Planner's end-of-Step-4 report. Planner ends at FLOW4-PLAN. The Governor sends its own message to the user after executing the writes.

#### 1.5 — planner.md WHAT THE PLANNER NEVER DOES

Add:
```
- Never writes sprint_1.status, focus, or session_notes to RESUME.md after /approve-sprint-[N] — that is the Governor's responsibility
- Never dispatches itself or issues a Task tool call — Planner stops after returning gadp_output
```

---

### CHANGE GROUP 2 — Critical: Bash Bypass Prohibition

**Files:** All six agent files  
**Priority:** P0 — closes the confirmed exploit vector

#### 2.1 — Prohibition text (identical across all agents)

Add to every NEVER DOES section:

```
- Never uses shell commands (cat >, echo >, tee, python3 -c open(...).write(...), or any 
  equivalent) to write file content when an edit tool denial would otherwise prevent it. 
  If a file write is denied, stop immediately and report the denial. Do not attempt any 
  alternative write method. The authorised write path — mutation scripts called via bash 
  (e.g., python3 gadp/scripts/gadp_update_contract.py) — is not affected by this rule; 
  script calls remain permitted. Direct file content writes via shell are never permitted 
  as a workaround.
```

#### 2.2 — Create NEVER DOES sections for missing agents

**intent-architect.md** — Add section before the final heading:

```markdown
## WHAT THE INTENT ARCHITECT NEVER DOES

- Never writes files outside the project root
- Never invents capabilities the user did not describe or confirm
- Never produces design-language.yaml before intent-store.yaml is validated and complete
- Never advances past a confirm/approve/choose gate without explicit user response
- Never overwrites existing entries in confirmed_data.derived_context — append only
- Never uses shell commands (cat >, echo >, tee, python3 -c open(...).write(...), or any 
  equivalent) to write file content as a workaround when a file write fails. If a write 
  fails, stop and report it. The authorised mutation scripts remain permitted.
- Never asks the user to fill in a field that can be reasonably derived from prior context
```

**outcome-resolver.md** — Add section:

```markdown
## WHAT THE OUTCOME RESOLVER NEVER DOES

- Never generates contracts, invariants, or OpenAPI before /approve-decisions is received
- Never invents requirements — every decision must have an intent_ref
- Never writes decisions.yaml or invariants.yaml before the single /approve-decisions gate
- Never modifies intent-store.yaml — that file is locked before this agent starts
- Never advances past a phase gate without explicit user response
- Never uses shell commands (cat >, echo >, tee, python3 -c open(...).write(...), or any 
  equivalent) to write file content as a workaround when a file write fails. Stop and report.
- Never produces a partial phase — if a file cannot be written, halt the phase and report
```

**project-setup.md** — Add section:

```markdown
## WHAT PROJECT SETUP NEVER DOES

- Never modifies decisions.yaml or invariants.yaml
- Never skips a task and continues to the next — each task is a hard prerequisite
- Never begins Sprint 0 verification without completing S0-T001 through S0-T010 first
- Never deploys to any environment — that gate belongs to the Governor
- Never cd outside the project root
- Never writes to /tmp or any system path — temporary work goes in ./tmp/ only
- Never uses shell commands (cat >, echo >, tee, python3 -c open(...).write(...), or any 
  equivalent) to write file content as a workaround when a file write fails. If a task 
  step fails to write a file, stop at that step and report the exact error. Authorised 
  mutation scripts remain permitted.
- Never generates a new AGENTS.md — the one in the project root is already correct
- Never creates model routing logic or mode-switching in AGENTS.md
```

---

### CHANGE GROUP 3 — High: Reconcile Auditor with opencode.json

**Files:** `auditor.md`, `AGENTS.md`  
**Priority:** P1 — resolves the spec/permission contradiction

#### 3.1 — auditor.md STEP 5 — Return resume_patch instead of writing directly

**Current text (STEP 5 end):**
```
Write these exact counts to RESUME.md status block. This is the Auditor's write — no other agent updates these counters.
```

**Replace with:**
```
Do NOT write these counts to RESUME.md directly. Return them in the gadp_output envelope 
as resume_patch (see REPORTING TO THE GOVERNOR). The Governor applies the patch.
This is the Auditor's authoritative count — the Governor writes it exactly as returned.
```

#### 3.2 — auditor.md STEP 6 — Clarify script calls remain authorised

Add a note to the top of STEP 6:

```
Mutation scripts (gadp_append_audit.py, gadp_update_contract.py) are called via bash 
as the authorised write pathway. These calls are NOT affected by the bash bypass prohibition.
RESUME.md writes are the exception — those go in resume_patch, not direct writes.
```

#### 3.3 — auditor.md REPORTING — Add resume_patch to both gadp_output formats

**Clean audit output** — add field:
```yaml
  resume_patch:
    status:
      passing: [N]
      in_review: [N]
      failing: [N]
      pending: [N]
      deferred: [N]
      next_audit_after: [passing_count + 5]
      audit_log_event_count: [current count + events added]
    audit:
      last_audit_result: "[clean|violations_found]"
      last_audit_date: "[current ISO-8601]"
      open_violations: []
```

**Violations found output** — same fields, `open_violations` populated.

#### 3.4 — AGENTS.md READING SUB-AGENT OUTPUT — Add resume_patch handling

Add step 5a after current step 4:

```
5a. If the gadp_output includes a resume_patch field: apply it to RESUME.md immediately.
    resume_patch keys map directly to RESUME.md schema paths. Write each key-value pair 
    exactly as returned. Do not interpret or modify the values. This is always the case 
    for Auditor output — the status counters and audit metadata come this way.
```

#### 3.5 — AGENTS.md AUTHORITY MODEL

Update the RESUME.md row:
```
RESUME.md | Governor (directly) and via resume_patch from Auditor/Planner sub-agents | Every session
```

Add a note row:
```
RESUME.md status block | Governor (applying Auditor's resume_patch) | After every Auditor output
```

---

### CHANGE GROUP 4 — High: Builder Step 9 RESUME.md Write

**Files:** `builder.md`  
**Priority:** P1 — eliminates Builder's post-completion RESUME.md write

#### 4.1 — builder.md STEP 9 — Remove direct focus write, add resume_patch to gadp_output

**Current STEP 9** writes focus block to RESUME.md directly and then reports to Governor.

**Change:** Remove the direct RESUME.md writes. Add `resume_patch` to the gadp_output envelope:

```yaml
gadp_output:
  agent: builder
  checkpoint: "[OC-NNN]-complete"
  narrative: |
    [Contract title] is passing. ...
  data:
    type: status_report
    payload:
      contract_id: "[OC-NNN]"
      ...
  resume_patch:
    focus:
      sprint: [N]
      contract_id: "[next pending contract id]"
      contract_title: "[next contract title]"
      intent_ref: "[next contract's intent_ref]"
      contract_path: "./outcomes/contracts.yaml"
      threat_refs: [next contract's threat_refs]
      implementation_target: []
      test_file: "[next contract's test_file]"
      next_action: "Ready to begin [next contract title]."
      blocked_on: null
    recent_events:
      - type: contract_passing
        timestamp: "[ISO-8601]"
        contract_id: "[OC-NNN]"
        note: "[contract title] — implemented and passing."
    session_notes: |
      [One-paragraph summary of what was implemented and what is next.]
  action_required: none
```

Add note to STEP 9: *"Do not write to RESUME.md directly. All RESUME.md updates go in resume_patch for the Governor to apply."*

#### 4.2 — builder.md WHAT THE BUILDER NEVER DOES

Add:
```
- Never writes focus, recent_events, or session_notes to RESUME.md directly — these go in resume_patch in gadp_output
```

---

### CHANGE GROUP 5 — Medium: gadp_output Envelope Spec Update

**Files:** `AGENTS.md`  
**Priority:** P1 — formalises the new fields the Governor must handle

#### 5.1 — Extend gadp_output envelope spec

Add optional fields to the envelope definition:

```yaml
gadp_output:
  agent: "[agent name]"
  checkpoint: "[STEP-ID or PHASE-ID]"
  narrative: |
    [Plain prose — what just happened and what the user needs to decide.]
  data:
    type: "[...]"
    payload: [structured YAML]
  file_writes:                          # Optional — present when agent returns writes for Governor to execute
    - cmd: "[gadp_append_audit | gadp_update_contract | gadp_append_contract | gadp_append_intent]"
      payload: [JSON object to pipe to the script]
  resume_patch:                         # Optional — present when agent returns RESUME.md updates
    [key]: [value]                      # Direct RESUME.md schema path assignments
  action_required: "[confirm | approve | choose | none]"
  prompt: "[Single question — omit if action_required: none]"
```

#### 5.2 — Governor rules for new fields

Add to the "Governor rules for handling envelopes" block:

```
- If file_writes is present: execute each entry in order. For each entry, pipe the payload 
  as JSON to the named script: echo '[payload JSON]' | python3 gadp/scripts/[cmd].py. 
  Execute all file_writes before responding to the user. If any script call fails, stop 
  and tell the user exactly which command failed and with what error.
- If resume_patch is present: write each key-value pair to RESUME.md immediately after 
  executing any file_writes. Do not modify or interpret the values. Apply resume_patch 
  before responding to the user.
```

---

### CHANGE GROUP 6 — Medium: Documentation Updates

**Files:** `gadp-handoff.md`, `README.md`  
**Priority:** P2 — correctness of reference documentation

#### 6.1 — gadp-handoff.md — Update directory listing

Add to the file structure listing:
```
opencode.json                         ← Agent routing, model assignment, permissions (added v3.3)
OPENCODE_SETUP.md                     ← OpenCode configuration guide (added v3.3)
```

#### 6.2 — gadp-handoff.md — Add opencode.json to v3.3 section

Add to the v3.3 section after item 4 (Scripts unification and skills integration):

> **5. OpenCode agent routing and permission model.** `opencode.json` added to the repository root. Defines three hidden sub-agents (`gadp-builder`, `gadp-auditor`, `gadp-planner`) with per-agent model assignment, permission scoping, and `task: deny` to prevent sub-agents spawning sub-agents. Auditor and Planner receive `edit: deny` — consistent with the read-only architecture described above. Builder receives `edit: allow` — it must write application source files. All three receive `bash: allow` — mutation scripts are called via bash. The Governor (running as the primary model) has no opencode.json restrictions — it is the environment operator.

#### 6.3 — README.md — Add opencode.json step

In the Setup section, between Step 3 and Step 4, add:

```markdown
**3a. (OpenCode only) Configure agent routing**

If you are using OpenCode, the `opencode.json` in the repository root configures sub-agent 
model routing and permissions. Edit it to set your preferred models and API provider:

```json
{
  "provider": {
    "nvidia": {
      "options": {
        "baseURL": "https://integrate.api.nvidia.com/v1",
        "apiKey": "YOUR_API_KEY"
      }
    }
  }
}
```

See `OPENCODE_SETUP.md` for model selection guidance and full configuration options.
If you are using Claude Code or another tool, skip this step — `AGENTS.md` is the entry point regardless of environment.
```

---

### CHANGE GROUP 7 — Low: AGENTS.md DISPATCH section clarification

**Files:** `AGENTS.md`  
**Priority:** P3 — minor spec clarity

#### 7.1 — Add explicit note about approval-write ownership

In the DISPATCH section, after the standard dispatch input block, add:

```
When a sub-agent returns gadp_output with action_required: approve and the user approves:
The Governor handles all resulting writes directly. It does NOT dispatch the sub-agent again.
The sub-agent's output already contains everything needed (in payload, file_writes, resume_patch).
The Governor executes file_writes, applies resume_patch, and communicates the result.
```

---

## PART 4 — IMPLEMENTATION SEQUENCE

Changes should be implemented in this order to avoid creating new inconsistencies mid-way:

**Step 1** — Group 2 (bash bypass rules, NEVER DOES sections). Self-contained, no cross-file dependencies.

**Step 2** — Group 1 (Hard Stop 2 + Planner Flow 4). Requires Planner payload extension first, then AGENTS.md Hard Stop 2 rewrite.

**Step 3** — Group 5 (gadp_output envelope spec). Needs to be written before Groups 3 and 4 reference it.

**Step 4** — Groups 3 and 4 in parallel (Auditor resume_patch + Builder Step 9 resume_patch). Both use the envelope spec from Step 3.

**Step 5** — Group 7 (AGENTS.md dispatch clarification). References Groups 1 and 3 being done.

**Step 6** — Group 6 (documentation updates). Should reflect all preceding changes.

---

## PART 5 — WHAT TO DEFER

These items from the feedback are correct in principle but deferred until the above changes are stable:

1. **Planner Flows 1, 2, 3 read-only architecture** — complex mid-conversation approval gates make this non-trivial. The two-phase dispatch model would be required. Defer until Flow 4 changes are validated in real use.

2. **Builder STEP 3 focus write migration** — the pre-implementation crash-recovery checkpoint is justified in Builder. Deferring unless crash recovery in the current model proves unreliable.

3. **Restricting bash further in opencode.json** — mutation scripts need bash. Any bash restriction granular enough to block `cat > file` while allowing `python3 gadp/scripts/...` is environment-specific and fragile. Prompt-level prohibition (Group 2) is the right layer for this.

4. **Full `file_writes` batch for Auditor mutation scripts** — the current model (Auditor calls scripts directly via bash) is technically correct given bash is allowed. The resume_patch change (Group 3) eliminates the RESUME.md write inconsistency. The script calls themselves are not the bypass problem. Full batch-return can wait.

---

## PART 6 — SUMMARY TABLE

| Change | File(s) | Priority | Group | Status |
|---|---|---|---|---|
| Fix Hard Stop 2 — Governor owns approval writes | AGENTS.md | P0 | 1 | Required |
| Extend FLOW4-PLAN payload with contract IDs | planner.md | P0 | 1 | Required |
| Remove Planner Flow 4 Step 4 | planner.md | P0 | 1 | Required |
| Bash bypass prohibition — Builder | builder.md | P0 | 2 | Required |
| Bash bypass prohibition — Auditor | auditor.md | P0 | 2 | Required |
| Bash bypass prohibition — Planner | planner.md | P0 | 2 | Required |
| NEVER DOES section — Intent Architect | intent-architect.md | P0 | 2 | Required |
| NEVER DOES section — Outcome Resolver | outcome-resolver.md | P0 | 2 | Required |
| NEVER DOES section — Project Setup | project-setup.md | P0 | 2 | Required |
| Extend gadp_output envelope spec | AGENTS.md | P1 | 5 | Required |
| Governor file_writes + resume_patch handling | AGENTS.md | P1 | 5 | Required |
| Auditor STEP 5 → resume_patch | auditor.md | P1 | 3 | Required |
| Auditor gadp_output resume_patch fields | auditor.md | P1 | 3 | Required |
| AUTHORITY MODEL update | AGENTS.md | P1 | 3 | Required |
| Builder STEP 9 → resume_patch | builder.md | P1 | 4 | Required |
| Builder NEVER DOES addition | builder.md | P1 | 4 | Required |
| Planner NEVER DOES additions | planner.md | P1 | 1+2 | Required |
| Governor NEVER DOES addition | AGENTS.md | P1 | 1 | Required |
| DISPATCH section approval-write note | AGENTS.md | P3 | 7 | Recommended |
| gadp-handoff.md opencode.json entry | gadp-handoff.md | P2 | 6 | Recommended |
| README.md opencode.json setup step | README.md | P2 | 6 | Recommended |

---

*End of document. Total: 7 change groups, 22 distinct changes across 8 files.*
