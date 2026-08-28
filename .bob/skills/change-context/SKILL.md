---
name: change-context
description: >-
  Reconstruct the repository context relevant to a developer change by
  investigating source code, components, tests, documentation, dependencies,
  configuration, and available repository history. Produce evidence-backed
  structured context without modifying project files.
---

# Change Context Reconstruction

## Purpose

Reconstruct the repository context relevant to a developer-provided change.

The goal is to help a developer understand an unfamiliar or evolving codebase before reviewing or modifying a change.

This skill is investigative only.

Do not modify project files.

## Input

The user will provide a developer change, for example:

"Refactor authentication session handling."

The change may also include:

- Changed files
- A branch or commit
- A pull request
- An issue
- A feature description
- A bug description

Use whatever information is available.

## Investigation Process

Perform the investigation in the following order.

### 1. Understand the requested change

Identify:

- What the developer wants to change
- The likely purpose of the change
- Explicitly mentioned components
- Explicitly mentioned files
- Important constraints

Do not assume implementation details that are not supported by the request or repository.

### 2. Inspect repository structure

Identify the repository structure relevant to the change.

Look for:

- Source directories
- Application entry points
- Major components
- Services
- Utilities
- Tests
- Documentation
- Configuration
- Dependency manifests

Do not inspect unrelated parts of a large repository unnecessarily.

### 3. Identify relevant source code

Find source files that appear relevant to the change.

For each important file record:

- Path
- Relevant symbol, function, class, or section when available
- Why it is relevant
- Evidence supporting the relationship

### 4. Identify related components

Determine whether the change interacts with other components.

Look for evidence such as:

- Imports
- Function calls
- Class relationships
- API calls
- Shared data structures
- Configuration references
- Dependency relationships

Do not claim a relationship without evidence.

### 5. Identify relevant tests

Search for tests related to the changed behavior.

Record:

- Test path
- Relevant test name or section
- Behavior covered
- Whether coverage appears relevant to the requested change

Do not claim that behavior is untested simply because a test was not found immediately.

Use wording such as:

"Relevant test not found in the inspected repository."


### 6. Identify relevant documentation

Inspect relevant:

- README files
- Architecture documentation
- API documentation
- Configuration documentation
- Developer guides
- Comments when useful

Record why the documentation matters.

If documentation appears inconsistent with the code, report the discrepancy rather than silently choosing one as correct.

### 7. Identify dependencies and configuration

Inspect relevant:

- package manifests
- requirements files
- lockfiles when useful
- configuration files
- environment configuration
- build configuration

Identify dependencies or configuration that could affect the change.

Never expose secret values.

### 8. Identify available repository history

When repository history is available, identify potentially relevant:

- commits
- branches
- tags
- issue references
- pull request references

Do not invent historical context.

Historical reasoning should only be reported when supported by repository evidence.

## Evidence Classification

Classify important conclusions as one of:

### DIRECT

Directly observed in repository artifacts.

### DERIVED

Reasonably derived from multiple repository artifacts.

### INFERENCE

AI interpretation that is not directly established by repository evidence.

### NOT_FOUND

The relevant evidence could not be located in the inspected repository.

Never present INFERENCE as DIRECT evidence.

## Output

Return a structured context report.

Use this format:

# Change Context

## Requested Change

<short description>

## Relevant Components

| Artifact | Type | Relevance | Evidence | Confidence |
|----------|------|-----------|----------|------------|

## Related Tests

| Test | Covers | Evidence | Confidence |
|------|--------|----------|------------|

## Documentation

| Document | Relevance | Evidence |
|----------|-----------|----------|

## Dependencies

| Dependency | Relationship | Evidence |
|------------|--------------|----------|

## Configuration

| Artifact | Relevance | Evidence |
|----------|-----------|----------|

## Historical Context

| Artifact | Relationship | Evidence | Confidence |
|----------|--------------|----------|------------|

## Important Relationships

List the most important relationships discovered.

Use:

CHANGE
→ RELATIONSHIP
→ ARTIFACT
→ EVIDENCE

## Evidence Gaps

Explicitly list important information that could not be established.

## Context Summary

Provide a concise summary of the repository context that a developer should understand before reviewing the change.

## Rules

1. Do not modify files.
2. Do not fabricate repository artifacts.
3. Do not fabricate historical information.
4. Do not fabricate tests or test results.
5. Do not expose secrets.
6. Prefer repository evidence over general software knowledge.
7. Clearly distinguish observation, derivation, and inference.
8. Keep investigation focused on the requested change.
9. Prefer specific evidence over generic explanations.
10. Report uncertainty explicitly.
