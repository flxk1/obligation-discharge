# SPDX-License-Identifier: MIT
# Copyright 2026 flxk1
"""obligation_discharge — decide whether an enforcement point may act on a
permit that carries duties, and whether those duties were later performed.

XACML 3.0 requires a PEP to deny access unless it understands and can discharge
every obligation attached to a permit. The engines that replaced XACML dropped
that rule: OPA leaves obligations "an implementation concern for the PEP", and
AuthZEN returns a boolean plus optional advice with no discharge semantics. The
practical consequence is that an enforcement point which does not recognise a
duty silently ignores it, turning *permit-with-a-duty* into a bare *permit*.

Two moments, because that is how enforcement actually deploys:

  * :func:`admit` runs in the request path. Given the obligations on a decision
    and a PEP's declared capabilities, it answers whether the permit may be
    acted on at all.
  * :func:`settle` runs afterwards, in an audit or batch job. Given what was
    admitted and what was actually discharged, it answers whether the duties
    were performed, and on time.

:func:`fitness` answers the third question, before any request exists: which
obligation types in a policy is this enforcement point unfit to carry?

Pure functions. No clock, no I/O — ``now`` is always supplied by the caller.
Obligations are plain data: this package models discharge, not deontic logic,
and takes no position on what a duty *means*. Any vocabulary works.

Silence is never taken for consent. A capability the PEP did not mention reads
UNDECLARED, never "supported", so a PEP that says nothing cannot quietly
downgrade a duty into permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from ._version import __version__

__all__ = [
    "__version__",
    "Obligation", "Declaration", "Discharge",
    "Admission", "Settlement", "AdmissionStatus", "SettlementStatus",
    "Admitted", "Settled", "Fitness", "Determination",
    "admit", "settle", "fitness",
    "OPTIONS_BY_ADMISSION", "OPTIONS_BY_SETTLEMENT",
]


# --------------------------------------------------------------------------
# verdicts
# --------------------------------------------------------------------------

class Admission(Enum):
    """Per-obligation outcome at decision time."""

    ACCEPTED = "ACCEPTED"
    """The PEP declares it can discharge this duty. It is now owed."""

    REFUSED = "REFUSED"
    """The PEP declares it cannot. A mandatory duty here forces a denial."""

    UNDECLARED = "UNDECLARED"
    """The PEP said nothing either way. Treated as a refusal when the duty is
    mandatory: silence is not a capability. Kept distinct from REFUSED because
    an honest "I cannot" and a silence call for different remedies, and because
    a system that declares its limits must never fare worse than one that
    stays quiet."""

    DROPPED = "DROPPED"
    """Advisory (non-mandatory) and not supported. XACML advice may be ignored,
    so this does not deny — but it is reported rather than discarded."""


class Settlement(Enum):
    """Per-obligation outcome after the fact."""

    DISCHARGED = "DISCHARGED"
    DISCHARGED_LATE = "DISCHARGED_LATE"
    """Performed, but after its deadline. Distinct from DISCHARGED because
    "log the access within 60 seconds" is not satisfied by logging it in an
    hour, and collapsing the two is how a deadline stops meaning anything."""

    PENDING = "PENDING"
    """Owed, not yet performed, not yet due."""

    OVERDUE = "OVERDUE"
    """Owed, not performed, past its deadline."""


class AdmissionStatus(Enum):
    ADMISSIBLE = "ADMISSIBLE"
    MUST_DENY = "MUST_DENY"

    UNDETERMINED = "UNDETERMINED"
    """Nobody said what was owed. `obligations=None` is not an empty list: an
    OPA rule that evaluates to undefined returns no `result` key at all, and a
    PDP that is unreachable returns nothing. Reading either as "no duties
    apply" is how a permit-with-duties degrades into a bare permit. Distinct
    from MUST_DENY because the remedy is to find out, not to refuse."""


class SettlementStatus(Enum):
    SETTLED = "SETTLED"
    """Every owed duty was discharged, each within its deadline."""

    OUTSTANDING = "OUTSTANDING"
    """Duties are owed and undone, but none is late. This is the ordinary
    steady state — an obligation with no deadline is owed indefinitely and can
    never do better than OUTSTANDING, which is why lateness is a status of its
    own rather than a shade of this one."""

    LATE = "LATE"
    """A deadline passed: something is overdue, or was discharged after it was
    due. Separated from OUTSTANDING because it is the only settlement state
    that warrants an alarm, and because DISCHARGED_LATE would otherwise reach
    no status at all and report a missed deadline as clean."""

    UNSETTLED = "UNSETTLED"
    """Nobody looked. Never let an absent record read as a clean one."""


OPTIONS_BY_ADMISSION = {
    Admission.REFUSED: ("route-to-a-capable-pep", "amend-the-policy", "deny"),
    Admission.UNDECLARED: ("declare-the-capability", "deny"),
    Admission.DROPPED: ("accept-the-gap", "implement-the-advice"),
    Admission.ACCEPTED: (),
}

OPTIONS_BY_SETTLEMENT = {
    Settlement.OVERDUE: ("discharge-now", "revoke-the-authorisation", "escalate"),
    Settlement.PENDING: ("wait", "discharge-now"),
    Settlement.DISCHARGED_LATE: ("review-the-deadline", "investigate-the-delay"),
    Settlement.DISCHARGED: (),
}


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
#
# NOTE: fields are APPENDED, never inserted. Positional construction is part of
# the public surface, so adding a field mid-dataclass silently rebinds every
# positional caller's arguments.

@dataclass(frozen=True)
class Obligation:
    """A duty attached to a permit.

    `type` is an opaque identifier in whatever vocabulary the deployment uses
    — a XACML ObligationId, a URI, a bare string. `mandatory` follows XACML's
    split: an obligation must be discharged, advice may be ignored.
    `deadline_s` is measured from the decision, so an obligation carries no
    absolute time of its own and stays reusable across decisions.
    """

    id: str
    type: str
    mandatory: bool = True
    deadline_s: float | None = None

    def __post_init__(self) -> None:
        if self.deadline_s is not None and self.deadline_s < 0:
            raise ValueError(
                f"deadline_s must not be negative (got {self.deadline_s!r}); "
                f"a duty cannot fall due before the decision that created it"
            )


@dataclass(frozen=True)
class Declaration:
    """What an enforcement point says it can do.

    Two explicit sets, plus a third state that is the absence of both. A type
    in neither set is UNDECLARED, and that is the point of keeping
    `unsupported` rather than inferring it by complement.
    """

    pep: str
    supports: frozenset[str] = frozenset()
    unsupported: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "supports", frozenset(self.supports))
        object.__setattr__(self, "unsupported", frozenset(self.unsupported))

    @property
    def contradictory(self) -> frozenset[str]:
        """Types claimed both supported and unsupported."""
        return self.supports & self.unsupported


@dataclass(frozen=True)
class Discharge:
    """Evidence that a duty was performed."""

    obligation_id: str
    at: str


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Determination:
    obligation: Obligation
    verdict: Admission | Settlement
    detail: str = ""

    @property
    def options(self) -> tuple[str, ...]:
        if isinstance(self.verdict, Admission):
            return OPTIONS_BY_ADMISSION[self.verdict]
        return OPTIONS_BY_SETTLEMENT[self.verdict]


@dataclass(frozen=True)
class Admitted:
    status: AdmissionStatus
    determinations: tuple[Determination, ...]
    pep: str
    detail: str = ""

    @property
    def may_permit(self) -> bool:
        """True only for ADMISSIBLE. UNDETERMINED is not a permit: the one
        thing this package must never do is let an unanswered question read
        as an answered one."""
        return self.status is AdmissionStatus.ADMISSIBLE

    @property
    def blocking(self) -> tuple[Determination, ...]:
        """The determinations forcing a denial."""
        return tuple(
            d for d in self.determinations
            if d.obligation.mandatory
            and d.verdict in (Admission.REFUSED, Admission.UNDECLARED)
        )

    @property
    def owed(self) -> tuple[Obligation, ...]:
        """Obligations the PEP accepted, and must therefore later discharge."""
        return tuple(
            d.obligation for d in self.determinations
            if d.verdict is Admission.ACCEPTED
        )


@dataclass(frozen=True)
class Settled:
    status: SettlementStatus
    determinations: tuple[Determination, ...]
    unmatched: tuple[Discharge, ...] = ()
    """Discharges naming an obligation that was never admitted. Reported, not
    dropped — a discharge for an unknown duty means the two sides disagree
    about what was owed."""

    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is SettlementStatus.SETTLED

    @property
    def outstanding(self) -> tuple[Determination, ...]:
        return tuple(
            d for d in self.determinations
            if d.verdict in (Settlement.PENDING, Settlement.OVERDUE)
        )

    @property
    def late(self) -> tuple[Determination, ...]:
        """Everything that missed a deadline, discharged or not."""
        return tuple(
            d for d in self.determinations
            if d.verdict in (Settlement.DISCHARGED_LATE, Settlement.OVERDUE)
        )


@dataclass(frozen=True)
class Fitness:
    pep: str
    supported: tuple[str, ...]
    refused: tuple[str, ...]
    undeclared: tuple[str, ...]

    @property
    def fit(self) -> bool:
        """Fit only when nothing is refused and nothing is unspoken."""
        return not self.refused and not self.undeclared


# --------------------------------------------------------------------------
# time
# --------------------------------------------------------------------------

def _parse(ts: str) -> datetime:
    """ISO-8601. `fromisoformat` did not accept a trailing Z before 3.11."""
    if not isinstance(ts, str):
        raise ValueError(f"timestamp must be a string, got {type(ts).__name__}")
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    # A naive timestamp compared against an aware one raises TypeError, which
    # would escape every ValueError guard below and crash the caller. Naive
    # input is read as UTC; mixing the two is otherwise unrecoverable here.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


# --------------------------------------------------------------------------
# the three questions
# --------------------------------------------------------------------------

def admit(obligations, declaration: Declaration) -> Admitted:
    """Decide whether a permit carrying `obligations` may be acted on.

    XACML 3.0's rule, kept intact: a mandatory obligation the PEP cannot
    discharge forces a denial. Silence counts as inability.
    """
    if obligations is None:
        return Admitted(
            AdmissionStatus.UNDETERMINED, (), declaration.pep,
            "no obligation list was supplied; absent duties are not absent duties",
        )
    determinations: list[Determination] = []
    for ob in obligations:
        # Resolve the declared capability first, then apply the mandatory /
        # advisory split once. Deciding both at the same time is what let a
        # contradictory declaration reach an advisory obligation as UNDECLARED,
        # offering "deny" for something that cannot deny.
        if ob.type in declaration.contradictory:
            known, why = None, (
                f"{declaration.pep!r} declares {ob.type!r} both supported and "
                f"unsupported; a contradictory declaration states nothing"
            )
        elif ob.type in declaration.supports:
            known, why = True, ""
        elif ob.type in declaration.unsupported:
            known, why = False, (
                f"{declaration.pep!r} declares it cannot discharge {ob.type!r}"
            )
        else:
            known, why = None, (
                f"{declaration.pep!r} does not declare {ob.type!r} either way"
            )

        if known is True:
            verdict, detail = Admission.ACCEPTED, ""
        elif not ob.mandatory:
            verdict, detail = Admission.DROPPED, f"advisory and may be ignored: {why}"
        elif known is False:
            verdict, detail = Admission.REFUSED, why
        else:
            verdict, detail = Admission.UNDECLARED, why
        determinations.append(Determination(ob, verdict, detail))

    blocking = [
        d for d in determinations
        if d.obligation.mandatory
        and d.verdict in (Admission.REFUSED, Admission.UNDECLARED)
    ]
    if blocking:
        return Admitted(
            AdmissionStatus.MUST_DENY, tuple(determinations), declaration.pep,
            f"{len(blocking)} mandatory obligation(s) cannot be discharged",
        )
    return Admitted(
        AdmissionStatus.ADMISSIBLE, tuple(determinations), declaration.pep,
    )


def settle(admitted: Admitted, discharges, *, decided_at: str, now: str) -> Settled:
    """Check what was owed against what was performed.

    Only obligations the PEP ACCEPTED are settled: a duty that was refused or
    undeclared denied the request, and a dropped advisory was never owed.

    `discharges=None` means no observation was made, which is UNSETTLED — it
    must never read as a clean settlement. An empty list means someone looked
    and found nothing, which is a real finding.
    """
    if admitted.status is AdmissionStatus.UNDETERMINED:
        return Settled(
            SettlementStatus.UNSETTLED, (), (),
            "the admission was UNDETERMINED; there is no record of what was owed",
        )
    if discharges is None:
        return Settled(
            SettlementStatus.UNSETTLED, (), (),
            "no discharge record was supplied; this is not a settlement",
        )
    try:
        t0, t_now = _parse(decided_at), _parse(now)
    except ValueError as exc:
        return Settled(SettlementStatus.UNSETTLED, (), (), f"unreadable timestamp: {exc}")
    if t_now < t0:
        return Settled(
            SettlementStatus.UNSETTLED, (), (),
            f"`now` ({now}) precedes the decision ({decided_at})",
        )

    owed = {ob.id: ob for ob in admitted.owed}

    # Earliest discharge wins: that is when the duty was met. Later repeats are
    # not an error, and are not evidence of anything further.
    earliest: dict[str, datetime] = {}
    unmatched: list[Discharge] = []
    for d in discharges:
        if d.obligation_id not in owed:
            unmatched.append(d)
            continue
        try:
            at = _parse(d.at)
        except ValueError as exc:
            return Settled(
                SettlementStatus.UNSETTLED, (), tuple(unmatched),
                f"unreadable discharge timestamp on {d.obligation_id!r}: {exc}",
            )
        if d.obligation_id not in earliest or at < earliest[d.obligation_id]:
            earliest[d.obligation_id] = at

    determinations: list[Determination] = []
    for ob in admitted.owed:
        due = t0 + timedelta(seconds=ob.deadline_s) if ob.deadline_s is not None else None
        at = earliest.get(ob.id)
        if at is not None:
            # "within 60 seconds" includes the 60th second, so the deadline is
            # inclusive and lateness is a strict inequality.
            if due is not None and at > due:
                verdict = Settlement.DISCHARGED_LATE
                detail = f"discharged {(at - due).total_seconds():g}s after the deadline"
            else:
                verdict, detail = Settlement.DISCHARGED, ""
        elif due is not None and t_now > due:
            verdict = Settlement.OVERDUE
            detail = f"overdue by {(t_now - due).total_seconds():g}s"
        else:
            verdict = Settlement.PENDING
            detail = "" if due is not None else "no deadline; cannot fall due"
        determinations.append(Determination(ob, verdict, detail))

    # Precedence: a missed deadline outranks an open one, which outranks clean.
    # DISCHARGED_LATE must reach the status — it is done, but not on time, and
    # letting it fall through reports a breached deadline as a clean run.
    late = [d for d in determinations
            if d.verdict in (Settlement.OVERDUE, Settlement.DISCHARGED_LATE)]
    owed = [d for d in determinations if d.verdict is Settlement.PENDING]
    if late:
        status = SettlementStatus.LATE
    elif owed:
        status = SettlementStatus.OUTSTANDING
    else:
        status = SettlementStatus.SETTLED
    return Settled(status, tuple(determinations), tuple(unmatched))


def fitness(obligation_types, declaration: Declaration) -> Fitness:
    """Ask, before any request exists, which duties in a policy this
    enforcement point cannot carry."""
    seen = dict.fromkeys(obligation_types)  # de-duplicate, keep order
    supported, refused, undeclared = [], [], []
    for t in seen:
        if t in declaration.contradictory or t not in (declaration.supports | declaration.unsupported):
            undeclared.append(t)
        elif t in declaration.supports:
            supported.append(t)
        else:
            refused.append(t)
    return Fitness(declaration.pep, tuple(supported), tuple(refused), tuple(undeclared))
