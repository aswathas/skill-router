# -*- coding: utf-8 -*-
"""Emit the ACM-style .tex and a PDF rendering from paper/content.py."""

import importlib.util
import pathlib
import sys
from xml.sax.saxutils import escape

HERE = pathlib.Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("content", HERE / "content.py")
C = importlib.util.module_from_spec(spec)
sys.modules["content"] = C
spec.loader.exec_module(C)

RESULTS_SUBSECTIONS = [
    ("Routing accuracy",
     ["The shipped router reaches 0.849 capability top-1 accuracy against "
      "0.614 for the pre-fix matcher, a gain of 23.5 points, and 0.477 for "
      "Okapi BM25 over skill descriptions. Mean reciprocal rank rises from "
      "0.678 to 0.878, and from 0.570 for BM25. The strict subset tells a "
      "different story: the shipped router scores 0.397 against 0.206 for "
      "the pre-fix matcher and 0.397 for BM25.",
      "That tie is the most important number in the paper. When the "
      "question is which capability a request belongs to, the taxonomy "
      "decisively beats lexical retrieval. When the question is which exact "
      "skill to load, a textbook BM25 retriever over skill descriptions "
      "matches the full router, and the pre-fix matcher is far behind. The "
      "taxonomy buys capability coverage, not skill disambiguation."]),

    ("Significance",
     ["The comparisons are paired, case by case. Against the pre-fix "
      "matcher the shipped router is right where the baseline is wrong on "
      "80 cases and wrong where it is right on 10, which McNemar's exact "
      "test puts at a raw p of 1.1e-14 and a Holm-corrected p of 4.2e-14 "
      "across the seven baselines. The paired bootstrap puts the MRR "
      "difference at +0.200 with a 95 percent interval of [0.155, 0.247].",
      "Against BM25 the router is right where BM25 is wrong on 118 cases "
      "and wrong where it is right on 7, an MRR difference of +0.308 with an "
      "interval of [0.259, 0.356] and a corrected p of 2.0e-26. The "
      "capability-level metric separates the two systems decisively; the "
      "strict metric does not, and we say which is which.",
      "Cases are not independent: several cases expect the same capability, "
      "and the router behaves consistently on them. Resampling capabilities "
      "rather than cases widens the interval, and we report both. The "
      "conclusion does not depend on which is used."]),

    ("On-topic rate",
     ["The taxonomy-independent on-topic rate is where the router's advantage "
      "over the pre-fix matcher is largest: 0.795 against 0.460, and 0.564 "
      "for BM25. The pre-fix matcher frequently selects a cheap skill that "
      "shares a word with the request but has nothing to do with the job. "
      "The shipped router selects a skill whose description is actually "
      "about the request."]),

    ("Ablations",
     ["Neither ablation changes capability top-1, which stays at 0.849 in "
      "all three configurations. Removing the outcome ledger leaves strict "
      "top-1 at 0.413 against 0.397 for the shipped router, so at this scale "
      "the ledger is indistinguishable from noise. Removing the Pareto cost "
      "gate leaves both metrics unchanged and cuts mean token cost from "
      "3,096 to 2,862. The gate is cheap and safe but close to inert.",
      "The ledger result is a null result and we report it as one. With "
      "only 19 skills carrying a score, and most benchmark cases not "
      "involving them, the ledger cannot move the aggregate. We believe the "
      "mechanism is sound but that its value is in long-tail cases rather "
      "than in the mean, and we have not measured that."]),

    ("The taxonomy ablation",
     ["The paper claims the taxonomy is the load-bearing part, so we "
      "measured it instead of asserting it. The same router, the same "
      "benchmark and the same cost gate were run against the pre-repair "
      "keyword lists, with the registry rebuilt from scratch so that the "
      "skills are tagged the way they would have been tagged before. "
      "Capability top-1 moves from 0.661 to 0.849, and mean reciprocal rank "
      "by 0.166 with a 95 percent paired bootstrap interval of [0.128, "
      "0.206]. The repaired taxonomy is right where the original is wrong on "
      "59 cases and wrong where it is right on 3, a paired difference that "
      "McNemar's exact test puts at p = 1.7e-14. Nothing else changed.",
      "The repair was guided by failures on one half of the benchmark, so "
      "that half is no longer an unbiased estimate: it scores 0.959. The "
      "other half was never looked at during the repair and scores 0.742, "
      "against 0.556 for the pre-fix matcher on the same cases. The gap "
      "between the halves, 21 points, is the size of the optimism we cannot "
      "rule out elsewhere, and we would rather report it than hide it. On "
      "the held-out half the difference is still significant: 36 cases "
      "favour the repaired taxonomy, 8 favour the original, p = 2.5e-05."]),

    ("The accuracy-cost frontier",
     ["Accuracy and per-invocation cost move in opposite directions. The "
      "pre-fix matcher spends a mean of 592 tokens per invocation; the "
      "shipped router spends 2,862, nearly five times more, while improving "
      "accuracy. The reason is visible in the wins: on the cases the shipped "
      "router gets right and the pre-fix matcher gets wrong, the mean cost "
      "of the chosen skill rises from 249 tokens for the pre-fix matcher to "
      "2,727 for the shipped router. The pre-fix matcher was cheap because "
      "it was often wrong, and being wrong is cheap.",
      "A hard budget recovers most of the cost. Restricting the router to "
      "skills of at most 1,000 tokens whenever such a skill covers the need "
      "gives a mean of 1,149 tokens, a 60 percent reduction, for 2.3 points "
      "of capability top-1 and 14.3 points of strict top-1. The frontier "
      "is therefore shallow: cost is cheap to recover, accuracy is not."]),

    ("Catalog and taxonomy",
     ["The catalog effects are unambiguous. Skills visible to the agent fall "
      "from 1,241 to 36, the catalog listing cost falls from an estimated "
      "1.87M tokens to 62.1K, the number of capabilities rises from 51 to "
      "78, the number of skills that no capability could reach falls from "
      "845 to 0, and the number of capabilities with no provider stays at 0.",
      "The registry itself grew during this work, from 4,098 to over 4,200 "
      "skills, because the builder was taught to read the host's built-in "
      "skill directory and its plugin directory. Before that change, 14 "
      "installed skills and a bundle of plugin skills were invisible to the "
      "router: they could be invoked by name but never selected. Making the "
      "router's view match the host's view was necessary before any "
      "evaluation could be trusted."]),

    ("Lexically isolated cases",
     ["On the 126 cases whose request shares no exact keyword string with "
      "the expected capability, the pre-fix matcher scores 0.254 and the "
      "shipped router 0.222. The shipped router is worse on this subset.",
      "This is the most interesting negative in the evaluation, and it has "
      "a clear explanation. The pre-fix matcher's flat inference fires on any "
      "substring overlap, including weak name words, so it lands on skills "
      "that happen to carry a wide spread of tags, which raises the chance "
      "that the expected tag is among them. The shipped router is more "
      "discriminating: it declines to route when the evidence does not "
      "identify a capability, and in doing so it gives up some accidental "
      "coverage. Discriminating and well-calibrated are not the same thing, "
      "and on this subset the less discriminating system benefits from "
      "luck."]),

    ("Error analysis",
     ["Of the 45 capability-level failures, 42 are inference misses: the "
      "request never named the expected capability, so no skill carrying it "
      "could win. Two are ranking errors and one is a near miss where the "
      "right capability was in the top three. On the strict subset the "
      "pattern is different: 27 of 38 failures choose a sibling skill that "
      "carries the right capability, and only 11 choose the wrong capability.",
      "That is the argument for spending effort on the taxonomy rather than "
      "on the ranker, and it is why the taxonomy ablation above matters "
      "more than any ranking change. It also explains the remaining ceiling: "
      "the strict failures are a disambiguation problem, and disambiguation "
      "needs either a better model of skill intent or a human in the loop."]),

    ("Robustness",
     ["Deleting the strongest matching keyword from a request and routing it "
      "again is brutal: the expected capability is still inferred in only "
      "18.5 percent of cases, and the same skill is chosen in 33.6 percent. "
      "The router is keyword-driven, not semantic, and it says so.",
      "We report this because it bounds the claim. The system does not "
      "understand the request; it recognises evidence in it. A request that "
      "says the same thing in different words is a different request to the "
      "router, and a learned or model-based router would be the obvious next "
      "step."]),
]


