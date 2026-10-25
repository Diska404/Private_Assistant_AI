import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import Mock,patch

from router_provider import RouterClient,base_url,save_key,load_key
from hybrid_engine import OnlineUnavailable
from agent_runtime import run_agent
from preferences import Preferences


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests=[];cls.status=200;cls.body={};cls.redirect=None
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.handle_request()
            def do_POST(self):self.handle_request()
            def handle_request(self):
                body=self.rfile.read(int(self.headers.get('Content-Length',0)))
                cls.requests.append({'path':self.path,'authorization':self.headers.get('Authorization'),'payload':json.loads(body) if body else None})
                self.send_response(cls.status)
                if cls.redirect:self.send_header('Location',cls.redirect)
                self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(cls.body).encode())
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.url='http://127.0.0.1:'+str(cls.server.server_port)+'/v1'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        type(self).requests.clear();type(self).status=200;type(self).body={};type(self).redirect=None
        self.client=RouterClient(self.url,'fixture/free',key_loader=lambda:'fake-test-key')
    def test_endpoint_requires_loopback_and_rejects_auth_query_and_remote_hosts(self):
        self.assertEqual(base_url('http://localhost:20128/'),'http://localhost:20128/v1')
        for url in ['https://remote.example/v1','http://127.0.0.1.evil.example/v1','http://user:secret@localhost:20128/v1','http://localhost/v1?key=x','file:///C:/data','http://localhost:99999/v1']:
            with self.subTest(url=url),self.assertRaises(ValueError):base_url(url)
    def test_models_are_retrieved_without_guessing_free_pricing(self):
        type(self).body={'data':[{'id':'fixture/free'},{'id':'fixture/paid'},{'id':'fixture/free'}]}
        self.assertEqual(self.client.models(),['fixture/free','fixture/paid'])
        self.assertEqual(self.requests[0]['authorization'],'Bearer fake-test-key')
    def test_native_tool_payload_and_response_roundtrip(self):
        type(self).body={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'get_time','arguments':'{}'}}]}}]}
        result=self.client.propose_tool([{'role':'user','content':'jam berapa'}],'system',[{'type':'function','function':{'name':'get_time','parameters':{'type':'object','properties':{}}}}])
        self.assertEqual(result,{'action':'get_time','args':{}})
        sent=self.requests[0]['payload'];self.assertEqual(sent['model'],'fixture/free');self.assertEqual(sent['tool_choice'],'required');self.assertFalse(sent['parallel_tool_calls']);self.assertFalse(sent['stream'])
    def test_plain_text_cannot_be_mistaken_for_a_desktop_tool_call(self):
        type(self).body={'choices':[{'finish_reason':'stop','message':{'content':'Aplikasi sudah dibuka!'}}]}
        with self.assertRaisesRegex(OnlineUnavailable,'router_tool_call_unsupported'):self.client.propose_tool([], '',[{}])
    def test_rate_limit_and_auth_errors_never_expose_response_credentials(self):
        type(self).body={'error':{'message':'private-debug-token'}}
        for status,reason in [(429,'router_rate_limit'),(401,'router_authentication'),(503,'router_http_503')]:
            type(self).status=status
            with self.assertRaises(OnlineUnavailable) as error:self.client.models()
            self.assertEqual(str(error.exception),reason);self.assertNotIn('private',str(error.exception))
    def test_redirect_does_not_forward_key(self):
        type(self).status=302;type(self).redirect=self.url+'/other'
        with self.assertRaises(OnlineUnavailable):self.client.models()
        self.assertEqual(len(self.requests),1)
    def test_windows_dpapi_key_roundtrip_and_nonplaintext_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'key.dpapi';save_key('only-a-fake-key-for-unit-test',path)
            self.assertNotIn(b'only-a-fake-key-for-unit-test',path.read_bytes());self.assertEqual(load_key(path),'only-a-fake-key-for-unit-test')
    def test_google_quota_pause_does_not_disable_router(self):
        local=Mock();client=Mock();client.propose_tool.return_value={'action':'respond','args':{'text':'Halo','speech_text':'Halo'}}
        with patch('router_provider.configured_client',return_value=client),patch('agent_runtime.online_propose_tool') as google:
            result=run_agent({'id':1,'mode':'router','online_paused':True,'messages':[{'role':'user','content':'halo'}]},local,queue.Queue(),Mock())
        self.assertEqual(result['provider'],'9router');google.assert_not_called();local.propose_tool.assert_not_called()
    def test_router_failure_falls_back_locally_without_using_google(self):
        local=Mock();local.propose_tool.return_value={'action':'respond','args':{'text':'Halo lokal','speech_text':'Halo lokal'}}
        client=Mock();client.propose_tool.side_effect=OnlineUnavailable('router_authentication')
        with patch('router_provider.configured_client',return_value=client),patch('agent_runtime.online_propose_tool') as google:
            result=run_agent({'id':1,'mode':'router','messages':[{'role':'user','content':'halo'}]},local,queue.Queue(),Mock())
        self.assertEqual(result['provider'],'local');self.assertEqual(result['fallback_reason'],'router_authentication');google.assert_not_called()
    def test_translation_uses_router_and_local_fallback(self):
        from chat_service import run_worker
        local=Mock();local.generate.return_value='ローカルです。';client=Mock();client.generate.side_effect=OnlineUnavailable('router_rate_limit')
        with patch('router_provider.configured_client',return_value=client):
            result=run_worker({'mode':'router','purpose':'translate','messages':[{'role':'user','content':'Ini uji.'}]},local)
        self.assertEqual(result['response'],'ローカルです。');self.assertEqual(result['provider'],'local')
    def test_provider_config_is_persistent_but_has_no_plaintext_key_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.sqlite3';p=Preferences(path)
            p.set_many({'provider':'9Router → Lokal','router_model':'fixture/free','router_local_model':'saluki'});p.close();p=Preferences(path)
            self.assertEqual(p.get('router_model'),'fixture/free')
            with self.assertRaises(ValueError):p.set('router_api_key','not-allowed')
            p.close()
    def test_stopping_gateway_does_not_terminate_an_external_service(self):
        from router_gateway import RouterGateway
        gateway=RouterGateway()
        with patch('router_gateway.subprocess.Popen') as launch,patch('router_gateway.reachable',return_value=True):
            self.assertIn('terpisah',gateway.start('http://127.0.0.1:20128/v1'));gateway.stop();launch.assert_not_called()


if __name__=='__main__':unittest.main()
