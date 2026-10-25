"""Owned capture child shields PortAudio callbacks from model/GIL stalls."""
import base64,json,os,subprocess,sys,threading
from pathlib import Path

class CaptureProcess:
    def __init__(self,request,callback):
        self.request=request;self.callback=callback;self.process=None;self.ready=threading.Event()
        self.info={};self.health={};self.error=None;self.closing=False
    def __enter__(self):
        script=Path(__file__).with_name('mic_capture_worker.py')
        self.process=subprocess.Popen([sys.executable,'-u','-B',str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.health['capture_pid']=self.process.pid
        self.process.stdin.write(json.dumps(self.request)+'\n');self.process.stdin.flush()
        def read():
            previous_drops=0;carry=b''
            try:
                for line in self.process.stdout:
                    event=json.loads(line)
                    if event['kind']=='capture_ready':self.info=event;self.ready.set()
                    elif event['kind']=='capture_error':self.error=event;self.ready.set()
                    elif event['kind']=='capture_audio':
                        self.health={**event['health'],'capture_pid':self.process.pid}
                        flags=event['flags'];drops=self.health['queue_dropped_frames']
                        broken='input_overflow' in flags or drops>previous_drops;previous_drops=drops
                        carry+=base64.b64decode(event['pcm'])
                        while len(carry)>=640:
                            pcm,carry=carry[:640],carry[640:]
                            self.callback(pcm,320,event['stamp'], 'capture_input_loss' if broken else None)
                            broken=False
            except (OSError,ValueError,KeyError) as error:
                if not self.closing:self.error={'code':type(error).__name__,'message':'capture_protocol_failure'}
            finally:
                if not self.closing and self.error is None:self.error={'code':'capture_child_exit','message':'Capture process ended.'}
                self.ready.set()
        self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
        if not self.ready.wait(15):self.close();raise OSError('microphone_capture_start_timeout')
        if self.error:
            error=self.error;self.close()
            if error['code']=='microphone_not_found':raise ValueError('microphone_not_found')
            raise OSError('microphone_capture_'+error['code'])
        return self
    def check(self):
        if self.error:raise OSError('microphone_capture_'+self.error['code'])
    def close(self):
        self.closing=True
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
            for stream in (self.process.stdin,self.process.stdout):
                try:stream.close()
                except OSError:pass
        if hasattr(self,'thread'):self.thread.join(timeout=1)
    def __exit__(self,*args):self.close()
