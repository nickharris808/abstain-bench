# abstain-bench

**How often does your verifier claim success on input it could not possibly have checked?**

[![tests](https://github.com/nickharris808/abstain-bench/actions/workflows/tests.yml/badge.svg)](https://github.com/nickharris808/abstain-bench/actions/workflows/tests.yml)
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)

Every verifier — a linter, an SBOM scanner, an attestation checker, a policy engine, a deadlock
detector — has the same tempting shape: *return success unless you find a problem.* Hand one an
empty file, a truncated log, or an artifact with no trust anchor and it finds no problem, so it
reports success. It has verified nothing and said so in green.

`abstain-bench` measures that, on any tool you can run from a shell.

## Install

```bash
pip install abstain-bench        # zero runtime dependencies
```

## 30-second quickstart

```bash
abstain-bench corpus                                    # what's in it and why each case counts
abstain-bench selftest                                  # the benchmark, pointed at itself
abstain-bench score --subject 'mytool verify {input}'   # score your verifier
```

Exit codes: **0** abstained on everything it should have · **1** claimed at least one unearned
pass · **2** no score could be established.

## Worked example

A deadlock checker that detects cycles perfectly and reports the empty graph as safe — because
`any(...)` over zero nodes is `False`. It ships in `examples/vacuous_checker.py`:

```console
$ abstain-bench score --subject 'python3 examples/vacuous_checker.py {input}'
subject: python3 examples/vacuous_checker.py {input}

unearned-pass rate  2/8 = 25.0%
95% CI (exact)      [3.2%, 65.1%]   Clopper-Pearson

  category                 n  unearned
  empty                    5         2
  malformed                2         0
  out_of_distribution      1         0

  claimed success on input it could not check:
    empty_json_object            an object with no members: there is no property here to check
    empty_graph                  no nodes: 'no cycle exists' is true and says nothing about your system
$ echo $?
1
```

That one line — `any(...)` over an empty collection — is the most common bug in this entire class
of tool, and it is invisible to every test written against non-empty input.

## The refusal that makes the number mean anything

**A verifier that exits non-zero on absolutely everything scores a perfect 0.0.** It is also
useless, and a benchmark that hands it top marks has measured nothing.

So the score is **refused** unless the subject first demonstrates it can discriminate:

- it must **accept** at least one *positive control* — a valid artifact a working verifier should
  pass. Reject those and its zero is an artefact of the harness, not a property of the tool;
- it must **reject** the *negative controls* in the families it handles — clearly broken
  artifacts. Pass those and it has no discrimination at all, so abstaining tells us nothing.

```console
$ abstain-bench score --subject 'true'
ABSTAIN — no unearned-pass rate is reported.
  negative control `cyclic_graph` was ACCEPTED (exit 0) in a family this subject claims to
  handle (graph). A subject with no discrimination tells us nothing by abstaining, so no score
  is reported.
```

A refused score is `null`, never `0.0`. Anything that treats a missing score as zero should crash
rather than average it in.

## What the corpus contains

24 scored cases across six ways of having nothing to check, plus 8 controls.

| category | why a pass is unearned |
|---|---|
| `empty` | zero records, nodes or bindings. `all([])` is `True` |
| `truncated` | a hash chain's prefix verifies **perfectly**; only an anchor reveals the missing tail |
| `no_anchor` | internally consistent, tied to nothing. Self-consistency is not authenticity |
| `degenerate` | structurally valid, semantically vacuous: a bound of 1.0, a sample of size zero |
| `malformed` | not the thing it claims to be. The right answer is a diagnosis, not a verdict |
| `out_of_distribution` | a schema, version or shape the verifier does not know |

Cases are **family-scoped** — `chain`, `graph`, `certificate`. A graph checker is not graded on a
truncated hash chain: it would refuse because the input is not a graph, collecting a free correct
answer for a reason unrelated to truncation. The subject earns a family by accepting that family's
positive control, and nothing is inferred from its command line.

### The corpus also records cases a verifier MAY pass

The first time this benchmark was pointed at a real tool it accused a **correct** verifier of two
unearned passes. `{"a": []}` — one node waiting on nothing — genuinely cannot deadlock. An acyclic
graph whose identifiers contain a right-to-left override is still acyclic; the deception there is
in how a terminal *renders* the name, not in the verdict.

Both moved to a `sound_pass` category that is not scored in either direction. **A benchmark that
manufactures findings is exactly as untrustworthy as the unearned passes it exists to measure.**
They are still run and still reported, because over-refusal is a real defect too — it is just not
this one.

## Why Clopper-Pearson

The corpus is small, so a naive proportion pretends to precision it does not have. 0 unearned
passes out of 24 is **not** "0% ± 0%" — it is 0% with a 95% upper bound of 14.2%. Reporting the
first would be this benchmark committing the exact overclaim it measures. The interval is exact
and computed with no runtime dependency; the test suite cross-checks it against SciPy when SciPy
happens to be installed.

## Responsible disclosure

**This ships the method and the corpus. It does not ship a league table of other people's
software, and it will not.** Point it at whatever you like and publish your own results under your
own name. The only subjects named in this repository are a synthetic example written for the
purpose and the author's own tools.

## Performance

Scoring runs 32 subprocesses, one per case, dominated by process startup rather than CPU. They run
on a small thread pool.

**The absolute times are stable. The ratio is not, and quoting a single speedup number was wrong
three times.**

```
two sessions on the same 14-core machine, pool of 8, n=5-7 runs each

              session A            session B (clean install)
jobs=1        1517-1565 ms         1156-1326 ms
jobs=auto      482-1008 ms          480- 561 ms
ratio             ~3.1x                ~2.3x
```

The parallel path lands near **0.5 s** every time. The sequential baseline moves with machine load,
so the *ratio* moves with it: this section has quoted 4.2x, then 3.1x, then 2.3x, all honestly
measured, none reproducible from the others. **Expect roughly 2-3x, and measure your own machine:**

```python
import time, sys
from abstain_bench.score import score
cmd = f"{sys.executable} -c 'import sys; sys.exit(1)'"
for jobs in (1, 0):
    t0 = time.perf_counter(); score("x", cmd, jobs=jobs)
    print(jobs, f"{(time.perf_counter()-t0)*1000:.0f} ms")
```

That instability is the whole reason this portfolio distrusts point-estimate speedups, and it took
three measurements of our own tool to stop producing one.

Pass `jobs=1` if the subject under test is stateful and cannot tolerate concurrent invocation —
this harness has no way to detect that. A test asserts the two produce byte-identical reports.

## Library use

```python
from abstain_bench import score

rep = score("mytool", "mytool verify {input}")
if rep.verdict == "SCORED":
    lo, hi = rep.interval
    print(f"{rep.unearned}/{rep.n} = {rep.rate:.1%}  [{lo:.1%}, {hi:.1%}]")
else:
    print("no score:", rep.control_failures)
```

## Honest scope — what a 0% means, and what it does not

A 0% unearned-pass rate says: *on these inputs, in the families this subject demonstrated it
handles, it never claimed success on something it could not check.* It does **not** say:

- **that the verifier is correct.** This measures one failure mode. A tool can abstain perfectly
  and still be wrong about real inputs — soundness is a different question and this is not it.
- **that the corpus is exhaustive.** Six ways to have nothing to check, and there are certainly
  others. The interval is wide on purpose.
- **anything about behaviour on valid input** beyond the positive controls.

A subject that cannot be run at all is counted as having refused, which is generous. The finding
this benchmark reports is that tools *claim success*; a generous denominator makes that finding
harder to argue with, not easier.

## What this does not do

`abstain-bench` **measures**. It runs a subject and counts exit codes. It never admits, refuses,
provisions or actuates anything. See [CLAIMS-MAP.md](CLAIMS-MAP.md).

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q          # 36 tests
abstain-bench selftest
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md).

