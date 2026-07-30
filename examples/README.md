# examples

The runnable example subjects moved into the package, at
[`src/abstain_bench/examples/`](../src/abstain_bench/examples/).

They were here, and it made the README's worked example fail for everyone who installed from PyPI:
this directory is outside `src/`, so it never shipped in the wheel. `score` also runs each subject
with `cwd` set to the case's temporary directory, so a relative path to a file here could not
resolve even in a clone.

Run them as modules, which works from any directory:

```bash
abstain-bench score --subject 'python3 -m abstain_bench.examples.vacuous_checker {input}'
```
