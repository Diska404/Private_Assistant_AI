"""Read-only R2 rig audit and source checkpoint. No inference or source-asset writes."""
from pathlib import Path
import collections,hashlib,json,struct,zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-premium-avatar-r2')

def main():
 for part in ('baseline','enhanced','videos','physics_debug','performance','reports'):(OUT/part).mkdir(parents=True,exist_ok=True)
 checkpoint=OUT/'baseline/source-v040-before.zip'
 if not checkpoint.exists():
  with zipfile.ZipFile(checkpoint,'w',zipfile.ZIP_DEFLATED) as z:
   for folder in ('app','experiments'):
    for p in (ROOT/folder).rglob('*'):
     if p.is_file() and '__pycache__' not in p.parts and 'vendor' not in p.parts and 'graphify-out' not in p.parts and p.suffix in {'.py','.js','.mjs','.html','.css','.json','.ps1'}:z.write(p,p.relative_to(ROOT))
   z.write(ROOT/'LEVA_PROJECT.json','LEVA_PROJECT.json')
 manifest=json.loads(Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets\leva-original-manifest.json').read_text())
 p=Path(manifest['path']);raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
 if digest!=manifest['sha256']:raise RuntimeError('source_hash_changed')
 n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);binary=raw[28+n:];nodes=doc['nodes'];parents={c:i for i,node in enumerate(nodes) for c in node.get('children',[])}
 def category(name):
  name=name.lower()
  if 'backhair' in name:return 'long_hair'
  if 'hair' in name:return 'hair_other'
  if 'bow' in name or 'ribbon' in name:return 'ribbon'
  if 'collar' in name:return 'collar'
  if 'coat' in name:return 'jacket'
  if 'skirt' in name or 'cloth' in name or 'cltoh' in name:return 'cloth_hem'
  return 'unclassified'
 def accessor(i):
  a=doc['accessors'][i];view=doc['bufferViews'][a['bufferView']];fmt={5121:'B',5123:'H',5126:'f'}[a['componentType']];count={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
  size=struct.calcsize('<'+fmt*count);start=view.get('byteOffset',0)+a.get('byteOffset',0);stride=view.get('byteStride',size)
  return [struct.unpack_from('<'+fmt*count,binary,start+j*stride) for j in range(a['count'])]
 weighted=collections.Counter();seen=set()
 for node in nodes:
  if 'mesh' not in node or 'skin' not in node:continue
  skin=doc['skins'][node['skin']]['joints']
  for prim in doc['meshes'][node['mesh']]['primitives']:
   attrs=prim['attributes'];pair=(node['skin'],attrs.get('JOINTS_0'),attrs.get('WEIGHTS_0'))
   if None in pair or pair in seen:continue
   seen.add(pair)
   for joints,weights in zip(accessor(pair[1]),accessor(pair[2])):
    for joint,weight in zip(joints,weights):
     if weight>0:weighted[skin[joint]]+=1
 groups=[]
 for g in doc['extensions']['VRM'].get('secondaryAnimation',{}).get('boneGroups',[]):
  roots=g.get('bones',[]);desc=set();todo=list(roots)
  while todo:
   i=todo.pop()
   if i in desc:continue
   desc.add(i);todo.extend(nodes[i].get('children',[]))
  groups.append({'settings':{k:v for k,v in g.items() if k!='bones'},'roots':[{'node':i,'name':nodes[i].get('name'),'category':category(nodes[i].get('name','')),'weighted_vertex_influences':weighted[i]} for i in roots],
   'descendant_nodes':len(desc),'categories':dict(collections.Counter(category(nodes[i].get('name','')) for i in desc))})
 report={'source_sha256':digest,'source_unchanged':True,'source_modification_allowed':manifest['modification_allowed'],'runtime_collision_for_leva':'blocked by source modification policy; do not attach/tune colliders on restricted source',
  'development_fixture':'existing pixiv VRM1 sample, allowModificationRedistribution','nodes':len(nodes),'humanoid':doc['extensions']['VRM']['humanoid']['humanBones'],'groups':groups,
  'source_colliders':len(doc['extensions']['VRM'].get('secondaryAnimation',{}).get('colliderGroups',[])),
  'weighted_vertices_by_node':[{'node':i,'name':nodes[i].get('name'),'category':category(nodes[i].get('name','')),'influence_count':count} for i,count in weighted.items()],
  'limits':['Categories from rig names are heuristic, not artist-authored semantics.','No automatic weight painting edits or mesh penetration acceptance.','Vertex influence counts are not unique vertices across nodes.']}
 (OUT/'reports/source-rig-audit-private.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 (OUT/'reports/directive-r2.txt').write_bytes(Path(r'C:\Users\Raizei\.codex\attachments\a16a7508-f46e-4c2a-9bb8-2e060509c280\Teks tempel.txt').read_bytes())
 print(json.dumps({'source_sha256':digest,'groups':len(groups),'colliders':report['source_colliders'],'weighted_nodes':len(weighted),'checkpoint':str(checkpoint)}))
if __name__=='__main__':main()
