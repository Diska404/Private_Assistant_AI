"""Read-only VRM0/1 structure checks. Not a visual/clipping/weight-paint quality score."""
import hashlib
import json
import struct
from avatar_assets import inspect

REQUIRED={'hips','spine','head','leftUpperArm','leftLowerArm','leftHand','rightUpperArm','rightLowerArm','rightHand',
          'leftUpperLeg','leftLowerLeg','leftFoot','rightUpperLeg','rightLowerLeg','rightFoot'}

def audit(raw):
    meta=inspect(raw);length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length])
    nodes=doc.get('nodes',[]);accessors=doc.get('accessors',[]);ext=doc.get('extensions',{});vrm=ext.get('VRMC_vrm',{})
    legacy=ext.get('VRM',{});is_v0=not vrm and bool(legacy)
    bones=({r.get('bone'):{'node':r.get('node')} for r in legacy.get('humanoid',{}).get('humanBones',[]) if r.get('bone')} if is_v0 else vrm.get('humanoid',{}).get('humanBones',{}))
    spring=ext.get('VRMC_springBone',{});issues=[]
    def node(index,where):
        if type(index) is not int or not 0<=index<len(nodes):issues.append('invalid_node:'+where);return False
        return True
    for name,row in bones.items():node(row.get('node'),name)
    for skin in doc.get('skins',[]):
        for i in skin.get('joints',[]):node(i,'skin')
    for i,c in enumerate(spring.get('colliders',[])):
        node(c.get('node'),'collider')
        if any(shape.get('radius',0)<0 for shape in c.get('shape',{}).values()):issues.append('negative_collider_radius')
    for s in spring.get('springs',[]):
        for joint in s.get('joints',[]):node(joint.get('node'),'spring')
        for group in s.get('colliderGroups',[]):
            if type(group) is not int or not 0<=group<len(spring.get('colliderGroups',[])):issues.append('invalid_collider_group')
    for group in spring.get('colliderGroups',[]):
        for i in group.get('colliders',[]):
            if type(i) is not int or not 0<=i<len(spring.get('colliders',[])):issues.append('invalid_collider_reference')
    legacy_physics=legacy.get('secondaryAnimation',{})
    if is_v0:
        for group in legacy_physics.get('colliderGroups',[]):
            node(group.get('node'),'collider')
            for collider in group.get('colliders',[]):
                if collider.get('radius',0)<0:issues.append('negative_collider_radius')
        for group in legacy_physics.get('boneGroups',[]):
            for index in group.get('bones',[]):node(index,'spring')
            for index in group.get('colliderGroups',[]):
                if type(index) is not int or not 0<=index<len(legacy_physics.get('colliderGroups',[])):issues.append('invalid_collider_group')
    geometry=[]
    for mesh in doc.get('meshes',[]):
        vertices=triangles=weighted=0
        for primitive in mesh.get('primitives',[]):
            attrs=primitive.get('attributes',{});position=attrs.get('POSITION')
            if type(position) is not int or not 0<=position<len(accessors):issues.append('invalid_position_accessor');continue
            count=accessors[position].get('count',0);vertices+=count
            index=primitive.get('indices');n=accessors[index].get('count',0) if type(index) is int and 0<=index<len(accessors) else count
            if primitive.get('mode',4)==4:triangles+=n//3
            if 'JOINTS_0' in attrs and 'WEIGHTS_0' in attrs:weighted+=count
        geometry.append({'name':mesh.get('name','unnamed'),'primitive_vertices':vertices,'triangles':triangles,'vertices_with_skin_attributes':weighted})
    missing=sorted(REQUIRED-set(bones))
    if missing:issues.append('missing_required_human_bones')
    presets=([r.get('presetName',r.get('name','')) for r in legacy.get('blendShapeMaster',{}).get('blendShapeGroups',[])] if is_v0 else vrm.get('expressions',{}).get('preset',{}))
    return {'schema':'leva.avatar-structure.v1','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'meta':meta,
        'format_version':'0' if is_v0 else '1','modification_allowed':meta.get('modification') in ('allowModification','allowModificationRedistribution'),
        'human_bones':{k:nodes[v['node']].get('name',k) for k,v in bones.items() if type(v.get('node')) is int and 0<=v['node']<len(nodes)},
        'missing_required_bones':missing,'geometry':geometry,'materials':len(doc.get('materials',[])),
        'mtoon_materials':sum(m.get('shader')=='VRM/MToon' for m in legacy.get('materialProperties',[])) if is_v0 else sum('VRMC_materials_mtoon' in m.get('extensions',{}) for m in doc.get('materials',[])),
        'images':len(doc.get('images',[])),'skins':len(doc.get('skins',[])),
        'preset_expressions':sorted(presets),'springs':len(legacy_physics.get('boneGroups',[])) if is_v0 else len(spring.get('springs',[])),
        'spring_joints':None if is_v0 else sum(len(s.get('joints',[])) for s in spring.get('springs',[])),
        'spring_root_count':sum(len(s.get('bones',[])) for s in legacy_physics.get('boneGroups',[])) if is_v0 else None,
        'colliders':sum(len(g.get('colliders',[])) for g in legacy_physics.get('colliderGroups',[])) if is_v0 else len(spring.get('colliders',[])),
        'warnings':['vrm0_source_has_no_colliders'] if is_v0 and not legacy_physics.get('colliderGroups') else [],'issues':sorted(set(issues)),
        'visual_quality_verified':False,'clipping_verified':False,'physics_stability_verified':False}
