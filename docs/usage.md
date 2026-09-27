# Usage and API


Decide whether an enforcement point may act on a permit that carries duties,
and whether those duties were later performed.

XACML 3.0 requires a PEP to deny access unless it understands and can discharge
every obligation attached to a permit. The engines that replaced XACML dropped
that rule. OPA leaves obligations to the PEP. AuthZEN 1.0 returns a boolean
`decision` plus optional advice, with no obligation field and no discharge
semantics. In both, an enforcement point that does not recognise a duty ignores
it, and *permit-with-a-duty* becomes a bare *permit*.

This package supplies the missing decision. It models discharge, not deontic
logic: obligations are opaque data and any vocabulary works.

## Install

```
pip install git+https://github.com/flxk1/obligation-discharge
```

Python 3.10+. No dependencies.

## Use

```python
from obligation_discharge import Declaration, Discharge, Obligation, admit, settle

duties = [
    Obligation("ob-1", "urn:log:access", deadline_s=60),
    Obligation("ob-2", "urn:notify:ciso"),
]
gateway = Declaration("api-gateway", supports={"urn:log:access"})

decided = admit(duties, gateway)
print(decided.status.name, decided.may_permit)
for d in decided.blocking:
    print(" ", d.obligation.type, d.verdict.name, "|", ", ".join(d.options))
```

```
MUST_DENY False
  urn:notify:ciso UNDECLARED | declare-the-capability, deny
```

Once the gateway declares the missing capability the permit is admissible, and
the duties are owed. Afterwards, an audit job asks whether they were performed:

```python
gateway = Declaration("api-gateway", supports={"urn:log:access", "urn:notify:ciso"})
decided = admit(duties, gateway)
settled = settle(
    decided,
    [Discharge("ob-1", "2026-03-01T10:01:30Z")],
    decided_at="2026-03-01T10:00:00Z",
    now="2026-03-01T10:05:00Z",
)
print(settled.status.name, settled.ok)
for d in settled.determinations:
    print(" ", d.obligation.type, d.verdict.name, d.detail)
```

```
LATE False
  urn:log:access DISCHARGED_LATE discharged 30s after the deadline
  urn:notify:ciso PENDING no deadline; cannot fall due
```

## API

| | |
|---|---|
| `admit(obligations, declaration)` | `Admitted` — may this permit be acted on? |
| `settle(admitted, discharges, *, decided_at, now)` | `Settled` — were the duties performed, and on time? |
| `fitness(obligation_types, declaration)` | `Fitness` — which duties can this PEP not carry, before any request exists |
| `Obligation(id, type, mandatory=True, deadline_s=None)` | a duty; `deadline_s` runs from the decision |
| `Declaration(pep, supports, unsupported)` | what a PEP says it can and cannot do |
| `Discharge(obligation_id, at)` | evidence a duty was performed |

`Admitted.may_permit`, `.blocking`, `.owed`. `Settled.ok`, `.outstanding`,
`.late`, `.unmatched`. Every determination carries `.options` — remedies to
choose from, never an action taken.
