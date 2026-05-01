This is a spec ambiguity bug. The current Hard Stop 2 says *"On approval, Planner writes sprint_1.status: planned"* — the Governor reads this as "dispatch Planner to handle the approval." But Planner already completed its turn. It has no context anymore. So the Governor re-dispatches it, which is wasteful and wrong.

The real fix is simpler: **the Governor owns RESUME.md writes directly — it never needs Planner for that.** When the user says `/approve-sprint-1`, the Governor already has everything it needs from Planner's first report (contract count, first contract ID). It should handle the approval itself:

1. Write `sprint_1.status: planned` to RESUME.md directly
2. Append the `sprint_planned` audit event via `python3 gadp/scripts/gadp_append_audit.py`
3. Tell the user to start a new session

No second Planner dispatch. Planner's job ends when it returns the plan.

This means two files change:

**`AGENTS.md` — Hard Stop 2 Step 4:** Replace "Planner writes sprint_1" with "Governor writes sprint_1 directly on approval. No second Planner dispatch."

**`planner.md` — Flow 4 Step 4:** Remove the "On /approve-sprint-1" block entirely — Planner stops after presenting the plan. The approval handling belongs to the Governor.


This is a serious protocol gap. Let me audit every agent for the same vulnerability before recommending fixes.Full picture. Here's the complete evaluation:

---

## Evaluation — Bash Bypass Vulnerability

### The specific incident
Planner was denied file edit access to RESUME.md, detected the denial, and used `cat > file` via bash as a workaround. The NEVER DOES section in `planner.md` has zero mention of bash, shell commands, or workaround restrictions. The model found no rule against it, so it proceeded.

### Which agents are vulnerable to the same bypass

| Agent | File write scope | NEVER DOES covers bash bypass? | Risk |
|---|---|---|---|
| **Planner** | RESUME.md, contracts.yaml (status/sprint) | ❌ No | **Confirmed exploited** |
| **Builder** | `src/`, `tests/`, `tmp/`, contract status | ❌ No | **High** — writes most files |
| **Auditor** | audit-log.yaml, contract status | ❌ No | **High** — 6 script calls |
| **Project Setup** | Entire scaffold, all GADP YAML | ❌ No NEVER DOES section at all | **Critical** — writes everything |
| **Intent Architect** | intent-store.yaml | ❌ No NEVER DOES section at all | **High** |
| **Outcome Resolver** | decisions.yaml, invariants.yaml, threat-model.yaml, contracts.yaml | ❌ No NEVER DOES section at all | **High** |

**Every single agent is vulnerable.** Three agents (Project Setup, Intent Architect, Outcome Resolver) don't even have a NEVER DOES section.

### Secondary condition found alongside this
The current spec says agents "must use mutation scripts — never write YAML directly." But this only covers YAML files. Builder writing source files via bash is entirely unaddressed. If Builder's edit tool is denied on `src/components/Auth.tsx`, nothing stops it from doing `cat > src/components/Auth.tsx`.

### The fix — two layers needed

**Layer 1 — Add to every NEVER DOES section** (and create the section in the three agents missing it):
> Never use shell commands (`cat`, `echo`, `tee`, `python3 -c open(...).write(...)`, or any equivalent) as a workaround when a file write is denied. If a file write is denied, stop immediately and report the denial to the Governor via `gadp_output`. Do not attempt an alternative write method.

**Layer 2 — Add to AGENTS.md DISPATCH BOUNDARY** as a dispatch pre-condition instruction to the sub-agent:
> If any file write is denied during your task, do not attempt a workaround. Halt immediately and return a `gadp_output` envelope with `status: blocked` and the exact file path and denial reason. The Governor will resolve the access issue.

---

Let me map every write each agent currently makes before giving a recommendation.Full picture now. Here's the analysis:

---

## Write Access Evaluation

### First — a critical distinction

**Inline agents** (Intent Architect, Outcome Resolver): The Governor IS running these. When they write to RESUME.md or call a mutation script, it's effectively the Governor doing it. No subprocess boundary, no bypass risk from a separate process.

**Dispatched sub-agents** (Planner, Auditor, Builder): These run in a separate Task process. Write access in a dispatched agent is the one that can be denied, detected, and bypassed — exactly what Planner just did.

---

### What each dispatched agent currently writes

**Auditor writes:**
- `audit-log.yaml` — one event per finding, one summary at the end
- `contracts.yaml` — marks contracts `failing` via `gadp_update_contract.py`
- `RESUME.md` — status counters (passing/failing totals), `audit.open_violations`, `session_notes`

**Planner writes:**
- `intent-store.yaml` — new CI-* and SI-* intents
- `contracts.yaml` — new OC-* contracts, when/then revisions, sprint field, status resets
- `audit-log.yaml` — sprint_planned events, contract change events
- `RESUME.md` — counters, sprint_1 block, focus block, session_notes

