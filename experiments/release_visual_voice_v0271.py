from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
for name in ['app/hud_view.py','app/web_host.py','app/leva_web/index.html']:
 p=root/name;s=p.read_text('utf8').replace('0.27.0','0.27.1');p.write_text(s,encoding='utf8')
p=root/'LEVA_PROJECT.json';data=json.loads(p.read_text('utf8'));data['version']='0.27.1';data['stage']='Visual orbit/fullscreen, flexible chat and synchronized avatar deployed. Long Higgs sentence queue and WebRTC AEC3 verified; remote audio survives automatic model release. Native SSE receiver/player is isolated and opt-in: two long language runs completed, but a prior native GGML assertion prevents enabling it by default. Physical acoustic validation remains pending.';p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for source,dest in [('verify_package_v027.py','verify_package_v0271.py'),('deploy_visual_voice_v027.py','deploy_visual_voice_v0271.py')]:
 s=(root/'experiments'/source).read_text('utf8').replace('0.27.0','0.27.1').replace("'app_full':469","'app_full':475").replace("'comfy_reliability':8","'visual_voice':6,'speech_stream':5")
 if source.startswith('deploy_'):s=s.replace('before-visual-voice-v027-','before-visual-voice-v0271-').replace("program/0.26.1/Leva/Leva.exe","program/0.27.0/Leva/Leva.exe")
 (root/'experiments'/dest).write_text(s,encoding='utf8')
print('Prepared final 0.27.1 release')
