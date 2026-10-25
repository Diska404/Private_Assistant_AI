"""Bounded recovery of local capture workers; never switches models or GPUs."""
import time

class MicRecovery:
    DELAYS=(5,15,45)
    def __init__(self):self.reset()
    def reset(self):self.failures=0;self.retry_at=None;self.ready_since=None
    def failed(self,retryable=True,now=None):
        now=time.monotonic() if now is None else now
        self.failures+=1;self.ready_since=None
        self.retry_at=now+self.DELAYS[self.failures-1] if retryable and self.failures<=len(self.DELAYS) else None
    def ready(self,now=None):self.ready_since=time.monotonic() if now is None else now
    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        if self.ready_since is not None and now-self.ready_since>=60:self.reset()
    def claim(self,now=None):
        now=time.monotonic() if now is None else now
        if self.retry_at is None or now<self.retry_at:return False
        self.retry_at=None;return True
    def remaining(self,now=None):
        now=time.monotonic() if now is None else now
        return None if self.retry_at is None else max(0,int(self.retry_at-now+.999))

def failure_details(error,phase='bootstrap'):
    """Keep technical context; no waveform or transcript is included."""
    winerror=getattr(error,'winerror',None);errno=getattr(error,'errno',None);detail=str(error)[:800]
    code='local_microphone_'+type(error).__name__;retryable=True
    message='Pendengar gagal pada tahap '+phase+'. Tekan Coba ulang mic jika masih berhenti.'
    if winerror in (8,14,1455):
        code='microphone_windows_memory';message='Windows tidak menyediakan cukup memori/commit untuk runtime suara.'
    elif winerror in (126,127,193,1114):
        code='microphone_runtime_dll';message='Library runtime suara gagal dimuat. Rincian tersimpan di diagnostik lokal.'
    elif isinstance(error,ValueError):
        code=detail
        retryable=code in ('microphone_not_found','speech_gpu_headroom_unavailable','speech_dual_gpu_headroom_unavailable')
        message={'microphone_not_found':'Mikrofon terpilih tidak ditemukan; periksa sambungan dan pilihan perangkat.',
                 'speech_asr_assets_missing':'Bobot/runtime ASR belum lengkap.',
                 'speech_dual_gpu_missing':'Dual GPU membutuhkan kedua kartu yang dipilih.',
                 'speech_gpu_headroom_unavailable':'VRAM kartu yang dipilih belum cukup untuk ASR.',
                 'speech_dual_gpu_headroom_unavailable':'VRAM salah satu kartu Dual belum cukup untuk ASR.'}.get(code,detail[:180])
    elif isinstance(error,OSError):
        message='Windows gagal memulai runtime suara'+(' (kode '+str(winerror or errno)+')' if winerror or errno else '')+'.'
    elif type(error).__name__=='PortAudioError':
        code='microphone_capture_error';message='Perangkat audio gagal dibuka; periksa mikrofon dan aplikasi audio yang sedang memakainya.'
    return {'kind':'error','code':code,'message':message,'phase':phase,'retryable':retryable,
            'error_type':type(error).__name__,'winerror':winerror,'errno':errno,'detail':detail}
