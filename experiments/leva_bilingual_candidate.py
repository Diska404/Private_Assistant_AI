"""File-only Indonesian/Japanese Leva candidate comparison on RTX 4050.

Uses pinned general models plus user-supplied reference audio; no training,
microphone, playback, uploads, or changes to the running assistant.
"""
import argparse
import csv
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from leva_openvoice_candidate import audio_info, sha

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r'D:\AI\AI Lokal Asisten\Leva')
MODELS = Path(r'D:\AI\AI Lokal Asisten\AI Models')
OUT = DATA / 'verification/leva-bilingual-v3'
PROFILE = MODELS / 'Leva-GFL2/SeedVC-bilingual-candidate-v3'
SOURCE = Path(r'D:\AI\AI Lokal Asisten\Model Suara Leva\SWATJudge')
JP = [
    ('01_profil', '指揮官、おかえり。クロームは、どのプロフィールで開けばいい？', 'Komandan, selamat datang kembali. Chrome mau dibuka dengan profil mana?'),
    ('02_menunggu', 'わかった。ここで待っているわ。必要になったら、呼んでちょうだい。', 'Baik, aku menunggu di sini. Panggil aku saat kamu membutuhkanku.'),
    ('03_istirahat', 'もう朝の四時よ。まだ続ける？それとも、少し休む？', 'Sudah pukul empat pagi. Mau melanjutkan, atau beristirahat sebentar?'),
]

def setup():
    OUT.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
        HF_HOME=str(DATA/'cache/hf-leva-bilingual'), HF_HUB_CACHE=str(DATA/'cache/hf-leva-bilingual/hub'),
        NUMBA_CACHE_DIR=str(DATA/'cache/numba-openvoice'), OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4',
        TEMP=str(OUT), TMP=str(OUT), PYTHONIOENCODING='utf-8')
    listing = subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name','--format=csv,noheader'],text=True)
    uuid = [line.split(',',1)[0].strip() for line in listing.splitlines() if 'RTX 4050' in line]
    if len(uuid)!=1: raise RuntimeError('expected_one_rtx4050')
    os.environ['CUDA_VISIBLE_DEVICES']=uuid[0]
    manifest=json.loads((MODELS/'Leva-Bilingual-v3/manifest.json').read_text('utf-8'))
    for row in manifest['files']:
        if sha(row['path'])!=row['sha256']: raise RuntimeError('asset_hash_mismatch: '+row['name'])
    import torch
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or 'RTX 4050' not in torch.cuda.get_device_name(0):
        raise RuntimeError('rtx4050_unavailable')
    return manifest, torch, uuid[0]

def save(proof):
    (OUT/'proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')

