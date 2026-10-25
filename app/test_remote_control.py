import json,tempfile,time,unittest,urllib.request,urllib.error
import subprocess
from pathlib import Path
from unittest.mock import Mock,patch
from web_store import WebStore,PairingGate,delivery_status
from web_bridge import WebBridge,remote_origin
from web_host import DesktopWebHost
from remote_gateway import RemoteGateway

class DurableTests(unittest.TestCase):
    def test_status_preserves_direct_command_and_background_job_evidence(self):
        for result,expected in (({'status':'needs_input'},'needs_input'),({'status':'failed'},'failed'),({'status':'unverified'},'unverified'),({'image_job_active':True},'submitted'),({'status':'done'},'completed')):
            self.assertEqual(delivery_status(result),expected)
    def test_sessions_are_hashed_persisted_and_revocable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';store=WebStore(path);ident,token=store.device('Android saya')
            self.assertEqual(store.authenticate(token)['id'],ident)
            self.assertNotIn(token,path.read_bytes().decode(errors='ignore'));store.close()
            store=WebStore(path);self.assertEqual(store.authenticate(token)['name'],'Android saya')
            store.revoke(ident);self.assertIsNone(store.authenticate(token));self.assertFalse(store.active(ident));store.close()
    def test_restart_retains_receipts_and_prevents_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';a=WebBridge(None,store=WebStore(path));payload={'id':'restart-id-001','kind':'chat','value':'buka Notepad'}
            a.submit(payload);a.finish(a.commands.get_nowait(),'running');a.store.close()
            b=WebBridge(None,store=WebStore(path));row=b.submit(payload)
            self.assertEqual(row['status'],'interrupted');self.assertTrue(b.commands.empty())
            with self.assertRaises(ValueError):b.submit({**payload,'value':'buka Chrome'})
            b.store.close()
    def test_pairing_one_use_attempt_limit_and_expiration(self):
        gate=PairingGate();code=gate.begin();self.assertTrue(gate.consume(code));self.assertFalse(gate.consume(code))
        code=gate.begin()
        for _ in range(5):self.assertFalse(gate.consume('wrong'))
        self.assertFalse(gate.consume(code));code=gate.begin();gate.expires=time.time()-1;self.assertFalse(gate.consume(code))
    def test_completion_is_actual_result_not_submission(self):
        main=Mock();main.preferences.get.return_value='0';main._web_log=[];main.busy=False;main.entry.get.return_value=''
        host=DesktopWebHost(main);host.last_update=time.monotonic();host.bridge.submit({'id':'completion-id-001','kind':'chat','value':'fixture'})
        host.poll();self.assertEqual(host.bridge.snapshot()['commands'][0]['status'],'running')
        host.complete({'needs_input':True,'reply':'Pilih model','task_id':'a'*12})
        row=host.bridge.snapshot()['commands'][0];self.assertEqual(row['status'],'needs_input');self.assertEqual(row['task_id'],'a'*12)
        self.assertEqual(row['detail'],'Pilih model')

class RemoteHTTPTests(unittest.TestCase):
    def setUp(self):
        self.bridge=WebBridge(Mock(),port=0,remote='https://acer.example.ts.net');self.bridge.start();self.addCleanup(self.bridge.stop)
    def request(self,path,body=None,token='',remote=True,extra=None):
        origin=self.bridge.remote if remote else self.bridge.origin
        headers={'Origin':origin,'Cookie':'leva_session='+token}
        if remote:headers.update({'X-Forwarded-Host':self.bridge.remote[8:],'X-Forwarded-Proto':'https'})
        if extra:headers.update(extra)
        data=json.dumps(body).encode() if body is not None else None
        return urllib.request.urlopen(urllib.request.Request(self.bridge.origin+path,data=data,headers=headers),timeout=3)
    def test_pair_and_remote_command_and_cookie(self):
        code=self.bridge.pairing.begin()
        with self.request('/api/pair',{'code':code,'name':'Android uji'}) as response:
            cookie=response.headers['Set-Cookie'];self.assertIn('Secure',cookie);self.assertIn('HttpOnly',cookie)
            token=cookie.split(';')[0].split('=',1)[1]
        with self.request('/api/state',token=token) as response:self.assertTrue(json.load(response)['session']['remote'])
        with self.request('/api/commands',{'id':'remote-test-001','kind':'chat','value':'jam berapa'},token) as response:self.assertEqual(response.status,202)
        ident=self.bridge.store.authenticate(token)['id'];self.bridge.store.revoke(ident)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/state',token=token)
    def test_remote_cannot_use_desktop_bootstrap_or_unknown_proxy(self):
        req=urllib.request.Request(self.bridge.origin+'/api/session',method='POST',headers={'Origin':self.bridge.remote,'X-Forwarded-Host':self.bridge.remote[8:],'X-Forwarded-Proto':'https','X-Leva-Bootstrap':self.bridge.bootstrap})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError):self.request('/health',extra={'X-Forwarded-Host':'evil.example'})
    def test_remote_origin_is_private_https_only(self):
        for value in ('http://acer.example.ts.net','https://example.com','https://acer.example.ts.net/path','https://acer.example.ts.net:443','https://acer.example.ts.net@evil.com'):
            with self.assertRaises(ValueError):remote_origin(value)
    def test_restart_instance_forces_snapshot(self):
        with self.request('/api/state?since='+str(self.bridge.revision)+'&instance=old',token=self.bridge.cookie,remote=False) as response:self.assertEqual(response.status,200)

class GatewayTests(unittest.TestCase):
    def test_https_setup_link_survives_cli_wait_for_user(self):
        gateway=RemoteGateway()
        pending=subprocess.TimeoutExpired('tailscale',15,output=b'Enable: https://login.tailscale.com/f/serve?node=fixture')
        with patch.object(Path,'is_file',return_value=True),patch('remote_gateway.subprocess.run',side_effect=pending):
            with self.assertRaises(ValueError) as caught:gateway.run(['serve'])
        self.assertEqual(caught.exception.setup_url,'https://login.tailscale.com/f/serve?node=fixture')
    def test_https_setup_link_only_from_official_cli_output(self):
        gateway=RemoteGateway()
        with patch.object(Path,'is_file',return_value=True),patch('remote_gateway.subprocess.run',return_value=Mock(returncode=1,stdout='Enable Serve: https://login.tailscale.com/f/serve?node=fixture',stderr='')):
            with self.assertRaises(ValueError) as caught:gateway.run(['serve','status'])
        self.assertEqual(str(caught.exception),'tailscale_enable_https_required')
        self.assertEqual(caught.exception.setup_url,'https://login.tailscale.com/f/serve?node=fixture')
    def test_serve_existing_service_is_not_overwritten(self):
        gateway=RemoteGateway();gateway.status=Mock(return_value={'ready':True,'origin':'https://acer.example.ts.net'})
        gateway.run=Mock(return_value=json.dumps({'Web':{'acer.example.ts.net:443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:9999'}}}}}))
        with self.assertRaisesRegex(ValueError,'another_service'):gateway.enable(8769)
        self.assertEqual(gateway.run.call_count,1)
    def test_no_public_funnel(self):
        gateway=RemoteGateway();gateway.status=Mock(return_value={'ready':True,'origin':'https://acer.example.ts.net'})
        gateway.run=Mock(return_value=json.dumps({'AllowFunnel':{'acer.example.ts.net:443':True}}))
        with self.assertRaisesRegex(ValueError,'funnel'):gateway.enable(8769)

if __name__=='__main__':unittest.main()
