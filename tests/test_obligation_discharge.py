# SPDX-License-Identifier: MIT
# Copyright 2026 flxk1
"""Tests for obligation_discharge. Runs under both `pytest` and
`python -m unittest discover -s tests`.

Pure functions over two moments — no clock, no I/O. The properties are here
rather than in a probe script because they are what found the real defects:
the exhaustive admission cross-product, and the precedence rules that decide
whether a missed deadline can reach the status."""

from __future__ import annotations

import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from obligation_discharge import (  # noqa: E402
    Admission, AdmissionStatus, Declaration, Discharge, Obligation,
    Settlement, SettlementStatus, admit, fitness, settle,
)

T0 = "2026-03-01T10:00:00Z"
LATER = "2026-03-01T11:00:00Z"

SUPPORTS = Declaration("pep", supports={"t"})
UNSUPPORTED = Declaration("pep", unsupported={"t"})
SILENT = Declaration("pep")
CONTRADICTORY = Declaration("pep", supports={"t"}, unsupported={"t"})


def owed(deadline_s=None, mandatory=True):
    return Obligation("o1", "t", mandatory, deadline_s)


class TestAdmissionFollowsXACML(unittest.TestCase):
    """XACML 3.0: deny unless every mandatory obligation can be discharged."""

    def test_a_supported_duty_is_accepted(self):
        a = admit([owed()], SUPPORTS)
        self.assertIs(a.status, AdmissionStatus.ADMISSIBLE)
        self.assertIs(a.determinations[0].verdict, Admission.ACCEPTED)
        self.assertEqual(len(a.owed), 1)

    def test_a_declared_inability_denies_a_mandatory_duty(self):
        a = admit([owed()], UNSUPPORTED)
        self.assertIs(a.status, AdmissionStatus.MUST_DENY)
        self.assertIs(a.determinations[0].verdict, Admission.REFUSED)

    def test_silence_denies_a_mandatory_duty(self):
        """The whole point: an unrecognised duty must not be ignored."""
        a = admit([owed()], SILENT)
        self.assertIs(a.status, AdmissionStatus.MUST_DENY)
        self.assertIs(a.determinations[0].verdict, Admission.UNDECLARED)

    def test_a_contradictory_declaration_states_nothing(self):
        a = admit([owed()], CONTRADICTORY)
        self.assertIs(a.determinations[0].verdict, Admission.UNDECLARED)

    def test_advice_never_denies(self):
        for decl in (UNSUPPORTED, SILENT, CONTRADICTORY):
            with self.subTest(decl=decl):
                a = admit([owed(mandatory=False)], decl)
                self.assertIs(a.status, AdmissionStatus.ADMISSIBLE)
                self.assertIs(a.determinations[0].verdict, Admission.DROPPED)

    def test_one_undischargeable_duty_denies_the_whole_decision(self):
        a = admit([Obligation("a", "t"), Obligation("b", "other")], SUPPORTS)
        self.assertIs(a.status, AdmissionStatus.MUST_DENY)
        self.assertEqual([d.obligation.id for d in a.blocking], ["b"])


class TestAdmissionProperties(unittest.TestCase):
    """The full cross product of declaration state x mandatory."""

    DECLS = {"supported": SUPPORTS, "unsupported": UNSUPPORTED,
             "contradictory": CONTRADICTORY, "silent": SILENT}

    def test_deny_exactly_when_a_mandatory_duty_is_unsupported(self):
        for name, decl in self.DECLS.items():
            for mandatory in (True, False):
                with self.subTest(decl=name, mandatory=mandatory):
                    a = admit([owed(mandatory=mandatory)], decl)
                    expected = mandatory and name != "supported"
                    self.assertEqual(a.status is AdmissionStatus.MUST_DENY, expected)

    def test_blocking_always_agrees_with_the_status(self):
        for decl, mandatory in itertools.product(self.DECLS.values(), (True, False)):
            a = admit([owed(mandatory=mandatory)], decl)
            self.assertEqual(bool(a.blocking), a.status is AdmissionStatus.MUST_DENY)

    def test_owed_is_exactly_what_was_accepted(self):
        for decl, mandatory in itertools.product(self.DECLS.values(), (True, False)):
            a = admit([owed(mandatory=mandatory)], decl)
            accepted = [d.obligation for d in a.determinations
                        if d.verdict is Admission.ACCEPTED]
            self.assertEqual(list(a.owed), accepted)

    def test_declaring_a_limit_never_fares_worse_than_hiding_it(self):
        """Non-punitive disclosure. If admitting "I cannot" were worse than
        saying nothing, every PEP would learn to say nothing."""
        for mandatory in (True, False):
            declared = admit([owed(mandatory=mandatory)], UNSUPPORTED)
            silent = admit([owed(mandatory=mandatory)], SILENT)
            self.assertFalse(declared.may_permit is False and silent.may_permit is True)

    def test_deny_is_never_offered_for_something_that_cannot_deny(self):
        for decl in self.DECLS.values():
            d = admit([owed(mandatory=False)], decl).determinations[0]
            self.assertNotIn("deny", d.options)


