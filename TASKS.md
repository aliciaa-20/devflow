# DevFlow
## Product
DevFlow is an agentic, context-aware code review assistant for developers working in unfamiliar or evolving codebases.
### Core Problem
Developers reviewing or modifying a change in an unfamiliar codebase must manually gather context across source code, tests, documentation, dependencies, and repository history before they can confidently assess the change.
This fragmented process increases review time and the risk of missed defects, regressions, security issues, and test gaps.
### Core Idea
DevFlow accepts a repository and a developer change, reconstructs the relevant technical and historical context, and presents it as a visual, evidence-backed Change Impact Map. 
DevFlow is repository-agnostic and should not depend on a specific project, technology stack, or repository structure.
### Tagline
From unfamiliar code to confident change.
---
# Primary User
A developer who needs to review or modify a change in a codebase they do not fully understand.
The developer provides a repository and describes the change they are considering.
---
# Core Workflow
```text
REPOSITORY + DEVELOPER CHANGE
        ↓
INGEST REPOSITORY
        ↓
INVESTIGATE
        ↓
RECONSTRUCT CONTEXT
        ↓
MAP IMPACT
        ↓
ASSESS RISK
        ↓
SYNTHESIZE EVIDENCE
        ↓
CHANGE IMPACT MAP
        ↓
RECOMMENDATIONS
        ↓
OPTIONAL BOB RESOLUTION
        ↓
TEST
        ↓
VALIDATE

⸻

Primary Output

Change Impact Map

The primary output must be visual and immediately understandable.

The map should show the relationship between a developer’s change and relevant repository context.

Potential node types:

* Change
* File
* Component
* Test
* Documentation
* Dependency
* Issue
* Pull Request
* Commit

Potential relationship types:

* modifies
* depends_on
* tested_by
* documented_by
* introduced_by
* fixes
* related_to
* impacts

The visualization should allow the user to understand:

1. What the change affects
2. Why those artifacts are relevant
3. What historical or technical context matters
4. Where risks exist
5. What evidence supports the finding

⸻

Evidence Requirement

DevFlow must distinguish between:

* Direct repository evidence
* Derived relationships
* AI inference

The system must not fabricate:

* Repository history
* Issues
* Pull requests
* Commits
* Relationships
* Findings
* Test results

Important findings should reference identifiable repository evidence whenever possible.

If evidence is unavailable, DevFlow should clearly indicate that the conclusion is an inference or that evidence was not found.

⸻

Development Principles

1. Build vertically.
2. Complete and validate the current phase before starting the next.
3. Do not implement future phases prematurely.
4. Prefer simple implementations over unnecessary complexity.
5. Keep the system understandable to a solo developer.
6. Do not add dependencies without a clear reason.
7. Preserve existing functionality.
8. Test completed functionality.
9. Never commit credentials, API keys, tokens, secrets, or personal information.
10. Do not fabricate evidence.
11. Human approval is required before potentially destructive changes.
12. Prioritize a reliable working demo over feature count.
13. Every major feature must contribute to the core DevFlow workflow.
14. IBM technologies should be used because they provide meaningful functionality, not merely to increase the number of IBM products used.
15. Keep the architecture modular enough that individual components can be replaced or improved.
16. Prefer deterministic repository evidence over unsupported AI assumptions.
17. Make important AI-generated conclusions traceable to their supporting evidence.
18. Keep the final workflow understandable within a short live demonstration.

⸻

PHASE 0

Foundation

Status: COMPLETE

Goal

Create a clean, runnable DevFlow project foundation.

Tasks

* Define initial project structure
* Define initial architecture
* Select implementation stack
* Create application entry point
* Create configuration structure
* Set up testing
* Confirm local execution

Acceptance Criteria

* DevFlow runs locally.
* Tests can be executed.
* Project structure is documented.
* No credentials or external secrets are required.
* The application has a clear entry point for future DevFlow functionality.

⸻

PHASE 1

Repository + Change Input

Status: COMPLETE

Goal

Allow a developer to provide a repository and describe the change they want to review or implement.

Primary MVP input:

- Public GitHub repository URL
- Developer change description

Example:

Repository:
https://github.com/example/project

Change:
"Refactor authentication session handling."

Tasks

* Define repository input model
* Accept a public GitHub repository URL
* Validate the repository URL
* Accept a developer change description
* Support changed files when available
* Support branch, commit, or pull request references when available
* Validate input
* Normalize the repository reference
* Normalize the developer change into an internal representation
* Keep repository-specific assumptions out of the core pipeline

Acceptance Criteria

DevFlow can accept:

1. A public GitHub repository URL
2. A developer change description

and represent both in a structured form for investigation.

The system must not require the developer to manually identify every affected file.

DevFlow must treat the supplied repository as an input rather than relying on a hard-coded project.

⸻

PHASE 2

Repository Ingestion + Context Reconstruction

Status: COMPLETE

Goal

Retrieve and inspect the supplied repository and reconstruct the repository context relevant to the developer change.

Tasks

* Retrieve the supplied repository
* Handle repository retrieval failures clearly
* Identify repository structure
* Identify application entry points
* Identify relevant source files
* Identify relevant components
* Identify relevant tests
* Identify relevant documentation
* Identify relevant dependencies
* Identify relevant configuration
* Identify available Git metadata
* Record reasons for relevance
* Produce structured repository context
* Preserve repository identity and source references throughout the workflow

Acceptance Criteria

Given:

- A supported repository URL
- A developer change

DevFlow can retrieve and inspect the repository and produce relevant repository context with evidence and reasons for relevance.

Each important context item should answer:

WHAT is relevant?
WHY is it relevant?
WHAT evidence supports this?

DevFlow must not contain hard-coded assumptions about a particular repository's structure, files, components, or technology stack.

If repository retrieval fails, DevFlow must report the failure clearly rather than producing fabricated analysis.

⸻

PHASE 3

Historical Context

Status: COMPLETE

Goal

Determine whether repository history contains context that could affect the developer’s decision.

Tasks

* Inspect available Git history
* Identify relevant commits
* Identify relevant issues when available
* Identify relevant pull requests when available
* Identify previous fixes
* Connect historical evidence to relevant artifacts
* Distinguish evidence from inference

Acceptance Criteria

DevFlow can explain historically relevant context when supported by repository evidence.

Historical findings must identify the source of the evidence.

If historical information cannot be established reliably, DevFlow must not invent it.

⸻

PHASE 4

Impact Analysis

Status: BLOCKED

Goal

Determine what the proposed change could affect.

Tasks

* Analyze affected files
* Analyze affected components
* Analyze dependencies
* Analyze affected tests
* Analyze documentation impact
* Identify potential downstream effects
* Produce structured impact findings

Acceptance Criteria

Each meaningful impact finding identifies:

* Affected artifact
* Relationship to the change
* Potential impact
* Supporting evidence
* Confidence or evidence strength where appropriate

⸻

PHASE 5

Risk Analysis

Status: BLOCKED

Goal

Identify and prioritize risks associated with the change.

Tasks

* Define risk model
* Identify code risks
* Identify regression risks
* Identify test gaps
* Identify security-relevant risks
* Identify dependency risks
* Identify historically relevant risks
* Assign severity
* Attach evidence
* Generate recommendations

Acceptance Criteria

Each significant risk contains:

* Severity
* Explanation
* Affected artifacts
* Supporting evidence
* Recommended action

Risk severity must be based on identifiable evidence or clearly labeled inference.

⸻

PHASE 6

Change Impact Map

Status: BLOCKED

Goal

Create the primary visual output of DevFlow.

Tasks

* Define graph data model
* Render the change as the central node
* Render relevant repository artifacts
* Render relationships
* Visually distinguish important findings
* Display risk information
* Allow inspection of evidence
* Provide summary information
* Keep the visualization understandable
* Support focusing on important relationships

Acceptance Criteria

A user can understand the major impact relationships and risks within seconds.

A user can inspect the evidence supporting an important relationship or finding.

The graph must be generated from structured DevFlow data rather than being a purely decorative visualization.

⸻

PHASE 7

Developer Report

Status: BLOCKED

Goal

Provide a concise explanation alongside the visual map.

Tasks

* Generate change summary
* Generate context summary
* Generate impact summary
* Generate risk summary
* Display evidence
* Display recommendations
* Provide clear next actions
* Connect report findings to graph nodes

Acceptance Criteria

The developer can move from:

Finding
    ↓
Evidence
    ↓
Impact
    ↓
Recommendation

without manually searching the repository.

⸻

PHASE 8

Bob Resolution

Status: BLOCKED

Goal

Allow IBM Bob to investigate and resolve an approved finding.

Tasks

* Define resolution request
* Pass relevant context to Bob
* Ask Bob to investigate the finding
* Generate proposed fix
* Require human approval
* Apply approved fix
* Generate or update tests
* Run validation
* Report modified files

Acceptance Criteria

Bob can resolve a selected finding while minimizing unrelated changes.

The user can see:

* What Bob changed
* Why Bob changed it
* Which tests were added or modified
* Which tests were executed
* Whether validation succeeded

⸻

PHASE 9

Validation

Status: BLOCKED

Goal

Verify that the resolution actually addresses the identified problem.

Tasks

* Run relevant tests
* Run regression tests
* Detect failures
* Re-evaluate relevant context
* Update risk status
* Generate final validation result

Acceptance Criteria

DevFlow clearly reports:

* Passed tests
* Failed tests
* Resolved risks
* Remaining risks
* Final status

The final result must be based on actual validation results.

⸻

PHASE 10

Agentic Workflow

Status: BLOCKED

Goal

Use IBM Bob’s agentic capabilities to coordinate the DevFlow investigation and resolution workflow.

Tasks

* Define investigation workflow
* Define specialized responsibilities
* Use parallel investigation where useful
* Use DevFlow skills
* Use DevFlow modes
* Coordinate findings
* Avoid redundant investigation
* Track workflow state
* Preserve evidence throughout the workflow

Acceptance Criteria

The workflow demonstrates meaningful multi-step agentic behavior rather than simply using Bob for code generation.

⸻

PHASE 11

Optional IBM Integration

Status: OPTIONAL

IBM watsonx Orchestrate

Evaluate whether watsonx Orchestrate improves workflow coordination.

Possible use:

Context Discovery
        ↓
Parallel Investigation
        ↓
Evidence Synthesis
        ↓
Risk Analysis
        ↓
Bob Resolution
        ↓
Validation

Only implement Orchestrate if it provides meaningful value to this workflow.

Do not add it solely to increase the number of IBM technologies used.

⸻

IBM Granite / watsonx.ai

Evaluate whether Granite or watsonx.ai improves a clearly defined part of DevFlow.

Potential areas include:

* Evidence classification
* Finding prioritization
* Risk synthesis
* Context summarization
* Confidence assessment

Only implement it if it provides meaningful value.

Do not add it solely to increase the number of IBM technologies used.

⸻

PHASE 12

Measurement

Status: BLOCKED

Goal

Demonstrate measurable practical value.

Tasks

* Define manual baseline workflow
* Measure manual context-gathering effort
* Measure DevFlow-assisted effort
* Measure relevant context discovered
* Measure meaningful risks identified
* Measure manual steps reduced
* Record evaluation methodology
* Record actual results

Acceptance Criteria

The final submission contains evidence of practical improvement.

Never invent metrics.

Clearly distinguish measured results from estimates.

⸻

PHASE 13

Demo

Status: BLOCKED

Goal

Create a reliable, visually compelling end-to-end demonstration.

Demo Sequence

1. Developer presents a change.
2. DevFlow begins investigation.
3. Relevant context is reconstructed.
4. The Change Impact Map appears.
5. Important relationships are highlighted.
6. Historical or technical evidence is surfaced.
7. A meaningful risk is identified.
8. Supporting evidence is displayed.
9. The developer chooses whether to resolve the finding.
10. Bob investigates the approved finding.
11. Bob proposes and applies the approved resolution.
12. Tests run.
13. DevFlow updates the impact and risk state.
14. Final validation status is displayed.

Acceptance Criteria

The complete workflow can be demonstrated reliably.

The primary value of DevFlow should be understandable within approximately 30 seconds.

The demo should show a meaningful before-and-after state.

⸻

PHASE 14

Submission

Status: BLOCKED

Tasks

* Finalize README
* Document architecture
* Document setup
* Document IBM technology usage
* Document evaluation methodology
* Document limitations
* Save relevant Bob task-session summaries
* Capture required screenshots
* Verify no secrets are committed
* Test clean setup
* Test final workflow
* Rehearse final demo

Acceptance Criteria

The repository is:

* Documented
* Reproducible
* Secure
* Demonstrable
* Ready for submission

⸻

Bob Execution Rules

Before every implementation task:

1. Read AGENTS.md.
2. Read TASKS.md.
3. Identify the current active task.
4. Inspect only the context needed for that task.
5. State the intended implementation approach before significant changes.
6. Implement only the requested task.
7. Run relevant tests.
8. Report files changed.
9. Report tests performed.
10. Update TASKS.md when the task is genuinely complete.
11. Do not claim a task is complete unless its acceptance criteria are satisfied.
12. Do not fabricate test results or implementation status.

Never start a blocked phase.

Never implement future phases without explicit approval.