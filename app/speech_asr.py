"""On-demand Qwen ASR, separate from the agent and TTS. No cloud or microphone."""
import os
from pathlib import Path
import time

MODELS = Path('D:/AI/AI Lokal Asisten/AI Models')
ASR_PYTHON = Path('D:/AI/AI Lokal Asisten/Leva/environments/speech-asr-qwen313/python.exe')
MODEL_PATHS = {'qwen_asr_06b': MODELS/'Qwen3-ASR-0.6B', 'qwen_asr_17b': MODELS/'Qwen3-ASR-1.7B'}

def ready(model):
    folder = MODEL_PATHS.get(model)
    return bool(folder and ASR_PYTHON.is_file() and (folder/'config.json').is_file()
                and any(folder.glob('*.safetensors')) and (folder/'leva-download-proof.json').is_file())

class SpeechASR:
    def __init__(self, model='qwen_asr_06b', gpu='auto',max_tokens=256):
        if model not in MODEL_PATHS or not ready(model): raise ValueError('speech_asr_assets_missing')
        from speech_resources import gpu_rows,select_asr_devices
        self.devices=select_asr_devices(gpu_rows(),model,gpu)
        self.gpu={'uuid':','.join(r['uuid'] for r in self.devices),
                  'name':' + '.join(r['name'] for r in self.devices)}
        self.requested_gpu=gpu
        # Must run before importing torch. This module is used only by a dedicated worker.
        os.environ.update(CUDA_VISIBLE_DEVICES=self.gpu['uuid'], HF_HUB_OFFLINE='1',
                          TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
        import torch
        torch.set_num_threads(4)
        from qwen_asr import Qwen3ASRModel
        start=time.monotonic()
        device_map={'thinker.audio_tower':0,'thinker.model':1,'thinker.lm_head':1} if len(self.devices)==2 else 'cuda:0'
        self.engine=Qwen3ASRModel.from_pretrained(str(MODEL_PATHS[model]),dtype=torch.float16,
            device_map=device_map,max_inference_batch_size=1,max_new_tokens=max(256,min(1024,int(max_tokens))),
            attn_implementation='sdpa',local_files_only=True)
        self.model=model;self.load_ms=round((time.monotonic()-start)*1000,1)
        self.parameter_counts={}
        for parameter in self.engine.model.parameters():
            name=str(parameter.device)
            self.parameter_counts[name]=self.parameter_counts.get(name,0)+parameter.numel()
        expected={f'cuda:{i}' for i in range(len(self.devices))}
        if set(self.parameter_counts)!=expected:raise RuntimeError('asr_device_placement_mismatch')

    def transcribe(self,samples,language='id',context=''):
        if language not in ('id','ja','auto'): raise ValueError('unsupported_asr_language')
        import torch
        # CUDA events around real module forwards prove computation, rather than
        # allocating dummy tensors or inferring it from other apps' GPU usage.
        execution={};handles=[];events={}
        modules=[self.engine.model.thinker.audio_tower,self.engine.model.thinker.model] if len(self.devices)==2 else [self.engine.model.thinker]
        for device,module in enumerate(modules):
            def before(mod,args,index=device):
                if index in events:return
                with torch.cuda.device(index):
                    begin=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
                    begin.record();events[index]=[begin,end,False]
            def after(mod,args,output,index=device):
                if index in events and not events[index][2]:
                    with torch.cuda.device(index):events[index][1].record()
                    events[index][2]=True
            handles.extend([module.register_forward_pre_hook(before),module.register_forward_hook(after)])
        start=time.monotonic()
        try:
            with torch.inference_mode():
                result=self.engine.transcribe(audio=(samples,16000),
                    language={'id':'Indonesian','ja':'Japanese','auto':None}[language],
                    context=context[:600],return_time_stamps=False)
            for index in range(len(self.devices)):
                torch.cuda.synchronize(index)
                pair=events.get(index)
                if not pair or not pair[2]:raise RuntimeError('asr_device_execution_missing')
                execution[str(index)]=round(pair[0].elapsed_time(pair[1]),4)
        finally:
            for handle in handles:handle.remove()
        return {'text':result[0].text.strip(),'language':result[0].language,'model':self.model,
                'gpu_name':self.gpu['name'],'asr_ms':round((time.monotonic()-start)*1000,1),
                'gpu_devices':self.devices,'requested_gpu':self.requested_gpu,'parameter_counts':self.parameter_counts,
                'module_forward_cuda_ms':execution,'device_map':{k:str(v) for k,v in getattr(self.engine.model,'hf_device_map',{}).items()},
                'executed_gpu_names':[torch.cuda.get_device_name(i) for i in range(len(self.devices))],
                'streaming':False}

def normalized_transcript(text):
    """Formatting only: never invent names, change negation/times, or expand permissions."""
    return ' '.join(text.split()) if isinstance(text,str) else ''
