# Evaluation

This is a measurement methodology, not a set of results. No experiments have
been run to produce the numbers below; every value that would require running
one is marked `[TO BE MEASURED]`.

## Evaluation Question

Does DevFlow reduce the effort required to understand the consequences of a
change in an unfamiliar repository, compared to a developer working without
it?

## Controlled Scenario

- **Repository:** a real, moderately sized open-source repository unfamiliar
  to the participant (e.g. the Flask repository already used in
  `bob_sessions/` and `docs/DEMO.md`).
- **Task:** given a one-sentence change description (e.g. "Refactor request
  context handling"), identify: (a) which files the change would plausibly
  touch, (b) which of those are imported by other files (blast radius), (c)
  which existing tests cover the affected area, and (d) at least one
  concrete risk worth reviewing before merging.
- **Participants:** developers without prior familiarity with the target
  repository.

## Manual Baseline

The participant performs the task above using only the repository itself:
`grep`/IDE search, reading imports by hand, `git log`/`git blame`, and
running the test suite manually to find relevant tests. Time is recorded
from task start to a written answer for (a)-(d). No AI assistance is used in
this condition.

## DevFlow Workflow

The participant runs:

```bash
devflow analyze <repo-url> "<change description>"
devflow findings --top N
devflow explain <finding-id>
```

and answers the same (a)-(d) using DevFlow's output. Time is recorded from
the first command to a written answer.

## Measurements

- **Time to answer:** manual baseline vs. DevFlow workflow, per participant.
- **Coverage:** whether the participant's answer, in each condition,
  identifies the same affected files, blast-radius dependents, and covering
  tests that DevFlow's import-graph evidence independently establishes as
  ground truth.
- **Evidence traceability:** whether the participant can, after using
  DevFlow, point to the specific repository fact (import edge, test file,
  git commit) backing each claim they made — a proxy for whether the tool
  produced verifiable understanding rather than just a faster guess.
- **False confidence:** cases where a participant's manual-baseline answer
  states something DevFlow's evidence contradicts (e.g. claiming a file is
  untested when a covering test exists).

## Results

`[TO BE MEASURED]`

## Interpretation

`[TO BE MEASURED]` — to be written after results are collected, addressing
specifically whether any time reduction came with equal or better coverage
(a faster wrong answer is not an improvement).

## Limitations

- A single-repository, single-change-type scenario does not establish
  general effort reduction across languages, repository sizes, or change
  types; DevFlow's import-graph evidence is currently strongest for Python
  (see `docs/LIMITATIONS.md`).
- Time-to-answer is a proxy for developer effort, not a direct measurement
  of decision quality or downstream defect rate.
- Participant unfamiliarity with the target repository is difficult to
  fully control for (prior exposure to similar codebases, frameworks, or
  patterns will vary).
- This methodology does not yet evaluate the Bob resolution workflow
  (Phase 8) end to end; only one recorded session in `bob_sessions/`
  completed the full gate-to-validation cycle, and its validation test
  command was a placeholder rather than a real project test run (see
  `docs/IBM_USAGE.md`), so no resolution-quality measurement can be made
  from existing evidence.
