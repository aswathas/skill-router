# -*- coding: utf-8 -*-
"""Build the research paper: ACM-style LaTeX source and a PDF rendering.

One content definition, two artefacts. The .tex is canonical; the PDF is
rendered from the same content with reportlab because this machine has no
LaTeX toolchain. Anyone with acmart can compile the .tex to the same paper.
"""

import json
import pathlib
from xml.sax.saxutils import escape

HERE = pathlib.Path(__file__).resolve().parent

TITLE = "Capability Routing for Agent Skill Libraries"
SUBTITLE = ("A taxonomy, a router, and an evidence-driven learning loop "
            "for over 4,200 installed skills")

AUTHORS = ["Aswath A S"]
AFFIL = ["Independent researcher"]

ABSTRACT = (
    "Coding agents increasingly ship with large libraries of skills: reusable "
    "instruction bundles that each describe one kind of job. Surfacing every "
    "skill in the prompt is unaffordable, and choosing the wrong one wastes "
    "the context window and the user's time. We present a capability-routing "
    "system for agent skill libraries, built and evaluated on one machine "
    "with over 4,200 installed skills. The system has four coupled parts: a "
    "host-level catalog gate that hides skills the agent never needs, a "
    "hand-curated capability taxonomy with evidence-based tagging, a router "
    "that resolves a free-text need to exactly one skill, and a learning loop "
    "that scores skills from what actually happens in a session rather than "
    "from the request text. The router reaches 0.849 capability top-1 "
    "accuracy against 0.614 for a faithfully reimplemented pre-fix matcher "
    "and 0.473 for Okapi BM25 over skill descriptions, and raises an "
    "on-topic rate from 0.460 to 0.799, while the runtime catalog falls from "
    "1,387 skills to 44 and the catalog listing cost from 1.92M tokens to "
    "89.2K. We make the taxonomy, not the ranker, the object of study: an "
    "error analysis shows that 98 of 101 failures were cases where the "
    "request never named the expected capability, and repairing the taxonomy "
    "on one half of the benchmark lifts accuracy on the held-out half from "
    "0.556 to 0.742, and over the whole benchmark from 0.661 to 0.849 "
    "(p = 3.2e-15). We also report three negative results: the "
    "outcome ledger does not measurably improve routing at the scale of our "
    "evidence, BM25 ties the full router on exact-skill selection, and "
    "per-invocation token cost rises as accuracy rises."
)

KEYWORDS = ("agent skills; tool selection; capability routing; context "
            "engineering; token efficiency; taxonomy design")

SECTIONS = []

def S(title, *paras, **kw):
    SECTIONS.append({"title": title, "paras": list(paras), **kw})

S("Introduction",
  "An agent skill is a small, self-contained instruction bundle: a markdown "
  "file that tells the agent how to perform one kind of job, optionally with "
  "reference files, scripts and assets. Skills are the unit of reuse in "
  "modern coding agents. They are also cheap to write and expensive to "
  "carry. A machine that installs skills from marketplaces, from plugins and "
  "from the user's own collection accumulates them faster than any agent can "
  "read them.",

  "The obvious answer, and the one most agent hosts take, is to expose every "
  "skill to the model and let it choose. This works until it does not. The "
  "catalog itself becomes a fixed cost on every single request. On the "
  "machine studied here, 1,387 skills were visible to the agent, and the "
  "skills that the agent actually needed were a tiny minority of them.",

  "We built a capability-routing system to fix this, and we report it with "
  "an evaluation rather than an anecdote. The contributions are:",

  "A measurement of the problem. We quantify the cost of a large catalog "
  "and show that the useful subset is small.",

  "A taxonomy design that treats capability tags as claims that need "
  "evidence. We define four evidence channels with different strengths and "
  "we make the auditor and the tagger agree on what counts as evidence. "
  "Before the repair, 845 of 1,318 local and plugin skills were unreachable "
  "by construction.",

  "A router that resolves a need to exactly one skill. The router's design "
  "follows a simple principle: the cheapest skill that fully covers the need "
  "wins. Getting there required replacing three naive mechanisms, each of "
  "which we document because they are common.",

  "An evidence-driven learning loop that scores skills from what a session "
  "actually did with them. A skill is good when the files it produced "
  "survived the session, and bad when they were deleted.",

  "An error analysis that says where the remaining failures live, and a "
  "repair that follows from it. Categorising the failures by whether the "
  "request named the expected capability at all showed that 98 of 101 "
  "failures were inference misses and only three were ranking misses. "
  "Repairing the taxonomy on one half of the benchmark lifted accuracy on "
  "the held-out half from 0.556 to 0.742, and over the whole benchmark "
  "from 0.661 to 0.849.",

  "Three negative results, stated plainly. The learning loop does not "
  "measurably improve routing at our scale; a textbook BM25 retriever ties "
  "the full router on exact-skill selection; and routing accuracy and "
  "per-invocation token cost move in opposite directions.",

  "The rest of the paper describes the system, the evaluation methodology, "
  "and the results, and closes with the limits of what we measured.")

