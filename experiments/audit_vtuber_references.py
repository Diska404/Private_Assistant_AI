"""Fetch pinned public documentation/licenses only. Never execute third-party files."""
import json
from pathlib import Path
import urllib.request

OUT=Path(r'D:\AI\AI Lokal Asisten\Github\VTuber-reference-audit\20261024')
REPOS=['moeru-ai/airi','Open-LLM-VTuber/Open-LLM-VTuber','pixiv/three-vrm']
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Leva-reference-audit','Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()
def main():
 OUT.mkdir(parents=True,exist_ok=True);rows=[]
 for repo in REPOS:
  meta=json.loads(get('https://api.github.com/repos/'+repo));branch=meta['default_branch']
  commit=json.loads(get('https://api.github.com/repos/'+repo+'/commits/'+branch))['sha']
  tree=json.loads(get('https://api.github.com/repos/'+repo+'/git/trees/'+commit+'?recursive=1'))
  folder=OUT/repo.replace('/','--');folder.mkdir(exist_ok=True)
  (folder/'tree.json').write_text(json.dumps(tree,indent=2),encoding='utf8')
  names=[v['path'] for v in tree['tree'] if v['type']=='blob'];selected=[n for n in names if n in ('README.md','LICENSE','LICENSE.md','LICENSE.txt','package.json','pyproject.toml')]
  for name in selected:(folder/name).write_bytes(get('https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+name))
  rows.append({'repo':repo,'revision':commit,'default_branch':branch,'license':meta.get('license'),
    'downloaded_docs':selected,'code_executed':False,'full_framework_benchmarked':False})
  print(repo+' documentation pinned',flush=True)
 (OUT/'manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
if __name__=='__main__':main()
