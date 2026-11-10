# Iteration 3: an independent agent's taxonomy proposals

An agent was given the **dev-half failure diagnosis** and nothing else, and
proposed keyword repairs for four capabilities. The proposals are in
`evals/agent-repair-proposals.json`.

They were never applied to the shipped taxonomy: the evaluation pipeline was
frozen once the ablation had been measured end to end, and changing the
taxonomy would have invalidated every number in the paper.

`evals/iteration3.py` applies them in a throwaway state directory, rebuilds
the registry with the proposed taxonomy, and re-runs the shipped router. It
does not touch the shipped system or the committed results.

## Result

| split | n | shipped | proposed | delta | discordant | McNemar p |
|---|---|---|---|---|---|---|
| overall | 298 | 0.849 | 0.856 | +0.007 | 2 / 0 | 0.50 |
| dev (used for the original repair) | 147 | 0.959 | 0.966 | +0.007 | 1 / 0 | 1 |
| test (held out from the original repair) | 151 | 0.742 | 0.748 | +0.007 | 1 / 0 | 1 |

Two cases changed. Both were fixed; none broke.

| case | request | shipped | proposed | split |
|---|---|---|---|---|
| A023 | *critique the structure of this module* | `21st-ui-build` | `egm-review` | dev |
| B180 | *prove it works before we call it done* | `mcode-tools-master` | `verification-before-completion` | test |

## What this does and does not show

It **replicates the paper's central diagnosis**. Given only the dev-half
failures, an independent agent independently concluded that the missing thing
was vocabulary — natural phrasing absent from the keyword lists — and not
ranking. It found the same failure mode we found, from the same evidence.

It does **not** clear the bar of significance. Two cases out of 298 is a
delta of 0.007, with a McNemar p of 0.50 and a paired bootstrap interval on
the MRR difference that includes zero.

**We did not adopt it.** Applying it would move two cases and invalidate
every number in the paper to do it. The shipped taxonomy stays as it is, and
this is recorded as the next measured iteration instead.

## Reproduce

~~~bash
cd evals
python iteration3.py     # writes iteration3.json
~~~