def bases():
    manifest,torch,uuid=setup()
    import numpy as np
    import soundfile as sf
    import librosa
    from kokoro import KModel
    from misaki.ja import JAG2P
    proof={'status':'preparing_sources','engine':'Seed-VC Whisper-small general converter',
           'dedicated_leva_checkpoint_trained':False,'human_similarity_validated':False,
           'microphone_opened':False,'speaker_opened':False,'audio_uploaded':False,
           'manifest':str(MODELS/'Leva-Bilingual-v3/manifest.json'),'gpu_name':torch.cuda.get_device_name(0),
           'gpu_uuid':uuid,'torch_version':torch.__version__,'cuda_runtime':torch.version.cuda,
           'seed_source_commit':manifest['seed_source_commit'],'references':[], 'prompts':[], 'base':[], 'converted':[],
           'voice_identity_note':'Nexus mod references supplied by user; not authenticated original game recordings',
           'rights_note':'private local evaluation of user-supplied files; no redistribution license claimed'}
    subtitles={r['Key']:r['Dialogue'] for r in csv.DictReader((SOURCE/'sub_ja.csv').open(encoding='utf-8-sig'))}
    by_id={}
    for ident in ('PanicRoom04_A_01','PanicRoom04_A_02','PanicRoom06_B_01'):
        original=SOURCE/(ident+'.ogg')
        before=sha(original)
        raw,sr=sf.read(original,dtype='float32')
        raw,interval=librosa.effects.trim(raw,top_db=35)
        raw=librosa.resample(raw,orig_sr=sr,target_sr=22050)
        output=OUT/(ident+'_reference.wav')
        sf.write(output,raw,22050,subtype='PCM_16')
        by_id[ident]=raw
        proof['references'].append({'id':ident,'text':subtitles[ident],'original_path':str(original),
            'original_sha256':before,'trim_samples':[int(v) for v in interval],**audio_info(output)})
    for label,ids in (('A',['PanicRoom04_A_02']),('B',['PanicRoom04_A_01','PanicRoom06_B_01'])):
        pieces=[]
        for ident in ids:
            raw=by_id[ident]
            raw=raw/max(float(np.abs(raw).max()),1e-6)*0.7
            if pieces: pieces.append(np.zeros(int(.18*22050),dtype='float32'))
            pieces.append(raw)
        path=OUT/f'reference_{label}.wav'
        sf.write(path,np.concatenate(pieces),22050,subtype='PCM_16')
        proof['prompts'].append({'id':label,'source_ids':ids,'text':' '.join(subtitles[i] for i in ids),**audio_info(path)})
        shutil.copyfile(path,PROFILE/path.name)
    old=json.loads((DATA/'verification/leva-openvoice-candidate/proof.json').read_text('utf-8'))
    for row in old['base']:
        path=OUT/('id_'+row['id']+'_piper.wav')
        shutil.copyfile(row['path'],path)
        if sha(path)!=row['sha256']: raise RuntimeError('base_copy_mismatch')
        proof['base'].append({**row,'id':'id_'+row['id'],'language':'id','base_engine':'Piper ID news_tts',
                              'reused_from_v1':True,**audio_info(path)})
    save(proof)
    kokoro_dir=Path(manifest['repositories']['hexgrad/Kokoro-82M']['local'])
    started=time.perf_counter()
    model=KModel(repo_id='hexgrad/Kokoro-82M',config=str(kokoro_dir/'config.json'),model=str(kokoro_dir/'kokoro-v1_0.pth')).to('cuda:0').eval()
    g2p=JAG2P(version='cutlet')
    proof['japanese_tts_load_seconds']=round(time.perf_counter()-started,4)
    for voice_name in ('jf_alpha','jf_nezumi'):
        voice=torch.load(kokoro_dir/'voices'/f'{voice_name}.pt',map_location='cpu',weights_only=True)
        for ident,text,translation in JP:
            pronunciation_text=text.replace('四時','よじ')
            phonemes,tokens=g2p(pronunciation_text)
            if '❓' in phonemes or len(phonemes)>490: raise RuntimeError('unsupported_phonemes')
            path=OUT/f'jp_{ident}_{voice_name}_base.wav'
            torch.manual_seed(20261019)
            started=time.perf_counter()
            with torch.inference_mode(): audio=model(phonemes,voice[len(phonemes)-1],speed=1.0).numpy()
            torch.cuda.synchronize()
            elapsed=time.perf_counter()-started
            sf.write(path,audio,24000,subtype='PCM_16')
            proof['base'].append({'id':f'jp_{ident}_{voice_name}','language':'ja','text':text,'translation_id':translation,
                'base_engine':'Kokoro-82M','base_voice':voice_name,'g2p':'misaki 0.9.4 cutlet / unidic-lite',
                'phonemes':phonemes,'pronunciation_text':pronunciation_text,'synthesis_seconds':round(elapsed,4),**audio_info(path)})
            save(proof)
            print(json.dumps({'base':path.name,'seconds':round(elapsed,3)}),flush=True)
    proof['status']='sources_completed'
    save(proof)

