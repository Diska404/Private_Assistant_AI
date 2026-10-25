"""Local input telemetry; dBFS describes captured level, not hardware microphone gain."""
from array import array
from datetime import datetime
import math
import time

FLOOR_DB=-80.0

def dbfs(amplitude):
    return max(FLOOR_DB,min(0.0,20*math.log10(max(1e-8,float(amplitude)))))

def pcm_measurements(pcm):
    samples=array('h');samples.frombytes(pcm[:len(pcm)//2*2])
    if not samples:return {'rms':0.0,'peak':0.0,'clipped':False}
    return {'rms':math.sqrt(sum(v*v for v in samples)/len(samples))/32768,
            'peak':max(abs(v) for v in samples)/32768,
            'clipped':any(abs(v)>=32760 for v in samples)}

class MicTelemetry:
    def __init__(self):
        self.text='';self.reason='';self.heard_at='';self.asr_ms=0
        self.reset_capture()

    def reset_capture(self):
        self.open=False;self.phase='off';self.rms=self.peak=0.0
        self.threshold=.009;self.noise=.001;self.voiced=False;self.echo=False;self.awake=False;self.awake_remaining=0
        self.last_meter=None;self.clipped_until=0;self.device='';self.error=''
        self.echo_backend='';self.echo_correlation=0;self.clean_rms=0;self.reference_resets=0

    def clear_text(self):self.text='';self.reason='';self.heard_at='';self.asr_ms=0

    def apply(self,event,now=None):
        now=time.monotonic() if now is None else now;kind=event.get('kind')
        if kind=='local_meter':
            self.rms=max(0.0,float(event.get('rms',0)));self.peak=max(0.0,float(event.get('peak',0)))
            self.threshold=float(event.get('threshold',.009));self.noise=float(event.get('noise',.001))
            self.voiced=bool(event.get('voiced',False));self.echo=bool(event.get('echo_rejected',False))
            self.awake=bool(event.get('awake',False))
            self.awake_remaining=event.get('awake_remaining',0)
            self.phase=event.get('phase','listening');self.last_meter=now
            self.echo_backend=str(event.get('echo_backend',''));self.echo_correlation=event.get('echo_correlation',0)
            self.clean_rms=event.get('clean_rms',0);self.reference_resets=event.get('reference_resets',0)
            if event.get('clipped'):self.clipped_until=now+1
        elif kind=='local_status':
            self.phase=event.get('state',self.phase)
            self.open=event.get('microphone_open',self.open);self.device=event.get('device_name',self.device)
        elif kind=='local_asr_state':self.phase=event['phase']
        elif kind in ('local_heard','local_heard_partial'):
            self.text=str(event.get('text',''));self.reason=event.get('reason','')
            self.asr_ms=event.get('asr_ms',0);self.heard_at=datetime.now().strftime('%H:%M:%S')
        elif kind in ('error','stopped'):
            self.open=False;self.phase='error' if kind=='error' else 'off';self.rms=self.peak=0
            self.error=event.get('code','')

    def snapshot(self,active=True,now=None):
        now=time.monotonic() if now is None else now
        fresh=self.last_meter is not None and now-self.last_meter<1.2
        running=bool(active and self.open)
        clipped=running and fresh and self.clipped_until>now
        state='off' if not running else 'stale' if not fresh else 'clipping' if clipped else 'buffering' if self.phase=='buffering' else 'collecting' if self.phase=='collecting' else 'transcribing' if self.phase=='transcribing' else 'echo' if self.echo else 'voice' if self.voiced else 'quiet'
        return {'state':state,'rms_db':dbfs(self.rms) if running and fresh else FLOOR_DB,
                'peak_db':dbfs(self.peak) if running and fresh else FLOOR_DB,'threshold_db':dbfs(self.threshold),
                'device':self.device,'text':self.text,'reason':self.reason,'heard_at':self.heard_at,
                'asr_ms':self.asr_ms,'phase':self.phase,'error':self.error,'awake':self.awake,'awake_remaining':self.awake_remaining,
                'echo_backend':self.echo_backend,'echo_correlation':self.echo_correlation,'clean_rms':self.clean_rms,'reference_resets':self.reference_resets}

class OutputTelemetry:
    """PCM sent to the output stream; independent of the microphone signal."""
    def __init__(self):self.reset()
    def reset(self):self.latest=None
    def offer(self,pcm,now=None):
        self.latest=(pcm_measurements(pcm),time.monotonic() if now is None else now)
    def snapshot(self,playing=False,now=None):
        now=time.monotonic() if now is None else now;latest=self.latest
        if not playing or latest is None or now-latest[1]>.5:
            return {'state':'off','rms_db':FLOOR_DB,'peak_db':FLOOR_DB}
        value=latest[0]
        return {'state':'clipping' if value['clipped'] else 'playing',
                'rms_db':dbfs(value['rms']),'peak_db':dbfs(value['peak'])}

class MicIndicator:
    """Vertical MIC/LEVA rails beside the orb; selectable transcript in the chat panel."""
    def __init__(self,parent,bg,fg,muted,accent,meter_parent=None,retry=None,arm=None,history=None,dictate=None):
        import tkinter as tk
        self.bg=bg;self.muted=muted;self.accent=accent;self.cached_text=None;self.snapshot_value=None
        self.frame=tk.Frame(parent,bg=bg);self.frame.pack(fill='x',pady=(0,7))
        header=tk.Frame(self.frame,bg=bg);header.pack(fill='x')
        self.device=tk.Label(header,text='MIC · belum aktif',bg=bg,fg=muted,font=('Segoe UI',9),anchor='w')
        self.device.pack(side='left',fill='x',expand=True)
        self.output_device=tk.Label(self.frame,text='LEVA → perangkat output',bg=bg,fg=muted,font=('Segoe UI',9),anchor='w')
        self.output_device.pack(fill='x')
        self.retry_button=None
        if retry:
            self.retry_button=tk.Button(header,text='Coba ulang mic',command=retry,bg='#182b3a',fg=fg,relief='flat',bd=0,padx=8,pady=3)
            self.retry_button.pack(side='right')
        self.arm_button=self.history_button=self.dictate_button=None
        if arm or history:
            controls=tk.Frame(self.frame,bg=bg);controls.pack(fill='x',pady=(3,0))
            for label,callback,attribute in [('Terima perintah · 45 dtk',arm,'arm_button'),('Rekam perintah panjang',dictate,'dictate_button'),('Catatan suara',history,'history_button')]:
                if callback:
                    button=tk.Button(controls,text=label,command=callback,bg='#182b3a',fg=fg,relief='flat',bd=0,padx=8,pady=3)
                    button.pack(side='left',padx=(0,5));setattr(self,attribute,button)
        self.meter_frame=tk.Frame(meter_parent if meter_parent is not None else self.frame,bg='#09121b',width=112)
        self.meter_frame.pack(fill='both',expand=True)
        self.meter_frame.pack_propagate(False)
        self.canvas=tk.Canvas(self.meter_frame,width=112,height=180,bg='#09121b',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True);self.canvas.bind('<Configure>',lambda _:self.draw())
        self.output_value={'state':'off','rms_db':FLOOR_DB,'peak_db':FLOOR_DB}
        self.level=tk.Label(self.frame,text='Level — · ambang —',bg=bg,fg=muted,font=('Consolas',9),anchor='w')
        self.level.pack(fill='x')
        self.state=tk.Label(self.frame,text='Mikrofon tidak aktif',bg=bg,fg=muted,font=('Segoe UI',9),anchor='w')
        self.state.pack(fill='x')
        box=tk.Frame(self.frame,bg=bg);box.pack(fill='x',pady=(3,0))
        self.heard=tk.Text(box,height=2,width=1,wrap='word',bg='#09121b',fg=fg,relief='flat',padx=6,pady=4,
                           font=('Segoe UI',10),state='disabled',highlightthickness=0)
        self.heard.pack(side='left',fill='x',expand=True)
        scroll=tk.Scrollbar(box,command=self.heard.yview,width=10);scroll.pack(side='right',fill='y')
        self.heard.configure(yscrollcommand=scroll.set)
        self.decision=tk.Label(self.frame,text='Tertangkap: belum ada ucapan',bg=bg,fg=muted,font=('Segoe UI',9),anchor='w')
        self.decision.pack(fill='x')

    def update(self,snapshot,notice='',google=None,output=None):
        value=dict(snapshot)
        if google:
            value.update(state='google',device='Google Live · level relatif',rms_db=max(0,min(1,google['level'])),
                         text=google['text'],reason='google',heard_at='',asr_ms=0)
        self.snapshot_value=value
        self.output_value=output or {'state':'off','rms_db':FLOOR_DB,'peak_db':FLOOR_DB}
        self.output_device.configure(text='LEVA → '+(self.output_value.get('device') or 'default Windows'))
        self.device.configure(text='MIC · '+(value['device'] or 'perangkat input terpilih'))
        labels={'off':'Mikrofon tidak aktif','stale':'Menunggu data mikrofon','clipping':'Terlalu keras · sinyal terpotong',
                'buffering':'Audio mengantre dalam RAM · ASR menunggu GPU','collecting':'Menggabungkan ucapan · belum dikirim ke agent',
                'transcribing':'Mengenali kalimat… · meter input tetap aktif','echo':'Gema keluaran disaring',
                'voice':'Suara melewati ambang deteksi','quiet':'Di bawah ambang · siaga mendengar','google':'Input Google Live · ambang server tidak tersedia'}
        state=value['state'];color='#ff857c' if state=='clipping' else self.accent if state in ('voice','google') else self.muted
        if state=='quiet' and value.get('awake'):labels['quiet']='Sesi perintah aktif · %s detik'%value.get('awake_remaining',0)
        self.state.configure(text=(notice[:100] if state=='off' and notice else labels[state]),fg=color)
        if state=='google':level='Level relatif %d%% · ambang Google tidak tersedia'%round(value['rms_db']*100)
        elif state in ('off','stale'):level='Level — · ambang %.1f dBFS'%value['threshold_db']
        else:level='RMS %.1f · puncak %.1f · ambang %.1f dBFS'%(value['rms_db'],value['peak_db'],value['threshold_db'])
        self.level.configure(text=level)
        text=value['text'] or 'Belum ada kalimat tertangkap.'
        if text!=self.cached_text:
            self.heard.configure(state='normal');self.heard.delete('1.0','end');self.heard.insert('1.0',text);self.heard.configure(state='disabled');self.cached_text=text
        reasons={'collecting':'Menyusun ucapan lengkap · belum dijalankan','incomplete':'Audio terputus · tidak dijalankan',
                 'awaiting_wake':'Belum diteruskan · panggilan Leva belum terdeteksi','wake':'Panggilan Leva dikenali',
                 'followup':'Ucapan lanjutan diterima','echo':'Diabaikan · mirip keluaran suara Leva','empty':'Tidak ada teks dikenali',
                 'google':'Transkrip Google Live','':'Belum ada ucapan'}
        self.decision.configure(text=(value['heard_at']+' · ' if value['heard_at'] else '')+reasons.get(value['reason'],'Hasil pengenalan')+
                                (' · %.2f s'%(value['asr_ms']/1000) if value['asr_ms'] else '')+
                                (' · AEC3' if value.get('echo_backend')=='webrtc_aec3' else ' · Gema: fallback' if value.get('echo_backend') else ''))
        self.draw()

    def draw(self):
        v=self.snapshot_value
        if not v:return
        c=self.canvas;c.delete('all');w=max(90,c.winfo_width());h=max(90,c.winfo_height())
        position=lambda db:max(0,min(1,(db-FLOOR_DB)/-FLOOR_DB))
        top,bottom=27,h-43;span=bottom-top
        for ident,label,value,center,color in [('mic','MIC',v,w*.27,self.accent),('leva','LEVA',self.output_value,w*.73,'#c29bf3')]:
            relative=value['state'] in ('google','relative')
            amount=value.get('level',value['rms_db']) if relative else position(value['rms_db'])
            amount=max(0,min(1,amount));left,right=center-10,center+10
            color='#ff857c' if value['state']=='clipping' else color
            c.create_text(center,12,text=label,fill=color,font=('Consolas',10,'bold'),tags=ident+'_label')
            c.create_rectangle(left,top,right,bottom,fill='#1a2b38',outline='',tags=ident+'_track')
            for fraction in (.25,.5,.75,1):
                y=bottom-span*fraction;c.create_line(left-3,y,right+3,y,fill='#36505e')
            c.create_rectangle(left,bottom-span*amount,right,bottom,fill=color,outline='',tags=ident+'_fill')
            if not relative:
                peak=bottom-span*position(value['peak_db'])
                c.create_line(left-2,peak,right+2,peak,fill='#e2ecee',tags=ident+'_peak')
            if ident=='mic' and not relative:
                threshold=bottom-span*position(value['threshold_db'])
                c.create_line(left-5,threshold,right+5,threshold,fill='#f7c66d',width=2,tags='mic_threshold')
            reading=('%d%%'%round(amount*100)) if relative else ('—' if value['state'] in ('off','stale') else '%.0f'%value['rms_db'])
            c.create_text(center,h-27,text=reading,fill=color,font=('Consolas',10),tags=ident+'_value')
            c.create_text(center,h-12,text='relatif' if relative else 'dBFS',fill=self.muted,font=('Consolas',8))
