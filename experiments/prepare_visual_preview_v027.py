from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'experiments/preview_host_access_v026.py').read_text('utf8')
source=source.replace('host-access-v026','visual-voice-v027').replace("'physics.js',","'physics.js','camera.js',")
source=source.replace("'Leva', 'text': 'Aku siap menemanimu. Neural Interface dan percakapan kini bisa dilihat bersama dari HP.'","'Leva', 'text': 'Aku siap menemanimu. Tarik jaringan untuk memutar bola, atau buka layar penuh.'")
source=source.replace("messages = [","messages = [\n    {'speaker':'Anda','text':'Leva, bantu aku melanjutkan proyek hari ini.'},")
(root/'experiments/preview_visual_voice_v027.py').write_text(source,encoding='utf8')
print('Prepared isolated preview on 8777')
