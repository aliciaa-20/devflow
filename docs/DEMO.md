# DevFlow — 4 minute demo script

One narrative, one wow moment. Not a feature tour.

**The wow moment is at 2:00: DevFlow overruling the AI.** Everything before it
exists to set that up; everything after it pays it off. If you are running
short, cut from the middle, never from that beat.

---

## Before you start

```bash
# 1. Warm the analysis so nothing clones live on stage
devflow analyze https://github.com/pallets/flask "Refactor request context handling."

# 2. Confirm the watsonx response is cached (demo works with the network off)
grep -c . .devflow/watsonx-cache.json

# 3. Confirm the story is intact
devflow findings --top 3
devflow status
```

Checklist:

- [ ] Terminal font large enough to read at the back of a room
- [ ] `.devflow/watsonx-cache.json` exists (offline safety)
- [ ] Bob IDE open on the `resolver` mode, already signed in
- [ ] Bob segment pre-recorded as backup
- [ ] Flask checkout ready at a known path for `devflow validate`
- [ ] Screen not showing your `.env`

---

## 0:00–0:30 — The problem

> "I've been asked to refactor request context handling in Flask. I've never
> worked on Flask. Where do I even start?"

Show the repository. Hundreds of files. Say the real cost out loud:

> "Normally this is twenty minutes of grepping before I can even form an
> opinion — and I still won't know what I missed."

---

## 0:30–1:15 — One command

```bash
devflow analyze https://github.com/pallets/flask "Refactor request context handling."
```

Then:

```bash
devflow findings --top 3
```

Land this line:

> "Three risks, ranked. Nothing here is a model's opinion — every one of them
> is derived from the repository."

---

## 1:15–2:00 — Why, with proof

```bash
devflow explain risk:0:code
```

Point at the blast-radius tree:

> "`ctx.py` isn't risky because a model said so. **Twenty-one files import it**,
> and DevFlow parsed every one of those import statements out of the source.
> That's the tree."

Then the evidence key:

> "Every claim is marked. A star is something the repository proves. A circle
> is something DevFlow derived. A question mark is interpretation — and this
> finding says, in its own output, *no defect is established*. It's telling me
> what it doesn't know."

---

## 2:00–2:30 — THE WOW MOMENT

Stay on the `CONFIDENCE` block:

```
ranked #1 by        IBM watsonx.ai judgment
  High code risk due to wide import-proven blast radius of 21 files.
```

> "IBM Granite ranked this first — and it's reasoning over DevFlow's evidence,
> not over the source code. It never sees the source."

Now the constraint. Run:

```bash
devflow findings --json | head -30
```

> "Granite ranked ten findings. DevFlow had forty-three. The other thirty-three
> were appended **by DevFlow, deterministically**, and every single entry is
> labelled with who ordered it.
>
> If Granite had returned a finding id that didn't exist, DevFlow would have
> thrown it away and told you it did.
>
> **The model proposes. The repository decides.**"

---

## 2:30–3:15 — Bob, under supervision

```bash
devflow resolve risk:0:code
```

> "Approving generates Bob's investigation prompt from the finding's own
> evidence — I never have to re-explain the problem to the agent."

Show `bob_sessions/<id>/bob_prompt.md` briefly, then Bob IDE (`resolver` mode)
investigating in parallel across the four DevFlow skills.

When Bob proposes:

> "Nothing has been modified. That's a second human gate, not a formality."

```bash
devflow apply <resolution-id> <bob-proposal.md>
```

---

## 3:15–4:00 — Verification, and the payoff

```bash
devflow validate <resolution-id> --local-path <flask-checkout> \
  --result <bob-result.md> --test-command "pytest tests/test_reqctx.py"
```

> "Bob says RESOLVED. DevFlow doesn't take its word for it — it runs the tests
> itself."

```bash
devflow status
```

Point at the reconciliation line:

```
bob claimed        RESOLVED   matches DevFlow's verified result
devflow verified   RESOLVED
```

> "Those are two different facts on purpose. If the tests had failed, this
> would read **DISAGREES**, and DevFlow would have downgraded the result to
> VALIDATION FAILED regardless of what the agent claimed.
>
> That's the whole product: an agent that can write the fix, and a tool that
> can tell you when it's wrong."

---

## Closing line

> "DevFlow doesn't ask you to trust an AI with your codebase. It shows you what
> your repository proves, keeps a human on both sides of every change, and
> verifies the result itself."

---

## If something breaks

| Failure | Recovery |
|---|---|
| watsonx times out | Already cached — it replays. If asked, say so; the fallback is a designed path, not a patch |
| No network at all | `devflow analyze --no-watsonx` still produces everything but the ranking |
| Bob is slow or Bobcoins exhausted | Cut to the pre-recorded segment. **Say it is a recording** |
| Bob finds no defect | This is a *good* outcome — say: "it declined to invent work, and recommended a regression test instead" |
| Tests genuinely fail | Even better. Show `DISAGREES`. That is the thesis, live |

---

## Questions judges are likely to ask

**"How is this different from an AI code reviewer?"**
> Every fact is deterministic and traceable to a file, an import edge, or a
> commit. The model only orders findings; it cannot create one. And validation
> can contradict the agent.

**"Why not use watsonx Orchestrate?"**
> Our orchestration is a deterministic pipeline plus two human gates, because
> repository facts have to be reproducible. Moving that into a hosted workflow
> engine would add failure modes and remove nothing. We evaluated it and said
> no on purpose.

**"What does Bob actually do?"**
> Bob is the only component that writes code. It investigates in parallel
> across four DevFlow skills, proposes a focused fix, implements it after
> approval, and writes or updates tests. DevFlow owns the gates and the
> verification on both sides.

**"What are the limitations?"**
> Import parsing is Python-only today; other languages fall back to structural
> evidence. Impact seeding still starts from keyword relevance — the graph
> expands and justifies it but doesn't yet choose it. And measurement is on a
> small sample. We'd rather say that than overclaim.