**Citing this?** Metadata is in [CITATION.cff](CITATION.cff) — GitHub's "Cite this repository" button reads it directly.

<!-- PORTFOLIO -->
---

## The rest of the portfolio

25 artifacts, one idea: **a measurement you cannot check is a press release.** Every tool
here reports; none of them gates.

**Tools**

| | |
|---|---|
| [`abstain-bench`](https://github.com/nickharris808/abstain-bench) | how often does a verifier pass input it could not check? ← you are here |
| [`evidence`](https://github.com/nickharris808/evidence) | run the whole portfolio over your repo — the weakest leg, never the mean |
| [`floorgen`](https://github.com/nickharris808/floorgen) | what must your system remember? an exact lower bound |
| [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) | a proof kernel for your coding agent |
| [`gatecount`](https://github.com/nickharris808/gatecount) | exactly how many states does removing this check admit? |
| [`gridlock`](https://github.com/nickharris808/gridlock) | certify a wait-for relation cannot wedge |
| [`honestbench`](https://github.com/nickharris808/honestbench) | measure your CI's escape rate |
| [`kvleak`](https://github.com/nickharris808/kvleak) | cross-tenant leak scanner |
| [`kvprobe`](https://github.com/nickharris808/kvprobe) | model-substitution detector with a measured FPR |
| [`preregister`](https://github.com/nickharris808/preregister) | refuses to seal a plan whose conclusion is already fixed |
| [`proof-carrying-ci`](https://github.com/nickharris808/proof-carrying-ci) | the whole portfolio as one CI check, with SARIF |
| [`proof-to-code-drift`](https://github.com/nickharris808/proof-to-code-drift) | fail the build when the proof stops matching |
| [`sf-verify`](https://github.com/nickharris808/sf-verify) | re-derive admission decisions offline |
| [`signoff-cert`](https://github.com/nickharris808/signoff-cert) | certificates that carry their own false-pass bound |
| [`tokencount`](https://github.com/nickharris808/tokencount) | a token count both parties can recompute |

**Benchmarks** — each recomputes one of our own published numbers from its certificate

| | |
|---|---|
| [`illusion-bench`](https://github.com/nickharris808/illusion-bench) | how many broken kernels does your oracle admit? |
| [`kv-reuse-econ-bench`](https://github.com/nickharris808/kv-reuse-econ-bench) | recompute our economics headline |
| [`llm-tenant-isolation-bench`](https://github.com/nickharris808/llm-tenant-isolation-bench) | recompute our isolation figures |

**Datasets**

| | |
|---|---|
| [`abstain-corpus`](https://huggingface.co/datasets/nickh007/abstain-corpus) | 32 inputs a verifier must NOT pass |
| [`kv-reuse-econ-traces`](https://huggingface.co/datasets/nickh007/kv-reuse-econ-traces) | per-workload reuse accounting + the closed form |
| [`kv-tenant-isolation-bench`](https://huggingface.co/datasets/nickh007/kv-tenant-isolation-bench) | isolation observations, uninterpretable rows included |
| [`llm-precision-fingerprints`](https://huggingface.co/datasets/nickh007/llm-precision-fingerprints) | precision-labelled logprobs with a negative control |

**Try it in a browser** — no install, no GPU

| | |
|---|---|
| [`negative-results-atlas`](https://huggingface.co/spaces/nickh007/negative-results-atlas) | ten claims we took back |
| [`tenant-leak-demo`](https://huggingface.co/spaces/nickh007/tenant-leak-demo) | the residency calculator |
| [`wait-for-visualiser`](https://huggingface.co/spaces/nickh007/wait-for-visualiser) | paste a wait-for graph, see the cycle |

### Documentation

Everything above, explained in one place: **<https://nickharris808.github.io/evidence-docs/>** —
the [tutorial](https://nickharris808.github.io/evidence-docs/start/tutorial/),
[what this proves and what it does not](https://nickharris808.github.io/evidence-docs/concepts/what-this-proves/),
and a [CLI reference](https://nickharris808.github.io/evidence-docs/reference/cli/) generated by
running `--help` on every published command.

### The commercial edition

Everything above is **measure-only** and Apache-2.0: it tells you what is true and never acts on
it. The **enforcement** side — binding a partition key at the admission decision, the compiled gate
corpus, and the certificate-*issuing* faucet — is covered by filed patents and licensed separately.

**Reading is free. Enforcing is licensed.**
<!-- /PORTFOLIO -->
