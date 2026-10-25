"""Shared desktop/web settings transaction and effective ASR/agent placements."""
from preferences import validate_setting
from speech_resources import GPU_CHOICES,ASR_CHOICES,AGENT_CHOICES,AGENT_GPU_CHOICES,pipeline_gpu,agent_mode
from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,route_spec

FIELDS=('asr_model','asr_gpu','asr_language','agent_local_model','agent_gpu','agent_provider')
AGENT_ROUTES={value:value for value in dict.fromkeys(SINGLE_CHOICES+DUAL_CHOICES)}
INPUT_MODELS={k:v for k,v in ASR_CHOICES.items() if k!='whisper_cpu'}
LANGUAGES={'id':'Indonesia','ja':'日本語','auto':'Deteksi otomatis'}

def validate_pipeline_settings(values):
    if not isinstance(values,dict) or not values or set(values)-set(FIELDS):raise ValueError('invalid_pipeline_settings')
    for key,value in values.items():validate_setting(key,value)
    if values.get('asr_model')=='whisper_cpu':raise ValueError('Pilih Qwen3-ASR untuk input GPU.')
    return dict(values)

def apply_pipeline_settings(main,values):
    values=validate_pipeline_settings(values)
    if main.busy:raise ValueError('Tunggu tugas aktif selesai sebelum mengganti model/GPU.')
    host=getattr(main,'_web_host',None)
    if host and host.bridge.speech.pending():raise ValueError('Tunggu transkrip HP selesai sebelum mengganti model/GPU.')
    model=values.get('asr_model',main.preferences.get('asr_model'))
    if model!='whisper_cpu':
        from speech_asr import ready
        if not ready(model):raise ValueError('Bobot/runtime ASR tersebut belum tersedia. Pengaturan tidak diubah.')
    if 'agent_provider' in values:values={**values,'agent_gpu':'auto'}
    main.preferences.set_many({**values,'separate_agent':True})
    main.local_mic.stop();main.local_mic_failed=False
    if hasattr(main,'mic_recovery'):main.mic_recovery.reset()
    main.cancel_inference();main.stop_reply_voice()
    main.audio_resource_hold=False
    main.local_notice='Pengaturan input suara diperbarui · memuat sesuai GPU pilihan'
    if hasattr(main,'ensure_local_mic'):main.root.after(0,main.ensure_local_mic)
    return {key:main.preferences.get(key) for key in FIELDS}

def configuration_snapshot(preferences,route):
    values={key:preferences.get(key) for key in FIELDS}
    disabled=route['gpu']=='none'
    effective_asr='none' if disabled else pipeline_gpu(route,'asr',values['asr_gpu'])
    agent_route=route_spec(values['agent_provider'])
    effective_agent=agent_mode(agent_route,values['agent_gpu'])
    gpu_names={'rtx4050':'RTX 4050','rtx5070':'RTX 5070','dual':'Dual GPU','none':'nonaktif',None:'nonaktif','gpu4050':'RTX 4050','gpu5070':'RTX 5070'}
    asr_name=ASR_CHOICES[values['asr_model']].split(' · ')[0]
    return {'values':values,'choices':{'asr_model':INPUT_MODELS,'asr_gpu':GPU_CHOICES,'asr_language':LANGUAGES,'agent_local_model':AGENT_CHOICES,'agent_gpu':AGENT_GPU_CHOICES,'agent_provider':AGENT_ROUTES},
        'effective':{'asr_gpu':effective_asr,'agent_mode':effective_agent},
        'summary':'Input: '+asr_name+' · '+gpu_names[effective_asr]+' | Agent: '+AGENT_CHOICES[values['agent_local_model']]+' · '+gpu_names[effective_agent]}
