"""Private, reversible AOM rig fork. No generated artwork; atlas bytes preserved.

Requires msgpack. Adds a modest head tilt (not yaw/perspective reconstruction)
and a front-hair deformer. Runtime export must be performed and inspected in
the editor before this fork can be promoted. Never overwrites an existing file.
"""
import argparse,copy,hashlib,json,math,struct,zlib
from pathlib import Path
import msgpack

def unpack_f32(blob):return list(struct.unpack('<'+'f'*(len(blob)//4),blob))
def pack_f32(values):return struct.pack('<'+'f'*len(values),*values)

def subdivide(mesh,cols=16,rows=24):
    """Subdivide the source rectangular quad without changing atlas sampling."""
    assert mesh['vertex_count']==4 and not mesh['binding']['axes']
    p=unpack_f32(mesh['positions']);uv=unpack_f32(mesh['uvs'])
    assert p[1]==p[3] and p[5]==p[7] and p[0]==p[4] and p[2]==p[6]
    positions=[];uvs=[];indices=[]
    for y in range(rows+1):
        v=y/rows
        for x in range(cols+1):
            u=x/cols
            for data,dest in ((p,positions),(uv,uvs)):
                for k in range(2):dest.append((1-v)*((1-u)*data[k]+u*data[k+2])+v*((1-u)*data[k+4]+u*data[k+6]))
    for y in range(rows):
        for x in range(cols):
            a=y*(cols+1)+x;b=a+1;c=a+cols+1;d=c+1
            indices.extend((b,a,c,c,d,b))
    mesh.update(vertex_count=len(positions)//2,positions=pack_f32(positions),uvs=pack_f32(uvs),indices=struct.pack('<'+'H'*len(indices),*indices))

def build(document):
    result=copy.deepcopy(document);model=result['model'];ds=model['deformers'];meshes=model['art_meshes'];params=model['parameters']
    if any(p['id']=='ParamAngleZ' for p in params):raise ValueError('already_rigged')
    assert len(meshes)==35 and meshes[33]['id']=='CHA_Levva_SSR_01' and meshes[34]['id']=='liuhai2'
    head=len(ds);hair=head+1;tilt=len(params);swing=tilt+1
    for id,minv,maxv in [('ParamAngleZ',-30,30),('ParamHairFront',-1,1)]:params.append({'id':id,'min':float(minv),'max':float(maxv),'default':0.,'repeat':False,'decimals':3})
    # A root warp maps unit coordinates back into source model space. All
    # existing root objects are re-expressed in that unit space at neutral.
    size=2.4;origin=-1.2
    for d in ds:
        if d['parent_deformer'] is None:
            r=d['kind']['Rotation'];r['origins_x']=[(v-origin)/size for v in r['origins_x']];r['origins_y']=[(v-origin)/size for v in r['origins_y']];d['parent_deformer']=head
    for i in (33,34):
        subdivide(meshes[i],16,24 if i==33 else 12)
        meshes[i]['positions']=pack_f32([(v-origin)/size for v in unpack_f32(meshes[i]['positions'])]);meshes[i]['parent_deformer']=head if i==33 else hair
    def grid_deformer(id,param,keys,parent,transform):
        rows=24;cols=16;positions=[]
        for key in keys:
            for y in range(rows+1):
                for x in range(cols+1):
                    px=origin+size*x/cols;py=origin+size*y/rows
                    qx,qy=transform(px,py,key)
                    if parent is not None:qx=(qx-origin)/size;qy=(qy-origin)/size
                    positions.extend((qx,qy))
        return {'id':id,'parent_part':None,'parent_deformer':parent,'visible':True,'enabled':True,'binding':{'axes':[{'parameter':param,'keys':keys}]},'kind':{'Warp':{'rows':rows,'cols':cols,'quad':True,'opacities':[1.]*len(keys),'positions':pack_f32(positions)}}}
    def head_pose(x,y,key):
        t=max(0.,min(1.,(-y-.02)/.18));weight=t*t*(3-2*t)
        angle=math.radians(key/30*4)*weight;cx=-.02;cy=-.10
        dx=x-cx;dy=y-cy
        return cx+dx*math.cos(angle)-dy*math.sin(angle),cy+dx*math.sin(angle)+dy*math.cos(angle)
    def hair_pose(x,y,key):
        # Root remains fixed; displacement increases towards the fringe tips.
        weight=max(0.,min(1.,(y+.50)/.35));return x+key*.008*weight,y+abs(key)*.001*weight
    ds.append(grid_deformer('Leva_AI_HeadTilt_R02',tilt,[-30.,0.,30.],None,head_pose))
    ds.append(grid_deformer('Leva_AI_FrontHair_R02',swing,[-1.,0.,1.],head,hair_pose))
    result['display']['param_names'].extend(['Leva AI · kemiringan kepala ±4°','Leva AI · poni ringan'])
    result['display']['deformer_names'].extend(['Leva AI · head tilt R02','Leva AI · front hair R02'])
    result['display']['groups'].append(['Leva AI · initial rig',[tilt,swing]])
    # moc3 requires parents to precede children. Keep the old order within
    # the recovered tree and remap every deformer reference explicitly.
    order=[head,hair,*range(head)];remap={old:new for new,old in enumerate(order)}
    model['deformers']=[ds[i] for i in order]
    for item in [*model['deformers'],*meshes]:
        if item['parent_deformer'] is not None:item['parent_deformer']=remap[item['parent_deformer']]
    result['display']['deformer_names']=[result['display']['deformer_names'][i] for i in order]
    for i,d in enumerate(model['deformers']):assert d['parent_deformer'] is None or d['parent_deformer']<i
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite existing rig.')
    source=args.input.read_bytes();magic,version,flags,length=struct.unpack('<4sHHI',source[:12]);assert magic==b'AOMX' and version==1 and flags==1 and length<256*1024*1024
    raw=zlib.decompress(source[12:],-15);assert len(raw)==length
    original=msgpack.unpackb(raw,raw=False);result=build(original)
    assert result['textures']==original['textures'] and result['expressions']==original['expressions']
    payload=msgpack.packb(result,use_bin_type=True);compressor=zlib.compressobj(6,zlib.DEFLATED,-15);blob=struct.pack('<4sHHI',magic,version,flags,len(payload))+compressor.compress(payload)+compressor.flush()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(blob)
    report={'source_sha256':hashlib.sha256(source).hexdigest(),'output_sha256':hashlib.sha256(blob).hexdigest(),'parameters':len(result['model']['parameters']),'deformers':len(result['model']['deformers']),'atlas_bytes_unchanged':True,'source_expressions_unchanged':True,'head_tilt_max_degrees':4,'head_yaw':False,'generated_artwork':False,'status':'candidate_requires_editor_export_and_visual_QA'}
    args.output.with_suffix('.report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))

if __name__=='__main__':main()
