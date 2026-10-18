from datetime import datetime, timedelta, timezone
import unittest
from action_contract import ActionState, SimulationSession, SleepStateMachine, validate_action


class ExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.state = ActionState(known_profiles=["Diska", "Frontline Raver"],
            authorized_profiles=["Diska"], sessions={"Diska": {"four": 4, "thirteen": 13}},
            requested_tab_count=13)

    def test_unapproved_alternative_does_not_execute(self):
        session = SimulationSession(self.state)
        decision, receipt = session.execute("restore_session", {"profile": "Diska", "session_id": "four"}, "one")
        self.assertEqual(decision.status, "needs_confirmation")
        self.assertIsNone(receipt)
        self.assertEqual(session.effect_count, 0)

    def test_habit_is_not_profile_permission(self):
        self.assertEqual(validate_action("open_youtube", {"profile": "Frontline Raver"}, self.state).status,
                         "needs_confirmation")

    def test_only_trusted_user_choice_unlocks_pending_profile(self):
        session = SimulationSession(self.state)
        session.execute("suggest_profile", {"profile": "Frontline Raver"}, "suggest")
        self.assertIsNone(session.execute("open_youtube", {"profile": "Frontline Raver"}, "task")[1])
        session.apply_user_profile_choice("Frontline Raver")
        self.assertTrue(session.execute("open_youtube", {"profile": "Frontline Raver"}, "task")[1].success)

    def test_unknown_profile_or_session_is_rejected(self):
        self.assertEqual(validate_action("open_youtube", {"profile": "Chrome"}, self.state).status, "rejected")
        self.assertEqual(validate_action("restore_session", {"profile": "Diska", "session_id": "missing"}, self.state).status, "rejected")

    def test_failed_receipt_cannot_create_completion_message(self):
        session = SimulationSession(self.state)
        _, receipt = session.execute("open_profile", {"profile": "Diska"}, "fail", fail=True)
        self.assertIn("gagal", session.render(receipt))
        self.assertEqual(session.effect_count, 0)
        self.assertIn("belum", session.render(None).lower())

    def test_provider_retry_does_not_repeat_effect(self):
        session = SimulationSession(self.state)
        first = session.execute("open_youtube", {"profile": "Diska"}, "same-id")
        second = session.execute("open_youtube", {"profile": "Diska"}, "same-id")
        self.assertEqual(first[1], second[1])
        self.assertEqual(session.effect_count, 1)
        self.assertIsNone(session.execute("open_profile", {"profile": "Diska"}, "same-id")[1])

    def test_handoff_blocks_further_automatic_actions(self):
        session = SimulationSession(self.state)
        session.execute("handoff", {}, "handoff")
        self.assertEqual(session.execute("open_youtube", {"profile": "Diska"}, "later")[0].reason, "user_has_control")

    def test_extra_arguments_and_boolean_minutes_are_rejected(self):
        self.assertEqual(validate_action([], {}, self.state).status, "rejected")
        self.assertEqual(validate_action("ask_profile", {"profile": "Diska"}, self.state).status, "rejected")
        self.assertEqual(validate_action("schedule_sleep", {"resume_at": "2026-10-19T04:00:00+07:00",
            "observe_minutes": True, "sleep_minutes": 60}, self.state).status, "rejected")

    def test_valid_session_can_complete_only_through_receipt(self):
        session = SimulationSession(self.state)
        decision, receipt = session.execute("restore_session", {"profile": "Diska", "session_id": "thirteen"}, "ok")
        self.assertEqual(decision.status, "allowed")
        self.assertIn("Dalam simulasi", session.render(receipt))


class SleepCycleTests(unittest.TestCase):
    def test_exact_user_sleep_cycle_and_activity_cancellation(self):
        wake = datetime(2026, 10, 19, 4, tzinfo=timezone(timedelta(hours=7)))
        machine = SleepStateMachine()
        machine.arm(wake)
        self.assertEqual(machine.advance(wake), "observing")
        self.assertEqual(machine.advance(wake + timedelta(minutes=30)), "paused")
        self.assertEqual(machine.next_transition, wake + timedelta(minutes=90))
        self.assertEqual(machine.advance(wake + timedelta(minutes=90)), "observing")
        self.assertEqual(machine.advance(wake + timedelta(minutes=95), activity=True), "off")
        self.assertIsNone(machine.next_transition)
        self.assertEqual(machine.advance(wake + timedelta(hours=5)), "off")

    def test_manual_stop_removes_old_wake_schedule(self):
        wake = datetime(2026, 10, 19, 4, tzinfo=timezone(timedelta(hours=7)))
        machine = SleepStateMachine()
        machine.arm(wake)
        machine.cancel()
        self.assertEqual(machine.advance(wake + timedelta(days=1)), "off")


if __name__ == "__main__":
    unittest.main()