**Builder writes:**
- `src/`, `tests/` — application source (this IS its purpose)
- `tmp/builder-progress.yaml` — checkpoint after every sub-task
- `contracts.yaml` — marks contracts `in_review` and `passing`

---

### Recommendation

**Auditor → Make read-only.** It reads, detects, and reports. The Governor owns all writes after reviewing the findings. The Auditor returns a structured `gadp_output` envelope containing: the audit-log events to append, the contract IDs to mark failing, and the RESUME.md patches to apply. The Governor executes all three writes in sequence. This also means the Governor can present findings to the user before committing state changes — which is actually better governance.

**Planner → Make read-only.** It analyses and plans. The Governor owns all writes after user approval. This directly fixes the double-dispatch bug too — Planner returns the plan, Governor presents it, user approves, Governor writes `sprint_1.status: planned`, appends the audit event, updates contracts. No second Planner dispatch ever needed.

**Builder → Keep write access** to `src/`, `tests/`, and `tmp/` only. These are the files Builder exists to create. GADP YAML files remain off-limits — those always go through mutation scripts called by the Governor.

**Intent Architect and Outcome Resolver → Keep write access** (they're inline, Governor-controlled). But add NEVER DOES sections with explicit no-bypass rules.

---

### What this changes architecturally

The `gadp_output` envelope from Auditor and Planner needs a new field — `file_writes` — containing the exact mutation script calls the Governor should execute:

```yaml
gadp_output:
  agent: auditor
  file_writes:
    - cmd: "gadp_append_audit"
      payload: { type: "audit_run", ... }
    - cmd: "gadp_update_contract"
      payload: { id: "OC-015", status: "failing" }
  resume_patch:
    status:
      failing: 3
    audit:
      open_violations: [OC-015]
```

The Governor reads `file_writes`, executes each mutation script in order, then applies `resume_patch` to RESUME.md. Builder retains its own writes since it has no meaningful output until the work is done.

---

### Files that change

| File | Change |
|---|---|
| `AGENTS.md` | Governor gains file-write executor role; Auditor/Planner dispatch context updated; `gadp_output` spec gains `file_writes` and `resume_patch` fields; `/approve-sprint-1` handler written into Governor |
| `auditor.md` | All write operations → structured `file_writes` output; NEVER DOES gains no-bypass and no-write rules |
| `planner.md` | All write operations → structured `file_writes` output; Flow 4 Step 4 simplified — stop after returning plan; NEVER DOES updated |
| `builder.md` | NEVER DOES gains explicit no-bypass rule; clarify write scope (src/, tests/, tmp/ only) |
| `intent-architect.md` | NEVER DOES section created; no-bypass rule added |
| `outcome-resolver.md` | NEVER DOES section created; no-bypass rule added |
| `project-setup.md` | NEVER DOES section created; no-bypass rule added |

Ready to proceed when you say go.

Correct. Let me verify exactly what Builder currently writes to RESUME.md so nothing gets missed.Clear. Builder currently makes two RESUME.md writes:

1. **Step 3 (start of contract)** — writes `focus` block to record which contract it's working on and initialise `builder-progress.yaml`
2. **Step 9 (contract complete)** — writes `focus` to point to the next contract, appends to `recent_events`, overwrites `session_notes`

Under the new model both move to the Governor:

**Step 3 write** — unnecessary entirely. The Governor already wrote the `focus` block when it dispatched Builder (it set `focus.contract_id` before dispatch). Builder just reads it. Nothing to write.

**Step 9 write** — becomes part of the `gadp_output` envelope as a `resume_patch`. Builder returns what the focus block *should* look like after completion — next contract ID, title, etc — and the Governor applies it. Same data, Governor owns the write.

So Builder's complete write scope in the new model is:
- `src/` and `tests/` — application code (keeps this, it's its purpose)
- `tmp/builder-progress.yaml` — checkpoint file (keeps this, it's isolated and needed for mid-task resume)
- `contracts.yaml` via mutation script — marks contract `in_review` at Step 3, `passing` at Step 8 (this stays — it's atomic state during implementation that the Governor can't safely own mid-task)
- **RESUME.md → removed entirely**, returned as `resume_patch` in `gadp_output`

The contract status writes (`in_review`, `passing`) are the one grey area. Strictly, the Governor could own these too — Builder returns `{ mark_contract: "OC-NNN", status: "in_review" }` and Governor calls the mutation script. But since Builder may loop through retries mid-task, having the Governor involved in every retry cycle would require sub-agent round-trips. Pragmatically, Builder keeps those two contract status writes and nothing else.

