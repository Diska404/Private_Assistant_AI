"""Performance invariants with isolated data; no real model, mic or PC actions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from conversation_rooms import ConversationRooms
from preferences import Preferences
from web_bridge import WebBridge
from web_store import WebStore
from profile_avatar import ProfileAvatar
from neural_orb import sphere_geometry,particle,particle_frame


class DisplayCacheTests(unittest.TestCase):
    def test_choices_are_bounded_and_settings_are_immediately_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs=Preferences(Path(folder)/'prefs.db');rooms=ConversationRooms(Path(folder)/'rooms.db')
            try:
                with patch('conversation_rooms.time.monotonic',return_value=10) as clock,patch('conversation_rooms.model_choices',side_effect=lambda room:{'qwen4b':room}) as choices:
                    first=rooms.snapshot(prefs);self.assertEqual(choices.call_count,3)
                    first['chat']['models']['tampered']='bad'
                    prefs.set('chat_gpu','dual')
                    second=rooms.snapshot(prefs)
                    self.assertEqual(choices.call_count,3);self.assertNotIn('tampered',second['chat']['models'])
                    self.assertEqual(second['chat']['gpu'],'dual')
                    clock.return_value=13.1;rooms.snapshot(prefs);self.assertEqual(choices.call_count,6)
            finally:rooms.close();prefs.close()

    def test_launch_validation_does_not_use_display_cache(self):
        from conversation_rooms import validate_room_settings
        with patch('conversation_rooms.MODELS',{'qwen4b':('Qwen',Path('missing-fixture-model.gguf'))}),patch('conversation_rooms.model_choices',return_value={'qwen4b':'Display cached'}):
            with self.assertRaisesRegex(ValueError,'Bobot model belum tersedia'):
                validate_room_settings({'workspace':'chat','model':'qwen4b','gpu':'gpu5070'})


class SnapshotTests(unittest.TestCase):
    def test_message_deltas_fall_back_after_trim_clear_or_instance_change(self):
        bridge=WebBridge(Mock(),port=0,store=WebStore())
        try:
            bridge.log('Anda','First');first=bridge.logs[-1]['id']
            bridge.log('Leva','Second');second=bridge.logs[-1]['id']
            value=bridge.snapshot(instance=bridge.instance,messages_since=str(first))
            self.assertEqual(value['messages_mode'],'append');self.assertEqual([r['id'] for r in value['messages']],[second])
            self.assertEqual(bridge.snapshot(instance=bridge.instance,messages_since=str(second))['messages'],[])
            self.assertEqual(bridge.snapshot(instance='old-instance',messages_since=first)['messages_mode'],'replace')
            for i in range(121):bridge.log('Leva',str(i))
            self.assertEqual(bridge.snapshot(instance=bridge.instance,messages_since=first)['messages_mode'],'replace')
            bridge.logs.clear()
            value=bridge.snapshot(instance=bridge.instance,messages_since=second)
            self.assertEqual(value['messages_mode'],'replace');self.assertEqual(value['messages'],[])
        finally:bridge.stop();bridge.store.close()

    def test_unchanged_revision_avoids_copy_and_delivery_io(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=WebBridge(Mock(),port=0,store=WebStore(),avatar=ProfileAvatar(Path(folder)))
            try:
                bridge.update({'phase':'idle'});revision=bridge.revision
                with patch.object(bridge.store,'recent',wraps=bridge.store.recent) as query:
                    self.assertIsNone(bridge.snapshot(str(revision),bridge.instance));query.assert_not_called()
                    self.assertIsNotNone(bridge.snapshot(str(revision),'old-server-instance'));query.assert_called_once()
                bridge.log('Leva','Fresh answer')
                self.assertEqual(bridge.snapshot(revision,bridge.instance)['messages'][-1]['text'],'Fresh answer')
            finally:bridge.stop();bridge.store.close()

    def test_snapshot_copy_cannot_change_host_state(self):
        bridge=WebBridge(Mock(),port=0,store=WebStore())
        try:
            bridge.update({'phase':'idle','nested':{'x':1}})
            bridge.snapshot()['state']['nested']['x']=2
            self.assertEqual(bridge.state['nested']['x'],1)
        finally:bridge.stop();bridge.store.close()


class ParticleTests(unittest.TestCase):
    def test_shared_frame_is_identical_to_individual_calculation(self):
        for state in ('idle','sleeping','connecting','listening','thinking','speaking','clarifying','interrupted','error'):
            for elapsed in (0.,2.,123.45):
                frame=particle_frame(elapsed,state)
                for index in range(320):
                    self.assertEqual(particle(index,320,elapsed,state,.5),particle(index,320,elapsed,state,.5,frame))
        self.assertEqual(sphere_geometry.cache_info().maxsize,8)


if __name__=='__main__':unittest.main()
