# CLAIMS-MAP — abstain-bench

**Tag: CLEAN. Licence: Apache-2.0.**

This file exists so the CLEAN tag is *auditable* rather than asserted.

## The line

Every independent claim in the corresponding filed specification terminates in a **physical
actuation** step — admitting or refusing an operation and thereby granting or withholding a
physical resource.

`abstain-bench` runs a subject process and counts its exit codes. It grants and withholds nothing,
and it has no admission point of any kind.

## Claims approached, and the step not performed

| Filed claim family | What it recites | What abstain-bench does instead |
|---|---|---|
| Fail-closed admission on insufficient evidence | detect that the evidence is insufficient to decide, **and refuse the operation** | Detects that a *third-party tool* failed to refuse, and reports a rate. The refusal it measures is somebody else's, and it actuates nothing on the strength of it. |
| Bounded false-pass certification | establish an error bound over an enumerated domain **and gate admission on it** | Computes an exact binomial interval over the corpus and prints it. There is no gate. |

## An important non-claim

Exit code 1 is not an actuation. A CI pipeline may choose to fail a build on it; that choice, and
the actuation it performs, belong entirely to the user's pipeline. Reporting a verdict is
measurement; acting on it is the gate.

## What would cross the line

A mode that blocks a release, refuses to publish a package, or gates admission of any operation on
the measured rate. None exists, and `oss/tools/check_measure_only.py` fails the build if one
appears.
