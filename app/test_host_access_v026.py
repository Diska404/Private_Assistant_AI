"""Regressions for observed file/LAN failures and manual mobile voice drafts."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import wave
import urllib.request
import urllib.error

from file_workspace import FileWorkspace,source_redact
from iot_lamp import RoomLamp
from remote_speech import RemoteSpeech,validate_wav
from web_presence import WebPresence
from assistant_tools import selected_skills
from web_bridge import WebBridge
from web_store import WebStore


def clip(frames=4000):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*frames)
    return out.getvalue()


class FileAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.folders=patch('file_workspace.known_folders',return_value={'documents':self.base,'downloads':self.base,'desktop':self.base});self.folders.start();self.addCleanup(self.folders.stop)
        self.files=FileWorkspace(self.base/'history')
    def test_offline_drive_does_not_break_known_folders(self):
        with patch('psutil.disk_partitions',side_effect=OSError('offline')):
            self.assertIn(str(self.base),self.files.roots()['paths'])
    def test_normalized_search_and_read_and_folder_alias(self):
        path=self.base/'Matematika Diskrit 2026 - 05.txt';path.write_text('one\ntwo\nthree')
        result=self.files.run({'action':'search','query':'Matematika Diskrit 2026-05.txt'},'cari berkas')
        self.assertEqual(result['paths'],[str(path)])
        result=self.files.run({'action':'read','path':'unduhan>Matematika Diskrit 2026-05.txt','line_count':'2'},'baca')
        self.assertEqual(result['content'],'one\ntwo');self.assertEqual(result['next_line'],3)
    def test_arduino_source_is_redacted_and_paged(self):
        path=self.base/'test.ino';path.write_text('#define FIREBASE_AUTH "private-secret"\nconst char* ssid = "private-network";\nvoid setup() {}')
        result=self.files.run({'action':'read','path':str(path)},'baca kode')
        self.assertNotIn('private-secret',result['content']);self.assertNotIn('private-network',result['content']);self.assertIn('void setup',result['content'])
    def test_read_scope_does_not_grant_unobserved_write(self):
        with self.assertRaisesRegex(ValueError,'file_path_not_observed'):self.files.run({'action':'write','path':str(self.base/'new.txt'),'text':'x'},'buat catatan')
    def test_ambiguous_name_does_not_silently_choose(self):
        (self.base/'a-b.txt').write_text('1');(self.base/'a b.txt').write_text('2')
        with self.assertRaisesRegex(ValueError,'ambiguous'):self.files.run({'action':'read','path':str(self.base/'ab.txt')},'baca')
    def test_pdf_extracts_pages_without_text_file_1mb_limit(self):
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.add_blank_page(width=100,height=100)
        path=self.base/'demo.pdf'
        with path.open('wb') as f:writer.write(f)
        result=self.files.run({'action':'read','path':str(path)},'baca PDF')
        self.assertEqual(result['total_pages'],2);self.assertEqual(result['next_page'],2);self.assertTrue(result['ocr_required'])
    def test_routing_selects_real_file_and_lan_tools(self):
        self.assertIn('file_action',{s.name for s in selected_skills('baca Arduino Smarthome_IoT.ino')})
        self.assertIn('iot_action',{s.name for s in selected_skills('bisakah mengontrol lampu ESP8266')})


class LampTests(unittest.TestCase):
    def test_capability_question_does_not_switch(self):
        transport=Mock(return_value=(200,b'{"systemOn":true}'))
        result=RoomLamp(transport).run({'action':'off'},'bisakah mengontrol lampu')
        self.assertEqual(result['status'],'needs_input');transport.assert_not_called()
    def test_state_change_verified_and_idempotent(self):
        transport=Mock(side_effect=[(200,b'{"systemOn":false}'),(302,b''),(200,b'{"systemOn":true}')])
        result=RoomLamp(transport).run({'action':'on'},'nyalakan lampu kamar')
        self.assertTrue(result['on']);self.assertEqual(result['status'],'done')
        self.assertEqual([c.args[0] for c in transport.call_args_list],['/quick/status','/on','/quick/status'])
        transport=Mock(return_value=(200,b'{"systemOn":true}'))
        result=RoomLamp(transport).run({'action':'on'},'nyalakan lampu kamar');self.assertFalse(result['changed']);self.assertEqual(transport.call_count,1)
    def test_negation_and_cancellation_prevent_write(self):
        transport=Mock(return_value=(200,b'{"systemOn":false}'))
        RoomLamp(transport).run({'action':'on'},'jangan nyalakan lampu');transport.assert_not_called()
        RoomLamp(transport).run({'action':'on'},'nyalakan lampu',lambda:False);self.assertEqual(transport.call_count,1)
    def test_schema_is_checked(self):
        with self.assertRaises(ValueError):RoomLamp(lambda path:(200,b'{"systemOn":"true"}')).status()


class PhoneDraftTests(unittest.TestCase):
    def test_conversation_receives_origin_without_granting_phone_filesystem(self):
        from conversation_frontend import conversation_request
        from pipeline_routing import route_spec
        service=Mock();service.ask.return_value={'response':'{"kind":"respond","text":"Dari Android."}'}
        conversation_request(service,'saya sedang dari perangkat mana?',route_spec('RTX 4050'),{},'id',False,client_context={'kind':'android'})
        self.assertEqual(service.ask.call_args.kwargs['tool_context']['client']['kind'],'android')
    def test_presence_expires_and_revocation_is_immediate(self):
        clock=[10];presence=WebPresence(lambda:clock[0]);session={'id':'a','name':'My Android'}
        presence.touch(session,'Android',True);self.assertEqual(presence.active()[0]['kind'],'android')
        self.assertEqual(presence.active(lambda owner:False),[])
        presence.touch(session,'Android',True);clock[0]+=26;self.assertEqual(presence.active(),[])
        presence.touch(session,'Android',False);self.assertEqual(presence.active(),[])
    def test_draft_is_owned_ephemeral_and_not_an_agent_command(self):
        speech=RemoteSpeech();result=speech.submit('recording-001','phone-a',clip())
        self.assertEqual(result['status'],'queued');self.assertNotIn('pcm',result);self.assertNotIn('owner',result)
        self.assertIsNone(speech.get('recording-001','phone-b'));self.assertFalse(speech.cancel('recording-001','phone-b'))
        self.assertTrue(speech.cancel('recording-001','phone-a'));self.assertFalse(speech.pending())
    def test_invalid_truncated_and_oversized_audio_rejected(self):
        for raw in (b'not-wave',clip()[:-20],b'0'*2_000_000):
            with self.assertRaises((ValueError,wave.Error,EOFError)):validate_wav(raw)
    def test_queue_is_bounded_and_duplicate_owner_checked(self):
        speech=RemoteSpeech();speech.submit('recording-001','a',clip());speech.submit('recording-002','b',clip())
        with self.assertRaises(ValueError):speech.submit('recording-003','a',clip())
        with self.assertRaises(ValueError):speech.submit('recording-001','b',clip())
        self.assertEqual(speech.submit('recording-001','a',clip())['status'],'queued')
        speech.stop();self.assertFalse(speech.pending())


class MobileHttpTests(unittest.TestCase):
    def setUp(self):
        self.bridge=WebBridge(Mock(),port=0,store=WebStore(),remote='https://laptop.example-tailnet.ts.net');self.bridge.start();self.addCleanup(self.bridge.stop)
        self.owner,self.token=self.bridge.store.device('Android test')
    def request(self,path,body=None,token=None,**extra):
        headers={'Host':'127.0.0.1:'+str(self.bridge.server.server_port),'Origin':self.bridge.remote,'X-Forwarded-Host':self.bridge.remote[8:],'X-Forwarded-Proto':'https','User-Agent':'Android test','Cookie':'leva_session='+(token or self.token)}|extra
        return urllib.request.urlopen(urllib.request.Request(self.bridge.origin+path,data=body,headers=headers,method='POST' if body is not None else 'GET'),timeout=3)
    def test_authenticated_phone_presence_and_trusted_source(self):
        with self.request('/api/state'):pass
        self.assertEqual(self.bridge.presence.active(self.bridge.store.active),[{'kind':'android','name':'Android test'}])
        with self.request('/api/commands',json.dumps({'id':'phone-command-001','kind':'chat','value':'baca PDF'}).encode(),**{'Content-Type':'application/json'}):pass
        job=self.bridge.commands.get_nowait();self.assertEqual(job['client']['kind'],'android');self.assertEqual(job['client']['executor'],'laptop Windows')
    def test_unpaired_request_cannot_suspend_mic_or_upload(self):
        for path,body in [('/api/state',None),('/api/transcribe',clip())]:
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request(path,body,token='invalid',**{'Content-Type':'audio/wav','X-Leva-Request':'phone-clip-001'})
            self.assertEqual(caught.exception.code,401)
        self.assertEqual(self.bridge.presence.active(),[]);self.assertEqual(self.bridge.speech.jobs,{})
    def test_audio_is_not_dispatched_as_chat_and_is_owner_scoped(self):
        with self.request('/api/transcribe',clip(),**{'Content-Type':'audio/wav','X-Leva-Request':'phone-clip-001'}) as response:self.assertEqual(response.status,202)
        self.assertTrue(self.bridge.commands.empty());self.assertEqual(self.bridge.store.recent(),[])
        _,other=self.bridge.store.device('Other phone')
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/transcribe?id=phone-clip-001',token=other)
        self.assertEqual(caught.exception.code,404)
        with self.request('/api/transcribe/cancel',b'',**{'X-Leva-Request':'phone-clip-001'}) as response:self.assertTrue(json.load(response)['cancelled'])
    def test_revoked_phone_cannot_read_or_submit(self):
        self.bridge.store.revoke(self.owner)
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/state')
        self.assertEqual(caught.exception.code,401)


if __name__=='__main__':unittest.main()
