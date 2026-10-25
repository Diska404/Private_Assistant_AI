import queue
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

from gui import LevaWindow
from local_audio_core import Segmenter,WakePolicy
from speech_turns import SpeechJournal,TurnAssembler,stop_request


class SpeechTurnsTests(unittest.TestCase):
    def test_ambiguous_alias_needs_greeting_and_does_not_invent_command(self):
        for text in ('Ay, lipa.','Hai, Alipa, buka Chrome Diska.'):
            row=WakePolicy().accept(text,now=1)
            self.assertTrue(row['accepted']);self.assertNotIn('lipa',row['command'].lower())
        for text in ('Dua Lipa menyanyi','alipa buka Chrome','lewat jalan','jangan panggil Lipa'):
            self.assertFalse(WakePolicy().accept(text,now=1)['accepted'])

    def test_long_turn_length_limit_is_not_a_command_endpoint(self):
        s=Segmenter(silence_frames=55,max_frames=30);parts=[]
        for i in range(65):
            pcm,_,_=s.push(b'v',.1)
            if pcm is not None:parts.append((s.last_boundary,pcm))
        for i in range(55):
            pcm,_,_=s.push(b'q',0)
            if pcm is not None:parts.append((s.last_boundary,pcm))
        self.assertEqual(parts[-1][0],'silence');self.assertTrue(all(p[0]=='limit' for p in parts[:-1]))
        a=TurnAssembler();turn=None
        for i,(boundary,_) in enumerate(parts):turn=a.append('x',str(i),boundary=='silence')
        self.assertTrue(turn['final']);self.assertEqual(turn['text'],' '.join(str(i) for i in range(len(parts))))

    def test_limit_on_last_voiced_frame_still_flushes_empty_tail(self):
        s=Segmenter(silence_frames=4,max_frames=12)
        for i in range(12):s.push(b'v',.1)
        self.assertEqual(s.last_boundary,'limit')
        values=[s.push(b'q',0)[0] for i in range(4)]
        self.assertEqual(values[-1],b'');self.assertEqual(s.last_boundary,'silence')

    def test_short_hesitation_keeps_command_together(self):
        s=Segmenter(silence_frames=55)
        for rms in ([.1]*20+[0]*30+[.1]*20+[0]*54):
            self.assertIsNone(s.push(b'x',rms)[0])
        self.assertIsNotNone(s.push(b'x',0)[0])

    def test_journal_keeps_entire_long_text_and_partial_to_final(self):
        with tempfile.TemporaryDirectory() as folder:
            db=SpeechJournal(Path(folder)/'speech.db');text='Leva, jangan buka sebelum jam 19:00. '*200
            db.capture({'turn_id':'a','text':text,'final':False})
            self.assertEqual(db.get('a')['state'],'collecting')
            db.capture({'turn_id':'a','text':text+' Selesai.','final':True,'accepted':True,'command':'buka Chrome','reason':'wake'})
            self.assertEqual(db.get('a')['text'],text+' Selesai.');self.assertEqual(db.get('a')['state'],'queued')
            db.capture({'turn_id':'a','text':'duplicate','reason':'echo'})
            self.assertEqual(db.get('a')['text'],text+' Selesai.')

    def test_rejected_echo_empty_and_incomplete_never_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            db=SpeechJournal(Path(folder)/'speech.db')
            for reason in ('awaiting_wake','echo','empty','incomplete'):
                db.capture({'text':'buka Chrome','reason':reason})
            db.capture({'text':'Leva, buka','reason':'wake','accepted':True,'command':'buka','incomplete':True})
            self.assertEqual(db.pending(),[])

    def test_worker_failure_marks_partial_incomplete_and_preserves_full_text(self):
        with tempfile.TemporaryDirectory() as folder:
            db=SpeechJournal(Path(folder)/'speech.db');raw='teks panjang '*600
            row=db.capture({'text':raw,'final':False})
            db.fail_collecting('Worker terputus')
            self.assertEqual(db.get(row['id'])['state'],'incomplete')
            self.assertEqual(db.get(row['id'])['text'],raw);self.assertFalse(db.pending())

    def test_hold_is_idempotent_and_resume_clears_stale_ack(self):
        from local_mic_service import LocalMicService
        service=LocalMicService();service.worker=Mock();service.asr_held.set()
        service.hold_asr(timeout=.01);service.worker.send.assert_not_called()
        service.resume_asr();self.assertFalse(service.asr_held.is_set())
        service.worker.send.assert_called_once_with({'kind':'resume_asr'})

    def test_restart_never_replays_unfinished_commands_and_clear_preserves_active(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'speech.db';db=SpeechJournal(path)
            row=db.capture({'text':'Leva buka Chrome','command':'buka Chrome','accepted':True})
            db.clear();self.assertEqual(len(db.pending()),1)
            db=SpeechJournal(path);db.recover();self.assertEqual(db.pending(),[])
            self.assertEqual(db.get(row['id'])['state'],'interrupted')

    def fixture(self,folder):
        m=LevaWindow.__new__(LevaWindow);m._speech_inbox=SpeechJournal(Path(folder)/'db')
        m.busy=True;m.closed=False;m.desktop=Mock(paused=False,sleeping=False)
        m.entry=Mock();m.entry.get.return_value='';m.voice_window=None;m.add=Mock();m.send=Mock()
        return m

    def test_busy_voice_queues_without_cancelling_then_dispatches_in_order(self):
        with tempfile.TemporaryDirectory() as folder:
            m=self.fixture(folder);m.cancel_inference=Mock();m.stop_reply_voice=Mock()
            for text in ('buka Chrome Diska','jam berapa sekarang'):
                m.receive_voice({'text':'Leva, '+text,'command':text,'accepted':True,'reason':'wake'})
            m.dispatch_voice();m.send.assert_not_called();m.cancel_inference.assert_not_called()
            m.busy=False;m.dispatch_voice();self.assertEqual(m.send.call_args.args[0],'buka Chrome Diska')
            self.assertEqual(len(m._speech_inbox.pending()),1)

    def test_typed_draft_waits_without_dropping_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            m=self.fixture(folder);m.busy=False;m.entry.get.return_value='draf penting'
            m.receive_voice({'text':'Leva buka Chrome','command':'buka Chrome','accepted':True})
            m.dispatch_voice();m.send.assert_not_called()
            self.assertEqual(m._speech_inbox.pending()[0]['state'],'waiting_draft')
            m.entry.get.return_value='';m.dispatch_voice();m.send.assert_called_once()

    def test_paused_capture_does_not_run_on_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            m=self.fixture(folder);m.desktop.paused=True
            m.receive_voice({'text':'Leva buka Chrome','command':'buka Chrome','accepted':True})
            self.assertFalse(m._speech_inbox.pending())

    def test_explicit_stop_is_narrow_and_negations_are_preserved(self):
        self.assertTrue(stop_request('tolong hentikan tugas sekarang'))
        for text in ('jangan hentikan tugas','bagaimana cara hentikan tugas','stop musik','batalkan pengingat'):
            self.assertFalse(stop_request(text))


if __name__=='__main__':unittest.main()
