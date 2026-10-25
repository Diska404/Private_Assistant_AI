import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import live2d_assets as assets

class Live2DAssetsTests(unittest.TestCase):
    def test_initial_rig_has_separate_pinned_root(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);models=base/'manifests';models.mkdir();sources=base/'sources'
            rig=sources/'Leva_Editable_R01/runtime_initial_rig_r02c';rig.mkdir(parents=True)
            (rig/'test.json').write_bytes(b'{}')
            row={'id':'leva_rig_r02','source_read_only':True,'model_is_leva':True,'root':str(rig),'files':{'test.json':{'path':'test.json','sha256':hashlib.sha256(b'{}').hexdigest()}}}
            p=models/'leva-rig-r02-manifest.json';p.write_text(json.dumps(row),encoding='utf8')
            with patch.object(assets,'MODELS',models),patch.object(assets,'LOCAL_MODELS',sources):
                self.assertEqual(assets.read('models/leva_rig_r02/test.json')[0],b'{}')
                row['root']=str(sources/'CHA_Levva_SSR_01');p.write_text(json.dumps(row),encoding='utf8')
                with self.assertRaises(ValueError):assets.read('models/leva_rig_r02/test.json')
    def test_character_manifest_is_read_only_and_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);models=root/'manifests';models.mkdir();source=root/'sources/CHA_Levva_SSR_01';source.mkdir(parents=True);(source/'test.json').write_bytes(b'{"test":true}')
            row={'id':'leva_ssr','source_read_only':True,'model_is_leva':True,'root':str(source),'files':{'test.json':{'path':'test.json','sha256':hashlib.sha256(b'{"test":true}').hexdigest()}}}
            p=models/'leva-ssr-manifest.json';p.write_text(json.dumps(row),encoding='utf8')
            with patch.object(assets,'MODELS',models),patch.object(assets,'LOCAL_MODELS',root/'sources'):
                self.assertEqual(assets.read('models/leva_ssr/test.json')[0],b'{"test":true}')
                for name in ('models/unknown/test.json','models/leva_ssr/../test.json'):
                    with self.assertRaises(ValueError):assets.read(name)
                row['source_read_only']=False;p.write_text(json.dumps(row),encoding='utf8')
                with self.assertRaises(ValueError):assets.read('models/leva_ssr/test.json')
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
