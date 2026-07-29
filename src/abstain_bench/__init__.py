"""abstain-bench — how often does a verifier claim success on input it cannot check?

Feed a verifier inputs that cannot legitimately be checked — empty, truncated, unanchored,
degenerate, malformed, out of distribution — and count how often it returns PASS anyway.

The score is REFUSED unless the subject passes the controls, because a verifier that rejects
everything scores a perfect zero and is useless.
"""
__version__ = "0.1.0"

from .corpus import CORPUS, BY_CATEGORY, Case, build_corpus, scored_cases  # noqa: E402
from .score import Report, score                                          # noqa: E402
from .stats import clopper_pearson                                        # noqa: E402

__all__ = ["score", "Report", "CORPUS", "BY_CATEGORY", "Case", "build_corpus", "scored_cases",
           "clopper_pearson", "__version__"]
