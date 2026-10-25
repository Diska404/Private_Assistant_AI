"""Install four new pinned Q4 models on the user-approved Y drive; reuse Qwen9B."""
import concurrent.futures,json,shutil,time
from pathlib import Path
from prepare_personal_models_v033 import metadata,download
BASE=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502\Leva-Personal-Models')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\model-expansion-v034')
TARGETS=[('hermes4_14b','Hermes-4-14B','bartowski/NousResearch_Hermes-4-14B-GGUF','NousResearch_Hermes-4-14B-Q4_K_M.gguf'),
 ('ministral3_8b','Ministral-3-8B','bartowski/mistralai_Ministral-3-8B-Instruct-2512-GGUF','mistralai_Ministral-3-8B-Instruct-2512-Q4_K_M.gguf'),
 ('gemma3_12b','Gemma-3-12B','bartowski/google_gemma-3-12b-it-GGUF','google_gemma-3-12b-it-Q4_K_M.gguf'),
 ('rocinante12b','Rocinante-X-12B','bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF','TheDrummer_Rocinante-X-12B-v1-Q4_K_M.gguf')]
if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);BASE.mkdir(parents=True,exist_ok=True)
    rows=list(concurrent.futures.ThreadPoolExecutor(4).map(metadata,TARGETS))
    for row in rows:row['path']=str(BASE/row['folder']/row['name'])
    needed=sum(row['bytes'] for row in rows if not Path(row['path']).is_file())
    if shutil.disk_usage(BASE).free<needed+3*1024**3:raise RuntimeError('insufficient_y_storage')
    (OUT/'download-plan.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    locations=Path(r'D:\AI\AI Lokal Asisten\Leva\model-locations.json')
    try:values=json.loads(locations.read_text('utf8'))
    except (OSError,ValueError):values={}
    values.update({row['key']:row['path'] for row in rows})
    locations.write_text(json.dumps(values,indent=2),encoding='utf8')
    print(json.dumps({'planned_bytes':needed,'root':str(BASE)}),flush=True)
    started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(4) as pool:completed=list(pool.map(download,rows))
    existing=json.loads((OUT/'existing-models-verified.json').read_text('utf8'))
    (OUT/'downloads.json').write_text(json.dumps({'files':completed,'reused':[r for r in existing if 'Qwen3.5-9B' in r['path']],'seconds':round(time.monotonic()-started,2)},indent=2),encoding='utf8')
