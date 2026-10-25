import unittest
from types import SimpleNamespace
from avatar_emotion import expression_for_reply,reaction_for_reply,observe_reply

class EmotionCalibrationTests(unittest.TestCase):
    def test_reaction_tags_do_not_celebrate_failure(self):
        for text,expected in [('Halo, Raizei.','greeting'),('Hehe, canda deh.','playful'),('Aku paham ini melelahkan.','comfort'),('Permintaan belum berhasil.','ponder'),('Maaf, aku perlu memeriksa.','apology'),('Integralnya adalah 3.','none')]:
            self.assertEqual(reaction_for_reply(text),expected)
        self.assertEqual(expression_for_reply('Maaf, aku keliru.'),'apologetic')
    def test_reaction_receipt_is_sent_once_per_reply_hint(self):
        from companion_avatar import AvatarDirector,presentation
        from unittest.mock import patch
        director=AvatarDirector(clock=lambda:10.)
        m=SimpleNamespace(workspace='companion_avatar',generation=2,avatar_director=director,preferences=SimpleNamespace(get=lambda key:False))
        observe_reply(m,'Leva','Halo, Raizei.')
        with patch('avatar_assets.choices',return_value={'placeholder':'fixture'}):
            a=presentation(m,'idle',0);b=presentation(m,'idle',0)
        self.assertEqual(a['reaction'],'greeting');self.assertEqual(a['reaction_id'],b['reaction_id'])
        director.cancel();self.assertEqual(director.snapshot()['reaction'],'none')
    def test_dialogue_tags_and_conservative_fallback(self):
        for text,expected in [('Selamat, tugasmu berhasil!','happy'),('Aku paham ini melelahkan.','soft_smile'),('Aku belum yakin, perlu memastikan sumbernya.','thinking'),('Hehe, aku bercanda.','playful'),('Halo, aku di sini untukmu.','soft_smile'),('Nilai integralnya adalah 2.','neutral'),('Permintaan belum berhasil.','thinking')]:
            self.assertEqual(expression_for_reply(text),expected,text)
    def test_hint_is_ephemeral_enum_only_and_room_scoped(self):
        m=SimpleNamespace(workspace='secret',generation=7)
        observe_reply(m,'Leva','Halo, data privat');self.assertFalse(hasattr(m,'_avatar_reply_emotion'))
        m.workspace='companion_avatar';observe_reply(m,'Leva Â· Proses','Berhasil');self.assertFalse(hasattr(m,'_avatar_reply_emotion'))
        observe_reply(m,'Leva','Selamat, kode privat tersimpan.')
        self.assertEqual(m._avatar_reply_emotion,{'generation':7,'expression':'happy','reaction':'celebrate','source':'reply_pattern_calibration'})
        self.assertNotIn('privat',str(m._avatar_reply_emotion))