S("Background",
  "Agent hosts differ in how they surface skills, but the common shape is a "
  "registry. Each installed skill contributes an entry with a name, a "
  "description and, often, the full body of the skill. The catalog is either "
  "injected into the system prompt or offered as a searchable tool. Both "
  "forms pay for the whole catalog, and both make the model's task of "
  "selection harder as the catalog grows.",

  "Three properties of skill catalogs make the problem different from "
  "ordinary retrieval. First, the catalog is mostly irrelevant to any given "
  "request: the useful skills for a code review are a small, stable subset. "
  "Second, description text is short and highly lexical, so a bag-of-words "
  "matcher is a surprisingly strong baseline and a surprisingly hard thing to "
  "beat. Third, the cost that matters is not the cost of the right skill, "
  "which is paid once, but the cost of the catalog, which is paid on every "
  "request.",

  "This suggests a division of labour. The catalog problem is a gating "
  "problem: remove what is not needed before the model ever sees it. The "
  "selection problem is a ranking problem: given what remains, choose one "
  "skill, and choose a cheap one.")

S("Related Work",
  "Tool selection. Much of the prior work on tool choice is about learning "
  "when to call a tool rather than which of thousands to call. Toolformer "
  "learns which API calls to emit; Gorilla and ToolLLM evaluate and train "
  "models for API selection; ReAct and Reflexion structure the loop in which "
  "a selection is made and then judged by what follows. Our setting differs "
  "in two respects. The candidate space is instruction bundles rather than "
  "API functions, and the selection is made by a deterministic program "
  "rather than by the model, so the router cannot be trained by gradient "
  "descent. We borrow Reflexion's central intuition, that the quality of a "
  "trajectory is observable after the fact, and apply it to skill selection "
  "instead of to reasoning steps.",

  "Retrieval and lexical matching. Our strongest baseline is a lexical "
  "matcher in the style of BM25 over skill descriptions, and it is "
  "competitive. We keep it in the evaluation rather than hiding it, because "
  "the honest finding is that a large part of routing is lexical matching "
  "and the router's contribution is concentrated in a smaller number of "
  "cases.",

  "Context efficiency. A line of work argues that long contexts degrade "
  "model performance, not just cost: the Lost in the Middle study shows "
  "that relevant information in the middle of a long context is used less "
  "reliably, RULER measures effective context length against nominal "
  "length, and recent work on context rot documents degradation with "
  "irrelevant material. The Chroma context-rot study is the clearest "
  "statement of the practical version of this: a catalog of mostly "
  "irrelevant entries is worse than a small one, not merely more expensive. "
  "Our catalog gate is an engineering response to that finding.",

  "Memory and context management. Letta and MemGPT treat conversation state "
  "as something to be actively managed rather than passively accumulated, and "
  "the token-guard and compaction tools that many agent hosts ship are "
  "practical versions of the same idea. The learning loop in this paper sits "
  "in this family: it decides what is worth keeping, but it keeps "
  "preferences about capabilities rather than facts about tasks.",

  "Capability taxonomies. The router needs a vocabulary of job kinds. We "
  "build it explicitly, in the style of WordNet-style lexical resources, "
  "and we treat it as a maintained artefact with an auditor rather than as "
  "a one-off annotation pass. Section 4.2 explains why that distinction "
  "mattered more than expected.")

S("The System",
  "The system has four coupled parts. The catalog gate and the parking "
  "mechanism decide what the model can see. The taxonomy and the registry "
  "decide what each skill is good for. The router turns a free-text need into "
  "one skill and loads it. The learning loop turns what happened in past "
  "sessions into scores that feed back into the router. A fifth part, the "
  "native skill-evolution channel, lets a broken or missing skill be "
  "reported from the command line; it was present in the host but "
  "unreachable, and repairing it was a precondition for the rest of the work.")

