# DevFlow Architecture
## 1. Overview
DevFlow is an agentic, context-aware code review assistant for
developers working in unfamiliar or evolving codebases.
DevFlow accepts:
1. A repository
2. A developer change
It investigates the repository, reconstructs relevant technical and
historical context, determines potential impact and risk, and presents
the result as a visual, evidence-backed Change Impact Map.
The primary purpose of DevFlow is to reduce the manual effort required
to understand an unfamiliar codebase before making or reviewing a
change.
The primary output is the Change Impact Map.
DevFlow also maintains a structured representation of the repository
that can optionally be explored through a Repository Knowledge Graph.
The two graphs have intentionally different purposes.
```text
Repository Knowledge Graph
        |
        | answers
        v
"What exists in this codebase?"
        |
        | orientation
        v
Developer understands repository
Change Impact Map
        |
        | answers
        v
"What does my proposed change affect?"
        |
        | focused analysis
        v
Developer understands change

The Repository Knowledge Graph is an optional repository-orientation
feature.

The Change Impact Map is the primary DevFlow experience.

⸻

2. Product Architecture

The high-level DevFlow workflow is:

                    REPOSITORY
                        +
                DEVELOPER CHANGE
                        |
                        v
              +-------------------+
              | Repository Input  |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Repository        |
              | Ingestion         |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Context           |
              | Reconstruction    |
              +---------+---------+
                        |
              +---------+---------+
              |                   |
              v                   v
     +-------------------+  +-------------------+
     | Repository        |  | Historical        |
     | Knowledge Graph   |  | Context           |
     |                   |  |                   |
     | "What's here?"    |  | "What happened?"  |
     +-------------------+  +---------+---------+
                                      |
                         +------------+
                         |
                         v
                +-------------------+
                | Impact Analysis   |
                +---------+---------+
                          |
                          v
                +-------------------+
                | Risk Analysis     |
                +---------+---------+
                          |
                          v
              +-------------------------+
              |   CHANGE IMPACT MAP     |
              |                         |
              |     PRIMARY OUTPUT      |
              +-----------+-------------+
                          |
                          v
                 Recommendations
                          |
                          v
                  Human Decision
                          |
                 +--------+--------+
                 |                 |
                 v                 v
                Stop        Optional Bob
                                  |
                                  v
                             Resolution
                                  |
                                  v
                              Testing
                                  |
                                  v
                             Validation

The workflow is implemented incrementally through the phases defined
in TASKS.md.

⸻

3. Architectural Principles

3.1 Repository Agnostic

DevFlow must work across different:

* repositories
* programming languages
* frameworks
* project structures
* technology stacks

The system must derive information from the supplied repository rather
than relying on hard-coded assumptions.

The pipeline should work conceptually as:

Repository A
    |
    v
Repository Analysis
    |
    v
Structured Context
    |
    v
Impact Analysis
    |
    v
Change Impact Map

The same pipeline should work for Repository B even if its structure
and technology stack are completely different.

⸻

3.2 Evidence First

Important findings should be supported by identifiable repository
evidence.

DevFlow should prefer:

Repository Evidence
        |
        v
Structured Finding
        |
        v
Visual Explanation

rather than:

AI Assumption
        |
        v
Unverified Finding

AI reasoning may supplement repository evidence, but it must not silently
replace it.

⸻

3.3 Structured Intermediate Representations

Each major phase produces structured data that can be consumed by later
phases.

The visualization should not independently rediscover repository
facts.

The intended flow is:

Context
   |
   v
Historical Context
   |
   v
Impact Analysis
   |
   v
Risk Analysis
   |
   v
Change Impact Map

This keeps the architecture modular, testable, and replaceable.

⸻

3.4 Deterministic Analysis Where Possible

Repository facts and structural relationships should be established
using deterministic repository information whenever possible.

Examples include:

* file existence
* imports
* declared dependencies
* test relationships
* configuration references
* Git history
* changed files

AI reasoning may be used where it provides meaningful value, but
AI-generated conclusions must remain distinguishable from direct
repository evidence.

⸻

3.5 Traceable Conclusions

Important findings should allow the developer to answer:

WHAT?
  |
  v
WHY?
  |
  v
EVIDENCE?
  |
  v
CONFIDENCE?
  |
  v
RISK?
  |
  v
RECOMMENDED ACTION?

A developer should be able to move from a graph finding to the evidence
supporting that finding.

⸻

3.6 Change Impact Map as the Primary Output

The Change Impact Map is the primary visual experience of DevFlow.

It should be the first and most prominent graph presented to the
developer after analysis.

The Repository Knowledge Graph is secondary and optional.

⸻

3.7 Repository Knowledge Graph as an Orientation Tool

The Repository Knowledge Graph exists to help developers understand an
unfamiliar codebase.

It answers:

"What is here?"

It should not replace the Change Impact Map.

⸻

3.8 Human Approval

Potentially destructive actions require human approval.

DevFlow should identify and explain findings before any resolution is
attempted.

Bob should not automatically modify a repository as a consequence of
an identified risk.

⸻

4. Phase Architecture

DevFlow is divided into sequential phases.

Phase 1
Repository + Change Input
        |
        v
Phase 2
Repository Ingestion + Context Reconstruction
        |
        v
Phase 3
Historical Context
        |
        v
Phase 4
Impact Analysis
        |
        v
Phase 5
Risk Analysis
        |
        v
Phase 6
Change Impact Map
        |
        v
Phase 7
Developer Report
        |
        v
Phase 8
Optional Bob Resolution
        |
        v
Phase 9
Validation
        |
        v
Phase 10
Agentic Workflow

Optional IBM technologies may be introduced later when they provide
meaningful functionality.

⸻

5. Phase 1: Repository + Change Input

Phase 1 defines the structured input to DevFlow.

The primary MVP input consists of:

Repository URL
Developer Change Description

Additional information may be available:

* changed files
* branch
* commit
* pull request reference

The input layer validates and normalizes the repository and developer
change.

The rest of the system should operate on structured internal models
rather than raw user input.

Conceptually:

User Input
    |
    v
Validation
    |
    v
Normalization
    |
    +------------------+
    |                  |
    v                  v
RepositoryInput    ChangeRequest

The input layer should not perform repository analysis.

⸻

6. Phase 2: Repository Ingestion + Context Reconstruction

Phase 2 retrieves and inspects the supplied repository.

The goal is not to understand every line of code.

The goal is to reconstruct enough structured context to answer:

What is in this repository?
What are the important parts?
Which parts are relevant to the proposed change?
Why are they relevant?
What evidence supports that conclusion?

The context reconstruction layer may identify:

* repository structure
* application entry points
* source files
* components
* tests
* documentation
* dependencies
* configuration
* Git metadata
* repository relationships

Conceptually:

Repository
    |
    +--> Structure
    |
    +--> Source
    |
    +--> Components
    |
    +--> Tests
    |
    +--> Documentation
    |
    +--> Dependencies
    |
    +--> Configuration
    |
    +--> Git Metadata

Each important context artifact should preserve a reason for relevance
where applicable.

Each important context item should answer:

WHAT is relevant?
WHY is it relevant?
WHAT evidence supports this?

Phase 2 also provides the structured repository information required by
the optional Repository Knowledge Graph.

⸻

7. Repository Knowledge Graph

7.1 Purpose

The Repository Knowledge Graph is an optional repository-orientation
feature.

It answers:

"What exists in this codebase
and how is it connected?"

It is particularly useful when a developer is encountering a repository
for the first time.

⸻

7.2 Scope

The Repository Knowledge Graph represents the broader repository rather
than focusing exclusively on one developer change.

Potential node types include:

* File
* Component
* Test
* Dependency
* Documentation
* Configuration
* Entry Point

Potential relationship types include:

* imports
* contains
* depends_on
* tested_by
* configured_by
* documents
* calls
* implements

The implementation may support a smaller set initially.

Only relationships that can be established from repository information
should be represented.

⸻

7.3 Graph Model

The Repository Knowledge Graph follows the fundamental rule:

NODE = an entity
EDGE = a relationship between entities

For example:

auth.py
   |
   | tested_by
   v
test_auth.py

Not:

auth.py
   |
   v
relationship:tested_by
   |
   v
test_auth.py

Relationship types must be represented as edges rather than synthetic
relationship nodes.

⸻

7.4 User Experience

The Repository Knowledge Graph should be available through an explicit
repository-exploration action such as:

+---------------------------+
|   CHANGE IMPACT MAP       |
|                           |
|      PRIMARY OUTPUT       |
+---------------------------+
       [Explore Repository]
                 |
                 v
+---------------------------+
| Repository Knowledge      |
| Graph                     |
|                           |
|      OPTIONAL             |
+---------------------------+

The knowledge graph should not interfere with the Change Impact Map.

⸻

8. Phase 3: Historical Context

Phase 3 investigates repository history that may affect the developer’s
decision.

Potential historical evidence includes:

* relevant commits
* previous fixes
* historical file changes
* commit frequency
* available issues
* available pull requests
* historical relationships between artifacts

Historical findings must identify their source.

The system must not invent:

* commits
* issues
* pull requests
* historical relationships
* historical findings

If reliable historical information is unavailable, DevFlow should
clearly indicate that evidence was not found.

⸻

9. Phase 4: Impact Analysis

Phase 4 determines what the proposed change could affect.

Impact analysis consumes structured repository context and, when
available, historical context.

It may identify:

* affected files
* affected components
* dependencies
* tests
* documentation
* configuration
* downstream effects

Each meaningful impact finding should contain:

Affected Artifact
Relationship
Potential Impact
Supporting Evidence
Confidence / Evidence Strength

Conceptually:

                  Developer Change
                         |
          +--------------+--------------+
          |              |              |
          |              |              |
       modifies       impacts       tested_by
          |              |              |
          v              v              v
        File         Component         Test
          |
          |
       depends_on
          |
          v
     Dependency

The graph should show the actual relationships discovered by the
analysis.

⸻

10. Phase 5: Risk Analysis

Risk analysis consumes structured impact findings and repository
context.

Potential risk categories include:

* Code risk
* Regression risk
* Test gap
* Security risk
* Dependency risk
* Historical risk

Each significant risk contains:

Severity
Category
Explanation
Affected Artifacts
Supporting Evidence
Recommended Action

Conceptually:

Impact Finding
      |
      v
Risk Analysis
      |
      v
Risk Finding
      |
      +--> Severity
      +--> Category
      +--> Explanation
      +--> Evidence
      +--> Affected Artifacts
      +--> Recommendation

Risk conclusions must be based on identifiable evidence or explicitly
labelled as inference.

⸻

11. Phase 6: Change Impact Map

11.1 Purpose

The Change Impact Map is the primary visual output of DevFlow.

It transforms the structured outputs of:

* Repository Context
* Historical Context
* Impact Analysis
* Risk Analysis

into a focused visual explanation of a developer’s proposed change.

The map should allow a developer unfamiliar with the repository to
understand:

WHAT is changing?
        |
        v
WHAT is affected?
        |
        v
HOW are the artifacts connected?
        |
        v
WHY are they relevant?
        |
        v
WHAT evidence supports this?
        |
        v
WHAT could go wrong?

The goal is not merely to display a graph.

The goal is to make the meaning of the change understandable at a glance.

⸻

11.2 Central Change Node

The developer’s proposed change is the central node.

Example:

+--------------------------------+
|        DEVELOPER CHANGE        |
|                                |
| Refactor authentication        |
| session handling               |
+---------------+----------------+
                |
        +-------+-------+
        |       |       |
        v       v       v

The central node should be visually distinct from repository artifacts.

⸻

11.3 Artifact Nodes

The graph may contain relevant:

* Files
* Components
* Tests
* Dependencies
* Documentation
* Configuration
* Historical artifacts
* Other repository artifacts

Node appearance should communicate artifact type.

For example:

FILE
TEST
COMPONENT
DEPENDENCY
DOCUMENTATION
CONFIGURATION
COMMIT
ISSUE
PULL REQUEST
RISK

The exact visual design may evolve, but the semantic meaning of the
node types must remain clear.

⸻

11.4 Risk Nodes

Risks are represented as nodes because they represent findings rather
than relationships.

Example:

Developer Change
       |
       | modifies
       v
auth/session.py
       |
       | associated_with
       v
+----------------------+
| HIGH RISK            |
| Authentication       |
| regression possible  |
+----------------------+

Risk nodes should communicate severity.

Possible severity levels:

* Low
* Medium
* High
* Critical

The exact relationship used to connect a risk should reflect the
structured risk model rather than being fabricated solely for
visualization.

⸻

11.5 Edges

Edges represent relationships between nodes.

Potential relationship types include:

* modifies
* impacts
* depends_on
* tested_by
* documented_by
* introduced_by
* fixes
* related_to

Edges should communicate their relationship type through labels and/or
visual styling.

Relationships must never become graph nodes.

Correct:

File A --------tested_by--------> Test A

Incorrect:

File A --> tested_by node --> Test A

⸻

11.6 Evidence

Important relationships and findings should retain evidence.

For example:

auth/session.py
       |
       | modifies
       v
Evidence:
"Path appears in supplied changed files"
Evidence Type:
DIRECT
Evidence Strength:
CONFIRMED

Evidence may be attached to:

* nodes
* edges
* findings
* risks

depending on what the evidence supports.

⸻

11.7 Evidence Classification

DevFlow distinguishes between three primary evidence categories.

Direct Evidence

A fact directly established from repository information.

Examples:

auth/session.py exists.
auth/session.py appears in changed files.
requirements.txt declares package X.
test_auth.py exists.

Derived Relationship

A relationship derived from deterministic repository structure.

Examples:

module A imports module B.
test_auth.py tests functionality from auth.py.
configuration references service X.

AI Inference

A conclusion requiring reasoning beyond directly established repository
facts.

Example:

The authentication change may introduce an authorization regression.

AI inference must be clearly labelled and must not be presented as
direct repository evidence.

⸻

11.8 Confidence

Where appropriate, findings should communicate confidence or evidence
strength.

Confidence should reflect the strength of the underlying evidence.

It should not simply represent an arbitrary AI confidence score.

⸻

11.9 Graph Interaction

The Change Impact Map should support:

* node selection
* edge selection
* node repositioning
* zoom
* pan
* focus on important relationships
* evidence inspection
* risk inspection

Selecting a node should expose information such as:

Artifact
Type
Description
Relationships
Evidence
Confidence
Risk
Historical Context

Selecting an edge should expose:

Relationship
Source
Target
Description
Evidence
Confidence

The user should be able to reposition nodes without breaking the
underlying graph relationships.

The graph should remain readable as the number of relevant artifacts
increases.

⸻

11.10 Graph Summary

The Change Impact Map should provide a concise summary of the current
analysis.

The summary should help answer:

What is changing?
How many artifacts are affected?
What important relationships exist?
How many risks were identified?
What is the highest risk?
What evidence is available?

The summary must be generated from structured DevFlow data.

⸻

11.11 Legend

The visualization should provide a clear legend explaining:

* node types
* relationship types
* risk severity
* evidence strength

The legend should make the graph understandable without requiring the
developer to inspect every node.

⸻

12. Graph Data Model

The graph is represented using structured data.

The fundamental structure is:

Graph
├── Nodes
└── Edges

The graph is generated from structured DevFlow outputs.

It is not a decorative visualization layer with independently invented
data.

⸻

12.1 Node

A node represents an entity or finding.

Conceptually:

Node
├── id
├── type
├── label
├── description
├── metadata
├── evidence
├── confidence
└── risk information

Potential node types include:

change
file
component
test
documentation
dependency
configuration
commit
issue
pull_request
risk

The implementation may initially support only the types required by the
current phases.

⸻

12.2 Edge

An edge represents a relationship between two nodes.

Conceptually:

Edge
├── source
├── target
├── relationship
├── description
├── evidence
└── confidence

Example:

source:
artifact:src/auth/session.py
target:
artifact:tests/test_session.py
relationship:
tested_by
confidence:
likely

⸻

12.3 Fundamental Graph Rule

The graph follows:

NODE
=
thing that exists or finding that exists
EDGE
=
relationship between things

Therefore:

CORRECT
File A --------tested_by--------> Test A

and not:

INCORRECT
File A --> tested_by node --> Test A

This rule applies to both the Repository Knowledge Graph and the
Change Impact Map.

⸻

13. Evidence Model

Evidence is a first-class concept throughout DevFlow.

Every important finding should preserve the relationship:

Finding
   |
   v
Evidence
   |
   v
Repository Source

Evidence should ideally identify the source from which the conclusion
was derived.

Potential evidence sources include:

* source files
* file paths
* configuration
* dependency declarations
* tests
* Git commits
* Git history
* issues
* pull requests
* repository structure

The exact evidence format depends on the source and implementation.

⸻

14. Historical Evidence

Historical context should enrich the interpretation of a change without
turning history into unnecessary graph clutter.

For example:

File
 |
 | introduced_by
 v
Commit

may be represented when the commit is relevant to understanding the
change.

However, historical information may also be presented as evidence in
an inspector or finding rather than always becoming a visible graph
node.

The visualization should prioritize clarity over displaying every
available piece of repository information.

⸻

15. Data Flow

The primary data flow is:

RepositoryInput
      +
ChangeRequest
      |
      v
RepositoryContext
      |
      +-------------------+
      |                   |
      v                   v
Knowledge Graph      RepositoryHistory
      |                   |
      +---------+---------+
                |
                v
          ImpactAnalysis
                |
                v
           RiskAnalysis
                |
                v
       ChangeImpactMap

Each stage should consume structured data from previous stages rather
than directly depending on unrelated implementation details.

⸻

16. Module Architecture

The source tree is organized by responsibility.

src/devflow/
│
├── input/
│   └── Repository and change input
│
├── context/
│   └── Repository ingestion and context reconstruction
│
├── history/
│   └── Historical repository analysis
│
├── impact/
│   └── Change impact analysis
│
├── risk/
│   └── Risk analysis
│
├── map/
│   └── Graph construction and visualization
│
├── models/
│   └── Shared structured data models
│
└── __main__.py
    └── Application entry point

Each module should have a clear responsibility.

⸻

17. Module Responsibilities

input

Responsible for:

* repository URL validation
* repository normalization
* developer change normalization
* input models

It should not perform repository analysis.

⸻

context

Responsible for:

* repository retrieval
* repository inspection
* context reconstruction
* artifact identification
* relevance reasoning
* context evidence

⸻

history

Responsible for:

* Git history
* relevant commits
* historical artifact relationships
* historical evidence

⸻

impact

Responsible for:

* affected artifact identification
* relationship identification
* impact findings
* impact evidence

⸻

risk

Responsible for:

* risk detection
* risk classification
* severity
* risk evidence
* recommendations

⸻

map

Responsible for:

* graph construction
* node generation
* edge generation
* graph presentation
* visualization
* interaction

The map module should consume structured DevFlow results.

It should not independently perform repository analysis.

⸻

models

Contains shared representations used across phases.

Examples include:

* RepositoryInput
* ChangeRequest
* RepositoryContext
* RepositoryHistory
* ImpactAnalysis
* RiskAnalysis
* Graph
* Node
* Edge
* Evidence

⸻

18. Separation Between the Two Graphs

DevFlow intentionally contains two different graph concepts.

Repository Knowledge Graph

Purpose:
Repository Orientation
Question:
"What is in this codebase?"
Scope:
Broader repository structure
Primary use:
Understanding an unfamiliar repository
Status:
Optional exploration feature

Change Impact Map

Purpose:
Change Review
Question:
"What does my proposed change affect?"
Scope:
Change-relevant repository context
Primary use:
Understanding impact and risk
Status:
Primary DevFlow output

The distinction is fundamental.

+--------------------------------------+
|      REPOSITORY KNOWLEDGE GRAPH     |
|                                      |
|      "WHAT IS IN THE REPO?"          |
|                                      |
|      OPTIONAL ORIENTATION            |
+-------------------+------------------+
                    |
                    v
+--------------------------------------+
|          CHANGE IMPACT MAP           |
|                                      |
|      "WHAT DOES MY CHANGE AFFECT?"   |
|                                      |
|          PRIMARY OUTPUT              |
+--------------------------------------+

⸻

19. Visualization Architecture

The Change Impact Map is rendered as an interactive visualization.

The visualization should contain four major areas.

19.1 Graph Canvas

Displays:

* change node
* artifact nodes
* risk nodes
* edges
* edge labels
* risk indicators

⸻

19.2 Summary

Displays high-level information about the current change.

Examples:

Changed artifacts
Impact relationships
Tests affected
Risks identified
Highest severity
Evidence availability

⸻

19.3 Inspector

Displays information about the selected graph object.

For a node:

Name
Type
Description
Relationships
Evidence
Confidence
Risk
Historical Context

For an edge:

Relationship
Source
Target
Description
Evidence
Confidence

⸻

19.4 Legend

Explains:

* node types
* relationship types
* risk severity
* evidence strength

⸻

20. Interaction Model

The Change Impact Map should support:

Click Node
    |
    v
Inspect Artifact / Risk
Click Edge
    |
    v
Inspect Relationship + Evidence
Drag Node
    |
    v
Reposition Graph Element
Zoom
    |
    v
Explore Graph at Different Scales
Pan
    |
    v
Navigate Graph
Focus
    |
    v
Emphasize Important Relationships

Interaction must not alter the underlying structured analysis.

Moving a node changes its visualization position only.

⸻

21. Repository Agnosticism

DevFlow must not assume a particular repository.

The system must not hard-code:

* repository names
* file paths
* frameworks
* languages
* components
* dependencies
* commit history
* test names
* architecture

Invalid:

if repository == "example/project":
    add auth/session.py

Correct:

Repository
    |
    v
Repository Analysis
    |
    v
Structured Context
    |
    v
Impact Analysis
    |
    v
Graph

The same implementation should be capable of processing unrelated
repositories.

⸻

22. Repository-Agnostic Validation

DevFlow should be tested against multiple unrelated repositories.

The purpose is to detect hidden assumptions such as:

* hard-coded paths
* framework-specific logic
* repository-specific node names
* assumed test structures
* assumed dependency formats

The desired behavior is:

Repository A
     |
     v
Context A
     |
     v
Impact A
     |
     v
Map A
Repository B
     |
     v
Context B
     |
     v
Impact B
     |
     v
Map B

The graph contents should differ because the repositories differ.

The pipeline itself should remain repository agnostic.

⸻

23. Error Handling

Failures must be explicit.

Examples include:

* invalid repository URL
* repository retrieval failure
* repository unavailable
* Git history unavailable
* missing evidence
* unsupported repository state
* incomplete analysis

DevFlow must not produce fabricated output to hide an analysis failure.

For example:

Repository retrieval failed.

is preferable to:

Repository retrieved successfully.

when retrieval did not actually succeed.

Similarly:

No historical evidence found.

is preferable to inventing a historical explanation.

⸻

24. Security and Privacy

DevFlow must not commit or expose:

* API keys
* credentials
* tokens
* secrets
* personal information

Credentials must never be embedded into:

* graph data
* documentation
* test fixtures
* generated visualization output

The system should avoid sending unnecessary repository content to
external AI services.

When external AI services are used, only the context required for the
specific task should be provided.

⸻

25. Bob Integration Boundary

IBM Bob is part of the broader DevFlow workflow, but Bob does not
replace the structured repository analysis layer.

The intended boundary is:

                    DevFlow
                       |
              Repository Analysis
                       |
               Context + Evidence
                       |
                Impact + Risk
                       |
               Change Impact Map
                       |
                Human Decision
                       |
              +--------+--------+
              |                 |
             Stop              Bob
                                |
                         Investigation /
                           Resolution
                                |
                             Testing
                                |
                           Validation

Bob should enter the workflow when its agentic capabilities provide
meaningful value.

Bob should not be used merely as a generic code generator.

⸻

26. Bob Modes

Potential DevFlow-specific Bob modes include:

26.1 DevFlow Investigator

Purpose:

Understand an unfamiliar repository without modifying it.

Responsibilities:

Repository
    |
    v
Structure
    |
    v
Architecture
    |
    v
Technology Stack
    |
    v
Components
    |
    v
Tests
    |
    v
Dependencies
    |
    v
Historical Context
    |
    v
Evidence

The Investigator should be read-only.

It should:

* inspect the repository
* identify structure
* explain architecture
* identify important components
* trace relevant relationships
* locate tests
* locate dependencies
* preserve evidence
* avoid modifying repository files

⸻

26.2 DevFlow Reviewer

Purpose:

Review a proposed developer change.

Responsibilities:

Developer Change
       |
       v
Context
       |
       v
Impact
       |
       v
Risk
       |
       v
Evidence
       |
       v
Recommendation

The Reviewer should be read-only.

It should not directly implement fixes.

⸻

26.3 DevFlow Resolver

Purpose:

Investigate and resolve an approved finding.

Conceptually:

Selected Finding
       |
       v
Evidence
       |
       v
Investigation
       |
       v
Proposed Fix
       |
       v
Human Approval
       |
       v
Implementation
       |
       v
Testing

The Resolver belongs to the later Bob Resolution phase.

It should not be implemented before that phase becomes active.

⸻

27. Bob Skills

DevFlow may eventually provide reusable skills for specialized
workflows.

Potential skills include:

Repository Investigation

Input:

Repository

Output:

Repository Structure
Architecture
Technology Stack
Entry Points
Components
Tests
Dependencies
Configuration
Evidence

⸻

Change Impact Analysis

Input:

Repository Context
Developer Change
Historical Context

Output:

Affected Artifacts
Relationships
Evidence
Confidence

⸻

Risk Analysis

Input:

Impact Findings
Repository Context
Historical Context

Output:

Risks
Severity
Evidence
Recommendations

⸻

Evidence Verification

Purpose:

Verify that an important finding is actually supported by repository
evidence.

Conceptually:

Claim
 |
 v
Locate Source
 |
 v
Trace Relationship
 |
 v
Verify Evidence
 |
 v
Accept
Reject
or
Mark as Inference

Skills should be introduced when they provide a meaningful reusable
workflow rather than simply increasing the number of configuration
files.

⸻

28. Optional IBM Technologies

IBM technologies should only be introduced when they provide meaningful
functionality.

IBM Bob

Bob is the primary agentic development environment.

Potential uses include:

* repository investigation
* context-aware development
* code review
* agentic workflows
* approved resolution
* testing
* validation

⸻

IBM watsonx.ai / Granite

Potential future uses include:

* evidence classification
* finding prioritization
* risk synthesis
* context summarization
* confidence assessment

These should only be introduced if they improve a clearly defined part
of DevFlow.

⸻

IBM watsonx Orchestrate

Potential future use:

Context Discovery
        |
        v
Parallel Investigation
        |
        v
Evidence Synthesis
        |
        v
Risk Analysis
        |
        v
Bob Resolution
        |
        v
Validation

Orchestrate should only be introduced if it meaningfully improves
workflow coordination.

⸻

29. Agentic Architecture

The long-term DevFlow workflow may use multiple specialized
responsibilities.

Conceptually:

                    DevFlow
                       |
             +---------+---------+
             |                   |
             v                   v
       Investigator          Reviewer
             |                   |
             +---------+---------+
                       |
                       v
                Evidence Synthesis
                       |
                       v
                  Risk Analysis
                       |
                       v
                Human Decision
                       |
                       v
                   Resolver
                       |
                       v
                  Validation

Parallel investigation may be useful when multiple independent
repository questions can be investigated simultaneously.

Agentic behavior should only be introduced where it reduces manual
effort or improves reliability.

⸻

30. Testing Architecture

Each major phase should have deterministic tests.

Tests should verify:

* input validation
* repository context extraction
* historical context
* impact findings
* risk findings
* graph construction
* graph relationships
* evidence preservation
* visualization generation

The Change Impact Map should be tested using structured fixture data
rather than depending exclusively on live GitHub repositories.

Tests should specifically verify that relationships are edges rather
than synthetic relationship nodes.

For example:

Change
  |
  +--> Artifact
  |
  +--> Artifact
  |
  +--> Risk

should produce the expected nodes and edges.

Repository-agnostic behavior should also be tested against more than one
repository shape where practical.

⸻

31. Current Implementation Boundary

DevFlow is built incrementally.

TASKS.md is the source of truth for implementation status.

This architecture document describes the intended system architecture,
while TASKS.md records which phases and tasks are actually complete.

The intended distinction is:

Architecture
    |
    v
What DevFlow is designed to become
TASKS.md
    |
    v
What DevFlow has actually implemented

Future components may therefore be documented architecturally without
being implemented prematurely.

Blocked phases must remain blocked until their prerequisites are
complete and explicit approval is given to begin them.

⸻

32. Future Extensions

The architecture is intentionally modular so that individual
components can be replaced or improved.

Potential extensions include:

* additional programming language analyzers
* richer repository graphs
* function-level graph nodes
* class-level graph nodes
* richer historical relationships
* pull request integration
* issue integration
* semantic enrichment
* AI-assisted finding prioritization
* multi-agent investigation
* automated resolution
* automated validation
* developer reports
* measurement and evaluation

Future extensions must preserve:

Evidence
Traceability
Repository Agnosticism
Modularity
Human Control

⸻

33. End-to-End Architecture

The complete conceptual architecture is:

                         DEVFLOW
                            |
             Repository + Developer Change
                            |
                +-----------+-----------+
                |                       |
                v                       v
        Repository Input          Change Request
                |                       |
                +-----------+-----------+
                            |
                            v
                 Repository Ingestion
                            |
                            v
                 Context Reconstruction
                            |
                 +----------+----------+
                 |                     |
                 v                     v
       Repository Knowledge      Historical Context
             Graph                     |
        "What's here?"                 |
                 |                     |
                 +----------+----------+
                            |
                            v
                    Impact Analysis
                            |
                            v
                     Risk Analysis
                            |
                            v
              +-----------------------+
              |   CHANGE IMPACT MAP   |
              |                       |
              |    PRIMARY OUTPUT     |
              |                       |
              | Change → Impact       |
              |      → Evidence      |
              |      → Risk           |
              +-----------+-----------+
                          |
                          v
                   Recommendations
                          |
                          v
                   Human Decision
                          |
                  +-------+-------+
                  |               |
                  v               v
                 Stop            Bob
                                  |
                            Investigation
                                  |
                            Human Approval
                                  |
                               Resolution
                                  |
                                Testing
                                  |
                              Validation

⸻

34. Core Product Model

DevFlow can be understood through four fundamental concepts:

NODE
=
A thing that exists or a finding that exists.
EDGE
=
A relationship between two nodes.
EVIDENCE
=
Why DevFlow believes a relationship or finding is valid.
RISK
=
A finding describing what could go wrong.

This produces the core mental model:

                 CHANGE
                    |
             relationship
                    |
                    v
                 ARTIFACT
                    |
             relationship
                    |
                    v
                 ARTIFACT
                    |
                 evidence
                    |
                    v
                  RISK

The graph should therefore never become a collection of arbitrary
labels.

Every visible graph element should have a meaningful role in explaining
the change.

⸻

35. Core Product Principle

The Repository Knowledge Graph helps the developer understand the
codebase.

The Change Impact Map helps the developer understand the change.

The Repository Knowledge Graph answers:

"What is here?"

The Change Impact Map answers:

"What does my change affect?"

The evidence model answers:

"Why should I believe this?"

The risk model answers:

"What could go wrong?"

The recommendation layer answers:

"What should I do next?"

Together:

       UNFAMILIAR CODEBASE
                |
                v
       UNDERSTAND THE REPO
                |
                v
        UNDERSTAND THE CHANGE
                |
                v
       UNDERSTAND THE IMPACT
                |
                v
       UNDERSTAND THE EVIDENCE
                |
                v
        UNDERSTAND THE RISK
                |
                v
        MAKE A CONFIDENT
             DECISION

DevFlow’s purpose is not to generate another generic code graph.

Its purpose is to transform repository context and evidence into a
focused explanation of what a developer’s change means.

From unfamiliar code to confident change.

### One important thing before you give this to Copilot
I would **not** ask Copilot to blindly overwrite `architecture.md` with the whole thing without first checking what you already have.
Give Copilot this prompt:
```text
Read AGENTS.md and TASKS.md first.
Create or update architecture.md using the architecture specification
provided below.
IMPORTANT:
- architecture.md is the technical source of truth for the intended
  DevFlow architecture.
- TASKS.md remains the source of truth for implementation status.
- Do not mark blocked phases as implemented.
- Do not modify source code.
- Do not modify TASKS.md.
- Do not create additional documentation files.
- Preserve any existing architecture information that is still correct.
- Remove contradictions with the current TASKS.md/product definition.
- Keep the architecture repository-agnostic.
- Keep the Repository Knowledge Graph and Change Impact Map explicitly
  separate.
- The Repository Knowledge Graph is optional and is accessed as a
  secondary "Explore Repository" capability.
- The Change Impact Map is the primary output.
- Relationships are edges, never synthetic relationship nodes.
- Evidence is distinct from nodes and edges.
- Risks are findings and may be represented as graph nodes.
- Do not claim features exist merely because they are described in
  architecture.md.
- Do not introduce implementation details that do not exist in the repo.
- Do not invent modules, APIs, data models, IBM integrations, Bob modes,
  or skills as currently implemented.
- Future architecture may be documented, but must be clearly identified
  as future/planned.
After updating architecture.md:
1. Show the file diff.
2. Verify that it is consistent with TASKS.md.
3. Do not make any other repository changes.