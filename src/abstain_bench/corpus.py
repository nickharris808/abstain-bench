"""corpus.py — inputs a verifier cannot legitimately pass, and the controls that make the score readable.

THE CATEGORIES. Each is a distinct way for a verifier to have nothing to check while still being
handed something that looks like input. They are separated because they fail differently and a
tool can be solid against one and hopeless against another.

    EMPTY              zero records, zero bindings, zero nodes. A property that holds over
                       nothing has not been established. `all([])` is True.
    TRUNCATED          a prefix of a valid artifact. A hash chain's prefix verifies PERFECTLY --
                       only an external anchor can detect that the tail was removed.
    NO_ANCHOR          internally consistent, but with nothing tying it to the outside world.
                       Self-consistency is not authenticity.
    DEGENERATE         structurally valid and semantically vacuous: one record, a single-node
                       graph, a bound of 1.0, a sample of size zero.
    MALFORMED          not the thing it claims to be. The correct response is a diagnosis, not
                       a verdict.
    OUT_OF_DISTRIBUTION  a plausible artifact from a schema, version or shape the verifier does
                       not know. "I do not recognise this" is the honest answer.

THE CONTROLS ARE NOT OPTIONAL, AND THIS IS THE WHOLE DESIGN.

A verifier that exits non-zero on absolutely everything scores a PERFECT zero unearned passes.
It is also useless, and a benchmark that hands it top marks has measured nothing. So the corpus
carries `POSITIVE` cases -- artifacts a working verifier SHOULD accept -- and the harness refuses
to report a score when they fail. That refusal is the same discipline the benchmark is measuring,
applied to the benchmark.

Symmetrically, a `NEGATIVE` control is a clearly broken artifact a working verifier should REJECT.
A subject that passes the negatives has no discrimination at all, and its score on the degenerate
cases means nothing either.

NOTHING HERE NAMES A THIRD-PARTY TOOL. The corpus is inputs; the subject is whatever command you
point it at. This package ships the method, never a league table of other people's software.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

EMPTY = "empty"
TRUNCATED = "truncated"
NO_ANCHOR = "no_anchor"
DEGENERATE = "degenerate"
MALFORMED = "malformed"
OUT_OF_DISTRIBUTION = "out_of_distribution"

#: Categories whose members a verifier must NOT pass. These are what the score is computed over.
UNCHECKABLE = [EMPTY, TRUNCATED, NO_ANCHOR, DEGENERATE, MALFORMED, OUT_OF_DISTRIBUTION]

POSITIVE = "positive_control"
NEGATIVE = "negative_control"

#: Cases a sound verifier MAY legitimately pass. Not scored in either direction.
#:
#: This category exists because the first live run of this benchmark accused a correct tool of
#: two unearned passes, and both accusations were wrong. `{"a": []}` — one node waiting on
#: nothing — genuinely cannot deadlock, and an acyclic graph whose identifiers contain a
#: right-to-left override is still acyclic; the deception there is in how a terminal RENDERS the
#: name, not in the verdict. A benchmark that manufactures findings is exactly as untrustworthy
#: as the unearned passes it exists to measure, so these moved here rather than staying in the
#: numerator. They are still run and still reported, because over-refusal is a real defect too —
#: it is just not THIS defect.
SOUND_PASS = "sound_pass"


#: Artifact families. A verifier speaks one or more of these; handing it another family's
#: artifact measures nothing, because it will refuse for the wrong reason and collect a free
#: correct answer. See `score.py` for how the subject's families are established.
CHAIN = "chain"
GRAPH = "graph"
CERTIFICATE = "certificate"
ANY = "any"          # malformed/empty inputs that are wrong for EVERY family
FAMILIES = [CHAIN, GRAPH, CERTIFICATE]


@dataclass
class Case:
    """One input, and what a sound verifier is obliged to do with it."""

    name: str
    category: str
    filename: str
    content: str
    why: str                       # why this input cannot be legitimately passed
    family: str = ANY

    @property
    def scored(self) -> bool:
        return self.category in UNCHECKABLE

    def to_dict(self) -> Dict:
        return {"name": self.name, "category": self.category, "family": self.family,
                "filename": self.filename, "why": self.why, "scored": self.scored}


def _j(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)


def _chain(n: int, anchor: bool = True) -> List[dict]:
    """A toy hash-chained log. Deliberately simple: the point is the SHAPE, not the crypto."""
    import hashlib
    out, prev = [], "0" * 64
    for i in range(n):
        body = {"seq": i, "decision": "admit", "prev": prev}
        h = hashlib.sha256(_j(body).encode()).hexdigest()
        rec = dict(body, hash=h)
        if anchor and i == n - 1:
            rec["anchor"] = {"sth": h, "witnessed_by": "example-log"}
        out.append(rec)
        prev = h
    return out


def build_corpus() -> List[Case]:
    """The corpus, constructed rather than stored, so every case is reproducible from source."""
    cases: List[Case] = []
    add = cases.append

    # ---------------------------------------------------------------- EMPTY
    add(Case("empty_json_object", EMPTY, "case.json", "{}",
             "an object with no members: there is no property here to check"))
    add(Case("empty_json_array", EMPTY, "case.json", "[]",
             "zero records; any 'all records satisfy P' is vacuously true"))
    add(Case("empty_file", EMPTY, "case.jsonl", "",
             "zero bytes; a verifier that reports success has verified nothing"))
    add(Case("whitespace_only", EMPTY, "case.jsonl", "   \n\n  \t\n",
             "no records, but not zero bytes — a naive length check passes this"))
    add(Case("empty_graph", EMPTY, "case.json", _j({}),
             "no nodes: 'no cycle exists' is true and says nothing about your system", family=GRAPH))
    add(Case("zero_bindings", EMPTY, "case.json",
             _j({"bindings": [], "checked": 0}),
             "nothing was bound, so nothing was compared", family=CERTIFICATE))

    # ---------------------------------------------------------------- TRUNCATED
    full = _chain(8)
    add(Case("chain_tail_removed", TRUNCATED, "case.jsonl",
             "\n".join(_j(r).replace("\n", "") for r in full[:4]),
             "a prefix of a hash chain verifies PERFECTLY; only an anchor reveals the missing tail", family=CHAIN))
    add(Case("chain_last_record_cut", TRUNCATED, "case.jsonl",
             "\n".join(_j(r).replace("\n", "") for r in full[:-1]) + "\n" + _j(full[-1])[:40],
             "the final record is cut mid-JSON: a line-wise reader may simply drop it", family=CHAIN))
    add(Case("json_truncated_mid_object", TRUNCATED, "case.json",
             _j({"records": [1, 2, 3], "bound": 0.01})[:30],
             "invalid JSON that begins validly; a streaming parser can emit a partial result", family=CERTIFICATE))

    # ---------------------------------------------------------------- NO_ANCHOR
    add(Case("chain_without_anchor", NO_ANCHOR, "case.jsonl",
             "\n".join(_j(r).replace("\n", "") for r in _chain(6, anchor=False)),
             "internally consistent and tied to nothing; self-consistency is not authenticity", family=CHAIN))
    add(Case("cert_unsigned", NO_ANCHOR, "case.json",
             _j({"schema": "example/v1", "verdict": "PASS", "bound": 0.001,
                 "signature": None}),
             "a verdict with no signature and no pinned key: nothing attests to it", family=CERTIFICATE))
    add(Case("self_referential_root", NO_ANCHOR, "case.json",
             _j({"root": "abc123", "index": {"root": "abc123"}, "verified_against": "index"}),
             "the artifact is checked against a value it itself supplies", family=CERTIFICATE))

    # ---------------------------------------------------------------- DEGENERATE
    add(Case("single_record", SOUND_PASS, "case.jsonl",
             _j(_chain(1)[0]).replace("\n", ""),
             "one record with a valid genesis pointer. A chain of length one has no LINK to "
             "check, but it is a well-formed chain and accepting it is defensible.",
             family=CHAIN))
    add(Case("single_node_graph", SOUND_PASS, "case.json", _j({"a": []}),
             "one node waiting on nothing. A verifier MAY pass this: a system where nobody "
             "waits genuinely cannot wedge. Listed so over-refusal is visible, not scored.",
             family=GRAPH))
    add(Case("bound_of_one", DEGENERATE, "case.json",
             _j({"verdict": "PASS", "false_pass_bound": 1.0, "n": 0}),
             "a bound of 1.0 excludes nothing; passing under it is not evidence", family=CERTIFICATE))
    add(Case("sample_size_zero", DEGENERATE, "case.json",
             _j({"trials": 0, "failures": 0, "rate": 0.0}),
             "0 failures in 0 trials is a rate of nothing, not a rate of zero", family=CERTIFICATE))
    add(Case("all_cases_skipped", DEGENERATE, "case.json",
             _j({"tests": 12, "passed": 0, "failed": 0, "skipped": 12}),
             "every case was skipped; a green result here means nobody ran anything", family=CERTIFICATE))

    # ---------------------------------------------------------------- MALFORMED
    add(Case("not_json", MALFORMED, "case.json", "this is not json at all\n",
             "the correct response is a diagnosis naming the expected shape, not a verdict"))
    add(Case("wrong_root_type", MALFORMED, "case.json", _j("a bare string"),
             "a string where an object was required"))
    add(Case("nan_bound", MALFORMED, "case.json",
             '{"verdict": "PASS", "false_pass_bound": NaN}',
             "NaN compares false against every threshold, so a naive `bound < t` check rejects "
             "it, but a naive `not (bound > t)` check ACCEPTS it", family=CERTIFICATE))
    add(Case("negative_count", MALFORMED, "case.json",
             _j({"records": -5, "verdict": "PASS"}),
             "a negative count is not a count", family=CERTIFICATE))
    add(Case("bom_and_crlf", MALFORMED, "case.jsonl",
             "﻿" + _j({"seq": 0, "prev": "0" * 64}).replace("\n", "") + "\r\n",
             "a byte-order mark ahead of the first record breaks strict parsers silently", family=CHAIN))

    # ---------------------------------------------------------------- OUT OF DISTRIBUTION
    add(Case("future_schema_version", OUT_OF_DISTRIBUTION, "case.json",
             _j({"schema": "example/v99", "verdict": "PASS", "fields_you_do_not_know": True}),
             "a schema version from the future: 'I do not recognise this' is the honest answer", family=CERTIFICATE))
    add(Case("unknown_verdict_value", OUT_OF_DISTRIBUTION, "case.json",
             _j({"schema": "example/v1", "verdict": "PROBABLY_FINE", "bound": 0.01}),
             "an unrecognised verdict string must not be coerced to the nearest known one", family=CERTIFICATE))
    add(Case("cyclic_where_dag_expected", OUT_OF_DISTRIBUTION, "case.json",
             _j({"a": ["b"], "b": ["a"]}),
             "a cyclic graph handed to something expecting a DAG; infinite loop or wrong answer", family=GRAPH))
    add(Case("seq_repeats", OUT_OF_DISTRIBUTION, "case.jsonl",
             "\n".join(_j({"seq": s, "prev": "0" * 64}).replace("\n", "")
                       for s in [0, 1, 1, 2]),
             "a repeated sequence number: two records claim the same position", family=CHAIN))
    add(Case("rtl_and_unicode_ids", SOUND_PASS, "case.json",
             _j({"‮admin": ["مستخدم"], "مستخدم": []}),
             "identifiers containing a right-to-left override RENDER deceptively, but the graph "
             "is genuinely acyclic. Passing it is correct; the defect is in display, not the "
             "verdict, so scoring it would be a false accusation.", family=GRAPH))

    # ---------------------------------------------------------------- CONTROLS
    add(Case("valid_chain_with_anchor", POSITIVE, "case.jsonl",
             "\n".join(_j(r).replace("\n", "") for r in _chain(6)),
             "a well-formed anchored chain: a working verifier SHOULD accept this", family=CHAIN))
    add(Case("valid_acyclic_graph", POSITIVE, "case.json",
             _j({"a": ["b"], "b": ["c"], "c": []}),
             "a genuine acyclic wait-for graph with three nodes and two edges", family=GRAPH))
    add(Case("valid_certificate", POSITIVE, "case.json",
             _j({"schema": "example/v1", "verdict": "PASS", "false_pass_bound": 0.001,
                 "n": 4000, "scope": "the enumerated domain", "signature": "deadbeef"}),
             "a complete certificate with a finite bound, a scope and a signature", family=CERTIFICATE))
    add(Case("broken_chain_link", NEGATIVE, "case.jsonl",
             "\n".join(_j(dict(r, prev="f" * 64 if r["seq"] == 3 else r["prev"])).replace("\n", "")
                       for r in _chain(6)),
             "record 3's back-pointer is wrong: a working verifier SHOULD reject this", family=CHAIN))
    add(Case("cyclic_graph", NEGATIVE, "case.json", _j({"a": ["b"], "b": ["a"]}),
             "a two-cycle: a working deadlock checker SHOULD reject this", family=GRAPH))

    return cases


CORPUS = build_corpus()

BY_CATEGORY: Dict[str, List[Case]] = {}
for _c in CORPUS:
    BY_CATEGORY.setdefault(_c.category, []).append(_c)


def scored_cases() -> List[Case]:
    return [c for c in CORPUS if c.scored]


def controls(kind: str) -> List[Case]:
    return [c for c in CORPUS if c.category == kind]


__all__ = ["CHAIN", "GRAPH", "CERTIFICATE", "ANY", "FAMILIES", "SOUND_PASS", "Case", "CORPUS", "BY_CATEGORY", "UNCHECKABLE", "POSITIVE", "NEGATIVE",
           "EMPTY", "TRUNCATED", "NO_ANCHOR", "DEGENERATE", "MALFORMED", "OUT_OF_DISTRIBUTION",
           "build_corpus", "scored_cases", "controls"]
