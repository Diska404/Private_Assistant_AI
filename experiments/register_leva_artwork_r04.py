"""Register the private separated-artwork checkpoint without changing selection."""
import hashlib,json,shutil
from pathlib import Path
BASE=Path(r'D:\AI\AI Lokal Asisten\Model Avatar Leva\Live2D')
runtime=BASE/'Leva_Artwork_R04/R04A_v3/runtime'
physics=BASE/'Leva_Advanced_R03/Leva_Advanced_R03.physics3.json'
shutil.copy2(physics,runtime/physics.name)
index=runtime/'CHA_Levva_SSR_01.model3.json';doc=json.loads(index.read_text(encoding='utf8'));doc['FileReferences']['Physics']=physics.name;index.write_text(json.dumps(doc,indent=2),encoding='utf8')
files={p.relative_to(runtime).as_posix():{'path':p.relative_to(runtime).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in runtime.rglob('*') if p.is_file()}
row={'id':'leva_artwork_r04a','label':'Leva 2D · R04-A · layer terpisah · belum rig lengan','index':index.name,'model_is_leva':True,'kind':'artwork_separation_checkpoint','source_read_only':True,'root':str(runtime),'rig_capabilities':{'head_parallax':True,'head_yaw':False,'body_breath':True,'reconstructed_left_eye':True,'physics_groups':4,'cloth_collision':False,'independent_arms':False,'full_body':False,'separated_visible_layers':12},'files':files}
target=Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets\live2d\leva-artwork-r04a-manifest.json');target.write_text(json.dumps(row,indent=2),encoding='utf8')
print(json.dumps({'registered':'leva_artwork_r04a','members':len(files),'production_selection_changed':False}))