class TestAbsenceIsNotEmptiness(unittest.TestCase):
    def test_no_obligation_list_is_undetermined_not_permissive(self):
        """An undefined OPA rule returns no result at all."""
        a = admit(None, SUPPORTS)
        self.assertIs(a.status, AdmissionStatus.UNDETERMINED)
        self.assertFalse(a.may_permit)

    def test_an_empty_list_is_a_real_finding(self):
        a = admit([], SUPPORTS)
        self.assertIs(a.status, AdmissionStatus.ADMISSIBLE)
        self.assertTrue(a.may_permit)

    def test_an_undetermined_admission_cannot_be_settled(self):
        s = settle(admit(None, SUPPORTS), [], decided_at=T0, now=LATER)
        self.assertIs(s.status, SettlementStatus.UNSETTLED)

    def test_no_discharge_record_is_unsettled(self):
        s = settle(admit([owed()], SUPPORTS), None, decided_at=T0, now=LATER)
        self.assertIs(s.status, SettlementStatus.UNSETTLED)
        self.assertFalse(s.ok)

    def test_looking_and_finding_nothing_differs_from_not_looking(self):
        a = admit([owed()], SUPPORTS)
        self.assertIs(settle(a, [], decided_at=T0, now=LATER).status,
                      SettlementStatus.OUTSTANDING)
        self.assertIs(settle(a, None, decided_at=T0, now=LATER).status,
                      SettlementStatus.UNSETTLED)


class TestDeadlines(unittest.TestCase):
    def test_the_deadline_is_inclusive(self):
        """"within 60 seconds" is satisfied at the 60th second."""
        a = admit([owed(deadline_s=60)], SUPPORTS)
        for offset, expected in ((0, Settlement.DISCHARGED),
                                 (60, Settlement.DISCHARGED),
                                 (61, Settlement.DISCHARGED_LATE)):
            with self.subTest(offset=offset):
                at = f"2026-03-01T10:{offset // 60:02d}:{offset % 60:02d}Z"
                s = settle(a, [Discharge("o1", at)], decided_at=T0, now=LATER)
                self.assertIs(s.determinations[0].verdict, expected)

    def test_a_missed_deadline_never_reads_as_clean(self):
        """Found by running the AuthZEN example: DISCHARGED_LATE reached no
        status, so a lone late discharge reported SETTLED with ok=True."""
        a = admit([owed(deadline_s=60)], SUPPORTS)
        s = settle(a, [Discharge("o1", "2026-03-01T10:01:30Z")], decided_at=T0, now=LATER)
        self.assertIs(s.status, SettlementStatus.LATE)
        self.assertFalse(s.ok)
        self.assertEqual(len(s.late), 1)

    def test_a_duty_with_no_deadline_can_never_fall_due(self):
        a = admit([owed()], SUPPORTS)
        s = settle(a, [], decided_at=T0, now="2099-01-01T00:00:00Z")
        self.assertIs(s.determinations[0].verdict, Settlement.PENDING)
        self.assertIs(s.status, SettlementStatus.OUTSTANDING)

    def test_pending_becomes_overdue_and_never_returns(self):
        a = admit([owed(deadline_s=120)], SUPPORTS)
        seen = [settle(a, [], decided_at=T0, now=f"2026-03-01T10:{m:02d}:00Z")
                .determinations[0].verdict for m in range(5)]
        self.assertEqual(seen, [Settlement.PENDING] * 3 + [Settlement.OVERDUE] * 2)

    def test_a_negative_deadline_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            Obligation("o1", "t", True, -1)

    def test_late_reports_both_overdue_and_late_discharges(self):
        a = admit([Obligation("a", "t", True, 60), Obligation("b", "t", True, 60)], SUPPORTS)
        s = settle(a, [Discharge("a", "2026-03-01T10:05:00Z")], decided_at=T0, now=LATER)
        self.assertEqual({d.verdict for d in s.late},
                         {Settlement.DISCHARGED_LATE, Settlement.OVERDUE})


