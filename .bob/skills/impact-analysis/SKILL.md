---
name: impact-analysis
description: >-
  Analyze the potential impact of a developer change across repository files,
  components, tests, dependencies, configuration, and documentation using
  evidence from the repository.
---

# Impact Analysis

## Purpose

Determine what a developer change could affect within the repository.

This skill analyzes the relationships discovered during context reconstruction and identifies meaningful technical and behavioral impact.

This skill is investigative and analytical.

Do not modify project files.

---

## Input

The input may contain:

- Developer change description
- Changed files
- Repository context
- Relevant components
- Tests
- Documentation
- Dependencies
- Configuration
- Historical context
- Repository relationships

Use the available information.

Do not assume that every discovered artifact is affected by the change.

---

## Analysis Process

### 1. Identify the change boundary

Determine:

- What behavior is being changed
- Which files are directly involved
- Which components are directly involved
- Which interfaces may change
- Which data or control flows may be affected

Separate direct impact from possible downstream impact.

---

### 2. Analyze file impact

For each relevant file determine:

- Whether it is directly modified
- Whether it is indirectly affected
- Why it is affected
- What evidence establishes the relationship

Classify impact as:

DIRECT
INDIRECT
POSSIBLE

Do not classify something as affected merely because it exists in the same directory.

---

### 3. Analyze component impact

Determine which application components may be affected.

Consider evidence such as:

- Imports
- Function calls
- Shared classes
- Shared data
- API boundaries
- Configuration references
- Service relationships

For each component explain the relationship.

---

### 4. Analyze dependency impact

Determine whether the change affects:

- Runtime dependencies
- Development dependencies
- Internal modules
- External APIs
- Shared libraries
- Configuration-dependent behavior

Do not report a dependency as affected without evidence.

---

### 5. Analyze test impact

Determine:

- Which existing tests exercise the changed behavior
- Which tests may need modification
- Which related behavior may require additional regression tests
- Whether relevant test coverage was found

Do not claim that coverage is missing simply because no test was found immediately.

Use:

"Relevant test not found in the inspected repository."

when appropriate.

---

### 6. Analyze documentation impact

Determine whether the change could make documentation inaccurate or incomplete.

Inspect relevant:

- README files
- API documentation
- Architecture documentation
- Configuration documentation
- Developer documentation

Only report documentation impact when there is a meaningful relationship.

---

### 7. Analyze configuration impact

Determine whether the change affects:

- Environment variables
- Configuration files
- Build configuration
- Deployment configuration
- Runtime settings

Do not expose secret values.

---

### 8. Analyze historical impact

Use available historical context to identify whether the change intersects with:

- Previous fixes
- Previous regressions
- Security-related changes
- Architectural decisions
- Frequently modified areas

Historical information must be supported by repository evidence.

Do not infer historical intent without evidence.

---

## Impact Classification

Classify each important impact as:

### DIRECT

The change explicitly modifies or directly interacts with the artifact.

### INDIRECT

The artifact is connected to the changed behavior through an identifiable repository relationship.

### POSSIBLE

The artifact could be affected, but the repository evidence is insufficient to establish the relationship confidently.

Do not present POSSIBLE impact as confirmed impact.

---

## Evidence Strength

For each important impact, classify evidence strength as:

### STRONG

Direct repository evidence clearly establishes the relationship.

### MODERATE

Multiple repository artifacts support the relationship.

### WEAK

The relationship is plausible but evidence is limited.

### NOT_ESTABLISHED

The relationship could not be established from the inspected repository.

---

## Output

Return a structured Impact Analysis.

# Change Impact Analysis

## Change

<short description>

## Directly Affected

| Artifact | Type | Impact | Evidence | Evidence Strength |
|----------|------|--------|----------|-------------------|

## Indirectly Affected

| Artifact | Type | Relationship | Potential Impact | Evidence | Evidence Strength |
|----------|------|--------------|------------------|----------|-------------------|

## Possible Impact

| Artifact | Type | Why It May Matter | Evidence Gap |
|----------|------|-------------------|--------------|

## Test Impact

| Test | Current Coverage | Potential Required Action | Evidence |
|------|------------------|---------------------------|----------|

## Dependency Impact

| Dependency | Relationship | Potential Effect | Evidence |
|------------|--------------|------------------|----------|

## Documentation Impact

| Document | Potential Effect | Evidence |
|----------|------------------|----------|

## Configuration Impact

| Configuration | Potential Effect | Evidence |
|---------------|------------------|----------|

## Historical Impact

| Historical Artifact | Relationship | Relevance | Evidence |
|---------------------|--------------|-----------|----------|

## Impact Relationships

Represent important relationships as:

CHANGE
→ RELATIONSHIP
→ ARTIFACT
→ POTENTIAL EFFECT
→ EVIDENCE

## Key Findings

List the most important impacts in priority order.

For each finding include:

- Impact
- Affected artifact
- Why it matters
- Evidence
- Evidence strength

## Evidence Gaps

List important relationships that could not be established.

## Impact Summary

Provide a concise summary of:

1. What is definitely affected
2. What is indirectly affected
3. What may be affected
4. What should be checked before approving the change
