"""Content-only SSE. Never forwards reasoning channels or treats prose as tool evidence."""
import json
import re
import time
import urllib.request

class ContentFilter:
    def __init__(self):self.raw='';self.sent=0
    def feed(self,text,final=False):
        self.raw+=text
        if len(self.raw)>24000:raise ValueError('stream_text_limit')
        clean=re.sub(r'<think>[\s\S]*?(?:</think>|$)','',self.raw,flags=re.I)
        # Delay a possible split opening control tag until its type is known.
        tail=clean.rfind('<')
        if tail>=0 and '>' not in clean[tail:]:clean=clean[:tail]
        if len(clean)<self.sent:raise ValueError('stream_content_retracted')
        delta=clean[self.sent:];self.sent=len(clean);return delta

def generate_stream(engine,messages,on_delta,on_event=lambda event:None):
    from hybrid_engine import EngineError
    start=time.perf_counter();engine.start();on_event({'event_type':'model.ready','load_seconds':engine.load_seconds})
    payload={'messages':[{'role':'system','content':engine.system}]+messages,'max_tokens':engine.max_output_tokens,
        **engine.sampling,'stream':True,'chat_template_kwargs':{'enable_thinking':False,**getattr(engine,'chat_template_kwargs',{})}}
    request=urllib.request.Request(engine.endpoint+'/v1/chat/completions',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+engine.api_key})
    filtering=ContentFilter();text='';finish=None;timings={};usage={};first=None;done=False
    on_event({'event_type':'model.prompt_started'})
    try:
        with engine.opener.open(request,timeout=90) as response:
            while True:
                line=response.readline(1024*1024+1)
                if not line:break
                if len(line)>1024*1024:raise EngineError('invalid_model_stream_event')
                if not line.startswith(b'data:'):continue
                raw=line[5:].strip()
                if raw==b'[DONE]':done=True;break
                row=json.loads(raw);timings=row.get('timings') or timings;usage=row.get('usage') or usage
                for choice in row.get('choices',[]):
                    finish=choice.get('finish_reason') or finish
                    delta=filtering.feed(choice.get('delta',{}).get('content') or '')
                    if delta:
                        if first is None:
                            first=(time.perf_counter()-start)*1000;on_event({'event_type':'model.response_started','ttft_ms':round(first,2)})
                        text+=delta;on_delta(delta)
        last=filtering.feed('',final=True)
        if last:text+=last;on_delta(last)
        if not done or finish!='stop' or not text.strip():raise EngineError('local_incomplete_stream')
        measured={'ttft_ms':round(first,2) if first is not None else None,'total_ms':round((time.perf_counter()-start)*1000,2),'timings':timings,'usage':usage}
        engine.last_stream_metrics=measured;on_event({'event_type':'model.completed',**measured});return text.strip()
    except (OSError,ValueError,KeyError) as error:raise EngineError('local_stream_transport_failure') from error

class AdaptiveSegmenter:
    """Stable prose phrases; code fences, URLs and decimal/abbreviation periods stay intact."""
    def __init__(self,language='id',clock=time.monotonic):
        self.language=language;self.clock=clock;self.buffer='';self.first=True;self.started=clock();self.code=False;self.code_cue=False
    def feed(self,delta,final=False):
        self.buffer+=delta
        if len(self.buffer)>24000:raise ValueError('speech_buffer_limit')
        out=[]
        while self.buffer:
            if self.code:
                end=self.buffer.find('```')
                if end<0:
                    if final:self.buffer='';self.code=False
                    break
                self.buffer=self.buffer[end+3:];self.code=False;continue
            fence=self.buffer.find('```')
            if fence==0:
                self.buffer=self.buffer[3:];self.code=True
                if not self.code_cue:out.append('コードは画面にあります。' if self.language=='ja' else 'Bagian kode tersedia di layar.');self.code_cue=True
                continue
            limit=(40 if self.first else 90) if self.language=='ja' else (105 if self.first else 220)
            cap=min(len(self.buffer),limit)
            if fence>0:cap=min(cap,fence)
            cut=None
            for m in re.finditer(r'[。！？!?]|[.;](?=\s|$)',self.buffer[:cap]):
                i=m.end();prefix=self.buffer[:i]
                if prefix.count('[')>prefix.count(']') or re.search(r'(?:https?://|www\.)\S*$',prefix):continue
                if prefix[-1]=='.' and re.search(r'\b(?:dr|prof|no|mr|mrs|pt|dll|dsb)\.$',prefix,re.I):continue
                if i>=4:cut=i;break
            if cut is None and fence>0 and cap==fence:cut=fence
            if cut is None and (len(self.buffer)>=limit or self.clock()-self.started>.6 and len(self.buffer)>45):
                # Prefer a phrase boundary. Never split the middle of a link/word.
                choices=[m.end() for m in re.finditer(r'[,;:]\s+',self.buffer[:cap])]
                cut=choices[-1] if choices else self.buffer.rfind(' ',0,cap)
                if cut<20:cut=None
            if cut is None:
                if final:cut=len(self.buffer)
                else:break
            part=self.buffer[:cut].strip();self.buffer=self.buffer[cut:].lstrip();self.started=self.clock()
            from spoken_text import prepare_spoken_text
            part=prepare_spoken_text(part,self.language)
            if part:out.append(part);self.first=False
        return out
