"""Decode our canvas-only QA videos with portable Blender; no model/GPU stress."""
import bpy,json
from pathlib import Path
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\avatar-production-20261025')
scene=bpy.context.scene;editor=scene.sequence_editor_create();collection=editor.strips
scene.render.use_sequencer=True;scene.render.image_settings.file_format='PNG';scene.render.resolution_percentage=100
scene.render.threads_mode='FIXED';scene.render.threads=2
scene.view_settings.view_transform='Standard'
report=[]
for filename in ('hair-collider.webm','clothing-motion.webm','facial-expressions.webm'):
    strip=collection.new_movie(filename,str(OUT/filename),channel=1,frame_start=1)
    element=strip.elements[0];scene.render.resolution_x=element.orig_width;scene.render.resolution_y=element.orig_height
    row={'file':filename,'frames':strip.frame_duration,'fps':strip.fps,'size':[element.orig_width,element.orig_height],'frames_rendered':[]}
    for fraction in (.25,.6):
        frame=max(1,int(strip.frame_duration*fraction));scene.frame_set(frame)
        target=OUT/(Path(filename).stem+'-frame-'+str(frame)+'.png');scene.render.filepath=str(target)
        bpy.ops.render.render(write_still=True);row['frames_rendered'].append(str(target))
    report.append(row);collection.remove(strip)
(OUT/'video-decode-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('LEVA_VIDEO_QA_DECODED',len(report))
