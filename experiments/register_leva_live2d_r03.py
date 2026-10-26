"""Attach editable physics and pin a private R03 runtime. Does not change preferences."""
import hashlib,json
from pathlib import Path
BASE=Path(r'D:\AI\AI Lokal Asisten\Model Avatar Leva\Live2D\Leva_Advanced_R03')
runtime=BASE/'runtime'
def group(name,destination,inputs,length,mobility,delay,scale):
    return {'Id':name,'Input':[{'Source':{'Target':'Parameter','Id':id},'Weight':weight,'Type':kind,'Reflect':False} for id,kind,weight in inputs],
     'Output':[{'Destination':{'Target':'Parameter','Id':destination},'VertexIndex':1,'Scale':scale,'Weight':100,'Type':'Angle','Reflect':False}],
     'Vertices':[{'Position':{'X':0,'Y':0},'Mobility':1,'Delay':1,'Acceleration':1,'Radius':0},{'Position':{'X':0,'Y':length},'Mobility':mobility,'Delay':delay,'Acceleration':1.5,'Radius':length}],
     'Normalization':{'Position':{'Minimum':-2,'Default':0,'Maximum':2},'Angle':{'Minimum':-4,'Default':0,'Maximum':4}}}
settings=[group('LevaFrontR03','ParamHairFront',[('ParamAngleX','X',60),('ParamAngleZ','Angle',40)],3,.85,.6,35),
 group('LevaBackR03','ParamHairBack',[('ParamAngleX','X',70),('ParamAngleZ','Angle',30)],4,.9,.8,30),
 group('LevaSideR03','ParamHairSide',[('ParamAngleZ','X',70),('ParamAngleY','Angle',30)],2.5,.8,.55,30),
 group('LevaJacketR03','ParamJacketSway',[('ParamBodyAngleX','X',70),('ParamBodyAngleZ','Angle',30)],3,.75,.65,25)]
physics={'Version':3,'Meta':{'PhysicsSettingCount':4,'TotalInputCount':8,'TotalOutputCount':4,'VertexCount':8,'EffectiveForces':{'Gravity':{'X':0,'Y':-1},'Wind':{'X':0,'Y':0}},'PhysicsDictionary':[{'Id':g['Id'],'Name':g['Id']} for g in settings]},'PhysicsSettings':settings}
name='Leva_Advanced_R03.physics3.json'
for folder in (BASE,runtime):(folder/name).write_text(json.dumps(physics,indent=2),encoding='utf8')
index=runtime/'CHA_Levva_SSR_01.model3.json';doc=json.loads(index.read_text(encoding='utf8'));doc['FileReferences']['Physics']=name;index.write_text(json.dumps(doc,indent=2),encoding='utf8')
files={p.relative_to(runtime).as_posix():{'path':p.relative_to(runtime).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in runtime.rglob('*') if p.is_file()}
row={'id':'leva_rig_r03','label':'Leva 2D · rig R03 · kepala, badan, napas & rambut','index':index.name,'model_is_leva':True,'kind':'derived_parallax_body_secondary_rig','source_read_only':True,'root':str(runtime),'rig_capabilities':{'head_parallax':True,'head_yaw':False,'body_breath':True,'reconstructed_left_eye':True,'physics_groups':4,'cloth_collision':False},'files':files}
target=Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets\live2d\leva-rig-r03-manifest.json');target.write_text(json.dumps(row,indent=2),encoding='utf8')
print(json.dumps({'registered':'leva_rig_r03','members':len(files),'physics_groups':len(settings),'production_preferences_changed':False}))
