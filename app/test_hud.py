import math
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "experiments")]
from hud_core import REPORTS, assistant_state, coordinates, filtered, inventory, project, shortest_path
from hud_view import WorkspaceHUD


class HUDTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [{"id": "user-7", "name": "Diska", "profile_directory": "Profile 7"},
                         {"id": "user-8", "name": "Diska", "profile_directory": "Profile 8"}]
        self.nodes, self.edges = inventory(self.profiles)

    def test_duplicate_profile_names_keep_distinct_real_targets(self):
        profiles = [n for n in self.nodes if n.group == "profile"]
        self.assertEqual({n.target for n in profiles}, {"user-7", "user-8"})
        self.assertEqual(len({n.id for n in self.nodes}), len(self.nodes))
        self.assertEqual(len(self.nodes), 7 + len(self.profiles) + len(REPORTS))

    def test_edges_only_reference_existing_nodes_and_documents_are_allowlisted(self):
        ids = {n.id for n in self.nodes}
        self.assertTrue(all(a in ids and b in ids for a, b in self.edges))
        self.assertTrue(all(n.target in REPORTS for n in self.nodes if n.action == "report"))
        self.assertFalse(any("rea" == n.action for n in self.nodes))

    def test_filter_is_case_insensitive_and_does_not_leave_dangling_edges(self):
        nodes, edges = filtered(self.nodes, self.edges, "  DISKA ")
        self.assertEqual(len(nodes), 2)
        self.assertEqual(edges, [])
        self.assertEqual(filtered(self.nodes, self.edges, "missing"), ([], []))

    def test_path_traces_ownership_between_profiles_and_voice(self):
        self.assertEqual(shortest_path(self.edges, "profile:user-7", "voice"),
                         ["profile:user-7", "chrome", "leva", "voice"])
        self.assertEqual(shortest_path(self.edges, "not-found", "voice"), [])

    def test_removed_profiles_leave_no_stale_nodes_or_relations(self):
        nodes, edges = inventory(self.profiles[:1])
        self.assertNotIn("profile:user-8", {n.id for n in nodes})
        self.assertFalse(any("profile:user-8" in edge for edge in edges))

    def test_projection_handles_both_layouts_and_zoom_without_nan(self):
        points = coordinates(self.nodes)
        self.assertEqual(set(points), {n.id for n in self.nodes})
        for flat in (True, False):
            for point in points.values():
                for zoom in (.5, 1, 2.6):
                    self.assertTrue(all(math.isfinite(v) for v in project(point, 7, -1, zoom, 500, 300, flat)))

    def test_voice_preview_and_closed_sessions_never_claim_live_listening(self):
        self.assertEqual(assistant_state(False, False, False, "listening"), "idle")
        self.assertEqual(assistant_state(False, False, True, "listening", True), "idle")
        self.assertEqual(assistant_state(False, False, True, "speaking"), "speaking")
        self.assertEqual(assistant_state(True, True, True, "listening"), "sleeping")
        self.assertEqual(assistant_state(False, True, False, "idle"), "thinking")

    def test_inspector_routes_profile_by_id_without_using_llm_or_listbox_state(self):
        hud = object.__new__(WorkspaceHUD)
        hud.nodes, hud.selected, hud.main = self.nodes, "profile:user-8", Mock()
        hud.invoke()
        hud.main.send.assert_called_once_with("buka Chrome profil user-8", display="buka Chrome profil Diska")
        hud.main.open_voice.assert_not_called()

    def test_document_viewer_rejects_unlisted_path_before_reading(self):
        hud = object.__new__(WorkspaceHUD)
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
            hud.open_report("../API Key.txt")


if __name__ == "__main__":
    unittest.main()
