#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the conformance vectors. Exit 0 if every vector reproduces.

The vectors are the specification: any implementation, in any language, that
reproduces these verdicts is conformant. They construct positionally on
purpose — a field inserted into the middle of a dataclass rebinds every
positional caller, and keyword-using tests cannot see it."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from obligation_discharge import (  # noqa: E402
    Declaration, Discharge, Obligation, admit, fitness, settle,
)

VECTORS = os.path.join(os.path.dirname(__file__), "vectors.json")


def _decl(v):
    return Declaration("pep", frozenset(v.get("supports", [])),
                       frozenset(v.get("unsupported", [])))


def _obs(v):
    if v["obligations"] is None:
        return None
    return [Obligation(*row) for row in v["obligations"]]


def main() -> int:
    data = json.load(open(VECTORS))
    failures = []
    total = 0

    for v in data["admit"]:
        total += 1
        got = admit(_obs(v), _decl(v))
        actual = {"status": got.status.name,
                  "verdicts": [d.verdict.name for d in got.determinations]}
        if actual != v["expect"]:
            failures.append((v["name"], v["expect"], actual))

    for v in data["settle"]:
        total += 1
        admitted = admit(_obs(v), _decl(v))
        discharges = (None if v["discharges"] is None
                      else [Discharge(*row) for row in v["discharges"]])
        got = settle(admitted, discharges,
                     decided_at=v["decided_at"], now=v["now"])
        actual = {"status": got.status.name,
                  "verdicts": [d.verdict.name for d in got.determinations]}
        if actual != v["expect"]:
            failures.append((v["name"], v["expect"], actual))

    for v in data["fitness"]:
        total += 1
        got = fitness(v["types"], _decl(v))
        actual = {"fit": got.fit, "supported": list(got.supported),
                  "refused": list(got.refused), "undeclared": list(got.undeclared)}
        if actual != v["expect"]:
            failures.append((v["name"], v["expect"], actual))

    for name, expect, actual in failures:
        print(f"FAIL {name}\n  expected {expect}\n  got      {actual}")
    print(f"{total - len(failures)}/{total} vectors reproduce")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
