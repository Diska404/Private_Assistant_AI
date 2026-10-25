"""Additional GGUF profiles; text models stay separate from ASR and voice packs."""
from pathlib import Path
import json

MODEL_ROOT=Path(r'D:\AI\AI Lokal Asisten\AI Models')
ALTERNATE=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502\Leva-Personal-Models')
LOCATION_MANIFEST=Path(r'D:\AI\AI Lokal Asisten\Leva\model-locations.json')
PROFILES={
 'qwen3_8b':{'label':'Qwen3 8B · Q4_K_M · non-thinking','folder':'Qwen3-8B','file':'Qwen3-8B-Q4_K_M.gguf','source':'Qwen/Qwen3-8B-GGUF'},
 'stheno8b':{'label':'Stheno v3.2 8B · Q4_K_M','folder':'Stheno-8B','file':'L3-8B-Stheno-v3.2-Q4_K_M.gguf','source':'bartowski/L3-8B-Stheno-v3.2-GGUF'},
 'rpmax12b':{'label':'ArliAI RPMax v1.1 12B · Q4_K_M','folder':'ArliAI-RPMax-12B','file':'Mistral-Nemo-12B-ArliAI-RPMax-v1.1.Q4_K_M.gguf','source':'mradermacher/Mistral-Nemo-12B-ArliAI-RPMax-v1.1-GGUF'}}
PROFILES.update({
 'qwen35_9b':{'label':'Qwen3.5 9B · Q6_K · non-thinking','folder':'Qwen3.5-9B','file':'Qwen3.5-9B-Q6_K.gguf','source':'unsloth/Qwen3.5-9B-GGUF','existing':ALTERNATE.parent/'Qwen3.5-9B-Q6_K.gguf'},
 'hermes4_14b':{'label':'Hermes 4 14B · Q4_K_M','folder':'Hermes-4-14B','file':'NousResearch_Hermes-4-14B-Q4_K_M.gguf','source':'bartowski/NousResearch_Hermes-4-14B-GGUF'},
 'ministral3_8b':{'label':'Ministral 3 8B Instruct · Q4_K_M','folder':'Ministral-3-8B','file':'mistralai_Ministral-3-8B-Instruct-2512-Q4_K_M.gguf','source':'bartowski/mistralai_Ministral-3-8B-Instruct-2512-GGUF'},
 'gemma3_12b':{'label':'Gemma 3 12B IT · Q4_K_M','folder':'Gemma-3-12B','file':'google_gemma-3-12b-it-Q4_K_M.gguf','source':'bartowski/google_gemma-3-12b-it-GGUF'},
 'rocinante12b':{'label':'Rocinante X 12B v1 · Q4_K_M','folder':'Rocinante-X-12B','file':'TheDrummer_Rocinante-X-12B-v1-Q4_K_M.gguf','source':'bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF'}})
# Limited Indonesian evaluation on RTX 5070, 24 Oct 2026; see PERSONAL_MODELS_V033.md.
# All three failed completion of the native agent harness: stay text-only until revalidated.
ROLE_RATINGS={
 'qwen3_8b':{'assistant':'discouraged','chat':'recommended','secret':'recommended'},
 'stheno8b':{'assistant':'discouraged','chat':'balanced','secret':'balanced'},
 'rpmax12b':{'assistant':'discouraged','chat':'balanced','secret':'discouraged'}}
ROLE_RATINGS.update({
 'qwen35_9b':{'assistant':'balanced','chat':'recommended','secret':'recommended'},
 'hermes4_14b':{'assistant':'recommended','chat':'recommended','secret':'balanced'},
 'ministral3_8b':{'assistant':'discouraged','chat':'balanced','secret':'discouraged'},
 'gemma3_12b':{'assistant':'discouraged','chat':'balanced','secret':'recommended'},
 'rocinante12b':{'assistant':'discouraged','chat':'discouraged','secret':'discouraged'}})
NO_AGENT_MODELS={'qwen3_8b','stheno8b','rpmax12b','ministral3_8b','gemma3_12b','rocinante12b'}

def model_path(key):
    profile=PROFILES[key]
    choices=[base/profile['folder']/profile['file'] for base in (MODEL_ROOT,ALTERNATE)]
    if profile.get('existing'):choices.insert(0,Path(profile['existing']))
    try:
        locations=json.loads(LOCATION_MANIFEST.read_text('utf8'))
        if not isinstance(locations,dict):raise ValueError('model_locations_object_required')
        candidate=Path(locations.get(key,''))
        if candidate.is_absolute() and not str(candidate).startswith(('\\\\','//')) and candidate.name==profile['file']:
            choices.insert(0,candidate)
    except (OSError,ValueError,TypeError):pass
    return next((path for path in choices if path.is_file()),choices[0])

def model_rows():
    return {key:(profile['label'],model_path(key)) for key,profile in PROFILES.items()}

def choice_label(key,room):
    label=PROFILES[key]['label'];rating=ROLE_RATINGS[key][room]
    label=({'recommended':'(Direkomendasikan) ','discouraged':'(Tidak Direkomendasikan) ','pending':'(Belum dinilai) '}.get(rating,''))+label
    if room=='assistant' and key in NO_AGENT_MODELS:label+=' · percakapan saja, tanpa agent'
    if not model_path(key).is_file():label+=' · belum tersedia'
    return label

def sampling_for(key,purpose):
    if purpose=='room_route':return {'temperature':0,'top_p':1}
    personal=purpose in ('room_secret','room_personal_chat')
    if key in ('qwen3_8b','qwen35_9b'):return {'temperature':0.7 if personal else 0.3,'top_p':0.8,'top_k':20,'min_p':0}
    if key=='hermes4_14b':return {'temperature':0.6,'top_p':0.95,'top_k':20}
    if key=='ministral3_8b':return {'temperature':0.7 if personal else 0.08,'top_p':0.95}
    return {'temperature':0.8 if personal else 0.3,'top_p':0.95,'min_p':0.05,'repeat_penalty':1.05}