S("Catalog gating and parking",
  "The host reads three external skill roots plus its own data directory, and "
  "exposes all of them by default. A single configuration key disables the "
  "three external roots, which removes 1,343 of the 1,387 visible skills "
  "without touching the data directory root, which the host always scans.",

  "Skills that live in the always-scanned root cannot be gated by "
  "configuration. They are parked instead: the directory is moved out of the "
  "scanned root into a holding directory, with a manifest recording what was "
  "moved so that any single skill can be restored. Parking is a move, not a "
  "copy, so it costs no disk space and is reversible by moving the "
  "directory back.",

  "The residual 44 skills are the token-control skills, the router itself, "
  "the forge family and the native evolution channel. The catalog listing "
  "cost falls from an estimated 1.92M tokens to 89.2K, a 95.4% reduction, "
  "and the visible catalog falls from 1,387 entries to 44, a 96.8% "
  "reduction.")

S("The capability taxonomy",
  "A capability tag is a claim that a skill provides a particular kind of "
  "job. We treat every tag as a claim that needs evidence, and we define "
  "four evidence channels of decreasing strength.",

  "Files. A skill that ships reference/critique.md critiques. Filename stems "
  "are matched exactly, never as substrings, so that a skill shipping "
  "type.md does not match every TypeScript skill.",

  "Strong keywords. A multi-word phrase in the description, such as write "
  "documentation or unit test. A phrase is strong evidence because it is "
  "specific.",

  "Weak keywords. A single word in the skill's name, such as browser or "
  "review. Weak evidence, and the source of most tagging errors.",

  "Exact and required keywords. Some names must match a whole token (cli must "
  "not match clickmeeting) and some capabilities only apply to skills whose "
  "name contains a given string (the automation capability only applies to "
  "skills named ... automation).",

  "Two properties of this design are worth stating because they were learned "
  "the hard way. First, matching must be done per name token, not by raw "
  "substring. Substring matching made form match transform, test match "
  "latest, git match digit and lock match block, and every one of those "
  "errors produced a wrong skill at routing time. Second, a single common "
  "noun used as a strong keyword is not strong evidence: process alone made "
  "one capability cover 159 of 1,318 skills, which is no coverage at all.",

  "The pre-fix system had a subtler defect. The auditor that reported stale "
  "tags and the tagger that produced them used different definitions of "
  "evidence, so the auditor called correct tags stale. The auditor now uses "
  "the same rules as the tagger, which is what makes its output actionable "
  "rather than merely alarming.")

S("The router",
  "The router takes a free-text need and returns exactly one skill, "
  "together with the reason it was chosen. It resolves and then acts: the "
  "chosen skill's body is loaded, not merely reported. Scoring proceeds in "
  "five stages.",

  "Capability inference. The request is matched against every capability's "
  "keyword lists. A strong phrase counts double a weak name word. This "
  "matters because a request typically names its object strongly and its "
  "context weakly: write unit tests for the auth module is a request for "
  "testing, and auth is what the tests are about. Under flat inference an "
  "auth-flavoured skill outranked the testing skill.",

  "Head capability. Among the capabilities the request names, the one "
  "mentioned first carries the intent. Generate an illustration for the "
  "landing page wants an illustration, on a landing page. When two "
  "capabilities are named at the same position, the more specific one wins, "
  "measured by how many skills carry it.",

  "Capability match. A skill scores by the capabilities it carries that the "
  "request also names. Primary capabilities dominate; a capability named only "
  "in passing contributes little.",

  "Name relevance and ledger. The score of a skill whose name shares a word "
  "with the request, and the skill's learned quality score, both act as "
  "tie-breakers. A negative ledger score is applied as a capped penalty "
  "rather than a ban, so a rejected skill stays reachable as a last resort.",

  "Cost gate. The final selection prefers the cheapest skill that covers the "
  "need. The naive form of this rule, comparing a candidate against the "
  "cheapest cover in the list, deleted the better match: a 3.5K-token skill "
  "that matched the request exactly died because a 64-token skill that "
  "matched it loosely was cheaper. The rule we ship is Pareto: a skill is "
  "too expensive only if some other skill matches at least as well and costs "
  "a fraction of it. A hard budget is also available as an option, and we "
  "report its effect in Section 7.4.")

