# SPDX-License-Identifier: MIT
"""An AuthZEN 1.0 decision that carries duties.

AuthZEN's Authorization API 1.0 response is a boolean `decision` plus an
optional `context` object. The specification defines `reason_admin` and
`reason_user` inside it, and nothing else — there is no obligation field and no
discharge rule. Deployments that need duties therefore put them in `context`
under a name of their own choosing, and every PEP is free to ignore what it
finds there. This maps such a response onto an explicit admission decision.

Run: python examples/authzen_pdp.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from obligation_discharge import Declaration, Discharge, Obligation, admit, settle

# A verbatim AuthZEN 1.0 response body. `decision` is true; the duties ride
# along in `context`, invisible to the specification.
RESPONSE = {
    "decision": True,
    "context": {
        "id": "0dc9c1d5-...",
        "reason_admin": {"en": "Granted by policy C076E82F"},
        "obligations": [
            {"id": "ob-1", "type": "urn:log:access", "deadline_s": 60},
            {"id": "ob-2", "type": "urn:notify:ciso"},
            {"id": "ob-3", "type": "urn:mask:pii", "advice": True},
        ],
    },
}


def obligations_from(response):
    """AuthZEN carries no obligation schema, so the mapping is the deployment's.
    Note the default: anything not explicitly marked as advice is mandatory."""
    for o in response.get("context", {}).get("obligations", []):
        yield Obligation(
            id=o["id"],
            type=o["type"],
            mandatory=not o.get("advice", False),
            deadline_s=o.get("deadline_s"),
        )


# This gateway logs, and knows it cannot notify. It has never heard of masking.
GATEWAY = Declaration(
    pep="api-gateway",
    supports={"urn:log:access"},
    unsupported={"urn:notify:ciso"},
)

duties = list(obligations_from(RESPONSE))
decided = admit(duties, GATEWAY)

print(f"AuthZEN said decision={RESPONSE['decision']}")
print(f"admission: {decided.status.name}  (may_permit={decided.may_permit})")
for d in decided.determinations:
    print(f"  {d.obligation.type:<20} {d.verdict.name:<11} {d.detail}")
    if d.options:
        print(f"  {'':<20} options: {', '.join(d.options)}")

# Suppose the gateway is fixed to notify, and the request is permitted.
CAPABLE = Declaration("api-gateway", supports={"urn:log:access", "urn:notify:ciso"})
decided = admit(duties, CAPABLE)
print(f"\nafter declaring the missing capability: {decided.status.name}")

# An hour later the audit job asks what actually happened. The access was
# logged, but 90 seconds after the decision.
settled = settle(
    decided,
    [Discharge("ob-1", "2026-03-01T10:01:30Z")],
    decided_at="2026-03-01T10:00:00Z",
    now="2026-03-01T11:00:00Z",
)
print(f"settlement: {settled.status.name}")
for d in settled.determinations:
    print(f"  {d.obligation.type:<20} {d.verdict.name:<16} {d.detail}")
