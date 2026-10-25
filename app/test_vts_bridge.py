import json,unittest
from vts_bridge import VTSClient,VTSService,validate_frame,tracking_parameters

class VTSBridgeTests(unittest.TestCase):
    def test_invalid_port_never_starts_background_worker(self):
        for port in (True,0,80,65536,'8001'):
            service=VTSService()
            with self.assertRaises(ValueError):service.start('desktop',port=port)
            self.assertIsNone(service.thread);self.assertEqual(service.snapshot()['state'],'off')
    def test_mapping_silence_and_bounds(self):
        params={x['id']:x['value'] for x in tracking_parameters({'mouth':0,'blink':1,'happy':.4})}
        self.assertEqual(params['MouthOpen'],0);self.assertEqual(params['EyeOpenLeft'],0);self.assertAlmostEqual(params['MouthSmile'],.6)
        for bad in ({'mouth':float('nan')},{'mouth':2},{'execute':'calc'},{'mouth':True}):
            with self.assertRaises(ValueError):validate_frame(bad)
    def test_client_fixed_loopback_and_correlated_receipts(self):
        class Socket:
            def send(self,raw):self.last=json.loads(raw)
            def recv(self,timeout):return json.dumps({'requestID':self.last['requestID'],'data':{'active':True}})
            def close(self):pass
        calls=[]
        def connect(url,**kw):calls.append((url,kw));return Socket()
        client=VTSClient(connector=connect);self.assertTrue(client.connect()['active']);client.close()
        self.assertEqual(calls[0][0],'ws://127.0.0.1:8001');self.assertIsNone(calls[0][1]['proxy'])
    def test_frame_owner_and_status_do_not_expose_credentials(self):
        service=VTSService(clock=lambda:10);service.owner='desktop';service.status['state']='connected'
        self.assertTrue(service.feed('desktop',{'mouth':.3}));self.assertFalse(service.feed('desktop',{'mouth':.4}))
        with self.assertRaises(ValueError):service.feed('different',{'mouth':1})
        self.assertNotIn('token',json.dumps(service.snapshot()));service.close('desktop');self.assertEqual(service.snapshot()['state'],'off')
