"""score.py — run a subject verifier over the corpus and report its unearned-pass rate.

THE MEASUREMENT. Feed the subject inputs it cannot legitimately check and count how often it
claims success anyway:

    unearned-pass rate = (cases the subject exited 0 on) / (uncheckable cases run)

reported with an exact Clopper-Pearson interval, because the counts are small and a naive
proportion at n=24 pretends to a precision it does not have.

THE REFUSAL THAT MAKES THE NUMBER MEAN ANYTHING. A verifier that exits non-zero on absolutely
everything scores a perfect 0.0. It is also completely useless. So the score is REFUSED unless
the subject demonstrates it can discriminate:

    * it must pass the POSITIVE controls -- artifacts a working verifier should accept. If it
      rejects those, either it is broken or the invocation is wrong, and in both cases its zero
      is an artefact of the harness rather than a property of the tool.
    * it must reject the NEGATIVE controls -- clearly broken artifacts. A subject that passes
      those has no discrimination at all, so its behaviour on the degenerate cases is not
      evidence of anything.

Either control failing yields ABSTAIN, not a score. This is the benchmark applying its own thesis
to itself, and it is the case most likely to be quietly dropped by anyone reimplementing this.

EXIT CODES OF THE SUBJECT. The portfolio dialect is 0 pass / 1 fail / 2 not-checked, and a subject
that speaks it gets full credit for abstaining. But most tools in the world only speak 0 and
non-zero, so anything non-zero counts as "did not claim success" -- the measurement is
deliberately generous, because the finding it reports is that tools claim success, and a generous
denominator makes that finding harder to argue with, not easier.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .corpus import (ANY, CORPUS, NEGATIVE, POSITIVE, UNCHECKABLE, Case, controls,
                     scored_cases)
from .stats import clopper_pearson

#: What the subject did with one case.
CLAIMED_PASS = "CLAIMED_PASS"        # exit 0 — asserted the property on uncheckable input
REFUSED = "REFUSED"                  # non-zero — did not claim success
ERRORED = "ERRORED"                  # could not be run at all


@dataclass
class CaseOutcome:
    case: Case
    outcome: str
    exit_code: Optional[int]
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> Dict:
        return {**self.case.to_dict(), "outcome": self.outcome, "exit_code": self.exit_code}


@dataclass
class Report:
    """The result of scoring one subject. `verdict` is SCORED or ABSTAIN — never a bare number."""

    subject: str
    verdict: str
    outcomes: List[CaseOutcome] = field(default_factory=list)
    control_failures: List[str] = field(default_factory=list)
    reason: str = ""
    #: The artifact families the subject DEMONSTRATED it handles, by accepting their positive
    #: control. Only these families are scored.
    families: List[str] = field(default_factory=list)

    # -------------------------------------------------- the score
    @property
    def scored_outcomes(self) -> List[CaseOutcome]:
        """Only uncheckable cases in a family the subject demonstrably speaks.

        Scoring a graph checker on a truncated hash chain measures nothing: it refuses because
        the input is not a graph, and collects a free correct answer for a reason unrelated to
        truncation. Family scoping is what stops the headline number being inflated by inputs
        the subject never understood.
        """
        fams = set(self.families) | {ANY}
        return [o for o in self.outcomes if o.case.scored and o.case.family in fams]

    @property
    def n(self) -> int:
        return len(self.scored_outcomes)

    @property
    def unearned(self) -> int:
        return sum(1 for o in self.scored_outcomes if o.outcome == CLAIMED_PASS)

    @property
    def rate(self) -> Optional[float]:
        """None when the score is refused. Deliberately not 0.0 — a refused score is not a
        good score, and any consumer that treats missing as zero should crash, not average."""
        if self.verdict != "SCORED" or not self.n:
            return None
        return self.unearned / self.n

    @property
    def interval(self) -> Optional[tuple]:
        if self.rate is None:
            return None
        return clopper_pearson(self.unearned, self.n)

    @property
    def by_category(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for o in self.scored_outcomes:
            d = out.setdefault(o.case.category, {"n": 0, "unearned": 0})
            d["n"] += 1
            d["unearned"] += (o.outcome == CLAIMED_PASS)
        return out

    @property
    def exit_code(self) -> int:
        """0 the subject abstained everywhere · 1 it claimed at least one unearned pass ·
        2 no score could be established."""
        if self.verdict != "SCORED":
            return 2
        return 1 if self.unearned else 0

    def to_dict(self) -> Dict:
        lo_hi = self.interval
        return {
            "artifact": "abstain_bench_score",
            "subject": self.subject,
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "unearned_passes": self.unearned if self.verdict == "SCORED" else None,
            "cases_scored": self.n if self.verdict == "SCORED" else None,
            "unearned_pass_rate": self.rate,
            "ci95_clopper_pearson": list(lo_hi) if lo_hi else None,
            "families_demonstrated": self.families,
            "control_failures": self.control_failures,
            "by_category": self.by_category if self.verdict == "SCORED" else {},
            "cases": [o.to_dict() for o in self.outcomes],
            "does_not_prove": DOES_NOT_PROVE,
        }


DOES_NOT_PROVE = [
    "that a 0% unearned-pass rate makes a verifier correct — this measures one failure mode, "
    "not soundness; a tool can abstain perfectly and still be wrong about real inputs",
    "that the corpus is exhaustive; it covers six ways to have nothing to check, and there are "
    "certainly others",
    "anything about the subject's behaviour on VALID input beyond the three positive controls",
]


def _run_case(cmd_template: str, case: Case, timeout: int, workdir: str) -> CaseOutcome:
    """Materialise the case as a file and run the subject against it."""
    d = tempfile.mkdtemp(prefix="abstain-", dir=workdir)
    path = os.path.join(d, case.filename)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(case.content)

    if "{input}" in cmd_template:
        cmd = cmd_template.replace("{input}", shlex.quote(path))
    else:
        cmd = f"{cmd_template} {shlex.quote(path)}"
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                           cwd=d)
    except subprocess.TimeoutExpired:
        return CaseOutcome(case, ERRORED, None, stderr=f"timed out after {timeout}s")
    except OSError as e:
        return CaseOutcome(case, ERRORED, None, stderr=str(e))

    outcome = CLAIMED_PASS if p.returncode == 0 else REFUSED
    return CaseOutcome(case, outcome, p.returncode, p.stdout[-2000:], p.stderr[-2000:])


def _default_jobs() -> int:
    """Enough to hide process startup, few enough not to thrash a laptop or a CI runner."""
    return max(1, min(8, (os.cpu_count() or 2)))


def score(subject: str, cmd_template: str, *, timeout: int = 60,
          cases: Optional[Sequence[Case]] = None, jobs: int = 0) -> Report:
    """Run `cmd_template` over the corpus and produce a Report.

    `cmd_template` may contain `{input}`; otherwise the case path is appended.

    `jobs` bounds the concurrency. Pass 1 for a strictly sequential run — useful if the subject
    under test is itself stateful and cannot tolerate concurrent invocations, which is a real
    property of some verifiers and not something this harness can detect.
    """
    cases = list(cases if cases is not None else CORPUS)
    workdir = tempfile.mkdtemp(prefix="abstain-bench-")

    # Each case is an independent subprocess against its own temporary directory, so they are
    # embarrassingly parallel and dominated by process startup rather than CPU. Run them on a
    # small thread pool: the GIL is irrelevant here because every thread is blocked in `wait`.
    # Order is preserved by `map`, and the subject is never told which case it is looking at,
    # so concurrency cannot change any individual verdict.
    with ThreadPoolExecutor(max_workers=jobs or _default_jobs()) as pool:
        outcomes = list(pool.map(lambda c: _run_case(cmd_template, c, timeout, workdir), cases))
    by_name = {o.case.name: o for o in outcomes}

    # Which families does this subject actually speak? A subject earns a family by ACCEPTING
    # that family's positive control. Nothing is assumed and nothing is inferred from the
    # command line: a tool that cannot accept a valid graph is not graded on graphs.
    families = sorted({c.family for c in controls(POSITIVE)
                       if (o := by_name.get(c.name)) is not None and o.outcome == CLAIMED_PASS})

    failures: List[str] = []
    if not families:
        rejected = [f"{c.name} (exit {by_name[c.name].exit_code})" for c in controls(POSITIVE)
                    if c.name in by_name]
        failures.append(
            "no positive control was accepted, so this subject has not demonstrated it can "
            "accept ANY valid artifact: " + ", ".join(rejected) + ". A verifier that rejects "
            "everything scores a perfect zero, so no score is reported.")

    # Negative controls only bite in a family the subject claims to speak. Passing a broken
    # chain is damning for a chain verifier and meaningless for a graph checker.
    for c in controls(NEGATIVE):
        o = by_name.get(c.name)
        if o is None or c.family not in families:
            continue
        if o.outcome == CLAIMED_PASS:
            failures.append(
                f"negative control `{c.name}` was ACCEPTED (exit 0) in a family this subject "
                f"claims to handle ({c.family}). A subject with no discrimination tells us "
                f"nothing by abstaining, so no score is reported.")

    provisional = Report(subject, "SCORED", outcomes, [], families=families)
    n_scored = len(provisional.scored_outcomes)
    n_errored = sum(1 for o in provisional.scored_outcomes if o.outcome == ERRORED)
    if families and n_scored == 0:
        failures.append("no uncheckable case falls in a family this subject handles, so there "
                        "is nothing to score")
    if n_scored and n_errored == n_scored:
        failures.append(f"every scored case failed to run at all ({n_errored}); the invocation "
                        f"is wrong, not the subject")

    if failures:
        return Report(subject, "ABSTAIN", outcomes, failures, families=families,
                      reason="the controls did not establish that this subject can discriminate, "
                             "so its behaviour on uncheckable input is not interpretable")

    return Report(subject, "SCORED", outcomes, [], families=families,
                  reason=f"controls passed for {', '.join(families)}: the subject accepts a "
                         f"valid artifact and rejects a clearly broken one, so its behaviour on "
                         f"uncheckable input in those families is readable")


__all__ = ["score", "Report", "CaseOutcome", "CLAIMED_PASS", "REFUSED", "ERRORED",
           "DOES_NOT_PROVE"]
