# obligation-discharge

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

## Semantics

**Admission.** `ACCEPTED` when the PEP declares support. `REFUSED` when it
declares inability. `UNDECLARED` when it said nothing. `DROPPED` for advice it
cannot perform, which XACML permits it to ignore. A mandatory duty that is
`REFUSED` or `UNDECLARED` yields `MUST_DENY`.

**Silence is not a capability.** An undeclared type reads `UNDECLARED`, never
"supported". `REFUSED` and `UNDECLARED` deny alike, but stay distinct: an
honest "I cannot" and a silence need different remedies, and a PEP that
declares its limits must never fare worse than one that says nothing.

**Absence is not emptiness.** `obligations=None` is `UNDETERMINED` and is not a
permit. An undefined Rego rule returns no `result` key at all, and
`.get("result", {}).get("obligations", [])` reads that as "no duties apply".
Likewise `discharges=None` is `UNSETTLED` — nobody looked — while `[]` means
someone looked and found nothing.

**Settlement.** Only accepted duties settle. Deadlines are inclusive: "within
60 seconds" is met at the 60th second. `DISCHARGED_LATE` is distinct from
`DISCHARGED`, and reaches the status as `LATE` — a missed deadline never
reports clean. A duty with no deadline is owed indefinitely and rests at
`PENDING`, which is why `LATE` is a status of its own rather than a shade of
`OUTSTANDING`. The earliest discharge decides, regardless of input order. A
discharge naming a duty that was never owed is reported in `.unmatched` rather
than dropped.

**No clock, no I/O.** `now` is always supplied by the caller, so results are
reproducible. Naive timestamps are read as UTC.

## Limitations

- It does not verify that a discharge is genuine. `Discharge` is an assertion
  that something happened; binding it to evidence is the caller's problem.
- It takes no position on what a duty *means*. `urn:log:access` is an opaque
  string, and two systems agreeing on discharge may still disagree on content.
- Deadlines are wall-clock seconds from the decision. Business-hours,
  calendar, and event-relative deadlines are not modelled.
- It reports; it never acts. `.options` are choices for a caller to make.
- Mapping an engine's response onto `Obligation` is deployment-specific, and
  that mapping is where the interesting bugs live. See `examples/`.

## Prior art

XACML 3.0 §7.18 defines obligations and the discharge rule this package keeps.
Its implementations bind that rule to XACML's XML policy language and PDP.
What is unpackaged is the decision itself, usable with the engines that
dropped it — hence a standalone function over plain data.

[AuthZEN Authorization API 1.0](https://openid.net/specs/authorization-api-1_0-01.html)
defines `reason_admin`/`reason_user` and no obligations.
[Deontic Policies for Runtime Governance of Agentic AI Systems](https://arxiv.org/pdf/2606.19464)
(2026) argues these duties are "structurally inexpressible in allow/deny or
ABAC rule engines". Deontic vocabularies such as DPV and ODRL name what a duty
*is*; this package decides whether one can be carried.

## Tests

```
pytest -q
python conformance/run_conformance.py
```

The conformance vectors in `conformance/vectors.json` are the specification:
any implementation reproducing those verdicts is conformant. They construct
positionally, which is deliberate — a field inserted into the middle of a
dataclass rebinds every positional caller, and keyword-using tests cannot see
it.

## Licence

MIT.
