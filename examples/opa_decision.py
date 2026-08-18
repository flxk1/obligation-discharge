# SPDX-License-Identifier: MIT
"""An OPA decision that carries duties, including the undefined case.

OPA leaves obligations to the PEP, so a Rego policy that wants them emits them
as ordinary result data under a name of its own. Two shapes matter:

    {"decision_id": "...", "result": {"allow": true, "obligations": [...]}}
    {"decision_id": "..."}                       # rule undefined: no result

The second is the dangerous one. When a Rego rule is undefined OPA omits
`result` entirely, and a mapping that reaches for `result.obligations` with a
default of `[]` turns "I do not know what is owed" into "nothing is owed".

Run: python examples/opa_decision.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from obligation_discharge import Declaration, Obligation, admit, fitness

PERMIT = {
    "decision_id": "8f5a...",
    "result": {
        "allow": True,
        "obligations": [
            {"id": "ob-1", "type": "urn:log:access", "deadline_s": 60},
            {"id": "ob-2", "type": "urn:redact:ssn"},
        ],
    },
}
UNDEFINED = {"decision_id": "a91c..."}   # the rule did not fire


def obligations_from(response):
    """Return None when OPA said nothing, [] when it said "no duties".

    The single line that matters is the `None` default. `.get("result", {})`
    followed by `.get("obligations", [])` is the idiomatic spelling and it is
    the bug: it cannot tell an unencumbered permit from an undefined rule."""
    result = response.get("result")
    if result is None:
        return None
    return [
        Obligation(o["id"], o["type"], not o.get("advice", False), o.get("deadline_s"))
        for o in result.get("obligations", [])
    ]


SIDECAR = Declaration("envoy-sidecar", supports={"urn:log:access"})

for name, response in (("permit with duties", PERMIT), ("undefined rule", UNDEFINED)):
    decided = admit(obligations_from(response), SIDECAR)
    print(f"{name:<20} {decided.status.name:<13} may_permit={decided.may_permit}")
    for d in decided.determinations:
        print(f"  {d.obligation.type:<18} {d.verdict.name}")
    if decided.detail:
        print(f"  {decided.detail}")

# Before any request exists: which duties in this policy can the sidecar carry?
POLICY_TYPES = ["urn:log:access", "urn:redact:ssn", "urn:notify:ciso"]
f = fitness(POLICY_TYPES, SIDECAR)
print(f"\nstatic fitness of {f.pep}: fit={f.fit}")
print(f"  supported  {list(f.supported)}")
print(f"  undeclared {list(f.undeclared)}")
