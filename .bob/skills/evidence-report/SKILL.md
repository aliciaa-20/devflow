---
name: evidence-report
description: >-
  Synthesize DevFlow investigation results into a structured, evidence-backed
  change impact model and developer report suitable for visualization, risk
  review, and downstream Bob resolution.
---

# Evidence Report

## Purpose

Synthesize the outputs of DevFlow's repository investigation into a structured, evidence-backed representation of a developer change.

This skill prepares information for:

- The Change Impact Map
- Evidence inspection
- Risk analysis
- Developer recommendations
- Bob resolution workflows

This skill is primarily a synthesis task.

Do not invent repository facts.

Do not modify project files.

---

# Input

The input may contain results from:

- Change Context Reconstruction
- Impact Analysis
- Historical Context Reconstruction
- Repository inspection
- Test inspection
- Dependency analysis
- Configuration analysis
- Risk analysis

Use the available investigation results.

If information is missing, represent the gap explicitly.

---

# Core Principle

Preserve the distinction between:

1. Repository evidence
2. Derived relationships
3. AI inference
4. Unknown or unavailable information

Do not convert an inference into a confirmed fact.

Do not create evidence that was not present in the investigation results.

---

# Evidence Normalization

For each important finding, identify:

- Unique identifier
- Finding type
- Description
- Affected artifact
- Relationship
- Evidence
- Evidence classification
- Evidence strength
- Confidence when available
- Potential impact
- Recommended action

---

# Graph Model

Create structured graph data representing the important context around the change.

## Node Types

Supported node types include:

- CHANGE
- FILE
- COMPONENT
- TEST
- DOCUMENTATION
- DEPENDENCY
- ISSUE
- PULL_REQUEST
- COMMIT
- CONFIGURATION

Each node should contain, where available:

- id
- type
- name
- path or reference
- description
- importance
- evidence references

Do not create nodes for artifacts that were not established by the investigation.

---

# Relationship Model

Supported relationship types include:

- MODIFIES
- DEPENDS_ON
- TESTED_BY
- DOCUMENTED_BY
- INTRODUCED_BY
- FIXES
- RELATED_TO
- IMPACTS

Each relationship should contain:

- source node
- target node
- relationship type
- explanation
- evidence references
- evidence strength
- confidence when available

Do not create a relationship solely because two artifacts appear conceptually related.

---

# Finding Model

Important findings should contain:

- id
- title
- category
- severity when available
- description
- affected nodes
- evidence
- evidence classification
- evidence strength
- confidence
- recommendation

Possible categories include:

- CODE
- TEST
- SECURITY
- DEPENDENCY
- DOCUMENTATION
- CONFIGURATION
- HISTORY
- REGRESSION
- ARCHITECTURE

---

# Evidence Model

Evidence should identify the repository artifact supporting the conclusion.

Where available include:

- file path
- symbol
- line or section
- commit
- issue
- pull request
- test
- configuration
- command or validation result

Do not expose secret values.

Evidence references should be concise and useful for a developer.

---

# Risk Representation

If risk information is provided by the investigation, represent it structurally.

Each risk may contain:

- id
- severity
- title
- description
- affected nodes
- evidence
- evidence strength
- confidence
- recommendation

Do not independently invent risk findings.

If risk severity was not established, do not assign an arbitrary severity.

---

# Evidence Hierarchy

When multiple pieces of evidence support the same finding, prefer:

1. Direct repository evidence
2. Multiple consistent repository artifacts
3. Strong derived relationships
4. AI inference

The report should make the evidence strength visible.

---

# Conflicting Evidence

If repository artifacts disagree:

1. Preserve the conflict.
2. Identify the conflicting artifacts.
3. Do not silently choose one.
4. Explain why the conflict matters.
5. Mark the conclusion as unresolved when appropriate.

---

# Missing Evidence

If an important conclusion cannot be established:

Represent it explicitly.

Examples:

- Evidence not found
- Historical information unavailable
- Relevant test not found in inspected repository
- Issue metadata unavailable
- Pull request metadata unavailable
- Relationship could not be established

Never fill evidence gaps with fabricated information.

---

# Output

Return two coordinated outputs:

1. Structured Change Impact Model
2. Developer-facing Evidence Report

---

# Structured Change Impact Model

Use the following conceptual structure:

```json
{
  "change": {
    "id": "",
    "title": "",
    "description": ""
  },
  "nodes": [],
  "relationships": [],
  "findings": [],
  "risks": [],
  "recommendations": [],
  "evidence_gaps": []
}
