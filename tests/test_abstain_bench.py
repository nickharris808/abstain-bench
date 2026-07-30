"""Tests for the benchmark, including the ones that point it at itself.

The plan flagged this before the code existed:

    `abstain-bench` must be run against itself. A benchmark that scores unearned passes and
    cannot itself abstain would be the most embarrassing defect available.

So the first section is the benchmark's own abstention, and the second is the failure mode that
turned up the moment it was pointed at a real tool: it accused a CORRECT verifier of two unearned
passes. A benchmark that manufactures findings is exactly as untrustworthy as the behaviour it
measures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from abstain_bench.corpus import (ANY, CERTIFICATE, CHAIN, CORPUS, GRAPH, NEGATIVE, POSITIVE,
                                  SOUND_PASS, UNCHECKABLE, build_corpus, controls, scored_cases)
from abstain_bench.score import CLAIMED_PASS, REFUSED, score
from abstain_bench.stats import betainc, clopper_pearson

PY = sys.executable
ALWAYS_PASS = f"{PY} -c 'import sys; sys.exit(0)'"
ALWAYS_FAIL = f"{PY} -c 'import sys; sys.exit(1)'"
# THE MODULE FORM, DELIBERATELY -- and this line is the whole point of the fix.
#
# This used to build an ABSOLUTE PATH to examples/vacuous_checker.py. Every test below then
# passed, including the one asserting the README's worked example reproduces, WHILE THE
# README'S ACTUAL COMMAND WAS BROKEN FOR EVERY READER: the file was outside `src/` so it never
# shipped in the wheel, and `score` runs each subject with cwd set to the case's temp
# directory, so the README's relative path could not resolve even inside a clone.
#
# The numbers were right the whole time. The test verified the NUMBERS and never the COMMAND,
# and an absolute path constructed in the test is exactly what hid the difference. Running the
# same module invocation the README prints is what closes that gap.
EXAMPLE_SUBJECT = f"{PY} -m abstain_bench.examples.vacuous_checker {{input}}"


# ------------------------------------------------------------------ the benchmark on itself

def test_a_subject_that_passes_everything_gets_no_score():
    """It would score 0% unearned only if the corpus were the whole story. The negative
    controls exist precisely so that indiscriminate acceptance cannot look like anything."""
    rep = score("always-pass", ALWAYS_PASS)
    assert rep.verdict == "ABSTAIN"
    assert rep.rate is None, "a refused score must be None, never 0.0"
    assert any("negative control" in f for f in rep.control_failures)
    assert rep.exit_code == 2


def test_a_subject_that_rejects_everything_gets_no_score():
    """The headline trap: rejecting everything is a perfect zero and a useless tool."""
    rep = score("always-fail", ALWAYS_FAIL)
    assert rep.verdict == "ABSTAIN"
    assert rep.rate is None
    assert any("positive control" in f for f in rep.control_failures)


def test_a_subject_that_cannot_be_run_gets_no_score():
    rep = score("ghost", "definitely-not-a-real-binary-xyz-abc")
    assert rep.verdict == "ABSTAIN"
    assert rep.rate is None


def test_a_refused_score_is_none_not_zero():
    """Anything treating a missing score as zero should crash rather than average it in."""
    rep = score("always-fail", ALWAYS_FAIL)
    d = rep.to_dict()
    assert d["unearned_pass_rate"] is None
    assert d["unearned_passes"] is None
    assert d["cases_scored"] is None


def test_selftest_subcommand_passes():
    out = subprocess.run([PY, "-m", "abstain_bench.cli", "selftest"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "abstains where it must" in out.stdout


# ------------------------------------------------------------------ no false accusations

@pytest.mark.parametrize("name", ["single_node_graph", "rtl_and_unicode_ids", "single_record"])
def test_cases_a_sound_verifier_may_pass_are_not_scored(name):
    """The three the benchmark got wrong on its first live run.

    `{"a": []}` is one node waiting on nothing — a system where nobody waits genuinely cannot
    wedge. An acyclic graph with RTL identifiers is still acyclic; the deception is in how a
    terminal renders the name. Scoring either would be a false accusation.
    """
    case = next(c for c in CORPUS if c.name == name)
    assert case.category == SOUND_PASS
    assert not case.scored


def test_a_correct_abstaining_verifier_scores_zero_with_no_findings():
    """A tool that refuses every uncheckable input must come out clean, or the benchmark is
    accusing correct software."""
    rep = score("strict", f"{PY} -c \"import json,sys;"
                          f"d=json.load(open(sys.argv[1]));"
                          f"sys.exit(0 if isinstance(d,dict) and d else 2)\"")
    if rep.verdict == "SCORED":
        assert rep.unearned == 0 or all(
            o.case.category in UNCHECKABLE for o in rep.scored_outcomes if o.outcome == CLAIMED_PASS)


def test_the_shipped_example_scores_nonzero_and_names_the_empty_case():
    """The example is deliberately vacuous. If it ever scores 0 the benchmark has stopped
    detecting the single most common bug in this class of tool."""
    rep = score("vacuous", EXAMPLE_SUBJECT)
    assert rep.verdict == "SCORED", rep.control_failures
    assert rep.unearned >= 1
    names = {o.case.name for o in rep.scored_outcomes if o.outcome == CLAIMED_PASS}
    assert "empty_graph" in names


# ------------------------------------------------------------------ family scoping

def test_only_families_the_subject_demonstrated_are_scored():
    """A graph checker refusing a truncated hash chain has refused for the wrong reason and
    would collect a free correct answer. Family scoping is what stops that inflating the score."""
    rep = score("vacuous", EXAMPLE_SUBJECT)
    assert rep.families == [GRAPH]
    fams = {o.case.family for o in rep.scored_outcomes}
    assert fams <= {GRAPH, ANY}
    assert CHAIN not in fams and CERTIFICATE not in fams


def test_a_negative_control_outside_the_subjects_families_does_not_abstain_it():
    """Passing a broken chain is damning for a chain verifier and meaningless for a graph one."""
    rep = score("vacuous", EXAMPLE_SUBJECT)
    assert rep.verdict == "SCORED"
    assert CHAIN not in rep.families


def test_every_positive_control_belongs_to_a_family():
    for c in controls(POSITIVE):
        assert c.family in (CHAIN, GRAPH, CERTIFICATE), f"{c.name} has no family"


def test_every_family_has_a_positive_control():
    have = {c.family for c in controls(POSITIVE)}
    for fam in (CHAIN, GRAPH, CERTIFICATE):
        assert fam in have, f"{fam} has no positive control, so it can never be scored"


# ------------------------------------------------------------------ the corpus

def test_the_corpus_is_reproducible_from_source():
    a = [(c.name, c.content) for c in build_corpus()]
    b = [(c.name, c.content) for c in build_corpus()]
    assert a == b


def test_case_names_are_unique():
    names = [c.name for c in CORPUS]
    assert len(names) == len(set(names))


def test_every_case_says_why_it_cannot_be_passed():
    for c in CORPUS:
        assert len(c.why) > 20, f"{c.name} has no explanation"


def test_every_scored_case_is_in_an_uncheckable_category():
    for c in scored_cases():
        assert c.category in UNCHECKABLE


def test_controls_are_never_scored():
    for c in CORPUS:
        if c.category in (POSITIVE, NEGATIVE, SOUND_PASS):
            assert not c.scored


def test_the_corpus_names_no_third_party_product():
    """Responsible disclosure: this ships the method, never a league table."""
    blob = " ".join(c.name + " " + c.why + " " + c.content for c in CORPUS).lower()
    for vendor in ("vllm", "sglang", "openai", "anthropic", "google", "aws", "azure",
                   "sigstore", "syft", "grype", "trivy", "snyk", "opa", "kyverno"):
        assert vendor not in blob, f"the corpus names {vendor}"


def test_export_writes_every_case(tmp_path):
    out = subprocess.run([PY, "-m", "abstain_bench.cli", "export", str(tmp_path)],
                         capture_output=True, text=True)
    assert out.returncode == 0
    idx = json.load(open(tmp_path / "index.json"))
    assert idx["n_cases"] == len(CORPUS)
    for c in CORPUS:
        assert (tmp_path / c.category / c.name / c.filename).exists()
        assert (tmp_path / c.category / c.name / "WHY.txt").exists()


# ------------------------------------------------------------------ the interval

def test_clopper_pearson_zero_of_n_has_a_lower_bound_of_exactly_zero():
    lo, hi = clopper_pearson(0, 26)
    assert lo == 0.0
    assert 0.10 < hi < 0.14, f"upper bound {hi} — 0/26 is not '0% plus or minus nothing'"


def test_clopper_pearson_n_of_n_has_an_upper_bound_of_exactly_one():
    lo, hi = clopper_pearson(9, 9)
    assert hi == 1.0
    assert lo > 0.6


def test_clopper_pearson_brackets_the_point_estimate():
    for k, n in ((1, 10), (3, 20), (13, 26), (25, 26)):
        lo, hi = clopper_pearson(k, n)
        assert lo <= k / n <= hi


def test_clopper_pearson_refuses_zero_trials():
    with pytest.raises(ValueError):
        clopper_pearson(0, 0)


def test_clopper_pearson_refuses_impossible_counts():
    with pytest.raises(ValueError):
        clopper_pearson(5, 3)


def test_betainc_endpoints():
    assert betainc(2, 3, 0.0) == 0.0
    assert betainc(2, 3, 1.0) == 1.0
    assert 0.0 < betainc(2, 3, 0.5) < 1.0


def test_clopper_pearson_matches_scipy_when_available():
    scipy_stats = pytest.importorskip("scipy.stats")
    for k, n in ((0, 26), (2, 8), (7, 20)):
        lo, hi = clopper_pearson(k, n)
        exp_lo = 0.0 if k == 0 else scipy_stats.beta.ppf(0.025, k, n - k + 1)
        exp_hi = 1.0 if k == n else scipy_stats.beta.ppf(0.975, k + 1, n - k)
        assert abs(lo - exp_lo) < 1e-6
        assert abs(hi - exp_hi) < 1e-6


# ------------------------------------------------------------------ CLI contract

def test_cli_score_exit_codes_follow_the_portfolio_dialect():
    ok = subprocess.run([PY, "-m", "abstain_bench.cli", "score", "--subject", ALWAYS_FAIL],
                        capture_output=True, text=True)
    assert ok.returncode == 2, "no score established must exit 2"

    bad = subprocess.run([PY, "-m", "abstain_bench.cli", "score",
                          "--subject", EXAMPLE_SUBJECT],
                         capture_output=True, text=True)
    assert bad.returncode == 1, "at least one unearned pass must exit 1"


def test_cli_json_and_text_agree_on_the_verdict():
    args = [PY, "-m", "abstain_bench.cli", "score", "--subject",
            EXAMPLE_SUBJECT]
    text = subprocess.run(args, capture_output=True, text=True)
    js = subprocess.run(args + ["--json"], capture_output=True, text=True)
    assert text.returncode == js.returncode
    d = json.loads(js.stdout)
    assert d["verdict"] == "SCORED"
    assert f"{d['unearned_passes']}/{d['cases_scored']}" in text.stdout


def test_cli_corpus_marks_the_unscored_categories_clearly():
    out = subprocess.run([PY, "-m", "abstain_bench.cli", "corpus"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "NOT scored" in out.stdout
    assert "sound_pass" in out.stdout


def test_json_carries_the_limits():
    rep = score("vacuous", EXAMPLE_SUBJECT)
    d = rep.to_dict()
    assert d["does_not_prove"]
    assert d["ci95_clopper_pearson"]
    assert d["families_demonstrated"] == [GRAPH]


# ------------------------------------------------------------------ counts must not go stale

def test_every_documented_count_matches_the_live_corpus():
    """The README and two docstrings quote the corpus size and the interval it implies.

    Those were written when the corpus had 26 scored cases; reclassifying three false
    accusations left them at 24 and every quoted number silently wrong. A prose number that
    nothing checks is a number that drifts, so this asserts them against the live values.
    """
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    n = len(scored_cases())
    lo, hi = clopper_pearson(0, n)
    hi_pct = f"{hi:.1%}"

    for rel in ("README.md", "src/abstain_bench/stats.py", "src/abstain_bench/score.py"):
        body = open(os.path.join(here, rel), encoding="utf-8").read()
        if "out of " in body or "n=" in body:
            assert f"out of {n}" in body or f"n={n}" in body, (
                f"{rel} quotes a corpus size that is not {n}")
        if "upper bound of" in body:
            assert hi_pct in body, f"{rel} quotes an interval that is not {hi_pct}"

    readme = open(os.path.join(here, "README.md"), encoding="utf-8").read()
    assert f"{n} scored cases" in readme, f"README does not say '{n} scored cases'"
    assert f"{len(CORPUS) - n} controls" in readme


def test_the_readme_worked_example_matches_a_real_run():
    """The console block in the README is a claim about what the shipped example prints."""
    rep = score("vacuous", EXAMPLE_SUBJECT)
    readme = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "README.md"), encoding="utf-8").read()
    assert f"{rep.unearned}/{rep.n} = {rep.rate:.1%}" in readme, (
        f"the README's worked example does not match a real run "
        f"({rep.unearned}/{rep.n} = {rep.rate:.1%})")
    lo, hi = rep.interval
    assert f"[{lo:.1%}, {hi:.1%}]" in readme


def test_the_readme_command_is_the_command_the_tests_run():
    """The gap that let a broken worked example ship, closed.

    The test above verifies the README's NUMBERS against a real run, and it passed for the entire
    life of the package while `abstain-bench score --subject 'python3 examples/vacuous_checker.py
    {input}'` — the command the README actually printed — failed for every reader with exit 2. It
    passed because the test built its own absolute path to the example instead of running what the
    README says. Verifying the output of a command you did not run is not verifying the command.

    So: the subject string in the README must be the subject string these tests use. Not
    equivalent to it, not a path to the same file — the same string.
    """
    readme = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "README.md"), encoding="utf-8").read()
    documented = "python3 -m abstain_bench.examples.vacuous_checker {input}"
    assert documented in readme, (
        f"the README no longer documents {documented!r}; if the invocation changed, this test and "
        f"EXAMPLE_SUBJECT must change with it")
    # EXAMPLE_SUBJECT differs only in naming THIS interpreter rather than a bare `python3`, which
    # is what makes the tests run under tox/CI pythons. Everything after it must be identical.
    assert EXAMPLE_SUBJECT.endswith(documented[len("python3 "):]), (
        f"tests run {EXAMPLE_SUBJECT!r} but the README documents {documented!r} — the exact "
        f"divergence that hid the last defect")


def test_the_example_ships_inside_the_package():
    """It used to live in a top-level `examples/`, outside `src/`, so `pip install abstain-bench`
    did not include it. The README told PyPI users to run a file they did not have. Importability
    is the check that this cannot silently regress."""
    import importlib.util
    assert importlib.util.find_spec("abstain_bench.examples.vacuous_checker") is not None, (
        "the worked example is not importable from the installed package; if it moved back "
        "outside src/, every PyPI reader's copy of the README is broken again")


def test_concurrency_never_changes_a_verdict():
    """Cases run on a thread pool (32 subprocess spawns; roughly 2-3x; the RATIO is load-dependent, the ~0.5s parallel time is not).

    Each case gets its own temporary directory and the subject is never told which case it is
    looking at, so parallelism cannot change an individual outcome — but that is an argument, and
    an argument about concurrency is worth checking rather than believing.
    """
    for cmd in (EXAMPLE_SUBJECT, ALWAYS_FAIL, ALWAYS_PASS):
        seq = score("s", cmd, jobs=1).to_dict()
        par = score("s", cmd, jobs=8).to_dict()
        assert json.dumps(seq, sort_keys=True) == json.dumps(par, sort_keys=True), (
            f"concurrency changed the report for {cmd}")


def test_jobs_one_is_available_for_stateful_subjects():
    """Some verifiers cannot tolerate concurrent invocation, and this harness cannot detect
    that, so the escape hatch has to exist and has to work."""
    rep = score("seq", ALWAYS_FAIL, jobs=1)
    assert rep.verdict == "ABSTAIN"
    assert len(rep.outcomes) == len(CORPUS)
