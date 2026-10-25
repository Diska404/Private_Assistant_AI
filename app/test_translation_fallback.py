from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import chat_service


class TranslationFallbackTests(unittest.TestCase):
    def test_missing_historical_qwen_uses_installed_small_translator_only_for_translation(self):
        with tempfile.TemporaryDirectory() as folder:
            available=Path(folder)/'available';available.write_bytes(b'fixture')
            missing=Path(folder)/'missing'
            with patch.multiple(chat_service,DEFAULT_SERVER=available,DEFAULT_MODEL=missing,QWEN_CHAT_MODEL=missing,TRANSLATION_FALLBACK_SERVER=available,TRANSLATION_FALLBACK_MODEL=available),patch.object(chat_service,'LocalEngine') as engine:
                chat_service.make_local({'purpose':'translate','local_model':'qwen4b','local_mode':'dual'})
                self.assertEqual(engine.call_args.args[:2],(available,available))
                self.assertEqual(engine.call_args.kwargs['mode'],'dual')
                self.assertEqual(engine.call_args.kwargs['thinking_budget'],0)
                chat_service.make_local({'purpose':'chat','local_model':'qwen4b'})
                self.assertEqual(engine.call_args.args[1],missing)

    def test_present_qwen_remains_preferred(self):
        with tempfile.TemporaryDirectory() as folder:
            existing=Path(folder)/'model';existing.write_bytes(b'fixture')
            with patch.multiple(chat_service,DEFAULT_SERVER=existing,DEFAULT_MODEL=existing,QWEN_CHAT_MODEL=existing),patch.object(chat_service,'LocalEngine') as engine:
                chat_service.make_local({'purpose':'translate','local_model':'qwen4b'})
                self.assertEqual(engine.call_args.args[1],existing)
                self.assertNotIn('thinking_budget',engine.call_args.kwargs)

    def test_translation_is_isolated_from_chat_history_and_removes_source_wrapper(self):
        from unittest.mock import Mock
        engine=Mock();engine.generate.return_value='<source>メモ帳を開きました。</source>'
        result=chat_service.run_worker({'mode':'local','purpose':'translate','messages':[{'role':'user','content':'old conversation'},{'role':'assistant','content':'old answer'},{'role':'user','content':'Notepad sudah dibuka.'}]},local=engine)
        self.assertEqual(result['response'],'メモ帳を開きました。')
        self.assertEqual(len(engine.generate.call_args.args[0]),1)
        self.assertIn('Notepad sudah dibuka.',engine.generate.call_args.args[0][0]['content'])

if __name__=='__main__':unittest.main()
