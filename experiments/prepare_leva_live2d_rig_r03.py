"""Reversible advanced AOM fork: limited head parallax, body, secondary motion,
and an optional left eye reconstructed from existing right-eye keyforms.
Atlas pixels remain unchanged. This does not create hidden-side head artwork.
"""
import argparse,copy,hashlib,itertools,json,math,struct,zlib
from pathlib import Path
import msgpack

def floats(blob):return struct.unpack('<'+'f'*(len(blob)//4),blob)
def binary(values):return struct.pack('<'+'f'*len(values),*values)
def clamp(v):return max(0.,min(1.,v))
def smooth(v):v=clamp(v);return v*v*(3-2*v)

def build(source,eye):
    doc=copy.deepcopy(source);model=doc['model'];params=model['parameters'];ds=model['deformers'];meshes=model['art_meshes'];ids={p['id']:i for i,p in enumerate(params)}
    assert len(ds)==54 and len(meshes)==35 and ds[0]['id']=='Leva_AI_HeadTilt_R02'
    specs=[('ParamAngleX',-30,30,0,'Arah kepala X · parallax terbatas'),('ParamAngleY',-30,30,0,'Arah kepala Y · parallax terbatas'),('ParamBodyAngleX',-10,10,0,'Badan · geser'),('ParamBodyAngleZ',-10,10,0,'Badan · miring'),('ParamBreath',0,1,0,'Napas'),('ParamHairBack',-1,1,0,'Rambut belakang · ringan'),('ParamHairSide',-1,1,0,'Rambut samping · ringan'),('ParamJacketSway',-1,1,0,'Kostum · ayunan ringan'),('ParamEyeLOpen',0,1,0,'Mata kiri · rekonstruksi opsional'),('ParamLeftEyeMood',-1,1,0,'Mata kiri · ekspresi turunan')]
    for name,lo,hi,default,label in specs:
        if name in ids:raise ValueError('already_rigged')
        ids[name]=len(params);params.append({'id':name,'min':float(lo),'max':float(hi),'default':float(default),'repeat':False,'decimals':3});doc['display']['param_names'].append(label)
    body=len(ds);headxy=body+1;back=body+2;side=body+3;jacket=body+4
    # Insert two identity-neutral wrappers above the existing tilt rig.
    ds[0]['parent_deformer']=headxy
    ds[0]['kind']['Warp']['positions']=binary([(v+1.2)/2.4 for v in floats(ds[0]['kind']['Warp']['positions'])])
    def warp(name,axes,parent,fn):
        positions=[];rows=24;cols=16
        # Axis zero is fastest in the AOM keyform product.
        combinations=[tuple(reversed(v)) for v in itertools.product(*(keys for _,keys in reversed(axes)))]
        min_area=1.
        for values in combinations:
            grid=[]
            for y in range(rows+1):
                for x in range(cols+1):
                    px=-1.2+2.4*x/cols;py=-1.2+2.4*y/rows;qx,qy=fn(px,py,*values)
                    grid.append((qx,qy));positions.extend((qx,qy) if parent is None else ((qx+1.2)/2.4,(qy+1.2)/2.4))
            for y in range(rows):
                for x in range(cols):
                    a=grid[y*(cols+1)+x];b=grid[y*(cols+1)+x+1];c=grid[(y+1)*(cols+1)+x]
                    area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);min_area=min(min_area,area)
                    if area<=0:raise ValueError('folded_warp: '+name)
        return {'id':name,'parent_part':None,'parent_deformer':parent,'visible':True,'enabled':True,'binding':{'axes':[{'parameter':ids[id],'keys':keys} for id,keys in axes]},'kind':{'Warp':{'rows':rows,'cols':cols,'quad':True,'opacities':[1.]*len(combinations),'positions':binary(positions)}}},min_area
    def body_pose(x,y,u,z,breath):
        angle=math.radians((u/10*.45+z/10*.8));dx=x;dy=y-.55
        qx=dx*math.cos(angle)-dy*math.sin(angle)+.006*u/10;qy=.55+dx*math.sin(angle)+dy*math.cos(angle)
        upper=1-smooth((y-.25)/.5);return qx+x*.003*breath*upper,qy-.004*breath*upper
    def head_pose(x,y,u,v):
        w=smooth((-y-.02)/.2);return x+(.020*u/30-.02*(u/30)**2*(x+.02))*w,y+(.014*v/30+.008*v/30*(y+.25))*w
    def back_pose(x,y,v):
        w=smooth((x-.14)/.14)*smooth((y+.48)/.28)*(1-smooth((y-.04)/.18));return x+.009*v*w,y+.002*abs(v)*w
    def side_pose(x,y,v):
        w=smooth((-x-.12)/.13)*smooth((y+.45)/.22)*(1-smooth((y+.02)/.15));return x+.006*v*w,y+.001*abs(v)*w
    def jacket_pose(x,y,v):
        w=smooth((y-.10)/.65)*(1-smooth((abs(x)-.18)/.18));return x+.005*v*w,y+.0015*abs(v)*w
    new=[];areas={}
    for name,axes,parent,fn in [('Leva_AI_BodyBreath_R03',[('ParamBodyAngleX',[-10.,0.,10.]),('ParamBodyAngleZ',[-10.,0.,10.]),('ParamBreath',[0.,1.])],None,body_pose),('Leva_AI_HeadParallax_R03',[('ParamAngleX',[-30.,0.,30.]),('ParamAngleY',[-30.,0.,30.])],body,head_pose),('Leva_AI_HairBack_R03',[('ParamHairBack',[-1.,0.,1.])],0,back_pose),('Leva_AI_HairSide_R03',[('ParamHairSide',[-1.,0.,1.])],back,side_pose),('Leva_AI_Jacket_R03',[('ParamJacketSway',[-1.,0.,1.])],side,jacket_pose)]:
        item,area=warp(name,axes,parent,fn);new.append(item);areas[name]=area
    ds.extend(new);meshes[33]['parent_deformer']=jacket
    doc['display']['deformer_names'].extend([d['id'] for d in new]);doc['display']['groups'].append(['Leva AI · advanced rig R03',[ids[name] for name,*_ in specs]])
    # Preserve the source closed-eye pose at ParamEyeLOpen=0. Fade only its
    # eyelid layers out when the optional reconstruction is explicitly enabled.
    for index in (12,13,15,16):
        mesh=meshes[index];mesh['binding']['axes'].append({'parameter':ids['ParamEyeLOpen'],'keys':[0.,1.]});mesh['positions']*=2;mesh['draw_orders']*=2;mesh['opacities']=[*mesh['opacities'],*[0.]*len(mesh['opacities'])]
    clones={row['sourceIndex']:len(meshes)+i for i,row in enumerate(eye['meshes'])}
    for row in eye['meshes']:
        index=row['sourceIndex'];mesh=copy.deepcopy(meshes[index]);mesh['id']='Leva_AI_Left_'+mesh['id'];mesh['parent_deformer']=0;mesh['binding']={'axes':[{'parameter':ids[a['id']],'keys':a['keys']} for a in eye['axes']]}
        positions=[]
        for sample in row['samples']:
            for x,y in zip(sample['vertices'][::2],sample['vertices'][1::2]):
                if row['mirrored']:x=.075-1.05*(x+.065);y+=.003
                positions.extend(((x+1.2)/2.4,(-y+1.2)/2.4))
        mesh['positions']=binary(positions);mesh['opacities']=[s['opacity'] for s in row['samples']];mesh['draw_orders']=[500.]*len(row['samples']);mesh['masks']=[clones[i] for i in mesh['masks']]
        if row['mirrored']:
            indices=list(struct.unpack('<'+'H'*(len(mesh['indices'])//2),mesh['indices']))
            for n in range(0,len(indices),3):indices[n+1],indices[n+2]=indices[n+2],indices[n+1]
            mesh['indices']=struct.pack('<'+'H'*len(indices),*indices)
        meshes.append(mesh);doc['display']['mesh_names'].append(mesh['id'])
    for group in model['draw_groups']:
        items=[]
        for item in group['items']:
            items.append(item)
            if not item['part'] and item['object'] in clones:items.append({'part':False,'object':clones[item['object']],'child_group':None})
        group['items']=items;group['total']=len(items)
    for group in doc['display']['model_groups']:
        if group[:2]==['Parameter','EyeBlink']:group[2].append('ParamEyeLOpen')
    # Stable topological order; export requires every parent before its child.
    order=[];remaining=set(range(len(ds)))
    while remaining:
        ready=[i for i in sorted(remaining) if ds[i]['parent_deformer'] is None or ds[i]['parent_deformer'] in order]
        if not ready:raise ValueError('deformer_cycle')
        order.extend(ready);remaining.difference_update(ready)
    remap={old:new for new,old in enumerate(order)};model['deformers']=[ds[i] for i in order]
    for item in [*model['deformers'],*meshes]:
        if item['parent_deformer'] is not None:item['parent_deformer']=remap[item['parent_deformer']]
    doc['display']['deformer_names']=[doc['display']['deformer_names'][i] for i in order]
    return doc,areas

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--eye-bake',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise SystemExit('Refusing to overwrite output.')
    b=a.input.read_bytes();magic,version,flags,length=struct.unpack('<4sHHI',b[:12]);assert (magic,version,flags)==(b'AOMX',1,1) and length<256*1024*1024
    original=msgpack.unpackb(zlib.decompress(b[12:],-15),raw=False);eye=json.loads(a.eye_bake.read_text(encoding='utf8'));doc,areas=build(original,eye)
    assert doc['textures']==original['textures'] and doc['expressions']==original['expressions']
    raw=msgpack.packb(doc,use_bin_type=True);c=zlib.compressobj(6,zlib.DEFLATED,-15);result=struct.pack('<4sHHI',magic,version,flags,len(raw))+c.compress(raw)+c.flush();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(result)
    proof={'source_sha256':hashlib.sha256(b).hexdigest(),'sha256':hashlib.sha256(result).hexdigest(),'parameters':len(doc['model']['parameters']),'deformers':len(doc['model']['deformers']),'meshes':len(doc['model']['art_meshes']),'atlas_bytes_unchanged':True,'source_expressions_unchanged':True,'left_eye':'optional geometry/UV reconstruction from source right eye; source wink default retained','head_motion':'limited 2.5D parallax, not hidden-side artwork reconstruction','positive_warp_cell_areas':areas,'generated_artwork':False,'status':'candidate_requires_export_and_visual_QA'}
    a.output.with_suffix('.report.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof))
if __name__=='__main__':main()
