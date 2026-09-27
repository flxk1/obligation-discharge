# obligation-discharge

Two decisions over a permit carrying duties: may an enforcement point act on it, and were the attached duties discharged on time.

## Problem

A permit with attached duties is treated as a plain permit. Decides admission and, later, whether the duties were discharged.

## Install

`pip install git+https://github.com/flxk1/obligation-discharge`

## Usage

```python
decided = admit(duties, Declaration("api-gateway", supports={"urn:log:access"}))
settled = settle(decided, [Discharge("ob-1", "2026-03-01T10:01:30Z")], decided_at=t0, now=t1)
decided.may_permit, settled.status.name   # True LATE
```

## Example

```
in : admit([Obligation("log-access", "audit", mandatory=True, deadline_s=60)], Declaration("api-gateway", supports=frozenset({"audit"})))
out: decided.status, decided.may_permit → AdmissionStatus.ADMISSIBLE True
```

## Interface

- `admit(obligations, declaration) -> Admitted(status, may_permit, blocking, owed)`; per duty ACCEPTED, REFUSED, UNDECLARED, DROPPED; mandatory REFUSED/UNDECLARED yields MUST_DENY; `None` -> UNDETERMINED
- `settle(admitted, discharges, *, decided_at, now) -> Settled(status, ok, outstanding, late, unmatched)`; per duty DISCHARGED, DISCHARGED_LATE, PENDING, OVERDUE; `None` -> UNSETTLED
- `Obligation(id, type, mandatory=True, deadline_s=None)`, `Declaration(pep, supports, unsupported)`, `Discharge(obligation_id, at)`; determinations carry `.options`

## Family

Assurance artifact, pillar "attached duties" of [governance-certification](https://github.com/flxk1/governance-certification). Consumes: obligation fields of a PDP response (XACML 3.0 §7.18, OPA, AuthZEN; `examples/`). Docs: [docs/](docs/).

## Status

0.1.0 · 36 tests · 21 conformance vectors · Python ≥ 3.10

## How this is made

The code and documentation are written with Loomground agents running on Claude (Anthropic). The maintainer reads and corrects all of it.

## License

MIT — [LICENSES/MIT.txt](LICENSES/MIT.txt)
