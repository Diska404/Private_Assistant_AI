"""Decode renderer recordings and inspect their audio; no avatar file is imported/modified."""
import bpy,json,numpy as np,subprocess,shutil
from pathlib import Path
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-premium-avatar-r1\videos')
scene=bpy.context.scene;editor=scene.sequence_editor_create();collection=editor.strips
scene.render.use_sequencer=True;scene.render.image_settings.file_format='PNG';scene.render.resolution_percentage=100
scene.render.threads_mode='FIXED';scene.render.threads=2;scene.view_settings.view_transform='Standard'
report=[]
for filename in ('r1-facial-transitions.webm','r1-fast-turn-source-physics.webm','r1-body-clothing.webm','r1-japanese-voice.webm'):
 strip=collection.new_movie(filename,str(OUT/filename),channel=1,frame_start=1);element=strip.elements[0]
 scene.render.resolution_x=element.orig_width;scene.render.resolution_y=element.orig_height
 row={'file':filename,'frames':strip.frame_duration,'fps':strip.fps,'size':[element.orig_width,element.orig_height],'frames_rendered':[]}
 for fraction in (.18,.52):
  frame=max(1,int(strip.frame_duration*fraction));scene.frame_set(frame);target=OUT/(Path(filename).stem+'-frame-'+str(frame)+'.png')
  scene.render.filepath=str(target);bpy.ops.render.render(write_still=True);row['frames_rendered'].append(str(target))
 collection.remove(strip)
 if filename=='r1-japanese-voice.webm':
  streams=json.loads(subprocess.run([shutil.which('ffprobe'),'-v','error','-show_streams','-of','json',str(OUT/filename)],capture_output=True,text=True,check=True,timeout=20).stdout)['streams']
  audio=next(s for s in streams if s['codec_type']=='audio')
  pcm=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',str(OUT/filename),'-vn','-f','f32le','-acodec','pcm_f32le','-'],capture_output=True,check=True,timeout=20).stdout
  data=np.frombuffer(pcm,dtype='<f4');rate=int(audio['sample_rate']);channels=audio['channels']
  row['audio']={'sample_rate':rate,'channels':channels,'seconds':len(data)/rate/channels,'samples':int(data.size),'rms':float(np.sqrt(np.mean(data.astype(np.float64)**2))),'peak':float(np.max(np.abs(data)))}
  assert row['audio']['rms']>0.001,'recorded_audio_is_silent'
 report.append(row)
(OUT/'video-decode-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('LEVA_ACTUAL_VIDEO_QA',len(report))
