import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

from assistant_tools import AssistantTools, selected_skills
from code_graph import CodeGraph
from rea_analysis import ReaAnalysis
from workflow_skills import WorkflowSkills


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def graph(self):
        folder = self.root / 'graphify-out'; folder.mkdir()
        (folder / 'graph.json').write_text(json.dumps({'nodes': [
            {'id': 'A', 'label': 'Controller', 'source_file': 'controller.py'},
            {'id': 'B', 'label': 'Service'}, {'id': 'C', 'label': 'Store'}, {'id': 'D', 'label': 'Separate'}],
            'links': [{'source': 'A', 'target': 'B', 'relation': 'calls', 'confidence': 'EXTRACTED'},
                      {'source': 'B', 'target': 'C', 'relation': 'imports', 'confidence': 'EXTRACTED'}]}))
        return CodeGraph(self.root)

    def test_graph_path_keeps_original_edges_and_reports_disconnection(self):
        service = self.graph()
        result = service.run({'action': 'path', 'query': 'A', 'target': 'C'})
        self.assertEqual([n['id'] for n in result['nodes']], ['A', 'B', 'C'])
        self.assertEqual(result['edges'][0]['relation'], 'calls')
        self.assertIn('undirected', result['direction'])
        result = service.run({'action': 'path', 'query': 'A', 'target': 'D'})
        self.assertEqual(result['nodes'], [])
        self.assertIn('tidak ditemukan', result['reply'])

    def test_graph_staleness_missing_sources_and_no_match_are_not_fabricated(self):
        service = self.graph()
        (self.root / 'graphify-out/.needs_update').touch()
        result = service.run({'action': 'query', 'query': 'nothing-matches'})
        self.assertTrue(result['stale_marker']); self.assertEqual(result['nodes'], [])
        self.assertEqual(service.run({'action': 'explain', 'query': 'Controller'})['nodes'][0]['source_check'], 'external_or_unspecified')
        self.assertEqual(service.run({'action': 'status'}, lambda: False)['status'], 'cancelled')
        (self.root / 'graphify-out/graph.json').write_text('bad-json')
        self.assertEqual(service.run({'action': 'status'})['status'], 'failed')

    def test_graph_discovery_allows_the_host_to_read_the_exact_source(self):
        from file_workspace import FileWorkspace
        (self.root/'controller.py').write_text('def controller(): return 42',encoding='utf8')
        tools=AssistantTools.__new__(AssistantTools);tools._code_graph=self.graph();tools.files=FileWorkspace(self.root/'history')
        result=tools.execute('code_graph',{'action':'query','query':'Controller'},'jelaskan graf kode')
        source=next(n['source_path'] for n in result['nodes'] if n['id']=='A')
        self.assertEqual(Path(source),self.root/'controller.py')
        tools.files.allowed(Path(source),'jelaskan graf kode')
        self.assertNotIn(str(self.root/'unrelated.py'),tools.files.observed)

    def test_workflows_over_twelve_are_available_but_context_stays_bounded(self):
        rows = [{'id': str(i), 'title': 'Guide', 'description': 'test', 'instructions': 'Read evidence.', 'source': 'fixture',
                 'triggers': ['project' if i < 16 else 'project graphify']} for i in range(17)]
        path = self.root / 'workflows.json'; path.write_text(json.dumps(rows))
        store = WorkflowSkills(path)
        self.assertEqual(len(store.rows()), 17)
        self.assertEqual(store.relevant('project graphify')[0]['id'], '16')
        self.assertEqual(len(store.relevant('project graphify')), 2)
        rows.append({**rows[0], 'id': 'bad', 'triggers': [True]})
        path.write_text(json.dumps(rows))
        self.assertEqual(len(store.rows()), 17)

    def rea(self, script):
        entry = self.root / 'fixture_cli.py'; entry.write_text(script, encoding='utf8')
        conf = self.root / 'runtime.json'
        conf.write_text(json.dumps({'version': 'fixture', 'node': sys.executable, 'entry': str(entry),
            'node_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest()}))
        target = self.root / 'project'; target.mkdir()
        (target / 'main.js').write_text('throw new Error("Do not execute the target");')
        return ReaAnalysis(conf, self.root / 'reports'), target

    def test_rea_report_is_hashed_redacted_and_target_is_only_an_argument(self):
        service, target = self.rea('import json,sys\nassert sys.argv[1]=="analyze-javascript-application"\nprint(json.dumps({"evidence_id":"fixture", "normalized_result":{"statistics":{"files":1}}, "limitations":["Static only"], "api_key":"never-return-this-key"}))')
        result = service.run({'action': 'javascript', 'path': str(target)}, lambda p: self.assertEqual(p, target))
        self.assertEqual(result['status'], 'done'); self.assertEqual(result['exit_code'], 0)
        self.assertNotIn('never-return-this-key', str(result))
        raw = Path(result['report_path']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result['report_sha256'])
        self.assertNotIn(b'never-return-this-key', raw)
        self.assertEqual(service.status()['always_running'], False)

    def test_rea_invalid_output_and_changed_runtime_do_not_claim_success(self):
        service, target = self.rea('print("not-json")')
        self.assertEqual(service.run({'action': 'javascript', 'path': str(target)}, lambda p: None)['status'], 'failed')
        (self.root / 'fixture_cli.py').write_text('print("changed")')
        self.assertEqual(service.status()['status'], 'needs_input')

    def test_rea_can_be_cancelled_or_timed_out_without_running_forever(self):
        service, target = self.rea('import time\ntime.sleep(30)')
        started = time.monotonic()
        result = service.run({'action': 'javascript', 'path': str(target)}, lambda p: None, lambda: time.monotonic()-started < .25)
        self.assertEqual(result['status'], 'cancelled')
        self.assertLess(time.monotonic()-started, 3)
        self.assertEqual(service.run({'action': 'javascript', 'path': str(target)}, lambda p: None, timeout=.1)['code'], 'timeout')

    def test_new_tools_are_lazy_and_dispatch_through_host(self):
        self.assertNotIn('rea_analysis', {s.name for s in selected_skills('halo')})
        self.assertIn('rea_analysis', {s.name for s in selected_skills('analisis Electron dengan REA')})
        self.assertIn('code_graph', {s.name for s in selected_skills('telusuri hubungan modul di graf kode')})
        tools = AssistantTools.__new__(AssistantTools); tools._code_graph = self.graph()
        result = tools.execute('code_graph', {'action': 'path', 'query': 'A', 'target': 'C'}, 'telusuri graf kode')
        self.assertEqual(len(result['nodes']), 3)
        tools.files = Mock(); tools.files.observed = set(); tools._rea_analysis = Mock()
        tools._rea_analysis.run.return_value = {'status': 'done', 'report_path': 'fixture-report'}
        tools.execute('rea_analysis', {'action': 'status'}, 'lihat status REA')
        self.assertIn('fixture-report', tools.files.observed)


if __name__ == '__main__':
    unittest.main()
