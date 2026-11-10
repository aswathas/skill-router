# -*- coding: utf-8 -*-
"""Tests for the capability router.

Two groups:

  behaviour  the routing rules themselves, exercised on a small synthetic
             registry so the tests need no installed skill library and no
             machine state;
  artefacts  checks that the files in this repository agree with each other,
             so a stale number in the paper cannot survive a commit.

Run:

    python -m unittest discover -s tests -v
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "aswath-capability"
INVOKE = SKILL / "scripts" / "invoke.py"
BUILD = SKILL / "scripts" / "build-registry.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


inv = _load("router_invoke", INVOKE)
brg = _load("router_build_registry", BUILD)

CAP_MAP = {
    "testing": {
        "strong": ["unit test", "integration test", "test suite"],
        "weak": ["test", "pytest", "jest"],
    },
    "design-direction": {
        "strong": ["art direction", "visual design"],
        "weak": ["typography", "aesthetic"],
    },
    "ecommerce": {
        "strong": ["ecommerce", "cart", "checkout"],
        "weak": ["shopify", "cart"],
    },
}


def skill(name, tags, tokens=800, source="local", quality=None, description=""):
    entry = {
        "name": name,
        "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
        "description": description,
        "source": source,
        "tokens_est": tokens,
        "tags": list(tags),
    }
    if quality is not None:
        entry["quality"] = quality
    return entry


class TestCapabilityInference(unittest.TestCase):
    """infer_capabilities() returns {cap: (weight, pos)}."""

    def test_returns_weight_and_position(self):
        out = inv.infer_capabilities("write a unit test for the parser", CAP_MAP)
        self.assertIn("testing", out)
        weight, pos = out["testing"]
        self.assertEqual(weight, 2, "a strong phrase must weigh more than a weak word")
        self.assertGreaterEqual(pos, 0)
        self.assertLess(pos, len("write a unit test for the parser"))

    def test_weak_keyword_weighs_less_than_strong(self):
        strong = inv.infer_capabilities("write a unit test", CAP_MAP)
        weak = inv.infer_capabilities("use pytest please", CAP_MAP)
        self.assertEqual(strong["testing"][0], 2)
        self.assertEqual(weak["testing"][0], 1)

    def test_weak_keyword_is_matched_per_token_not_by_substring(self):
        """'test' must not fire on 'latest', 'form' not on 'transform'."""
        cap_map = {"testing": {"strong": [], "weak": ["test"]}}
        self.assertNotIn("testing",
                         inv.infer_capabilities("give me the latest release notes", cap_map))
        self.assertNotIn("testing",
                         inv.infer_capabilities("transform the shape of the data", cap_map))

    def test_weak_keyword_still_matches_an_inflection(self):
        cap_map = {"testing": {"strong": [], "weak": ["test"]}}
        self.assertIn("testing", inv.infer_capabilities("add tests for the parser", cap_map))

    def test_unrelated_request_infers_nothing(self):
        self.assertEqual(inv.infer_capabilities("what is the weather today", CAP_MAP), {})


class TestWeakKeywordNameMatching(unittest.TestCase):
    """A weak keyword matches a name token, never an arbitrary substring."""

    def test_substring_collisions_are_rejected(self):
        for kw, name in (("form", "transform"), ("test", "latest"),
                         ("git", "digit"), ("lock", "block")):
            self.assertFalse(
                brg.name_token_match(name, kw),
                f"{kw!r} must not match the name {name!r}",
            )

    def test_prefix_of_a_real_token_still_matches(self):
        self.assertTrue(brg.name_token_match("brainstorming", "brainstorm"))
        self.assertTrue(brg.name_token_match("cli-for-agents", "cli"))

    def test_exact_match_needs_the_whole_token(self):
        self.assertTrue(brg.name_token_exact("cli-for-agents", "cli"))
        self.assertTrue(brg.name_token_exact("hyperframes-cli", "cli"))
        self.assertFalse(brg.name_token_exact("clickmeeting", "cli"))


class TestTagging(unittest.TestCase):
    """Evidence channels decide what a skill is tagged with."""

    def test_reference_files_are_the_strongest_evidence(self):
        tags = brg.tag_capabilities(
            "a shopping cart helper", "cart-helper",
            {"ecommerce": {"strong": [], "weak": [], "files": ["cart"]}},
            {"cart"},
        )
        self.assertEqual(tags, ["ecommerce"])

    def test_require_name_filters_out_skills_the_capability_does_not_cover(self):
        """require_name is a gate, not evidence: it can only exclude."""
        cap_map = {"ecommerce": {"strong": ["cart"], "weak": [],
                                  "require_name": ["shopify"]}}
        self.assertEqual(brg.tag_capabilities("build a cart", "cart-helper", cap_map), [],
                         "a skill whose name lacks the required string must not be tagged")
        self.assertEqual(brg.tag_capabilities("build a cart", "shopify-cart", cap_map),
                         ["ecommerce"],
                         "the gate lets an otherwise-evidenced skill through")

    def test_require_name_alone_does_not_establish_evidence(self):
        cap_map = {"ecommerce": {"strong": [], "weak": [], "files": [],
                                  "require_name": ["shopify"]}}
        self.assertEqual(brg.tag_capabilities("build a cart", "shopify-cart", cap_map), [])

    def test_a_weak_keyword_tags_on_the_name_only(self):
        cap_map = {"testing": {"strong": [], "weak": ["pytest"]}}
        self.assertEqual(brg.tag_capabilities("runs a suite", "suite-runner", cap_map), [])
        self.assertEqual(brg.tag_capabilities("runs a suite", "pytest-runner", cap_map),
                         ["testing"])


class TestRanking(unittest.TestCase):
    """Capability overlap dominates; the ledger demotes; cost gates."""

    def setUp(self):
        self.reg = {
            "local": [
                skill("pytest-runner", ["testing"], tokens=700),
                skill("unit-test-helper", ["testing"], tokens=3000),
                skill("design-typo", ["design-direction"], tokens=600),
            ],
            "plugin": [],
            "marketplace": [],
        }

    def test_capability_overlap_beats_a_name_match(self):
        ranked, _ = inv.score_candidates(
            self.reg, "write a unit test for the parser", CAP_MAP)
        self.assertEqual(ranked[0]["name"], "unit-test-helper")

    def test_a_rejected_skill_is_demoted_not_banned(self):
        reg = {
            "local": [
                skill("unit-test-helper", ["testing"], tokens=3000, quality=-50),
                skill("pytest-runner", ["testing"], tokens=700, quality=0),
            ],
            "plugin": [],
            "marketplace": [],
        }
        ranked, _ = inv.score_candidates(reg, "write a unit test", CAP_MAP)
        self.assertEqual(ranked[0]["name"], "pytest-runner")
        self.assertEqual(len(ranked), 2, "a rejected skill must stay reachable")

    def test_the_ledger_penalty_is_capped(self):
        """A -50 reject must not bury a skill below any plausible rival."""
        reg = {
            "local": [
                skill("unit-test-helper", ["testing"], tokens=3000, quality=-50),
                skill("pytest-runner", ["testing"], tokens=700, quality=0),
            ],
            "plugin": [],
            "marketplace": [],
        }
        ranked, _ = inv.score_candidates(reg, "write a unit test", CAP_MAP)
        rejected = [s for s in ranked if s["name"] == "unit-test-helper"][0]
        accepted = [s for s in ranked if s["name"] == "pytest-runner"][0]
        self.assertLessEqual(accepted["_match"] - rejected["_match"], 15 + 6)

    def test_the_cost_gate_drops_a_skill_that_costs_an_order_of_magnitude(self):
        reg = {
            "local": [
                skill("unit-test-helper", ["testing"], tokens=9800),
                skill("pytest-runner", ["testing"], tokens=190),
            ],
            "plugin": [],
            "marketplace": [],
        }
        ranked, _ = inv.score_candidates(reg, "write a unit test", CAP_MAP)
        gated = inv.cost_gate(ranked, cheap_cap=4.0)
        names = [s["name"] for s in gated]
        self.assertIn("pytest-runner", names)

    def test_the_cost_gate_keeps_a_skill_that_matches_better(self):
        """The regression the Pareto rule exists to prevent."""
        reg = {
            "local": [
                skill("unit-test-helper", ["testing"], tokens=3500),
                skill("cheap-loose", ["testing"], tokens=64),
            ],
            "plugin": [],
            "marketplace": [],
        }
        ranked, _ = inv.score_candidates(reg, "write a unit test for the parser", CAP_MAP)
        gated = inv.cost_gate(ranked, cheap_cap=4.0)
        self.assertIn("unit-test-helper", [s["name"] for s in gated],
                      "the better match must not be deleted by the cost gate")

    def test_a_skill_without_the_capability_is_not_selected(self):
        reg = {
            "local": [
                skill("design-typo", ["design-direction"], tokens=100),
                skill("unit-test-helper", ["testing"], tokens=3000),
            ],
            "plugin": [],
            "marketplace": [],
        }
        ranked, _ = inv.score_candidates(reg, "write a unit test", CAP_MAP)
        self.assertEqual(ranked[0]["tags"], ["testing"])


class TestArtefactConsistency(unittest.TestCase):
    """The files in this repository must agree with each other."""

    def test_capabilities_file_is_well_formed(self):
        data = json.loads((SKILL / "registry" / "capabilities.json")
                          .read_text(encoding="utf-8"))
        caps = data["capabilities"]
        self.assertGreater(len(caps), 50)
        for name, spec in caps.items():
            self.assertTrue(spec.get("strong") or spec.get("weak") or spec.get("files"),
                            f"capability {name} has no evidence channel")

    def test_the_pre_repair_taxonomy_is_still_shipped_for_the_ablation(self):
        data = json.loads((ROOT / "evals" / "taxonomy-v1.json").read_text(encoding="utf-8"))
        self.assertIn("capabilities", data)
        current = json.loads((SKILL / "registry" / "capabilities.json")
                             .read_text(encoding="utf-8"))
        self.assertNotEqual(
            data["capabilities"], current["capabilities"],
            "the ablation needs a taxonomy that differs from the shipped one",
        )

    def test_every_benchmark_case_is_well_formed(self):
        for name in ("benchmark-a.jsonl", "benchmark-b.jsonl",
                     "benchmark-c.jsonl", "historical.jsonl"):
            path = ROOT / "evals" / name
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    case = json.loads(line)
                    self.assertIn("id", case, f"{name}:{lineno}")
                    self.assertIn("request", case, f"{name}:{lineno}")
                    self.assertIn("cap", case, f"{name}:{lineno}")

    def test_benchmark_case_ids_are_unique(self):
        seen = set()
        for name in ("benchmark-a.jsonl", "benchmark-b.jsonl",
                     "benchmark-c.jsonl", "historical.jsonl"):
            with open(ROOT / "evals" / name, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    cid = json.loads(line)["id"]
                    self.assertNotIn(cid, seen, f"duplicate case id {cid}")
                    seen.add(cid)

    def test_the_recorded_results_match_the_recorded_case_count(self):
        results = json.loads((ROOT / "evals" / "results.json").read_text(encoding="utf-8"))
        meta = results["meta"]
        self.assertEqual(
            meta["n_authored"] + meta["n_historical"],
            len(results["cases"]),
            "the result file must cover exactly the cases it claims",
        )

    def test_the_shipped_router_is_the_best_capability_system(self):
        results = json.loads((ROOT / "evals" / "results.json").read_text(encoding="utf-8"))
        systems = results["systems"]
        full = systems["full"]["cap_top1"]
        for name, s in systems.items():
            self.assertLessEqual(s["cap_top1"], full + 1e-9,
                                 f"{name} beat the shipped router on capability top-1")

    def test_the_paper_abstract_matches_the_arxiv_metadata(self):
        sys.path.insert(0, str(ROOT / "paper"))
        try:
            import content as paper_content
        finally:
            sys.path.pop(0)
        meta = (ROOT / "arxiv" / "metadata.yaml").read_text(encoding="utf-8")
        block = meta.split("abstract: |" + chr(10), 1)[1]
        lines = []
        for line in block.splitlines():
            if line and not line.startswith("  "):
                break
            lines.append(line[2:] if line.startswith("  ") else line)
        self.assertEqual(chr(10).join(lines).strip(),
                         paper_content.ABSTRACT.strip(),
                         "the arXiv form abstract must be the paper's own abstract")

    def test_the_paper_reports_the_case_count_the_harness_measured(self):
        results = json.loads((ROOT / "evals" / "results.json").read_text(encoding="utf-8"))
        n = len(results["cases"])
        tex = (ROOT / "paper" / "skill-router.tex").read_text(encoding="utf-8")
        self.assertIn(str(n), tex, f"the paper must report the {n} measured cases")

    def test_the_paper_and_the_analysis_agree_on_the_headline(self):
        results = json.loads((ROOT / "evals" / "results.json").read_text(encoding="utf-8"))
        analysis = json.loads((ROOT / "evals" / "analysis.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(
            results["systems"]["full"]["cap_top1"],
            analysis["intervals"]["full_cap_top1"]["p"],
            places=6,
        )



class TestPaperNumbersMatchTheArtefacts(unittest.TestCase):
    """Every number the paper quotes must come from the measured artefacts.

    The paper is generated from the artefacts, but its prose is written by
    hand. This is where the two are tied together, so a hand-written number
    cannot drift away from the measurement it describes.
    """

    @classmethod
    def setUpClass(cls):
        cls.tex = (ROOT / "paper" / "skill-router.tex").read_text(encoding="utf-8")
        cls.results = json.loads((ROOT / "evals" / "results.json")
                                 .read_text(encoding="utf-8"))
        cls.analysis = json.loads((ROOT / "evals" / "analysis.json")
                                  .read_text(encoding="utf-8"))
        cls.ablation = json.loads((ROOT / "evals" / "taxonomy-ablation.json")
                                  .read_text(encoding="utf-8"))

    def test_the_headline_numbers_are_quoted(self):
        full = self.results["systems"]["full"]
        for label, s in self.results["systems"].items():
            for value in (s["cap_top1"], s["mrr"]):
                self.assertIn(f"{value:.3f}", self.tex,
                              f"{label} {value:.3f} is missing from the paper")
        self.assertIn(f"{full['cap_top1']:.3f}", self.tex)

    def test_the_ablation_numbers_are_quoted(self):
        paired = self.ablation["paired"]
        self.assertIn(f"{paired['v2_only_right']}", self.tex,
                      "the discordant-pair count is missing from the paper")
        self.assertIn(f"{paired['mcnemar_p']:.1e}".replace("e-14", "e-14"), self.tex)

    def test_the_isolation_claim_matches_the_measured_subset(self):
        """The paper must not claim the router is worse if it is not."""
        iso = self.analysis.get("isolation", {})
        self.assertTrue(iso, "the analysis must measure the isolated subset")
        for label, entry in iso.items():
            full = entry["systems"]["full"]["cap_top1"]
            pre = entry["systems"]["keyword_substring"]["cap_top1"]
            self.assertGreaterEqual(
                full, pre,
                f"on the {label} subset the shipped router is not worse "
                "than the pre-fix matcher, so the paper must not say it is",
            )
        self.assertNotIn("shipped router is worse on this subset", self.tex)

    def test_the_isolation_counts_are_quoted(self):
        for entry in self.analysis.get("isolation", {}).values():
            self.assertIn(str(entry["n"]), self.tex,
                          f"the isolated subset size {entry['n']} is not quoted")



class TestPlainLanguageGuide(unittest.TestCase):
    """The guide for a general reader must not drift from the measurements."""

    @classmethod
    def setUpClass(cls):
        cls.guide = (ROOT / "docs" / "PLAIN-LANGUAGE.md").read_text(encoding="utf-8")
        cls.results = json.loads((ROOT / "evals" / "results.json")
                                 .read_text(encoding="utf-8"))
        cls.analysis = json.loads((ROOT / "evals" / "analysis.json")
                                  .read_text(encoding="utf-8"))
        cls.metrics = json.loads((ROOT / "evals" / "system-metrics.json")
                                 .read_text(encoding="utf-8"))

    def test_the_headline_accuracies_are_quoted(self):
        systems = self.results["systems"]
        for key in ("full", "keyword_substring", "bm25", "random"):
            value = systems[key]["cap_top1"]
            self.assertIn(f"{value * 100:.0f}%", self.guide,
                          f"{key} capability accuracy {value:.3f} is not quoted")

    def test_the_exact_skill_accuracies_are_quoted(self):
        systems = self.results["systems"]
        for key in ("full", "keyword_substring", "bm25"):
            value = systems[key].get("strict_top1", 0.0)
            self.assertIn(f"{value * 100:.0f}%", self.guide,
                          f"{key} strict accuracy {value:.3f} is not quoted")

    def test_the_catalog_numbers_are_quoted(self):
        cat = self.metrics["runtime_catalog"]
        self.assertIn(f"{cat['before_gate']:,}", self.guide)
        self.assertIn(str(cat["after_gate"]), self.guide)

    def test_the_case_count_is_quoted(self):
        self.assertIn(str(self.analysis["n_cases"]), self.guide)

    def test_the_taxonomy_ablation_is_quoted(self):
        ablation = json.loads((ROOT / "evals" / "taxonomy-ablation.json")
                              .read_text(encoding="utf-8"))
        before = ablation["v1_original_taxonomy"]["cap_top1"]
        after = ablation["v2_repaired_taxonomy"]["cap_top1"]
        self.assertIn(f"{before * 100:.0f}%", self.guide)
        self.assertIn(f"{after * 100:.0f}%", self.guide)

    def test_the_held_out_half_is_quoted(self):
        halves = self.analysis["halves"]
        self.assertIn(f"{halves['dev']['full_cap_top1'] * 100:.0f}%", self.guide)
        self.assertIn(f"{halves['test']['full_cap_top1'] * 100:.0f}%", self.guide)


if __name__ == "__main__":
    unittest.main()