def fix_time_reading():
    """Regenerate only the two time sources; preserve superseded artifacts."""
    manifest,torch,uuid=setup()
    import soundfile as sf
    from kokoro import KModel
    from misaki.ja import JAG2P
    proof=json.loads((OUT/'proof.json').read_text('utf-8'))
    folder=OUT/'revisions/before-time-reading-fix'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'proof-before-fix.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    kdir=Path(manifest['repositories']['hexgrad/Kokoro-82M']['local'])
    model=KModel(repo_id='hexgrad/Kokoro-82M',config=str(kdir/'config.json'),model=str(kdir/'kokoro-v1_0.pth')).to('cuda:0').eval()
    g2p=JAG2P(version='cutlet')
    changed=set()
    for row in proof['base']:
        if row['language']!='ja' or '03_istirahat' not in row['id']: continue
        if row.get('pronunciation_text')==row['text'].replace('四時','よじ'): continue
        shutil.copyfile(row['path'],folder/Path(row['path']).name)
        pronunciation_text=row['text'].replace('四時','よじ')
        phonemes,_=g2p(pronunciation_text)
        voice=torch.load(kdir/'voices'/(row['base_voice']+'.pt'),weights_only=True,map_location='cpu')
        started=time.perf_counter()
        torch.manual_seed(20261019)
        with torch.inference_mode(): audio=model(phonemes,voice[len(phonemes)-1],speed=1.0).numpy()
        torch.cuda.synchronize()
        elapsed=time.perf_counter()-started
        sf.write(row['path'],audio,24000,subtype='PCM_16')
        row.update(phonemes=phonemes,pronunciation_text=pronunciation_text,synthesis_seconds=round(elapsed,4),**audio_info(row['path']))
        changed.add(row['id'])
    for row in proof['converted']:
        if row['base_id'] in changed: shutil.copyfile(row['path'],folder/Path(row['path']).name)
    proof['converted']=[row for row in proof['converted'] if row['base_id'] not in changed]
    proof['pronunciation_fix']={'term':'四時','reading':'よじ / yoji','reason':'default G2P rendered yonji; explicit standard time reading',
        'changed_base_ids':sorted(changed),'previous_artifacts':str(folder)}
    proof['status']='time_sources_corrected_pending_reconversion'
    save(proof)

