# Semantics and limitations

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