class TestSettlementMechanics(unittest.TestCase):
    def test_only_accepted_duties_are_settled(self):
        """A dropped advisory was never owed, so there is nothing to settle."""
        a = admit([owed(mandatory=False)], SILENT)
        s = settle(a, [], decided_at=T0, now=LATER)
        self.assertEqual(s.determinations, ())
        self.assertIs(s.status, SettlementStatus.SETTLED)

    def test_the_earliest_discharge_wins_whatever_the_input_order(self):
        a = admit([owed(deadline_s=60)], SUPPORTS)
        early = Discharge("o1", "2026-03-01T10:00:30Z")
        late = Discharge("o1", "2026-03-01T10:05:00Z")
        for order in ((early, late), (late, early)):
            with self.subTest(order=[d.at for d in order]):
                s = settle(a, list(order), decided_at=T0, now=LATER)
                self.assertIs(s.determinations[0].verdict, Settlement.DISCHARGED)

    def test_a_discharge_for_something_never_owed_is_surfaced(self):
        a = admit([owed()], SUPPORTS)
        s = settle(a, [Discharge("ghost", T0)], decided_at=T0, now=LATER)
        self.assertEqual([d.obligation_id for d in s.unmatched], ["ghost"])

    def test_a_naive_timestamp_does_not_crash_against_an_aware_one(self):
        """Mixing the two raises TypeError, which escaped every ValueError
        guard. Naive input is read as UTC."""
        a = admit([owed(deadline_s=60)], SUPPORTS)
        s = settle(a, [Discharge("o1", "2026-03-01T10:00:30")], decided_at=T0, now=LATER)
        self.assertIs(s.determinations[0].verdict, Settlement.DISCHARGED)

    def test_an_unreadable_timestamp_refuses_rather_than_raises(self):
        a = admit([owed()], SUPPORTS)
        s = settle(a, [], decided_at="not-a-time", now=LATER)
        self.assertIs(s.status, SettlementStatus.UNSETTLED)

    def test_now_before_the_decision_is_unsettled(self):
        a = admit([owed()], SUPPORTS)
        s = settle(a, [], decided_at=LATER, now=T0)
        self.assertIs(s.status, SettlementStatus.UNSETTLED)

    def test_settlement_is_deterministic(self):
        a = admit([owed(deadline_s=60)], SUPPORTS)
        args = ([Discharge("o1", "2026-03-01T10:00:30Z")],)
        self.assertEqual(settle(a, *args, decided_at=T0, now=LATER),
                         settle(a, *args, decided_at=T0, now=LATER))


class TestFitness(unittest.TestCase):
    def test_it_names_what_the_pep_cannot_carry_before_any_request(self):
        f = fitness(["t", "u", "v"], Declaration("pep", supports={"t"}, unsupported={"u"}))
        self.assertEqual((f.supported, f.refused, f.undeclared), (("t",), ("u",), ("v",)))
        self.assertFalse(f.fit)

    def test_fitness_requires_silence_to_be_broken(self):
        self.assertFalse(fitness(["t"], SILENT).fit)
        self.assertTrue(fitness(["t"], SUPPORTS).fit)

    def test_duplicate_types_are_reported_once_in_order(self):
        self.assertEqual(fitness(["t", "t"], SUPPORTS).supported, ("t",))


class TestDoctrine(unittest.TestCase):
    def test_the_package_offers_no_verdict_on_conduct(self):
        """It reports what was owed and what was done. It does not judge."""
        import obligation_discharge as od
        forbidden = ("breach", "violation", "penalt", "guilty", "sanction", "fault")
        offenders = [n for n in od.__all__ if any(w in n.lower() for w in forbidden)]
        self.assertEqual(offenders, [])

    def test_every_verdict_has_an_options_entry(self):
        """A half-wired options table is how a new verdict reaches a caller
        with no remedy attached."""
        import obligation_discharge as od
        for verdict in list(Admission) + list(Settlement):
            table = (od.OPTIONS_BY_ADMISSION if isinstance(verdict, Admission)
                     else od.OPTIONS_BY_SETTLEMENT)
            self.assertIn(verdict, table)

    def test_field_order_is_part_of_the_public_surface(self):
        """A field inserted mid-dataclass silently rebinds positional callers.
        This has happened once already, in a sibling package."""
        import dataclasses
        self.assertEqual([f.name for f in dataclasses.fields(Obligation)],
                         ["id", "type", "mandatory", "deadline_s"])
        self.assertEqual([f.name for f in dataclasses.fields(Discharge)],
                         ["obligation_id", "at"])

    def test_version_matches_packaging(self):
        import importlib.metadata
        import obligation_discharge as od
        declared = importlib.metadata.version("obligation-discharge")
        self.assertEqual(od.__version__, declared)


if __name__ == "__main__":
    unittest.main()
