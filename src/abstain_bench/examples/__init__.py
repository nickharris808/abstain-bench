"""Runnable example subjects, shipped INSIDE the package on purpose.

They used to live in a top-level `examples/` directory. Two things were wrong with that, and both
broke the README's worked example for every reader who was not standing in a clone:

  1. `examples/` is outside `src/`, so it was NOT in the wheel. Anyone who ran `pip install
     abstain-bench` did not have the file the README told them to run.
  2. `score` deliberately runs each subject with `cwd` set to the case's own temporary directory,
     so a RELATIVE path to a subject cannot resolve even when the file does exist. The documented
     command was unrunnable by construction, not merely stale.

Invoked as a module, neither problem exists — `-m` resolves through `sys.path`, so the command
works from any directory, in any environment where the package is installed:

    abstain-bench score --subject 'python3 -m abstain_bench.examples.vacuous_checker {input}'
"""
