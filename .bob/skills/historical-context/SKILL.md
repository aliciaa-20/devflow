---
name: historical-context
description: >-
  Reconstruct historical context relevant to a developer change by investigating
  Git commits, branches, issues, pull requests, and previous fixes, while
  clearly separating repository evidence from inference.
---

# Historical Context Reconstruction

## Purpose

Determine whether repository history contains information that is relevant to understanding a developer change.

This skill answers questions such as:

- Why was this code introduced?
- Has this area changed before?
- Was similar behavior previously fixed?
- Did a previous change introduce or remove related behavior?
- Are there historical patterns that should influence the current review?

This skill is investigative only.

Do not modify project files.

---

## Input

The input may contain:

- Developer change description
- Changed files
- Repository context
- Relevant components
- Existing impact analysis
- Known risks
- Specific files or symbols to investigate

Use the available information to focus the historical investigation.

---

# Investigation Process

## 1. Establish the historical scope

Identify:

- Files directly involved in the change
- Relevant components
- Relevant functions, classes, or modules
- Related tests
- Relevant configuration
- Areas identified as potentially impacted

Use this scope to avoid searching unrelated repository history.

---

## 2. Inspect Git history

When Git history is available, investigate relevant:

- Commits
- Commit messages
- File history
- Line history when useful
- Branches when relevant
- Tags when relevant

Prioritize history directly connected to the affected code.

Look for:

- Previous changes to the same files
- Previous changes to the same functions or components
- Reverts
- Bug fixes
- Refactors
- Security-related changes
- Regression fixes
- Changes that modified tests alongside implementation

Do not treat a commit message alone as proof of implementation intent if the actual change contradicts it.

---

## 3. Compare historical changes

When useful, inspect the actual historical diff.

Determine:

- What changed
- Which files changed together
- Whether tests were added or modified
- Whether documentation changed
- Whether configuration changed
- Whether a previous change was later reverted or corrected

Focus on relationships that can inform the current developer change.

---

## 4. Identify previous fixes

Look specifically for historical changes that appear related to:

- Bugs
- Regressions
- Security problems
- Validation problems
- Error handling
- Authentication or authorization
- Data integrity
- Performance issues
- Test failures

Only classify something as a previous fix when repository evidence supports that conclusion.

---

## 5. Identify issue and pull request references

When issues or pull requests are available in the repository or provided through repository metadata, identify relevant references.

Look for:

- Issue identifiers
- PR identifiers
- Commit references
- References in commit messages
- References in documentation

Do not invent issue or PR information.

If external issue or PR information is unavailable, report that limitation.

---

## 6. Reconstruct historical relationships

For each meaningful historical relationship, determine:

WHAT happened?
↓
WHEN did it happen?
↓
WHAT artifact did it affect?
↓
WHY is it relevant to the current change?
↓
WHAT evidence supports the relationship?

Do not infer historical intent merely because two changes touch the same file.

---

# Evidence Classification

Every historical conclusion must be classified as one of:

## DIRECT

The repository directly establishes the historical fact.

Example:

A commit modified the same function and added a regression test.

## DERIVED

The historical relationship is supported by multiple repository artifacts.

Example:

A commit modified a function, added a test, and was followed by a related corrective commit.

## INFERENCE

The available evidence suggests a possible explanation but does not establish it.

Example:

The change may have been intended to address a particular edge case based on surrounding code and commit timing.

## NOT_ESTABLISHED

The repository does not contain sufficient evidence to determine the historical explanation.

---

# Historical Confidence

For important historical findings, assign:

### HIGH

Direct evidence clearly establishes the relationship.

### MEDIUM

Multiple pieces of evidence support the relationship, but some interpretation is required.

### LOW

The relationship is plausible but evidence is limited.

### UNKNOWN

The repository does not provide enough evidence.

---

# Special Rule: Historical Intent

Do not claim to know why a developer made a historical change unless evidence supports the claim.

For example, do not write:

"The developer added this validation because users were experiencing authentication failures."

unless repository evidence actually establishes that reason.

Instead write:

"A commit introduced this validation. The commit message references authentication handling, but the repository does not establish the specific user-facing reason."

---

# Special Rule: Recency

When multiple historical artifacts are relevant:

1. Prefer evidence directly connected to the affected code.
2. Prefer changes that explain the current behavior.
3. Consider recent changes.
4. Consider older changes when they establish important architectural or behavioral context.
5. Do not assume the newest commit represents the original design intent.

---

# Special Rule: Reverts and Corrections

Pay particular attention to:

- Reverted commits
- Follow-up fixes
- Repeated changes to the same code
- Tests added after a bug fix
- Changes that repeatedly modify the same behavior

Repeated historical changes may indicate an area that requires additional caution.

Do not automatically classify repeated changes as a risk.

Explain the evidence.

---

# Output

Return a structured Historical Context Report.

# Historical Context

## Current Change

<short description>

## Relevant Historical Artifacts

| Artifact | Type | Date | Affected Area | Relevance | Evidence | Confidence |
|----------|------|------|---------------|-----------|----------|------------|

## Previous Changes

For each important historical change:

### <Change>

- What changed:
- Affected files:
- Related tests:
- Historical evidence:
- Relevance to current change:
- Confidence:

---

## Previous Fixes or Regressions

| Historical Change | Problem or Behavior | Evidence | Relevance to Current Change | Confidence |
|------------------|---------------------|----------|-----------------------------|------------|

Only include entries supported by evidence.

---

## Issue / Pull Request Context

| Reference | Relationship | Evidence | Relevance |
|-----------|--------------|----------|-----------|

If no reliable issue or pull request context is available, explicitly state that.

---

## Historical Relationships

Represent important relationships as:

CURRENT CHANGE
→ RELATES_TO
→ HISTORICAL ARTIFACT
→ EVIDENCE
→ RELEVANCE

---

## Repeated Change Areas

Identify areas that have been changed repeatedly when that pattern is supported by repository history.

For each:

- Artifact
- Number or pattern of relevant changes when determinable
- Nature of changes
- Evidence
- Why it may matter

Do not automatically label repeated changes as problematic.

---

## Historical Evidence Gaps

List information that could not be established.

Examples:

- No relevant commit history found
- Issue tracker unavailable
- Pull request metadata unavailable
- Commit messages do not establish intent
- Repository history is incomplete

---

## Historical Summary

Provide a concise summary answering:

1. What relevant history exists?
2. What does that history establish?
3. What does it suggest but not establish?
4. What historical context should the developer consider before approving the change?

---

# Rules

1. Do not modify project files.
2. Do not fabricate commits.
3. Do not fabricate issues.
4. Do not fabricate pull requests.
5. Do not fabricate dates.
6. Do not fabricate historical intent.
7. Do not fabricate test results.
8. Do not expose secrets.
9. Prefer actual Git evidence over assumptions.
10. Clearly distinguish direct evidence, derived conclusions, and inference.
11. Treat commit messages as evidence, not unquestionable truth.
12. Inspect actual diffs when necessary.
13. Pay attention to reverts and corrective changes.
14. Report unavailable historical information honestly.
15. Keep the investigation focused on the current developer change.
16. Do not modify the repository.
