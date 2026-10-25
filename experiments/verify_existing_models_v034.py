"""Verify user's existing Flash-Next shards and Qwen9B against publisher LFS hashes."""
import hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\model-expansion-v034');OUT.mkdir(parents=True,exist_ok=True)
records=[]
for repo,names in [('unsloth/Qwen3.5-9B-GGUF',['Qwen3.5-9B-Q6_K.gguf']),('unsloth/Qwen3.8-Flash-Next-GGUF',[f'UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-{i:05d}-of-00003.gguf' for i in range(1,4)])]:
 with urllib.request.urlopen('https://huggingface.co/api/models/'+repo+'?blobs=true',timeout=35) as r:meta=json.load(r)
 for name in names:
  source=next(row for row in meta['siblings'] if row['rfilename']==name);path=ROOT/Path(name).name;started=time.monotonic()
  if path.stat().st_size!=source['lfs']['size']:raise RuntimeError('size_mismatch_'+path.name)
  with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
  record={'repo':repo,'revision':meta['sha'],'source_name':name,'path':str(path),'bytes':path.stat().st_size,'sha256':actual,'expected_sha256':source['lfs']['sha256'],'verified':actual==source['lfs']['sha256'],'seconds':round(time.monotonic()-started,2)}
  records.append(record);(OUT/'existing-models-verified.json').write_text(json.dumps(records,indent=2),encoding='utf8');print(json.dumps({'name':path.name,'verified':record['verified'],'seconds':record['seconds']}),flush=True)
  if not record['verified']:raise RuntimeError('sha256_mismatch_'+path.name)
