"""Register only independently acquired, SHA-verified local assets; no preference changes."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from model_registry import TRIALS,REGISTRY,model_path
from inspect_models_v034 import inspect
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
def main():
 acquisition=json.loads((OUT/'acquisition.json').read_text('utf8'))
 if acquisition['status']!='verified':raise RuntimeError('acquisition_not_verified')
 models={};metadata=[]
 for source in acquisition['assets']:
  key=next(k for k,v in TRIALS.items() if v['source']==source['repo'])
  if source.get('local_sha256')!=TRIALS[key]['sha256']:raise RuntimeError('hash_not_verified')
  models[key]={'path':source['path'],'bytes':source['bytes'],'sha256':source['sha256'],'quant':'Q4_K_M','verified':True,
    'context_tested':0,'ratings':{},'source_revision':source['revision'],'tool_policy':'none','experimental':True}
  metadata.append({'id':key,**inspect(Path(source['path']))})
 REGISTRY.write_text(json.dumps({'schema':'leva.model-registry.v1','models':models},indent=2),encoding='utf8')
 for key in models:model_path(key,verify=True)
 (OUT/'gguf-inspection.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
 print(json.dumps({'registered':list(models),'preferences_modified':False,'enabled_by_default':False}))
if __name__=='__main__':main()
