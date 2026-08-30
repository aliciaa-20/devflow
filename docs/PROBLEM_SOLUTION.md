# Problem + Solution

## The Problem

Before making or reviewing a change in an unfamiliar or evolving repository, a
developer must manually reconstruct context: which files matter, what imports
what, which tests cover the change, what history says, and what could break.
That work is slow, fragmented, and easy to get wrong. Existing AI review tools
mostly compress this into an unverifiable opinion: a model reads a diff and
tells you what it thinks, with no way to check its reasoning against the
repository.

**Target users:** developers picking up a change in a codebase they don't
own — onboarding engineers, cross-team contributors, reviewers.

## The Solution

DevFlow reconstructs that context directly from the repository and turns it
into an evidence-backed **Change Impact Map** and **Developer Report**,
instead of an unverifiable opinion.

Given a repository URL and a change description, DevFlow clones the
repository, classifies its files, and parses real static import edges into a
**Repository Knowledge Graph** — what exists in the codebase. It determines
which files are relevant to the change, walks the import graph to find every
file that transitively depends on them, and reads git history for the
affected area. Impact and risk findings follow from that evidence — severity
is scaled by real blast radius, not guesswork — and every finding is labelled
`DIRECT_EVIDENCE`, `DERIVED_RELATIONSHIP`, or `INFERENCE` so a developer sees
how firmly the repository supports each claim.

IBM watsonx.ai (Granite) then ranks the findings DevFlow already produced. Its
authority is bounded structurally: it cannot introduce a finding, remove one,
or change a severity — it can only order them, and any id it returns that
DevFlow didn't produce is discarded.

A developer then selects one finding and explicitly approves it for
resolution — the first of two required human approvals. DevFlow generates a
prompt from the finding's own evidence and hands it to IBM Bob, which
investigates and proposes a minimal fix. Only after a second approval is the
fix applied. DevFlow then runs the real test command and a real `git diff`
itself, rather than trusting Bob's claim — if Bob reports the finding
resolved but tests actually fail, DevFlow downgrades the outcome to
`VALIDATION_FAILED`.

## What Makes DevFlow Different

Most AI code tools ask you to trust a model's opinion about your code.
DevFlow inverts that: every repository fact — file classification, import
edges, test coverage, git history — is computed by deterministic Python, not
a model. The model's role is bounded to judgment it's suited for (ranking,
investigation, proposing a fix), and every output is checked against ground
truth rather than trusted at face value. The tool contradicts the agent when
evidence disagrees with its claim.

## Practical Value

A developer gets, in one command, what would otherwise take minutes of manual
grepping: a ranked list of what a change touches, why it matters, what tests
already cover it, and a human-supervised path to a verified fix — with every
claim traceable to something the repository actually proves.
