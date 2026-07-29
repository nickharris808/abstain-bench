"""abstain_bench.cli — score a verifier on the failure this portfolio exists to prevent.

    abstain-bench corpus                      what the corpus contains, and why each case counts
    abstain-bench export ./cases              write every case to disk
    abstain-bench score --subject 'mytool verify {input}'
    abstain-bench selftest                    run the benchmark against itself

Exit codes: 0 the subject abstained on every uncheckable input · 1 it claimed at least one
unearned pass · 2 no score could be established.

RESPONSIBLE DISCLOSURE. This ships the method and the corpus. It does not ship, and will not
ship, a table of verdicts against named third-party tools. Point it at whatever you like and
publish your own results with your own name on them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .corpus import (BY_CATEGORY, CORPUS, NEGATIVE, POSITIVE, SOUND_PASS, UNCHECKABLE,
                     scored_cases)
from .score import CLAIMED_PASS, ERRORED, score


def _cmd_corpus(a) -> int:
    print(f"{len(CORPUS)} cases: {len(scored_cases())} scored, "
          f"{len(CORPUS) - len(scored_cases())} controls\n")
    for cat in UNCHECKABLE + [SOUND_PASS, POSITIVE, NEGATIVE]:
        cases = BY_CATEGORY.get(cat, [])
        if not cases:
            continue
        if cat in UNCHECKABLE:
            label = cat
        elif cat == SOUND_PASS:
            label = f"{cat}  (NOT scored — a verifier may legitimately pass these)"
        else:
            label = f"{cat}  (not scored — makes the score readable)"
        print(f"{label}  [{len(cases)}]")
        for c in cases:
            print(f"    {c.name:<28} {c.why}")
        print()
    print("A subject must not exit 0 on any SCORED case. It must exit 0 on every positive")
    print("control and non-zero on every negative one, or no score is reported at all.")
    return 0


def _cmd_export(a) -> int:
    os.makedirs(a.out, exist_ok=True)
    n = 0
    for c in CORPUS:
        d = os.path.join(a.out, c.category, c.name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, c.filename), "w", encoding="utf-8", newline="") as fh:
            fh.write(c.content)
        with open(os.path.join(d, "WHY.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{c.name}\ncategory: {c.category}\nscored: {c.scored}\n\n{c.why}\n")
        n += 1
    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"n_cases": n, "cases": [c.to_dict() for c in CORPUS]}, fh, indent=2)
    print(f"wrote {n} cases to {a.out}")
    return 0


def _render(rep) -> str:
    out = [f"subject: {rep.subject}", ""]
    if rep.verdict != "SCORED":
        out.append("ABSTAIN — no unearned-pass rate is reported.")
        for f in rep.control_failures:
            out.append(f"  {f}")
        out.append("")
        out.append("  A verifier that rejects everything scores a perfect zero and is useless.")
        out.append("  The controls exist so that zero means something; until they pass, this")
        out.append("  benchmark refuses to hand out a number — which is the property it measures.")
        return "\n".join(out)

    lo, hi = rep.interval
    out.append(f"unearned-pass rate  {rep.unearned}/{rep.n} = {rep.rate:.1%}")
    out.append(f"95% CI (exact)      [{lo:.1%}, {hi:.1%}]   Clopper-Pearson")
    out.append("")
    out.append(f"  {'category':<22}{'n':>4}{'unearned':>10}")
    for cat, d in sorted(rep.by_category.items()):
        out.append(f"  {cat:<22}{d['n']:>4}{d['unearned']:>10}")
    bad = [o for o in rep.scored_outcomes if o.outcome == CLAIMED_PASS]
    if bad:
        out.append("")
        out.append("  claimed success on input it could not check:")
        for o in bad:
            out.append(f"    {o.case.name:<28} {o.case.why}")
    over = [o for o in rep.outcomes
            if o.case.category == SOUND_PASS and o.case.family in set(rep.families)
            and o.outcome != CLAIMED_PASS]
    if over:
        out.append("")
        out.append("  refused input it could legitimately have passed (over-refusal — a real")
        out.append("  defect, but NOT the one scored above):")
        for o in over:
            out.append(f"    {o.case.name:<28} exit {o.exit_code}")

    errored = [o for o in rep.scored_outcomes if o.outcome == ERRORED]
    if errored:
        out.append("")
        out.append(f"  {len(errored)} case(s) could not be run and are counted as REFUSED, which "
                   f"is generous to the subject")
    out.append("")
    out.append("  This does NOT prove:")
    from .score import DOES_NOT_PROVE
    for line in DOES_NOT_PROVE:
        out.append(f"    - {line}")
    return "\n".join(out)


def _cmd_score(a) -> int:
    rep = score(a.name or a.subject, a.subject, timeout=a.timeout)
    if a.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(_render(rep))
    return rep.exit_code


def _cmd_selftest(a) -> int:
    """Run the benchmark against subjects whose behaviour is known by construction.

    A benchmark that scores unearned passes and cannot itself abstain would be the most
    embarrassing defect available here, so the always-pass and always-fail subjects are run on
    every invocation rather than left to the test suite.
    """
    py = sys.executable
    checks = []

    always_pass = f"{py} -c 'import sys; sys.exit(0)'"
    rep = score("always-pass", always_pass, timeout=a.timeout)
    checks.append((
        "a subject that passes EVERYTHING is caught by the negative controls",
        rep.verdict == "ABSTAIN" and any("negative control" in f for f in rep.control_failures),
        f"verdict={rep.verdict}"))

    always_fail = f"{py} -c 'import sys; sys.exit(1)'"
    rep = score("always-fail", always_fail, timeout=a.timeout)
    checks.append((
        "a subject that rejects EVERYTHING scores no zero — the positives catch it",
        rep.verdict == "ABSTAIN" and any("positive control" in f for f in rep.control_failures),
        f"verdict={rep.verdict}, rate={rep.rate}"))

    missing = "definitely-not-a-real-binary-xyz-abc"
    rep = score("nonexistent", missing, timeout=a.timeout)
    checks.append((
        "a subject that cannot be run at all yields ABSTAIN, not a score",
        rep.verdict == "ABSTAIN", f"verdict={rep.verdict}"))

    ok = True
    for desc, passed, detail in checks:
        print(f"  [{'ok  ' if passed else 'FAIL'}] {desc}")
        if not passed:
            print(f"         {detail}")
            ok = False
    print()
    print("RESULT: " + ("the benchmark abstains where it must" if ok
                        else "A SELF-CHECK FAILED — the score cannot be trusted"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="abstain-bench",
        description="how often does a verifier claim success on input it cannot check? "
                    "(measure-only)")
    ap.add_argument("--version", action="version", version=f"abstain-bench {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("corpus", help="what the corpus contains and why each case counts")
    c.set_defaults(fn=_cmd_corpus)

    e = sub.add_parser("export", help="write every case to disk")
    e.add_argument("out")
    e.set_defaults(fn=_cmd_export)

    s = sub.add_parser("score", help="run a subject over the corpus")
    s.add_argument("--subject", required=True,
                   help="shell command; `{input}` is replaced with the case path, or the path "
                        "is appended if the placeholder is absent")
    s.add_argument("--name", default="", help="label for the report")
    s.add_argument("--timeout", type=int, default=60)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_score)

    t = sub.add_parser("selftest", help="run the benchmark against itself")
    t.add_argument("--timeout", type=int, default=60)
    t.set_defaults(fn=_cmd_selftest)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
