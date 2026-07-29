#!/usr/bin/env python3
"""A deadlock checker that is CORRECT about cycles and vacuous about nothing.

Shipped so the README's worked example is reproducible without pointing at anybody's product.
It detects cycles properly — it passes the negative control — and it reports success on the empty
graph, because `any(...)` over zero nodes is False. That single line is the defect `abstain-bench`
exists to measure, and it is the most common bug in this entire class of tool.

    abstain-bench score --subject 'python3 examples/vacuous_checker.py {input}'
"""
import json
import sys

try:
    g = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
if not isinstance(g, dict) or not all(isinstance(v, list) for v in g.values()):
    sys.exit(1)

WHITE, GREY, BLACK = 0, 1, 2
colour = {n: WHITE for n in g}


def has_cycle_from(n):
    colour[n] = GREY
    for m in g.get(n, []):
        c = colour.get(m, WHITE)
        if c == GREY:
            return True
        if c == WHITE and has_cycle_from(m):
            return True
    colour[n] = BLACK
    return False


# THE BUG, on purpose: `any(...)` over an empty graph is False, so a graph with no nodes at all
# is reported as "no deadlock" — a confident answer about a system this never saw.
sys.exit(1 if any(colour[n] == WHITE and has_cycle_from(n) for n in list(g)) else 0)