def sections():
    out = []
    for s in C.SECTIONS:
        if s["title"] == "None":
            continue
        out.append(s)
    return out


def tex_table(rows, caption=None, label=None):
    head, body = rows[0], rows[1:]
    lines = []
    if label:
        lines.append("\\begin{table}[t]")
        lines.append("\\centering")
        lines.append("\\caption{%s}" % caption)
        lines.append("\\label{tab:%s}" % label)
        lines.append("\\begin{tabular}{%s}" % ("l" + "c" * (len(head) - 1)))
        lines.append("\\toprule")
        lines.append(" & ".join("\\textbf{%s}" % escape(h) for h in head) + " \\\\")
        lines.append("\\midrule")
        for r in body:
            lines.append(" & ".join(escape(str(c)) for c in r) + " \\\\")
        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
    return "\n".join(lines)


def build_tex():
    L = []
    head = [
        r"\documentclass[sigconf,acmsmall]{acmart}",
        r"\setcopyright{rightsretained}",
        r"\acmConference[SkiLL-Routing 2026]{Workshop on Agent Skill Routing}"
        r"{November 2026}{Online}",
        r"\acmBooktitle{Workshop on Agent Skill Routing}",
        r"\begin{document}",
        r"\title{" + escape(C.TITLE) + "}",
        r"\subtitle{" + escape(C.SUBTITLE) + "}",
        r"\author{" + " \\and ".join(escape(a) for a in C.AUTHORS) + "}",
        r"\affiliation{%",
        r"  \institution{Independent research}",
        r"  \city{}",
        r"  \country{}",
        r"}",
        r"\renewcommand{\shortauthors}{" + escape(", ".join(C.AUTHORS)) + "}",
        r"\begin{abstract}",
        escape(C.ABSTRACT),
        r"\end{abstract}",
        r"\keywords{" + escape(C.KEYWORDS) + "}",
        r"\maketitle",
    ]
    L.append("\n".join(head))

    n = 0
    for s in sections():
        n += 1
        L.append("\\section{%s}" % escape(s["title"]))
        for p in s["paras"]:
            L.append(escape(p))
        L.append("")
        if s["title"] == "Results":
            for sub, paras in RESULTS_SUBSECTIONS:
                L.append("\\subsection{%s}" % escape(sub))
                for p in paras:
                    L.append(escape(p))
                L.append("")
            for key, caption, label in C.TABLE_SPECS:
                L.append(tex_table(C.RESULTS[key], caption, label))

    L.append("\\begin{thebibliography}{9}")
    for key, authors, title, venue in C.REFERENCES:
        L.append("\\bibitem{%s}\n%s. %s. In %s." % (key, escape(authors), escape(title), escape(venue)))
    L.append("\\end{thebibliography}")
    L.append("\\end{document}")
    return "\n".join(L)


def main():
    tex = HERE / "skill-router.tex"
    tex.write_text(build_tex(), encoding="utf-8")
    print("wrote", tex, tex.stat().st_size, "bytes")
    try:
        import build_pdf
        build_pdf.build(C, sections(), RESULTS_SUBSECTIONS)
    except Exception as err:
        print("pdf build failed:", err)


if __name__ == "__main__":
    main()
