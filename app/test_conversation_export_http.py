import json
import urllib.error
import unittest
import test_web_integration as fixtures

class ExportHTTPTests(unittest.TestCase):
    setUp=fixtures.BridgeTests.setUp
    request=fixtures.BridgeTests.request
    def test_export_requires_session_and_reads_full_provider_not_preview_window(self):
        data={'workspace':'chat','text':'Lengkap '*5000,'message_count':180,'messages':[]}
        self.bridge.transcript_provider=lambda room:data if room=='chat' else (_ for _ in ()).throw(ValueError('workspace_changed_retry'))
        with self.assertRaises(urllib.error.HTTPError) as denied:self.request('/api/conversation?workspace=chat',authenticated=False)
        self.assertEqual(denied.exception.code,401)
        with self.request('/api/conversation?workspace=chat') as response:
            self.assertEqual(json.load(response)['text'],data['text']);self.assertIn('no-store',response.headers['Cache-Control'])
        with self.assertRaises(urllib.error.HTTPError) as changed:self.request('/api/conversation?workspace=secret')
        self.assertEqual(changed.exception.code,409)

if __name__=='__main__':unittest.main()
