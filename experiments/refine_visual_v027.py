from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'app/leva_web/graph.js';s=p.read_text('utf8').replace('(n.z||0)*scale,this.camera.yaw','(n.z||0)*scale/(this.mode===\'neural\'?.6:1),this.camera.yaw');p.write_text(s,encoding='utf8')
# Keep display versions consistent; archived reports and packages remain historical.
for name in ['app/hud_view.py','app/web_host.py']:
 p=root/name;s=p.read_text('utf8').replace('0.26.1','0.27.0');p.write_text(s,encoding='utf8')
print('Camera sphere proportions and display versions updated')