S("The learning loop",
  "The router is told which skills worked by watching what happens in a "
  "session. A plugin hook fires on every user prompt and after every tool "
  "use. When a skill is loaded, the hook remembers it. When the session then "
  "edits or writes a file, that is an accept: the skill's output was good "
  "enough to build on. When the session then deletes a file that the same "
  "skill had produced, that is a reject.",
  "The rule is deliberately conservative. A delete that does not target a "
  "file the skill produced is not evidence against that skill, and neither "
  "is a file the skill never touched. An early version counted any delete "
  "in the window as a rejection, which produced systematically pessimistic "
  "scores. The evidence rules are also enforced in a batch learner that "
  "replays stored transcripts, which is how the corpus of 304 sessions was "
  "scored and how 19 skills acquired a quality score.",
  "The hook is a failure-tolerant boundary. Every path exits zero. A hook "
  "that has no opinion must never block the agent.")

S("The native evolution channel",
  "Hosts expose a mechanism for reporting that a skill is missing a step or "
  "uses a wrong default, and for turning such reports into improved skills. "
  "On this machine the mechanism existed but could not be reached: its calls "
  "are not top-level JSON-RPC methods but live on a separate service "
  "contract, reachable only through a transport method that the command line "
  "did not speak. The repair was a small client that implements the "
  "transport, plus the instruction bundle the runtime asked for at startup "
  "and which had never existed. Signals and proposals can now be reported, "
  "listed and cancelled from the shell, verified end to end against a live "
  "host.",
  "Two operations, reverting and running the lifecycle, remain unavailable: "
  "the embedded runtime answers them with a hard error. We report this as a "
  "limit of the environment rather than of the design.")

S("Evaluation",
  "We ask four questions. RQ1: how well does the router select a skill, and "
  "how does it compare with weaker selection strategies? RQ2: how much of "
  "the gain comes from each component? RQ3: what does the system cost in "
  "tokens, and what is the shape of the accuracy-cost frontier? RQ4: what "
  "happens to the catalog and the taxonomy?")

S("Benchmark",
  "We constructed 242 requests labelled by the capability they should "
  "resolve to, covering 61 of the 78 capabilities, and authored 51 further "
  "requests together with the single unambiguous skill they should resolve "
  "to. Of the 293 authored requests, 58 name exactly one skill and therefore "
  "form the strict subset. A further 5 cases were extracted from stored "
  "sessions, giving 298 cases in total and 63 strict cases.",
  "Two properties protect the benchmark from circularity. The requests were "
  "written in the language a person would type, and they deliberately avoid "
  "the taxonomy's exact keyword strings where a natural paraphrase exists; "
  "the harness computes a lexically isolated subset, defined as the cases "
  "whose request shares no exact keyword string with the expected "
  "capability's lists, and reports accuracy on that subset separately. And "
  "the strict subset names one skill rather than a category, so it measures "
  "selection rather than classification.",
  "The benchmark is split in half by a stable hash of the case id. Every "
  "taxonomy change reported in this paper was made using the dev half alone, "
  "so the test half is a held-out measurement of the repair. We say plainly "
  "that this is not a clean held-out evaluation of the system as a whole, "
  "because the router's rules and the taxonomy's structure were both "
  "designed while every case was visible. It is a held-out measurement of "
  "one specific intervention.",
  "We attempted the obvious alternative: using the user's own history as "
  "ground truth. Across 304 transcripts holding 757 user messages there "
  "were 67 skill invocations, and only 5 request-to-skill pairs could be "
  "associated with any confidence, because skill loads are preceded by long "
  "tool sequences. That scarcity is itself a finding: usage-based ground "
  "truth is rare, which is why the system learns from outcomes rather than "
  "from request-to-skill pairs, and why a hand-labelled benchmark is needed.")

S("Systems compared",
  "We compare eight systems. Random samples uniformly from the catalogue. "
  "Name-only ranks by name-word overlap. BM25 is Okapi BM25 over skill name "
  "and description with no taxonomy, no ledger and no cost gate: a real "
  "retrieval baseline, and the one a reviewer is right to ask for. "
  "Keyword-substring is a faithful reimplementation of the pre-fix router: "
  "flat strong-plus-weak inference by raw substring, substring name and "
  "description hits, additive capability overlap, and a cost gate comparing "
  "against the cheapest cover. No-ledger is the shipped router with the "
  "outcome ledger neutralised. No-cost-gate is the shipped router without "
  "the Pareto gate. Full-budget is the shipped router restricted to skills "
  "costing at most 2,000 tokens whenever such a skill covers the need. Full "
  "is the shipped router.")

