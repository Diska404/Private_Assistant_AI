import json
from pathlib import Path
import unittest
from unittest.mock import patch
from action_contract import ActionState, SimulationSession, tool_definitions
from guarded_hybrid_trial import guarded_step
from hybrid_engine import HybridEngine, OnlineUnavailable, online_generate, online_propose_tool


class GuardedFlowTests(unittest.TestCase):
    def test_incomplete_provider_output_cannot_execute_even_if_arguments_look_valid(self):
        state = ActionState(known_profiles=["Diska"], authorized_profiles=["Diska"])
        session = SimulationSession(state)
        router = HybridEngine(lambda _: {"action": "open_youtube", "args": {"profile": "Diska"},
                                        "error": "incomplete_native_tool_response"}, lambda _: None)
        result = guarded_step(router, session, [], "incomplete")
        self.assertEqual(result["decision"]["status"], "rejected")
        self.assertEqual(session.effect_count, 0)

    def test_asking_in_prose_cannot_authorize_action(self):
        state = ActionState(known_profiles=["Diska"])
        session = SimulationSession(state)
        router = HybridEngine(lambda _: {"action": "open_youtube", "args": {"profile": "Diska"},
                                        "reply": "Sudah dibuka!"}, lambda _: self.fail("No local call"))
        result = guarded_step(router, session, [], "habit")
        self.assertEqual(result["decision"]["status"], "needs_confirmation")
        self.assertIsNone(result["receipt"])
        self.assertNotIn("Sudah dibuka", result["reply"])

    def test_online_to_local_retry_preserves_execution_ledger(self):
        state = ActionState(known_profiles=["Diska"], authorized_profiles=["Diska"])
        session = SimulationSession(state)
        proposal = {"action": "open_youtube", "args": {"profile": "Diska"}}
        first = HybridEngine(lambda _: proposal, lambda _: self.fail("Unexpected fallback"))
        guarded_step(first, session, [], "same-task")
        def exhausted(_):
            raise OnlineUnavailable("quota_or_rate_limit")
        fallback = HybridEngine(exhausted, lambda _: proposal)
        result = guarded_step(fallback, session, [], "same-task")
        self.assertEqual(result["provider"], "local")
        self.assertEqual(session.effect_count, 1)
        self.assertEqual(result["decision"]["reason"], "already_recorded_no_reexecution")


class GoogleAdapterTests(unittest.TestCase):
    @patch("hybrid_engine._online_request")
    def test_native_function_call_is_parsed_and_tools_are_declared(self, request):
        request.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"functionCall": {"name": "ask_profile", "args": {}}}]}}]}
        result = online_propose_tool([{"role": "user", "content": "Chrome dong"}],
                                    Path("unused"), "test-model", "policy", tool_definitions())
        self.assertEqual(result["action"], "ask_profile")
        payload = json.loads(request.call_args.args[0])
        self.assertEqual(payload["toolConfig"]["functionCallingConfig"]["mode"], "ANY")
        self.assertEqual(len(payload["tools"][0]["functionDeclarations"]), 13)

    @patch("hybrid_engine._online_request")
    def test_text_smoke_interface_is_preserved(self, request):
        request.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "OK"}]}}]}
        self.assertEqual(online_generate([], Path("unused"), "test-model"), "OK")


if __name__ == "__main__":
    unittest.main()
