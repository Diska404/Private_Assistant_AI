import unittest
from types import SimpleNamespace
from avatar_emotion import expression_for_reply,observe_reply

class EmotionCalibrationTests(unittest.TestCase):
    def test_dialogue_tags_and_conservative_fallback(self):
        for text,expected in [('Selamat, tugasmu berhasil!','happy'),('Aku paham ini melelahkan.','soft_smile'),('Aku belum yakin, perlu memastikan sumbernya.','thinking'),('Hehe, aku bercanda.','playful'),('Halo, aku di sini untukmu.','soft_smile'),('Nilai integralnya adalah 2.','neutral'),('Permintaan belum berhasil.','thinking')]:
            self.assertEqual(expression_for_reply(text),expected,text)
    def test_hint_is_ephemeral_enum_only_and_room_scoped(self):
        m=SimpleNamespace(workspace='secret',generation=7)
        observe_reply(m,'Leva','Halo, data privat');self.assertFalse(hasattr(m,'_avatar_reply_emotion'))
        m.workspace='companion_avatar';observe_reply(m,'Leva · Proses','Berhasil');self.assertFalse(hasattr(m,'_avatar_reply_emotion'))
        observe_reply(m,'Leva','Selamat, kode privat tersimpan.')
        self.assertEqual(m._avatar_reply_emotion,{'generation':7,'expression':'happy','source':'reply_pattern_calibration'})
        self.assertNotIn('privat',str(m._avatar_reply_emotion))
