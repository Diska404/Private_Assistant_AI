import urllib.request,json
from pathlib import Path
root=Path('D:/AI/AI Lokal Asisten/Github/audio-cpp-stream-review');root.mkdir(parents=True,exist_ok=True)
url='https://api.github.com/repos/0xShug0/audio.cpp/git/trees/main?recursive=1'
with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Leva-local-development'}),timeout=20) as r:tree=json.load(r)
paths=[e['path'] for e in tree['tree'] if e['path'].endswith(('.cpp','.md')) and ('server' in e['path'])]
print('\n'.join(paths))
for path in paths:
 if path.endswith('.cpp') and ('server' in path) and len(paths)<80:
  with urllib.request.urlopen('https://raw.githubusercontent.com/0xShug0/audio.cpp/main/'+path,timeout=20) as r:raw=r.read(2*1024*1024)
  if b'speech.audio.delta' in raw or b'streaming speech currently' in raw:
   file=root/path.replace('/','_');file.write_bytes(raw);print('SAVED',file)
