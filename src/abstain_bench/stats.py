"""stats.py — the exact binomial interval, with no dependency.

Clopper-Pearson rather than a normal approximation, because the counts here are small (a corpus of
a few dozen cases) and Wald intervals are badly wrong at the ends: 0 unearned passes out of 24 is
NOT "0% +/- 0%", it is 0% with an upper bound of 14.2%, and reporting the first would be the
benchmark committing the exact overclaim it measures.

Implemented from the Beta quantile via a continued fraction for the regularised incomplete beta,
so the package has no runtime dependency at all. Checked against SciPy's `beta.ppf` in the test
suite when SciPy happens to be installed, and skipped when it is not.
"""
from __future__ import annotations

import math
from typing import Tuple


def _betacf(a: float, b: float, x: float, itmax: int = 300, eps: float = 3e-16) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Inverse of `betainc` by bisection. Slow and obviously correct, which is the right trade
    for a function called a handful of times per run."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Exact two-sided binomial interval for k successes in n trials.

    The endpoints are the standard Beta quantiles, with the conventional degenerate cases:
    k=0 has a lower bound of exactly 0, k=n an upper bound of exactly 1.
    """
    if n <= 0:
        raise ValueError("n must be positive; an interval over zero trials is not defined")
    if not 0 <= k <= n:
        raise ValueError(f"k={k} out of range for n={n}")
    alpha = 1.0 - confidence
    lo = 0.0 if k == 0 else _beta_ppf(alpha / 2.0, k, n - k + 1)
    hi = 1.0 if k == n else _beta_ppf(1.0 - alpha / 2.0, k + 1, n - k)
    return (lo, hi)


__all__ = ["clopper_pearson", "betainc"]
