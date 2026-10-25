import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import avatar_assets
from test_avatar_validation import glb

class LocalLevaTests(unittest.TestCase):
    def test_read_only_registration_hash_and_local_path_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);source=base/'sources';source.mkdir();registered=base/'registered'
            raw=glb({'extensions':{'VRM':{'meta':{'title':'Leva','allowedUserName':'Everyone','otherLicenseUrl':'modification=disallow&redistribution=disallow'}}}})
            path=source/'leva.vrm';path.write_bytes(raw)
            with patch.object(avatar_assets,'LOCAL_LEVA_FOLDER',source),patch.object(avatar_assets,'FOLDER',registered):
                row=avatar_assets.register_local_leva(path)
                self.assertEqual(path.read_bytes(),raw);self.assertTrue(row['source_read_only']);self.assertFalse(row['modification_allowed'])
                self.assertFalse(row['redistribution_allowed']);self.assertEqual(avatar_assets.read('leva_original'),raw)
                self.assertIn('leva_original',avatar_assets.choices());self.assertEqual(len(list(source.iterdir())),1)
                outside=base/'other.vrm';outside.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'invalid_local_leva_source'):avatar_assets.register_local_leva(outside)
                path.write_bytes(raw+b' ')
                with self.assertRaises(ValueError):avatar_assets.read('leva_original')
    def test_restricted_user_or_different_character_is_not_registered(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(avatar_assets,'LOCAL_LEVA_FOLDER',Path(folder)):
            path=Path(folder)/'source.vrm'
            for meta in ({'title':'Leva','allowedUserName':'OnlyAuthor'},{'title':'Other','allowedUserName':'Everyone'}):
                path.write_bytes(glb({'extensions':{'VRM':{'meta':meta}}}))
                with self.assertRaises(ValueError):avatar_assets.register_local_leva(path)