S("Metrics",
  "Capability top-1 is the share of cases where the chosen skill carries "
  "the expected capability. Capability top-3 and MRR extend this to a ranked "
  "list. Strict top-1 is the share of strict-subset cases where the chosen "
  "skill is exactly the expected one. On-topic rate is the share of cases "
  "where at least a fifth of the request's content words appear in the "
  "chosen skill's name or description; it consults no taxonomy at all, so "
  "it is comparable across every system including random. Cost is the "
  "on-invoke token cost of the chosen skill, as mean and median.")

S("Threats to Validity",
  "The benchmark is small and written by one author, so its distribution of "
  "requests reflects one person's habits, and its labels reflect one "
  "person's reading of what each request means. Capability labels are the "
  "weaker of the two labelling schemes: a skill can carry the expected "
  "capability and still be a poor answer, which is why we report the strict "
  "subset and the taxonomy-independent on-topic rate alongside it. The "
  "evaluation runs against a registry of 4,225 skills on one machine with "
  "one catalogue of third-party skills, so the results should not be read as "
  "generalising to other collections. The learning loop is evaluated with "
  "only 19 scored skills, which is too few to measure its effect, and we "
  "report that as a null result rather than a positive one.")

S("Results",
  "Table 1 gives the headline numbers over all 298 cases, of which 63 "
  "carry a single expected skill. The remaining tables give the "
  "significance of the differences, the intervals around the estimates, the "
  "lexically isolated subset, the accuracy-cost frontier, the error "
  "analysis and the system-level effects.")

S("Limitations",
  "The evaluation is one machine, one catalogue of third-party skills and one "
  "author. The benchmark contains 293 authored requests and 63 strict cases; "
  "the strict subset, which is the metric we trust most, is small.",
  "Capability labels are coarse. A skill can carry the expected capability "
  "and still be a poor answer. There is no human-preference study, and that "
  "would be the natural next step.",
  "The audit numbers are constructive rather than causal. We repaired the "
  "auditor so that it uses the same evidence rules as the tagger, and the "
  "count of unsupported tags went to zero because the definition changed, "
  "not because 78 bad tags were individually found and fixed. The honest "
  "statement is that the two tools now agree, and that they did not before.",
  "The taxonomy repair was guided by failures on the dev half, so the dev "
  "half is no longer an unbiased estimate of accuracy. The test half is, and "
  "we report it, but the gap between them is the size of the optimism we "
  "cannot rule out elsewhere.",
  "The learning loop is evaluated with 19 scored skills. Its null result is "
  "a statement about the amount of evidence available, not proof that the "
  "mechanism cannot work.",
  "Two native evolution operations, reverting a skill and running its "
  "lifecycle, are unavailable in the embedded runtime and could not be "
  "evaluated.",
  "The catalog gate is host-specific. It relies on a configuration key "
  "whose name and semantics are properties of this host, not a standard.")

S("Conclusion",
  "Routing a large agent skill library is mostly a gating problem and a "
  "ranking problem, and treating it as either one alone leaves value on the "
  "table. Gating alone cuts the visible catalogue by 97%. Ranking alone, "
  "with a careful taxonomy, lifts capability accuracy from 0.614 to 0.849 "
  "against a faithful reconstruction of the pre-fix matcher.",
  "The load-bearing part is the taxonomy, and we now have the measurement to "
  "say so rather than the assertion. With the router, the benchmark and the "
  "cost gate held fixed, replacing the taxonomy's keyword lists with a "
  "repaired set moves accuracy from 0.661 to 0.849. The error analysis that "
  "motivated the repair says the same thing from the other side: before it, "
  "98 of 101 failures were requests that never named the expected "
  "capability, and only three were ranking errors.",
  "The most useful negative results are that the outcome ledger does not yet "
  "earn its place in the router, that a textbook BM25 retriever ties the "
  "full router when the question is which exact skill to load, and that "
  "accuracy and token cost pull against each other. Each is a statement "
  "about the evidence available at this scale rather than about the design, "
  "and all three point at the same next step: a larger, human-judged "
  "evaluation.",

  "One further check supports the diagnosis. We handed the dev-half failure "
  "analysis to an independent agent and asked it for keyword repairs, and "
  "it independently concluded that the missing thing was vocabulary rather "
  "than ranking, and proposed repairs for four capabilities. Applied to the "
  "shipped system they fixed two of 298 cases and broke none, which "
  "replicates the finding without clearing the bar of significance: we "
  "report the proposal as the next measured iteration rather than adopting "
  "it, and the shipped taxonomy is unchanged.")

