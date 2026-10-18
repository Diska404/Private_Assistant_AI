import unittest
from hybrid_engine import HybridEngine, EngineError, OnlineUnavailable, check_online_status, select_gpu_devices


class RoutingTests(unittest.TestCase):
    def test_gpu_selection_uses_device_names_not_nvidia_smi_order(self):
        listing = ("  CUDA0: NVIDIA GeForce RTX 5070 (12199 MiB, 10000 MiB free)\n"
                   "  CUDA1: NVIDIA GeForce RTX 4050 Laptop GPU (6140 MiB, 5000 MiB free)")
        devices, budgets = select_gpu_devices(listing, "gpu4050")
        self.assertEqual(devices, ["CUDA1"])
        self.assertEqual(budgets, [3976.0])
        devices, budgets = select_gpu_devices(listing, "dual")
        self.assertEqual(devices, ["CUDA1", "CUDA0"])
        self.assertEqual(budgets, [3976.0, 8976.0])

    def test_explicit_dual_mode_does_not_silently_ignore_missing_gpu(self):
        with self.assertRaises(EngineError):
            select_gpu_devices("CUDA1: NVIDIA GeForce RTX 4050 Laptop GPU (6140 MiB, 5000 MiB free)", "dual")

    def test_healthy_online_never_loads_local(self):
        def forbidden(_):
            self.fail("Local engine must stay unloaded while online succeeds")
        result = HybridEngine(lambda _: "online-ok", forbidden).generate([])
        self.assertEqual(result["provider"], "google")

    def test_quota_falls_back_and_preserves_context(self):
        messages = [{"role": "user", "content": "Pakai profil Diska"},
                    {"role": "assistant", "content": "Baik"},
                    {"role": "user", "content": "Profil yang tadi apa?"}]
        seen = []
        def limited(_):
            check_online_status(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        def local(actual):
            seen.append(actual)
            return "Diska"
        result = HybridEngine(limited, local).generate(messages)
        self.assertEqual(result["provider"], "local")
        self.assertEqual(seen, [messages])

    def test_does_not_retry_exhausted_online_within_session(self):
        calls = []
        def limited(_):
            calls.append(1)
            raise OnlineUnavailable("quota_or_rate_limit")
        engine = HybridEngine(limited, lambda _: "local-ok")
        engine.generate([])
        engine.generate([])
        self.assertEqual(len(calls), 1)

    def test_credentials_or_bad_requests_do_not_trigger_fallback(self):
        for status in [400, 401, 403, 500]:
            with self.subTest(status=status):
                def fail_online(_):
                    check_online_status(status, {"error": {"status": "DENIED"}})
                def forbidden(_):
                    self.fail("Do not hide an unrelated error as exhausted quota")
                with self.assertRaises(EngineError):
                    HybridEngine(fail_online, forbidden).generate([])

    def test_local_failure_does_not_report_success(self):
        def limited(_):
            raise OnlineUnavailable("quota_or_rate_limit")
        def unavailable(_):
            raise EngineError("local_model_missing")
        with self.assertRaises(EngineError):
            HybridEngine(limited, unavailable).generate([])


if __name__ == "__main__":
    unittest.main()