def convert():
    manifest,torch,uuid=setup()
    import yaml
    import soundfile as sf
    import numpy as np
    proof=json.loads((OUT/'proof.json').read_text('utf-8'))
    vendor=Path(manifest['seed_vendor'])
    sys.path.insert(0,str(vendor))
    import inference as engine
    local={repo:Path(meta['local']) for repo,meta in manifest['repositories'].items()}
    def local_asset(repo,model_filename='pytorch_model.bin',config_filename=None):
        model_path=str(local[repo]/model_filename)
        return (model_path,str(local[repo]/config_filename)) if config_filename else model_path
    engine.load_custom_model_from_hf=local_asset
    # Match every parameter strictly; do not silently drop mismatching tensors.
    def strict_checkpoint(models,optimizer,path,**kwargs):
        state=torch.load(path,map_location='cpu',weights_only=True)
        proof['checkpoint_keys']=sorted(state.keys())
        for key in models:
            parameters={name.removeprefix('module.'):value for name,value in state['net'][key].items()}
            expected=models[key].state_dict()
            # Upstream added deterministic timestep-frequency buffers after this
            # checkpoint, and stopped creating the unused f0 table for VC.
            # Migrate only these known nonlearned/unused entries; fail on others.
            if key=='cfm':
                restored=[]
                for name in ('estimator.t_embedder.freqs','estimator.t_embedder2.freqs'):
                    if name not in parameters and name in expected:
                        parameters[name]=expected[name]
                        restored.append(name)
                name='estimator.input_pos'
                if name in parameters and parameters[name].shape!=expected[name].shape:
                    original=parameters[name]
                    if not torch.equal(original,torch.arange(original.numel(),dtype=original.dtype)):
                        raise RuntimeError('unexpected_non_arange_position_buffer')
                    parameters[name]=expected[name]
                    restored.append(name)
                ignored=[]
                if not args.f0_condition and 'estimator.f0_embedder.weight' not in expected:
                    if parameters.pop('estimator.f0_embedder.weight',None) is not None:
                        ignored.append('estimator.f0_embedder.weight')
                proof['checkpoint_migration']={'deterministic_buffers_initialized_from_code':restored,'unused_legacy_f0_table_omitted':ignored}
            missing=sorted(set(expected)-set(parameters))
            unexpected=sorted(set(parameters)-set(expected))
            if missing or unexpected:
                raise RuntimeError(json.dumps({'module':key,'missing':missing,'unexpected':unexpected}))
            models[key].load_state_dict(parameters,strict=True)
        proof['seed_checkpoint_strict_after_known_format_migration']=True
        return models,optimizer,0,0
    engine.load_checkpoint=strict_checkpoint
    config_name='config_dit_mel_seed_uvit_whisper_small_wavenet.yml'
    config=yaml.safe_load((local['Plachta/Seed-VC']/config_name).read_text('utf-8'))
    config['model_params']['vocoder']['name']=str(local['nvidia/bigvgan_v2_22khz_80band_256x'])
    config['model_params']['speech_tokenizer']['name']=str(local['openai/whisper-small'])
    config_path=PROFILE/'local_config.yml'
    config_path.write_text(yaml.safe_dump(config),encoding='utf-8')
    args=argparse.Namespace(f0_condition=False,fp16=True,
         checkpoint=str(local['Plachta/Seed-VC']/'DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth'),
         config=str(config_path),auto_f0_adjust=False,semi_tone_shift=0,length_adjust=1.0,
         diffusion_steps=30,inference_cfg_rate=0.7,source=None,target=None,output=str(OUT/'raw'))
    started=time.perf_counter()
    loaded=engine.load_models(args)
    torch.cuda.synchronize()
    elapsed_load=round(time.perf_counter()-started,4)
    if 'seed_load_history_seconds' not in proof:
        proof['seed_load_history_seconds']=[proof['seed_load_seconds']] if 'seed_load_seconds' in proof else []
    proof['seed_load_history_seconds'].append(elapsed_load)
    proof['seed_load_seconds']=elapsed_load
    proof['seed_vendor_patch']='optional DAC import deferred until vector_quantize=True; explicit sampling_rate=16000 in Whisper feature extraction (same as processor default)'
    engine.load_models=lambda _:loaded
    proof['status']='converting'
    save(proof)
    new_in_process=0
    for base in proof['base']:
        for prompt in proof['prompts']:
            ident=base['id']+'_seed_'+prompt['id']
            if any(row['id']==ident for row in proof['converted']): continue
            args.source=base['path']; args.target=prompt['path']
            torch.manual_seed(20261019)
            torch.cuda.reset_peak_memory_stats()
            started=time.perf_counter()
            with torch.inference_mode(): engine.main(args)
            torch.cuda.synchronize()
            elapsed=time.perf_counter()-started
            raw_path=Path(args.output)/f'vc_{Path(args.source).stem}_{Path(args.target).stem}_1.0_30_0.7.wav'
            target=OUT/(ident+'.wav')
            shutil.copyfile(raw_path,target)
            details=audio_info(target)
            if abs(details['duration_seconds']-base['duration_seconds'])>.3: raise RuntimeError('duration_mismatch')
            proof['converted'].append({'id':ident,'base_id':base['id'],'language':base['language'],'text':base['text'],
                'translation_id':base.get('translation_id'),'reference_id':prompt['id'],'engine':'Seed-VC',
                'diffusion_steps':30,'cfg':0.7,'length_adjust':1.0,'pitch_shift':0,
                'conversion_seconds':round(elapsed,4),'real_time_factor':round(elapsed/details['duration_seconds'],4),
                'first_conversion_in_process':new_in_process==0,
                'torch_peak_allocated_mib':round(torch.cuda.max_memory_allocated()/1048576,2),
                'torch_peak_reserved_mib':round(torch.cuda.max_memory_reserved()/1048576,2),**details})
            save(proof)
            new_in_process+=1
            print(json.dumps({'converted':ident,'seconds':round(elapsed,3),'audio_seconds':details['duration_seconds']}),flush=True)
    for row in proof['references']:
        if sha(row['original_path'])!=row['original_sha256']: raise RuntimeError('source_modified')
    proof['source_hashes_unchanged']=True
    proof['status']='file_inference_completed_requires_listening'
    save(proof)
    (PROFILE/'profile.json').write_text(json.dumps({'id':'leva_seedvc_bilingual_candidate_v3','status':'experimental_not_default',
        'engine':'Seed-VC','base_manifest':proof['manifest'],'prompts':proof['prompts'],'proof':str(OUT/'proof.json'),
        'dedicated_leva_checkpoint_trained':False,'human_similarity_validated':False,'streaming_verified':False},indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['bases','convert','fix-time'],required=True)
    args=parser.parse_args()
    {'bases':bases,'convert':convert,'fix-time':fix_time_reading}[args.stage]()
