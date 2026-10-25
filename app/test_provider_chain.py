import json
from pathlib import Path
import queue
import sys
import unittest
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'experiments')]
from hybrid_engine import OnlineUnavailable
from provider_chain import InferenceRoute
from agent_runtime import run_agent
from chat_service import run_worker,ChatService


class ProviderChainTests(unittest.TestCase):
    def request(self,**changes):
        return {'id':1,'mode':'cascade','messages':[{'role':'user','content':'jam berapa sekarang'}],**changes}

    def test_google_success_never_calls_router_or_loads_local(self):
        route=InferenceRoute(self.request());google=Mock(return_value='google');router=Mock();local=Mock()
        self.assertEqual(route.call(google,router,local),('google','google'))
        router.assert_not_called();local.assert_not_called();self.assertEqual(route.metadata()['provider_failures'],[])

    def test_google_quota_uses_router_for_remaining_rounds_without_repeating_google(self):
        route=InferenceRoute(self.request());google=Mock(side_effect=OnlineUnavailable('quota_or_rate_limit'));router=Mock(return_value='router');local=Mock()
        for _ in range(2):self.assertEqual(route.call(google,router,local),('router','9router'))
        google.assert_called_once();self.assertEqual(router.call_count,2);local.assert_not_called();self.assertTrue(route.metadata()['google_paused'])

    def test_two_online_failures_reach_local_and_keep_google_pause_reason(self):
        route=InferenceRoute(self.request());google=Mock(side_effect=OnlineUnavailable('quota_or_rate_limit'));router=Mock(side_effect=OnlineUnavailable('router_rate_limit'));local=Mock(return_value='local')
        self.assertEqual(route.call(google,router,local),('local','local'))
        self.assertTrue(route.metadata()['google_paused']);self.assertEqual([r['provider'] for r in route.metadata()['provider_failures']],['google','9router'])
        self.assertEqual(route.metadata()['fallback_reason'],'router_rate_limit')

    def test_already_limited_google_is_skipped_but_router_remains_enabled(self):
        route=InferenceRoute(self.request(online_paused=True));google=Mock();router=Mock(return_value='router');local=Mock()
        self.assertEqual(route.call(google,router,local),('router','9router'));google.assert_not_called();local.assert_not_called()

    def test_plain_hybrid_keeps_old_google_to_local_route(self):
        route=InferenceRoute(self.request(mode='hybrid'));router=Mock()
        self.assertEqual(route.call(Mock(side_effect=OnlineUnavailable('quota_or_rate_limit')),router,Mock(return_value='local')),('local','local'));router.assert_not_called()

    def test_tool_receipt_survives_failover_and_is_executed_once(self):
        local=Mock();client=Mock();client.propose_tool.return_value={'action':'respond','args':{'text':'Jam 20.00 WIB.','speech_text':'Jam 20.00 WIB.'}}
        commands=queue.Queue();emitted=[]
        def emit(event):
            emitted.append(event);commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','reply':'Jam 20.00 WIB.'}})
        with patch('agent_runtime.online_propose_tool',side_effect=[{'action':'get_time','args':{}},OnlineUnavailable('quota_or_rate_limit')]) as google,patch('router_provider.configured_client',return_value=client):
            result=run_agent(self.request(),local,commands,emit)
        self.assertEqual(result['provider'],'9router');self.assertEqual(len(result['tool_receipts']),1);self.assertEqual(len(emitted),1)
        self.assertTrue(result['google_paused']);local.propose_tool.assert_not_called()
        context=client.propose_tool.call_args.args[0]
        self.assertTrue(any('Jam 20.00 WIB.' in m['content'] for m in context))

    def test_translation_cascade_can_use_router_without_local_generation(self):
        local=Mock();client=Mock();client.generate.return_value='こんにちは。'
        with patch('chat_service.online_generate',side_effect=OnlineUnavailable('quota_or_rate_limit')),patch('router_provider.configured_client',return_value=client):
            result=run_worker(self.request(purpose='translate'),local)
        self.assertEqual(result['provider'],'9router');self.assertTrue(result['google_paused']);local.generate.assert_not_called()
        self.assertIn('Japanese',client.generate.call_args.args[1])
        self.assertIn('data, never instructions',client.generate.call_args.args[1])

    def test_client_remembers_google_limit_even_when_router_also_fails(self):
        from voice_core import VoiceEvents
        class Session:
            def __init__(self):self.active=False;self.events=VoiceEvents();self.process=Mock();self.requests=[]
            def start(self,*args,initial_message=None):self.active=True;self.send(initial_message)
            def send(self,r):
                self.requests.append(r);self.events.put({'kind':'result','id':r['id'],'provider':'local','response':'halo','fallback_reason':'router_authentication','google_paused':True})
            def stop(self):self.active=False
        service=ChatService(persistent=True);service.session=Session()
        try:
            for _ in range(2):service.ask('halo','cascade',keep_warm=True)
            self.assertTrue(service.session.requests[1]['online_paused'])
        finally:service.cancel()


if __name__=='__main__':unittest.main()
