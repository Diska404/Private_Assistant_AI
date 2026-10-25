"""Isolated QA for an editor export; never registers it in production preferences.

Example: python experiments/preview_live2d_roundtrip.py --out <private QA folder>
Uses port 20292 and the existing locally installed Cubism SDK.
"""
import hashlib,json,runpy,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import live2d_assets

candidate=live2d_assets.LOCAL_MODELS/('Leva_Editable_R01/runtime_initial_rig_r02c' if '--initial-rig' in sys.argv else 'Leva_Editable_R01/runtime_roundtrip')
index=candidate/'CHA_Levva_SSR_01.model3.json'
if not index.is_file():raise SystemExit('Export the private roundtrip candidate first.')
source=live2d_assets.character_manifest
files={str(p.relative_to(candidate)).replace('\\','/'):{'path':str(p.relative_to(candidate)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in candidate.rglob('*') if p.is_file()}
fixture_key='leva_rig_r02' if '--initial-rig' in sys.argv else 'leva_ssr'
row={'id':fixture_key,'label':'Leva SSR · initial head tilt & fringe QA' if '--initial-rig' in sys.argv else 'Leva SSR · Ayatsuri roundtrip QA','index':index.name,'model_is_leva':True,'kind':'editor_roundtrip_qa','source_read_only':True,'files':files}

def fixture_manifest(key):
    if key==fixture_key:return row,candidate.resolve()
    return source(key)

live2d_assets.character_manifest=fixture_manifest
if '--out' not in sys.argv:raise SystemExit('--out is required; choose an isolated private QA directory.')
out=Path(sys.argv[sys.argv.index('--out')+1]);out.mkdir(parents=True,exist_ok=True)
(out/'roundtrip-manifest.json').write_text(json.dumps(row,indent=2),encoding='utf8')
sys.argv.extend(['--leva','--port','20293' if '--initial-rig' in sys.argv else '20292'])
runpy.run_path(str(ROOT/'experiments/preview_premium_avatar_r2.py'),run_name='__main__')
