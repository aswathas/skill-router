# What we built, in plain language

*This page has no jargon in it. If you want the technical version, read the
[paper](../paper/skill-router.pdf) or the [architecture notes](ARCHITECTURE.md).*

---

## The problem

Modern coding agents come with a growing pile of **skills**: small instruction
bundles that tell the agent how to do one kind of job. Review code. Query a
database. Draft a blog post. Generate an image. Set up a spreadsheet.

Two things go wrong, and they are separate problems:

1. **Too many to read.** On the machine we tested, the agent could see 1,387
   skills. Listing them all in the prompt costs about 1.9 million tokens —
   roughly 2 million tokens of context spent on a table of contents before
   the agent does any work.
2. **Hard to pick the right one.** Even when you narrow the list down, a
   request like *"critique the structure of this module"* can plausibly match
   a dozen skills. Pick wrong and the agent burns a chunk of its context
   window reading a manual for the wrong job.

Most existing answers attack one half of this. We built both.

---

## What we built

Think of it as four parts that work together.

### 1. Hide what will never be needed

The agent only needs a handful of skills for any given job. One configuration
setting turns off three of the places where skills are stored, and a small
program moves the skills that live in the one folder the agent always reads
into a holding area. They are *moved*, not copied, so it costs no disk space
and any of them can be put back with one command.

**Result:** the agent sees **44 skills instead of 1,387**, and the cost of
listing them falls from about **1.92 million tokens to 89,200**.

### 2. Describe what each skill is actually for

This is the heart of the project, and it is hand-written rather than learned.

We wrote a **taxonomy**: a vocabulary of about 78 kinds of job (\"testing\",
\"code review\", \"research\", \"ecommerce\", \"image generation\"...). Every skill
gets tagged with the kinds of job it can genuinely do.

The important rule is that **a tag is a claim that has to be backed by
evidence**. We accept four kinds of evidence, strongest first:

- the skill ships a file named `reference/cart.md` — that skill really does
  handle carts;
- the skill's description says `unit test`;
- the skill's *name* contains a word like `browser`;
- the skill's name contains a required string, so a \"shopify\" capability only
  applies to skills named `shopify-*`.

We also built a **checker** that looks for tags the evidence does not support.
The trick is that the checker and the tagger use *exactly* the same rules. An
earlier version did not, and the checker called perfectly good tags
"unsupported" — its output was noise, and fixing that was part of the work.

### 3. Pick exactly one skill

The **router** takes a free-text request and returns one skill, with the
reasoning attached. It is a plain program — no neural network, no training.

It works in stages: work out which kinds of job the request names (a request
that says `unit test` is firmly about testing, while one that merely mentions
`auth` in passing is about something else); prefer the job mentioned *first*;
score every skill on how well its tags match; and use cost as a tie-breaker,
so a 9,000-token manual never gets loaded to do a 200-token job.

One rule took real effort to get right. The naive version of the cost filter
was \"pick the cheapest skill that covers the need\", and it kept deleting the
*best* match because a cheaper, sloppier one existed. The rule we shipped
only discards a skill when some other skill matches **at least as well** and
costs a fraction as much.

### 4. Learn from what actually happened

A hook watches each session. If a skill produced files that survived to the
end of the session, that skill was probably right. If the files it produced
were deleted, that skill was probably wrong. The scores accumulate into a
ledger, and a skill you keep rejecting is *demoted* — never banned, so it
stays reachable as a last resort.

---

## A request, start to finish

Take: *"research the realistic risks of migrating off postgres for a small
team\"*

1. **Gate.** Only 44 skills are visible. Most of the library never entered
   the conversation.
2. **Understand.** The request names `research` and `database`. `research`
   comes first, so that is the intent; `database` is context.
3. **Match.** Every visible skill is scored by how well its tags cover that
   intent. A handful of candidates survive.
4. **Cost check.** If one of them is far more expensive than an equally good
   match, it is dropped.
5. **Answer.** One skill is chosen and *loaded*, not merely reported — the
   agent gets the instructions, not a name it has to go and look up.
6. **Remember.** Whatever happens to the files that skill produces feeds
   back into the ledger.

---

## How we know it works

We wrote **298 test requests** — written the way a person would actually type
them, deliberately avoiding the exact words our taxonomy uses, so the test
cannot simply be memorised. Each request has a right answer.

We compared the router against four alternatives, including a real, textbook
retrieval system (Okapi BM25, the algorithm behind most search engines):

| | picks the right *kind* of job | picks the right *exact* skill |
|---|---|---|
| Random guessing | 1% | 0% |
| A real search engine (BM25) | 47% | 40% |
| The old system, faithfully rebuilt | 61% | 21% |
| **Our router** | **85%** | **40%** |

Two things worth noticing:

- **Random guessing is 1%.** With 78 kinds of job, guessing is hopeless, so
  the 85% is a real result, not a small edge.
- **On exact-skill choice, BM25 ties us (40% each).** We report that rather
  than the metric that flatters us. The taxonomy buys you *knowing what kind
  of job this is*; it does not by itself pick the single best tool for that
  job.

The second experiment is the one we think matters most. We swapped the
taxonomy for the version we had *before* the repair, changing nothing else —
same router, same test set, same cost rules — and re-ran everything:

**66% → 85%.** The vocabulary, not the ranking, was the thing that was
broken. That is a claim we could only make because we measured it.

---

## What surprised us

We went looking for problems and found some, which we think says more about
the work than a clean sweep would.

- **The learning loop did nothing measurable.** We had 19 skills with enough
  history to score, and the difference was indistinguishable from noise. We
  believe the mechanism is sound but that it needs far more evidence before
  it can move a number. We report it as a null result.
- **Accuracy costs tokens.** The router spends about 2,900 tokens per call
  against the old system's 600. We measured the trade-off curve: a 1,000-token
  budget recovers 60% of the cost for a loss of 2.3 points of accuracy.
- **We were over-optimistic on our own test set.** We repaired the taxonomy
  using half the test requests (that half now scores 96%); the half we never
  touched scores 74%. The 22-point gap is the size of the optimism we cannot
  rule out elsewhere, so we publish it.
- **When a request avoids our vocabulary, the router is much weaker.** On the
  hardest subset it drops to 36%, below half its overall score. It recognises
  evidence; it does not understand.

---

## What it is not

It is worth being blunt about the limits, because this is a small study on one
machine with one author:

- No learned model. The router is a deterministic program, which is exactly
  why it cannot be trained the way tool selection usually is.
- No human-preference study. The test set is our own judgement of what each
  request meant.
- The taxonomy was written by one person for one collection of skills. It
  does not transfer to a different library without that work.
- We cannot yet `revert` a skill or run its full lifecycle; two operations in
  the host are unavailable in this runtime.

---

## Where to go next

The obvious step is a bigger, human-judged evaluation. The second is a
smaller, sharper vocabulary that says what it is for and nothing more. Both
are in the [paper](../paper/skill-router.pdf).

We also handed the failure analysis to a separate program and asked it to fix
the word list. It reached the same conclusion we did, on its own: the wording
was missing, not the matching. Its fix changed 2 of 298 test cases and broke
none. That is too small to be proof, so we kept it as a recorded next step
instead of shipping it. See [iteration3](../evals/iteration3.md).

Everything here is reproducible: the test set, the scoring code, the
statistics, and the paper's tables are all in this repository, and the
commands to re-run them are in [REPRODUCE.md](REPRODUCE.md).
