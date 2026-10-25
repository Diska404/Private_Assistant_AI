"""Attach a newly authored, small Cubism fringe pendulum to the private export.

Run only after exporting Leva_SSR_initial_rig_r02.aom in Ayatsuri. The editable
AOM contains the mesh/deformer rig. This physics preset is an external editable
sidecar, not a claim that the original game model supplied physics.
"""
import json
from pathlib import Path

ROOT=Path(r'D:\AI\AI Lokal Asisten\Model Avatar Leva\Live2D\Leva_Editable_R01')
OUT=ROOT/'runtime_initial_rig_r02c';index=OUT/'CHA_Levva_SSR_01.model3.json'

def main():
    doc=json.loads(index.read_text(encoding='utf8'));moc=OUT/doc['FileReferences']['Moc']
    if moc.read_bytes()[:4]!=b'MOC3':raise ValueError('missing_editor_export')
    name='Leva_AI_Fringe_R02b.physics3.json'
    if (OUT/name).exists():raise SystemExit('Refusing to overwrite existing physics.')
    physics={'Version':3,'Meta':{'PhysicsSettingCount':1,'TotalInputCount':2,'TotalOutputCount':1,'VertexCount':2,'EffectiveForces':{'Gravity':{'X':0,'Y':-1},'Wind':{'X':0,'Y':0}},'PhysicsDictionary':[{'Id':'LevaFringeR02','Name':'Leva AI · front hair initial rig'}]},'PhysicsSettings':[{'Id':'LevaFringeR02','Input':[{'Source':{'Target':'Parameter','Id':'ParamAngleZ'},'Weight':100,'Type':'X','Reflect':False},{'Source':{'Target':'Parameter','Id':'ParamAngleZ'},'Weight':100,'Type':'Angle','Reflect':False}],'Output':[{'Destination':{'Target':'Parameter','Id':'ParamHairFront'},'VertexIndex':1,'Scale':.5,'Weight':100,'Type':'Angle','Reflect':False}],'Vertices':[{'Position':{'X':0,'Y':0},'Mobility':1,'Delay':1,'Acceleration':1,'Radius':0},{'Position':{'X':0,'Y':3},'Mobility':.85,'Delay':.6,'Acceleration':1.5,'Radius':3}],'Normalization':{'Position':{'Minimum':-2,'Default':0,'Maximum':2},'Angle':{'Minimum':-4,'Default':0,'Maximum':4}}}]}
    text=json.dumps(physics,ensure_ascii=False,indent=2)
    (ROOT/name).write_text(text,encoding='utf8');(OUT/name).write_text(text,encoding='utf8')
    backup=index.with_suffix('.before-physics.json')
    if not backup.exists():backup.write_bytes(index.read_bytes())
    doc['FileReferences']['Physics']=name
    index.write_text(json.dumps(doc,indent=2),encoding='utf8')
    print('Attached initial two-particle fringe physics; not whole-hair or clothing physics.')

if __name__=='__main__':main()
