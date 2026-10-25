"""Run using isolated portable Blender --background --factory-startup --disable-autoexec.

Only the licensed pixiv fixture is an approved input in this proof. Source is never saved over.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import bpy

BASE=Path(r'D:\AI\AI Lokal Asisten\Github\Leva-Avatar-Production-Tools')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\avatar-production-20261025')
SOURCE=Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets\pixiv-vrm1-sample.vrm')

def main():
    OUT.mkdir(exist_ok=True)
    folder=BASE/'addons/io_scene_vrm'
    if not folder.exists():
        import shutil
        shutil.copytree(BASE/'VRM_Addon_for_Blender-release',folder)
    sys.path.insert(0,str(folder.parent))
    import addon_utils
    addon_utils.enable('io_scene_vrm',default_set=True,persistent=False)
    before=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if before!='12c2b97e95e700783a6a550dc0eee2d7880aeedccef9ae67bc4c5a2f0f2631a2':raise RuntimeError('fixture_source_changed')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    if bpy.ops.import_scene.vrm(filepath=str(SOURCE))!={'FINISHED'}:raise RuntimeError('vrm_import_failed')
    # Add-on shader setup can append a default unskinned Cube. It is not in this
    # hash-pinned source asset; exclude only that known fixture artifact.
    removed=[]
    for obj in list(bpy.data.objects):
        if obj.name=='Cube' and obj.type=='MESH' and not obj.vertex_groups:
            removed.append(obj.name);bpy.data.objects.remove(obj,do_unlink=True)
    meshes=[obj for obj in bpy.data.objects if obj.type=='MESH'];arms=[obj for obj in bpy.data.objects if obj.type=='ARMATURE']
    audit={'blender':bpy.app.version_string,'source_sha256':before,'asset':'pixiv test sample, not final Leva','excluded_import_artifacts':removed,
        'meshes':[{'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),
                   'shape_keys':list(o.data.shape_keys.key_blocks.keys()) if o.data.shape_keys else [],
                   'vertex_groups':len(o.vertex_groups),'nonfinite_vertices':sum(not all(__import__('math').isfinite(v) for v in point.co) for point in o.data.vertices)} for o in meshes],
        'armatures':[{'name':o.name,'bones':len(o.data.bones),'root_bones':[b.name for b in o.data.bones if not b.parent]} for o in arms],
        'textures':[{'name':im.name,'size':list(im.size),'packed':im.packed_file is not None} for im in bpy.data.images if im.type=='IMAGE'],
        'materials':[{'name':m.name,'mtoon':m.vrm_addon_extension.mtoon1.enabled} for m in bpy.data.materials]}
    for arm in arms:arm.show_in_front=True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'pixiv-source-audit.blend'))
    layer=[]
    # Reversible artist-directed material layer; keep mesh, rig, UVs and texture maps intact.
    for material in bpy.data.materials:
        gltf=material.vrm_addon_extension.mtoon1
        if not gltf.enabled:continue
        m=gltf.extensions.vrmc_materials_mtoon
        fields=('shading_toony_factor','shading_shift_factor','gi_equalization_factor','outline_width_factor')
        old={key:getattr(m,key) for key in fields}
        m.shading_toony_factor=.82
        m.gi_equalization_factor=.85
        # Preserve the artist's no-outline eye/mouth layers. Creating inverted
        # hulls for every transparent face part causes unwanted black seams.
        if m.outline_width_mode!='none':m.outline_width_factor=.0005 if 'face' in material.name.lower() else .0008
        if 'skin' in material.name.lower():m.shading_shift_factor=-.08
        layer.append({'name':material.name,'before':old,'after':{key:getattr(m,key) for key in fields}})
    bpy.context.scene['leva_asset_status']='licensed pipeline fixture; not final Leva character'
    bpy.context.scene['leva_original_source_sha256']=before
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'pixiv-toon-layer.blend'))
    target=OUT/'pixiv-toon-layer.vrm'
    if bpy.ops.export_scene.vrm(filepath=str(target))!={'FINISHED'}:raise RuntimeError('vrm_export_failed')
    audit['layer_changes']=layer;audit['source_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before
    audit['export']={'path':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (OUT/'blender-pipeline-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print('LEVA_PIPELINE_SUCCESS',target)

main()