# ---------------------------------------------------------------------------
# The results tables are derived from the evaluation artefacts, so the paper
# cannot drift from the harness that produced the numbers. Re-run
# evals/run_eval.py and rebuild to refresh them.
# ---------------------------------------------------------------------------
EVALS_DIR = HERE.parent / "evals"
RESULTS_JSON = EVALS_DIR / "results.json"
SYSTEM_METRICS_JSON = EVALS_DIR / "system-metrics.json"

SYSTEM_LABELS = [
    ("random", "random"),
    ("name_only", "name-only"),
    ("keyword_substring", "keyword-substring (pre-fix)"),
    ("no_ledger", "no-ledger"),
    ("no_cost_gate", "no-cost-gate"),
    ("full_budget", "full-budget (2K)"),
    ("full", "full (shipped)"),
]


def _f(x, nd=3):
    return ("%." + str(nd) + "f") % x


def _i(x):
    return "{:,}".format(int(round(x)))


def _routing_table(sysm):
    rows = [["system", "cap top-1", "cap top-3", "MRR", "strict top-1",
             "on-topic", "mean tok", "median tok"]]
    for key, label in SYSTEM_LABELS:
        s = sysm[key]
        rows.append([label, _f(s["cap_top1"]), _f(s["cap_top3"]), _f(s["mrr"]),
                     _f(s.get("strict_top1", 0.0)), _f(s.get("on_topic", 0.0)),
                     _i(s["mean_cost"]), _i(s.get("median_cost", 0))])
    return rows


def _isolation_table(sysm):
    """Accuracy on the lexically isolated subset, under both definitions.

    Which cases count as isolated depends on the keyword lists used to
    define the subset, so the table shows both: the shipped taxonomy's
    lists and the pre-repair lists. Every system is scored on the same
    subset within each column pair.
    """
    iso = ANALYSIS.get("isolation", {})
    shipped = iso.get("shipped_taxonomy", {})
    pre = iso.get("pre_repair_taxonomy", {})
    if not shipped:
        rows = [["system", "n", "top-1", "top-3"]]
        for key, label in SYSTEM_LABELS:
            s = sysm[key]
            if "iso_n" not in s:
                continue
            rows.append([label, str(s["iso_n"]), _f(s["iso_top1"]),
                         _f(s["iso_top3"])])
        return rows
    n_ship = str(shipped.get("n", ""))
    n_pre = str(pre.get("n", ""))
    rows = [["system", "shipped lists (n=" + n_ship + ")", "top-1", "top-3",
             "pre-repair lists (n=" + n_pre + ")", "top-1", "top-3"]]
    for key, label in SYSTEM_LABELS:
        a = shipped.get("systems", {}).get(key)
        b = pre.get("systems", {}).get(key)
        if not a and not b:
            continue
        rows.append([
            label,
            _f(a["cap_top1"]) if a else "-",
            _f(a["cap_top3"]) if a else "-",
            _f(b["cap_top1"]) if b else "-",
            _f(b["cap_top3"]) if b else "-",
        ])
    return rows


def _system_table():
    m = json.loads(SYSTEM_METRICS_JSON.read_text(encoding="utf-8"))
    cat, tax, reg = m["runtime_catalog"], m["taxonomy"], m["registry"]
    return [
        ["quantity", "before", "after"],
        ["skills visible to the agent",
         "{:,}".format(cat["before_gate"]), "{:,}".format(cat["after_gate"])],
        ["catalog listing cost (tokens, est.)",
         "{:,}".format(cat["listing_tokens_full_estimate"]),
         "{:,}".format(cat["listing_tokens_now"])],
        ["capabilities in the taxonomy",
         str(tax["capabilities_before"]), str(tax["capabilities"])],
        ["skills no capability could reach",
         str(tax["unroutable_before"]), str(tax["unroutable_now"])],
        ["tags unsupported by their evidence",
         str(tax["stale_tags_before"]), str(tax["stale_tags_now"])],
        ["skills in the registry", "4,098", "{:,}".format(reg["total"])],
    ]


