import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import live2d_assets as assets

class Live2DAssetsTests(unittest.TestCase):
    def test_allowlist_hash_and_root_guards(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(assets,'ROOT',Path(folder)):
            root=Path(folder);p=root/'core.js';p.write_bytes(b'fixture');files={'runtime/core.js':{'path':'core.js','sha256':hashlib.sha256(b'fixture').hexdigest()}}
            (root/'leva-runtime-manifest.json').write_text(json.dumps({'model_is_leva':False,'model':'sample','sdk_version':'test','files':files}),encoding='utf8')
            self.assertTrue(assets.status()['available']);self.assertEqual(assets.read('runtime/core.js'),(b'fixture','text/javascript'))
            for name in ('../core.js','runtime/../core.js','model/unknown.json'):
                with self.assertRaises(ValueError):assets.read(name)
            p.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'hash_changed'):assets.read('runtime/core.js')
            files['runtime/core.js']['path']='../outside.js'
            (root/'leva-runtime-manifest.json').write_text(json.dumps({'model_is_leva':False,'files':files}),encoding='utf8')
            with self.assertRaises(ValueError):assets.read('runtime/core.js')
    def test_missing_runtime_is_optional(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(assets,'ROOT',Path(folder)):
            self.assertFalse(assets.status()['available'])
