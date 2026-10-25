"""Pinned public-model download to D; verify LFS hashes before marking ready."""
import hashlib
import json
import os
from pathlib import Path
os.environ['HF_HOME']='D:/AI/AI Lokal Asisten/AI Models/hf-cache'
from huggingface_hub import HfApi,snapshot_download

root=Path('D:/AI/AI Lokal Asisten/AI Models/Qwen3-ASR-0.6B')
info=HfApi(token=False).model_info('Qwen/Qwen3-ASR-0.6B',files_metadata=True)
snapshot_download(info.id,revision=info.sha,local_dir=root,token=False,
    allow_patterns=['*.json','*.safetensors','*.txt','*.md','LICENSE*'],max_workers=3)
rows=[]
for entry in info.siblings:
    file=root/entry.rfilename
    if not file.is_file():continue
    with file.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    expected=entry.lfs.sha256 if entry.lfs else None
    if expected and expected!=digest:raise ValueError('asr_download_hash_mismatch')
    rows.append({'file':entry.rfilename,'bytes':file.stat().st_size,'sha256':digest,'lfs_verified':bool(expected)})
proof={'model':info.id,'revision':info.sha,'files':rows,'microphone_opened':False}
(root/'leva-download-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps({'model':info.id,'revision':info.sha,'bytes':sum(r['bytes'] for r in rows)}))