def _significance_table():
    rows = [["baseline", "full only", "base only", "MRR diff",
             "CI (cases)", "CI (clust)", "p", "p (Holm)"]]
    sig = ANALYSIS.get("significance", {})
    for name, v in sorted(sig.items(),
                          key=lambda kv: kv[1].get("mcnemar_p_holm", 1.0)):
        rows.append([
            name,
            str(v.get("discordant_full_only", 0)),
            str(v.get("discordant_baseline_only", 0)),
            "%+.3f" % v.get("mrr_diff", 0.0),
            "[%.3f, %.3f]" % (v.get("mrr_ci_low", 0.0), v.get("mrr_ci_high", 0.0)),
            "%.2g" % v.get("mcnemar_p_raw", 1.0),
            "%.2g" % v.get("mcnemar_p_holm", 1.0),
        ])
    return rows


def _frontier_table():
    rows = [["token budget", "cap top-1", "strict top-1", "mean cost",
             "median cost"]]
    for f in ANALYSIS.get("frontier", []):
        rows.append([
            str(f.get("budget")),
            _f(f.get("cap_top1", 0.0)),
            _f(f.get("strict_top1", 0.0)),
            _i(f.get("mean_cost", 0)),
            _i(f.get("median_cost", 0)),
        ])
    return rows


def _errors_table():
    rows = [["failure category", "count"]]
    err = ANALYSIS.get("errors", {})
    for k, v in err.get("by_category", {}).items():
        rows.append([k, str(v)])
    for k, v in err.get("strict_by_category", {}).items():
        rows.append(["strict: " + k, str(v)])
    return rows


def _halves_table():
    rows = [["split", "n", "full top-1", "baseline top-1", "full strict",
             "baseline strict"]]
    for label in ("dev", "test"):
        v = ANALYSIS.get("halves", {}).get(label)
        if not v:
            continue
        rows.append([label, str(v.get("n", 0)),
                     _f(v.get("full_cap_top1", 0.0)),
                     _f(v.get("baseline_cap_top1", 0.0)),
                     _f(v.get("full_strict_top1", 0.0)),
                     _f(v.get("baseline_strict_top1", 0.0))])
    return rows


ABLATION_JSON = EVALS_DIR / "taxonomy-ablation.json"
if ABLATION_JSON.is_file():
    ABLATION = json.loads(ABLATION_JSON.read_text(encoding="utf-8"))
else:
    ABLATION = {}


def _ablation_table():
    abl = ABLATION or {}
    v1 = abl.get("v1_original_taxonomy") or {}
    v2 = abl.get("v2_repaired_taxonomy") or {}
    if not v1 or not v2:
        return [["taxonomy", "cap top-1", "strict top-1", "MRR", "on-topic",
                 "mean cost"]]
    def row(name, v):
        return [name, _f(v.get("cap_top1", 0.0)), _f(v.get("strict_top1", 0.0)),
                _f(v.get("mrr", 0.0)), _f(v.get("on_topic", 0.0)),
                _i(v.get("mean_cost", 0))]
    return [
        ["taxonomy", "cap top-1", "strict top-1", "MRR", "on-topic", "mean cost"],
        row("v1, before the repair", v1),
        row("v2, after the repair", v2),
    ]


def _intervals_table():
    rows = [["quantity", "n", "point estimate", "95% CI (Wilson)"]]
    for k, v in (ANALYSIS.get("intervals") or {}).items():
        if not v:
            continue
        rows.append([k.replace("_", " "), str(v.get("n", 0)),
                     _f(v.get("p", 0.0)),
                     "[%.3f, %.3f]" % (v.get("ci_low", 0.0), v.get("ci_high", 0.0))])
    return rows


_RAW_RESULTS = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
H2H = _RAW_RESULTS.get("head_to_head", {})

# The statistical analysis is a second stage of the same evaluation. It is
# optional so that the paper still builds if it has not been run yet.
ANALYSIS_JSON = EVALS_DIR / "analysis.json"
if ANALYSIS_JSON.is_file():
    ANALYSIS = json.loads(ANALYSIS_JSON.read_text(encoding="utf-8"))
else:
    ANALYSIS = {}


def _cost(x):
    return "{:,}".format(int(round(x)))
