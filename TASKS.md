# DevFlow Task Plan

## Product

**DevFlow**

**Tagline:** From unfamiliar code to confident change.

DevFlow is an agentic, context-aware code review and change-impact assistant
for developers working in unfamiliar or evolving codebases.

The primary product output is the **Change Impact Map**.

The long-term workflow is:

```text
Repository + Developer Change
        ↓
Repository Ingestion
        ↓
Context Reconstruction
        ↓
Historical Context
        ↓
Impact Analysis
        ↓
Risk Analysis
        ↓
Change Impact Map
        ↓
Developer Report
        ↓
Human Decision
        ↓
Approved Resolution
        ↓
IBM Bob
        ↓
Tests
        ↓
Validation
        ↓
Updated Risk / Final Status
```

---

# Current Status

| Phase | Area | Status |
|---|---|---|
| 0 | Foundation | COMPLETE |
| 1 | Repository + Change Input | COMPLETE |
| 2 | Repository Ingestion + Context Reconstruction | COMPLETE |
| 3 | Historical Context | COMPLETE |
| 4 | Impact Analysis | COMPLETE |
| 5 | Risk Analysis | COMPLETE |
| 6 | Change Impact Map | COMPLETE |
| 7 | Developer Report | COMPLETE |
| 8 | Bob Resolution | COMPLETE (human-gated vertical slice) |
| 9 | Validation | COMPLETE (deterministic, DevFlow-owned) |
| 10 | Agentic Workflow | PARTIAL (Bob modes/skills + generated investigation prompt) |
| 11 | watsonx Integration | COMPLETE (Granite priority judge, live) |
| 12 | Measurement | IN PROGRESS |
| 13 | Demo | SCRIPTED (docs/DEMO.md); rehearsal pending |
| 14 | Submission | IN PROGRESS |

Status must reflect verified implementation, not merely the existence of
source files.

---

# P0: Phase 8, Bob Resolution

## Goal

Allow a developer to select a meaningful finding from the Change Impact Map
or Developer Report and initiate a controlled, human-approved resolution
workflow using IBM Bob.

## Required workflow

```text
Finding
   ↓
Inspect evidence
   ↓
Developer chooses "Resolve"
   ↓
Human approval
   ↓
Resolution request created
   ↓
Relevant context/evidence passed to Bob
   ↓
Bob investigates
   ↓
Bob proposes focused fix
   ↓
Human approval
   ↓
Fix applied
   ↓
Tests generated/updated
   ↓
Tests executed
   ↓
Validation result
   ↓
Risk status updated
```

## Tasks

- [ ] Define a structured resolution request model.
- [ ] Define the minimum context required for resolution.
- [ ] Include finding ID and supporting evidence.
- [ ] Include affected artifacts.
- [ ] Include relevant risk information.
- [ ] Include relevant historical/context information where useful.
- [ ] Define a human approval boundary before modifications.
- [ ] Define how Bob receives the resolution request.
- [ ] Implement Bob investigation workflow.
- [ ] Implement proposed-fix representation.
- [ ] Require approval before applying a potentially destructive change.
- [ ] Apply approved changes.
- [ ] Generate or update relevant tests.
- [ ] Run relevant tests.
- [ ] Record modified files.
- [ ] Record why the files were changed.
- [ ] Record tests added/modified.
- [ ] Record tests executed.
- [ ] Return a structured resolution result to DevFlow.
- [ ] Preserve evidence throughout the workflow.
- [ ] Add tests for the resolution workflow.

## Acceptance Criteria

A developer can select a finding and initiate resolution.

The resolution request contains enough evidence and context for Bob to
investigate without forcing the user to manually reconstruct the issue.

Bob can investigate the selected finding.

Bob proposes a focused resolution.

Human approval is required before the fix is applied.

The resolution minimizes unrelated changes.

The user can see:

- What Bob changed
- Why Bob changed it
- Which files changed
- Which tests were added or modified
- Which tests were executed
- Whether validation succeeded

## Scope guard

Do not implement the complete autonomous agentic workflow in Phase 8.

First build one reliable end-to-end resolution vertical slice.

---

# P0: Phase 9, Validation

## Goal

Verify that an approved resolution actually addresses the identified problem.

## Tasks

- [ ] Define validation result model.
- [ ] Run targeted tests.
- [ ] Run regression tests.
- [ ] Capture actual command/results.
- [ ] Detect failures.
- [ ] Re-evaluate affected findings.
- [ ] Update risk status.
- [ ] Distinguish resolved risks from remaining risks.
- [ ] Produce final validation result.
- [ ] Add deterministic tests for validation behavior.

## Acceptance Criteria

DevFlow reports:

- Passed tests
- Failed tests
- Resolved risks
- Remaining risks
- Final status

No validation result may be fabricated.

---

# P1: Phase 10, Agentic Workflow

## Goal

Use IBM Bob's agentic capabilities to make the investigation/resolution
workflow meaningfully multi-step.

This should demonstrate more than simple code generation.

## Candidate workflow

```text
Selected Finding
       ↓
Context Preparation
       ↓
Parallel Investigation
   ┌───┼────┐
   ↓   ↓    ↓
Code Test Security
Analysis Analysis Analysis
   └───┼────┘
       ↓
Evidence Synthesis
       ↓
Resolution Proposal
       ↓
Human Approval
       ↓
Implementation
       ↓
Validation
       ↓
Final Result
```

## Tasks

- [ ] Define workflow state.
- [ ] Define investigation responsibilities.
- [ ] Identify useful parallel work.
- [ ] Avoid duplicate investigation.
- [ ] Reuse existing DevFlow structured evidence.
- [ ] Use appropriate Bob skills/modes.
- [ ] Coordinate investigation results.
- [ ] Preserve evidence through every stage.
- [ ] Implement meaningful multi-step agent behavior.
- [ ] Capture Bob task-session evidence.

