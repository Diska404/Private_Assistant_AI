import hashlib
import json
from pathlib import Path
import queue
import struct
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import Mock, patch

from conversation_frontend import conversation_request
from pipeline_routing import route_spec
from preferences import DEFAULTS, Preferences
from reply_voice import ReplyVoice
from saluki_backend import SalukiEngine
from speech_resources import agent_mode
from task_reactions import cache_key, cached_reaction, needs_reaction


class TaskReactionTests(unittest.TestCase):
    def window(self, language='id'):
        from gui import LevaWindow
        m=LevaWindow.__new__(LevaWindow)
        values={**DEFAULTS,'speech_language':language,'provider':'RTX 4050','asr_model':'qwen_asr_06b',
                'agent_local_model':'qwen4b','auto_memory':False,'target_voice_pack':'higgs_leva'}
        m.preferences=Mock();m.preferences.get.side_effect=values.__getitem__
        m.mode=Mock();m.mode.get.return_value='RTX 4050'
        m.dual=Mock();m.dual.get.return_value=False
        m.spoken_replies=Mock();m.spoken_replies.get.return_value=True
        m.speech_language=Mock();m.speech_language.get.return_value='日本語' if language=='ja' else 'Indonesia'
        m.busy=False;m.closed=False;m.generation=0;m.events=queue.Queue();m._scheduled_job=None
        m.desktop=Mock(paused=False,sleeping=False,memory_notice='')
        m.desktop.tools.context.return_value={}
        m.chat=Mock(process=None);m.chat.history=[]
        m.frontend=Mock(process=None);m.frontend.history=[]
        m.reply_voice=Mock(active=False,is_reaction=False);m.reply_voice.poll.return_value=[]
        m.local_mic=Mock(active=False);m.voice_window=m.duplex_window=m.voice_pack_window=None
        m.entry=Mock();m.hud=Mock();m.root=Mock();m.add=Mock();m.activity=Mock();m.activity.get.return_value=''
        m.poll_local_mic=Mock()
        m.set_busy=lambda busy:setattr(m,'busy',busy)
        return m

    def wait(self,condition):
        end=time.monotonic()+2
        while not condition() and time.monotonic()<end:time.sleep(.005)
        self.assertTrue(condition())

    def test_action_bypasses_frontend_model_but_preserves_negation_and_schedule(self):
        service=Mock()
        text='Besok jam 19:00 buka Chrome Diska, jangan sekarang; jangan hapus berkas.'
        result=conversation_request(service,text,route_spec('Google → RTX 5070'),None,'ja',False)
        service.ask.assert_not_called()
        self.assertEqual(result['original_goal'],text);self.assertEqual(result['summary'],'')
        self.assertEqual(result['kind'],'delegate')

    def test_reaction_is_visible_while_agent_is_still_blocked(self):
        m=self.window();gate=threading.Event();entered=threading.Event()
        m.desktop.handle.return_value={'kind':'chat'}
        def task(*args,**kwargs):
            entered.set();gate.wait(2)
            return {'response':'Belum dapat diverifikasi.','provider':'local'}
        m.chat.ask.side_effect=task
        try:
            with patch('task_reactions.cached_reaction',return_value=None):
                m.send('Buat alur ComfyUI tanpa generate.')
                self.assertTrue(entered.wait(1))
                from leva_persona import ACKS
                self.assertTrue(any(c.args[0]=='Leva · Proses' and c.args[1] in ACKS['work'] for c in m.add.call_args_list))
                self.assertTrue(m.busy);m.frontend.ask.assert_not_called()
                self.assertEqual(m.chat.ask.call_args.args[0],'Buat alur ComfyUI tanpa generate.')
                self.assertLess(m.last_reaction_ms,100)
        finally:gate.set()
        self.wait(lambda:not m.events.empty())

    def test_factual_text_arrives_before_slow_japanese_translation(self):
        m=self.window('ja');gate=threading.Event();entered=threading.Event()
        m.desktop.handle.return_value={'kind':'command','reply':'Input dikirim; isi halaman belum diverifikasi.'}
        def translate(*args,**kwargs):
            entered.set();gate.wait(2)
            return {'response':'入力は送信したけれど、ページの内容はまだ確認できていないよ。'}
        m.frontend.ask.side_effect=translate
        m.speak_reply=Mock()
        try:
            with patch('task_reactions.cached_reaction',return_value=None):m.send('Buka Chrome Diska.')
            self.assertTrue(entered.wait(1))
            m.poll()
            self.assertFalse(m.busy)
            self.assertTrue(any(c.args[1]=='Input dikirim; isi halaman belum diverifikasi.' for c in m.add.call_args_list))
            m.speak_reply.assert_not_called()
        finally:gate.set()
        self.wait(lambda:not m.events.empty())
        m.poll();m.speak_reply.assert_called_once()

    def test_stale_translation_never_speaks_after_new_generation(self):
        m=self.window('ja');m.speak_reply=Mock()
        m.events.put((0,{'_voice_only':True,'speech_text':'古い返事です。'}));m.generation=1
        m.poll();m.speak_reply.assert_not_called()

    def test_interim_speech_cannot_cancel_an_active_agent_for_vram(self):
        m=self.window();m.busy=True
        with patch('speech_resources.gpu_rows') as query:m.speak_reply('Sedang diproses.')
        query.assert_not_called();m.chat.cancel.assert_not_called();m.reply_voice.speak.assert_not_called()

    def test_pause_has_no_opening_reaction(self):
        self.assertFalse(needs_reaction('Leva, jedakan sistemmu.'))
        self.assertFalse(needs_reaction('hai'))
        self.assertTrue(needs_reaction('dua menit lagi buka Chrome'))

    def test_saluki_obeys_actual_agent_device_for_all_routes(self):
        for label in ('RTX 4050','RTX 5070','Dual GPU'):
            mode=agent_mode(route_spec(label))
            engine=SalukiEngine(Path('unused'),acceleration='plain',mode=mode)
            self.assertEqual(engine.mode,mode)
        self.assertEqual(agent_mode(route_spec('Dual GPU'),'rtx5070'),'gpu5070')
        with tempfile.TemporaryDirectory() as folder:
            p=Preferences(Path(folder)/'p.db');p.set('agent_gpu','dual');p.close()
            p=Preferences(Path(folder)/'p.db');self.assertEqual(p.get('agent_gpu'),'dual');p.close()

    def test_auto_acceleration_does_not_extrapolate_single_gpu_measurements(self):
        from saluki_backend import chosen_acceleration
        with tempfile.TemporaryDirectory() as folder,patch('saluki_backend.MODEL_ROOT',Path(folder)):
            (Path(folder)/'runtime-profile.json').write_text(json.dumps({'recommended_acceleration':'mtp','measured':True}))
            self.assertEqual(chosen_acceleration('auto','gpu5070'),'mtp')
            self.assertEqual(chosen_acceleration('auto','dual'),'plain')
            self.assertEqual(chosen_acceleration('mtp','dual'),'mtp')

    def test_final_voice_follows_reaction_instead_of_interrupting_it(self):
        service=Mock(active=False,can_play=False);service.events=queue.Queue();service.check_timeout.return_value=False
        service.use_cached.return_value={'actual':'higgs_leva'}
        service.generate.return_value={'actual':'higgs_leva'}
        voice=ReplyVoice(service)
        voice.speak_cached(Path('fixture.wav'),'higgs_leva','ja')
        voice.enqueue('結果はまだ確認できていないよ。','higgs_leva','ja')
        service.generate.assert_not_called()
        service.events.put({'kind':'playback_finished'});voice.poll()
        service.generate.assert_called_once_with('higgs_leva','結果はまだ確認できていないよ。',language='ja',style='assistant')
        self.assertFalse(voice.is_reaction)

    def test_cancel_discards_queued_final_voice(self):
        service=Mock(active=False);service.events=queue.Queue()
        voice=ReplyVoice(service);voice.speak_cached(Path('fixture.wav'),'higgs_leva','ja')
        voice.enqueue('結果です。','higgs_leva','ja');voice.cancel()
        self.assertFalse(voice.utterances);self.assertFalse(voice.active);service.generate.assert_not_called()

    def test_cache_rejects_corruption_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=cache_key('higgs_leva','ja');path=root/(key+'.wav')
            with wave.open(str(path),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(24000)
                audio.writeframes(struct.pack('<h',500)*4800)
            record={'key':key,'actual_pack':'higgs_leva','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            (root/(key+'.json')).write_text(json.dumps(record))
            self.assertEqual(cached_reaction('higgs_leva','ja',root),path)
            self.assertIsNone(cached_reaction('higgs_leva','ja',root,speech='別の言葉です。'))
            self.assertIsNone(cached_reaction('higgs_native','ja',root))
            with path.open('ab') as stream:stream.write(b'corrupt')
            self.assertIsNone(cached_reaction('higgs_leva','ja',root))

    def test_preparation_accepts_worker_event_queue_and_never_opens_playback(self):
        from task_reactions import prepare_reaction
        from voice_core import VoiceEvents
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.wav'
            with wave.open(str(source),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(24000)
                audio.writeframes(struct.pack('<h',500)*4800)
            voice=Mock();voice.events=VoiceEvents();voice.generated=source
            voice.events.put_nowait({'kind':'generated','actual_pack':'higgs_leva','path':str(source)})
            with patch('task_reactions.resolve_pack',return_value={'available':True,'actual':'higgs_leva'}):
                result=prepare_reaction('higgs_leva','ja',service=voice,root=Path(folder)/'cache')
            self.assertTrue(Path(result['path']).is_file());voice.play.assert_not_called();voice.stop.assert_called_once()


if __name__=='__main__':unittest.main()