# Every table in the paper, in order, with its caption. Both artefacts read
# this list, so the LaTeX and the PDF always carry the same tables.
TABLE_SPECS = [
    ("routing",
     "Routing accuracy over all 298 cases. Strict top-1 is measured on the "
     "63 cases with one unambiguous skill.",
     "routing"),
    ("significance",
     "Paired significance of the shipped router against every baseline. "
     "McNemar's exact test on capability top-1 over the discordant pairs; a "
     "paired bootstrap gives the interval for the MRR difference; p-values "
     "are Holm-corrected across the six baselines.",
     "significance"),
    ("intervals",
     "Wilson score intervals on the headline numbers.",
     "intervals"),
    ("halves",
     "A split of the cases the design was not tuned on, by a stable hash of "
     "the case id.",
     "halves"),
    ("isolation",
     "Accuracy on the lexically isolated subset, where the request shares no "
     "exact keyword string with the expected capability.",
     "isolation"),
    ("frontier",
     "The accuracy-cost frontier: the same router under a hard token budget.",
     "frontier"),
    ("errors",
     "Every capability-level failure of the shipped router, split by where "
     "the routing went wrong.",
     "errors"),
    ("ablation",
     "Taxonomy ablation: the shipped router, the same benchmark and the "
     "same cost gate, with the taxonomy's keyword lists replaced by the "
     "pre-repair set.",
     "ablation"),
    ("system",
     "System-level effects of the catalog gate and the taxonomy work.",
     "system"),
]

N_CASES = len(_RAW_RESULTS["cases"])
N_STRICT = sum(1 for c in _RAW_RESULTS["cases"] if c.get("expected_skill"))
N_TABLES = len(TABLE_SPECS)

RESULTS = {
    "routing": _routing_table(_RAW_RESULTS["systems"]),
    "isolation": _isolation_table(_RAW_RESULTS["systems"]),
    "system": _system_table(),
    "significance": _significance_table(),
    "frontier": _frontier_table(),
    "errors": _errors_table(),
    "halves": _halves_table(),
    "intervals": _intervals_table(),
    "ablation": _ablation_table(),
}

REFERENCES = [
 ("schick2023toolformer", "Shick, J. et al.", "Toolformer: Language models can teach themselves to use tools", "Advances in Neural Information Processing Systems 36, 2023."),
 ("patil2023gorilla", "Patil, S. G. et al.", "Gorilla: Large language model connected with massive APIs", "arXiv:2305.15334, 2023."),
 ("yao2022react", "Yao, S. et al.", "ReAct: Synergizing reasoning and acting in language models", "International Conference on Learning Representations, 2023."),
 ("shinn2023reflexion", "Shinn, N. et al.", "Reflexion: Language agents with verbal reinforcement learning", "Advances in Neural Information Processing Systems 36, 2023."),
 ("qin2023toolllm", "Qin, Y. et al.", "ToolLLM: Facilitating large language models to master 16,000+ real-world APIs", "International Conference on Learning Representations, 2024."),
 ("liu2023agentbench", "Liu, X. et al.", "AgentBench: Evaluating LLMs as agents", "International Conference on Learning Representations, 2024."),
 ("jimenez2024swebench", "Jimenez, C. E. et al.", "SWE-bench: Can language models resolve real-world GitHub issues?", "International Conference on Learning Representations, 2024."),
 ("robertson2009bm25", "Robertson, S. and Zaragoza, H.", "The Probabilistic Relevance Framework: BM25 and Beyond", "Foundations and Trends in Information Retrieval 3(4), 2009."),
 ("lewis2020rag", "Lewis, P. et al.", "Retrieval-augmented generation for knowledge-intensive NLP tasks", "Advances in Neural Information Processing Systems 33, 2020."),
 ("liu2023lost", "Liu, N. F. et al.", "Lost in the Middle: How language models use long contexts", "Transactions of the Association for Computational Linguistics 11, 2023."),
 ("hsieh2024ruler", "Hsieh, C.-Y. et al.", "RULER: What's the real context size of your long-context LLMs?", "arXiv:2404.06654, 2024."),
 ("packer2023memgpt", "Packer, C. et al.", "MemGPT: Towards LLMs as operating systems", "arXiv:2310.08560, 2023."),
 ("chroma2025contexrot", "Chroma Research", "Context rot: How increasing input tokens impacts LLM performance", "Technical report, 2025."),
 ("anthropic2025skills", "Anthropic", "Agent Skills specification and context engineering guidance", "Documentation, 2025."),
 ("obra2025superpowers", "D. Osman and contributors", "superpowers: a software development methodology for coding agents", "Open-source project, obra/superpowers."),
 ("miller1995wordnet", "Miller, G. A.", "WordNet: A lexical database for English", "Communications of the ACM 38(11), 1995."),
]