## Acceptance Criteria

The demonstrated Bob workflow performs meaningful multi-step investigation
and resolution rather than acting as a generic code generator.

---

# P1: Phase 11, watsonx Integration

## Goal

Integrate IBM watsonx where it provides genuine product value.

This phase is intentionally not a checklist of IBM products. The integration
must solve a real DevFlow problem.

## Candidate A: watsonx Orchestrate

Potential responsibility:

```text
Context Discovery
        ↓
Parallel Investigation
        ↓
Evidence Synthesis
        ↓
Risk / Finding Prioritization
        ↓
Bob Resolution
        ↓
Validation
```

Potential benefits:

- workflow coordination
- state management
- routing between specialized responsibilities
- agent/tool coordination

## Candidate B: watsonx.ai / Granite

Potential responsibility:

- evidence classification
- finding prioritization
- risk synthesis
- context summarization
- confidence assessment

## Tasks

- [ ] Identify one concrete problem suitable for watsonx.
- [ ] Define input contract.
- [ ] Define output contract.
- [ ] Define where it enters the existing pipeline.
- [ ] Compare against deterministic/local alternatives.
- [ ] Implement only the highest-value integration.
- [ ] Handle API/authentication configuration securely.
- [ ] Add failure/fallback behavior.
- [ ] Add tests where practical.
- [ ] Demonstrate the integration live.
- [ ] Document why the IBM service is used.

## Acceptance Criteria

The watsonx integration:

1. performs a real product responsibility,
2. consumes real DevFlow data,
3. produces an output used by the workflow,
4. has a clear failure path,
5. is securely configured,
6. can be demonstrated in the final workflow.

---

# P1: Phase 12, Measurement

## Goal

Demonstrate measurable practical value.

## Tasks

- [ ] Define manual baseline workflow.
- [ ] Measure manual context-gathering effort.
- [ ] Measure DevFlow-assisted effort.
- [ ] Measure relevant context discovered.
- [ ] Measure meaningful risks identified.
- [ ] Measure manual steps reduced.
- [ ] Define evaluation scenario.
- [ ] Record actual results.
- [ ] Document methodology.

## Rules

Never invent metrics.

Clearly label:

- measured results
- calculated results
- estimates
- qualitative observations

---

# P1: End-to-End Demo

## Goal

Create a reliable, short demonstration showing the product's actual value.

## Target demo

```text
1. Developer presents a change.
2. DevFlow investigates the repository.
3. Context is reconstructed.
4. Change Impact Map appears.
5. Important relationships are highlighted.
6. Evidence and risk are inspected.
7. Developer selects a meaningful finding.
8. Developer approves resolution.
9. Bob investigates.
10. Bob proposes a focused fix.
11. Developer approves.
12. Fix is applied.
13. Tests run.
14. Validation result appears.
15. Risk state updates.
16. Final result is shown.
```

## Tasks

- [ ] Select a compelling demo repository/scenario.
- [ ] Ensure deterministic reproducibility.
- [ ] Ensure the core analysis works.
- [ ] Ensure the Bob workflow works.
- [ ] Ensure watsonx workflow works.
- [ ] Ensure validation works.
- [ ] Prepare before/after state.
- [ ] Prepare evidence.
- [ ] Rehearse failure paths.
- [ ] Keep the core value understandable within approximately 30 seconds.

---

# P2: Submission

## Tasks

- [ ] Final README.
- [ ] Architecture documentation.
- [ ] Setup documentation.
- [ ] IBM technology usage documentation.
- [ ] watsonx integration explanation.
- [ ] Bob workflow explanation.
- [ ] Evaluation methodology.
- [ ] Measured results.
- [ ] Limitations.
- [ ] Save required Bob task-session summaries.
- [ ] Capture required screenshots.
- [ ] Verify no credentials/secrets are committed.
- [ ] Test clean setup.
- [ ] Test complete workflow.
- [ ] Rehearse final presentation.

---

# Development Rules

## Vertical development

Complete and validate one meaningful capability before starting another.

## Evidence first

Repository facts must come from repository evidence.

AI inference must be distinguished from observed facts.

## Repository agnostic

Do not hard-code assumptions about a specific repository, framework, language,
or directory structure.

## Scope control

Do not refactor unrelated code.

Do not redesign working components without a demonstrated reason.

Do not add dependencies without a clear reason.

## Security

Never commit:

- credentials
- API keys
- tokens
- passwords
- private keys
- `.env` secrets

## Human approval

Potentially destructive or repository-modifying resolution actions require
explicit human approval.

## Testing

Do not claim tests passed without actually running them.

Do not weaken or delete tests simply to make the suite pass.

## IBM integration

Use IBM technologies because they provide meaningful functionality.

Do not add IBM products solely to increase the technology count.

---

# Current Next Action

**Phases 8, 9 and 11 are implemented and verified.**

Remaining, in priority order:

1. Bob IDE task-session screenshots into `bob_sessions/` (submission
   deliverable, currently unmet).
2. Run one real Bob resolution end to end against `risk:0:code`.
3. Frontend rework to match the CLI's presentation quality.
4. Measurement capture and demo rehearsal (`docs/DEMO.md`).

Before coding:

1. Inspect the current finding/report/map models.
2. Inspect the existing server/API boundary.
3. Inspect Bob skills/modes and existing Bob session structure.
4. Determine the safest resolution request shape.
5. Determine how the selected finding can be passed to Bob.
6. Produce an implementation plan.
7. Identify files and tests that will change.
8. Implement only the approved Phase 8 slice.
