"""Speak completed chat replies locally, with bounded chunks and explicit cancellation."""
from collections import deque
import re

from voice_pack_service import VoicePackService
from voice_packs import voice_error_notice
from spoken_text import prepare_spoken_text

def speech_chunks(text,language='id'):
    if not isinstance(text,str) or not text.strip() or len(text)>8000:
        raise ValueError('spoken_reply_too_long_or_empty')
    text=prepare_spoken_text(text,language)
    if not text:return []
    parts=[]
    limit=90 if language=='ja' else 220
    while len(text)>limit:
        ends=[m.end() for m in re.finditer(r'[。！？]|[.!?;]\s+',text[:limit])]
        cut=ends[-1] if ends and ends[-1]>limit//4 else text.rfind(' ',0,limit)
        if cut<1:cut=limit
        parts.append(text[:cut].strip()); text=text[cut:].strip()
    if text:parts.append(text)
    if not parts:raise ValueError('spoken_reply_too_long_or_empty')
    return parts

class ReplyVoice:
    def __init__(self,service=None,keep_warm=True):
        self.service=service or VoicePackService(persistent=keep_warm)
        self.pending=deque()
        self.ready=False
        self.requested='neutral_id'
        self.actual=None
        self.state='idle'
        self.language='id'
        self.style='assistant'
        self.utterances=deque()
        self.is_reaction=False
        self.current_text='';self.retry_budget=3;self.completed_chunks=0;self.failed_chunks=0;self.total_chunks=0
        self.stream=None

    def progress(self):
        return {'completed':self.completed_chunks,'failed':self.failed_chunks,'total':self.total_chunks,'remaining':len(self.pending),'state':self.state,'retries_left':self.retry_budget}

    def recover(self,code):
        """Retry only the unplayed chunk, with a smaller unit and a fresh worker."""
        if code not in ('local_tts_failed','voice_server_timeout','invalid_voice_server_audio','silent_preview_audio') or not self.current_text:return False
        if self.stream and self.stream.audible:return False
        if self.retry_budget<=0:return False
        text=self.current_text;self.retry_budget-=1;self.ready=False
        if self.stream:self.stream.cancel();self.stream=None
        self.service.stop()
        if len(text)>50:
            mid=len(text)//2;cut=text.rfind(' ',max(1,mid//2),mid+1)
            if cut<1:cut=mid
            pieces=[text[:cut].strip(),text[cut:].strip()];self.total_chunks+=1
        else:pieces=[text]
        self.pending.extendleft(reversed(pieces));self._next();return True

    @property
    def active(self):return bool(self.pending or self.utterances or self.ready or self.service.active)

    def speak_cached(self,path,requested,language='id'):
        self.cancel(keep_warm=True)
        self.requested=requested;self.language=language;self.style='assistant'
        result=self.service.use_cached(path,requested)
        self.service.language=language
        self.actual=requested;self.ready=True;self.state='connecting';self.is_reaction=True
        self.completed_chunks=self.failed_chunks=0;self.total_chunks=1;self.retry_budget=3
        return result

    def enqueue(self,text,requested,language='id',style='assistant'):
        """A final answer follows the opening reaction instead of cutting it off."""
        if not self.active:return self.speak(text,requested,language,style)
        self.utterances.append((speech_chunks(text,language),requested,language,style))
        return {'actual':requested,'reason':'Jawaban akhir diantrekan setelah balasan awal'}

    def speak(self,text,requested,language='id',style='assistant'):
        if style not in ('assistant','personal'):raise ValueError('invalid_speech_style')
        chunks=speech_chunks(text,language)
        self.cancel(keep_warm=True)
        self.requested=requested
        self.language=language
        self.style=style
        self.pending.extend(chunks)
        self.total_chunks=len(chunks);self.retry_budget=3;self.completed_chunks=self.failed_chunks=0
        return self._next()

    def _next(self):
        if not self.pending:
            if not self.utterances:
                self.state='idle';self.is_reaction=False;return None
            chunks,self.requested,self.language,self.style=self.utterances.popleft()
            self.pending.extend(chunks);self.is_reaction=False
            self.total_chunks+=len(chunks)
            if not self.pending:return self._next()
        self.state='thinking'
        text=self.pending.popleft()
        self.current_text=text
        if self.requested.startswith(('higgs_','omnivoice_')):
            resolved=self.service.generate(self.requested,text,language=self.language,style=self.style)
        else:resolved=self.service.generate(self.requested,text,language=self.language) if self.language!='id' else self.service.generate(self.requested,text)
        self.actual=resolved['actual']
        return resolved

    def poll(self):
        notices=[]
        if self.service.check_timeout():
            if self.recover('voice_server_timeout'):return ['Satu potongan suara diulang lebih pendek setelah batas waktu.']
            self.stop(); return ['Sintesis melewati batas waktu; jawaban teks tetap tersedia.']
        while not self.service.events.empty():
            event=self.service.events.get_nowait()
            kind=event.get('kind')
            try:
                if kind=='audio_delta':
                    path=self.service.accept_delta(event)
                    if self.stream is None:
                        from stream_playback import StreamPlayback
                        self.stream=getattr(self,'stream_factory',StreamPlayback)(self.service)
                    self.stream.offer(path,event['sequence'])
                elif kind=='generated':
                    self.service.accept_generated(event)
                    if self.stream:self.stream.end()
                    else:self.ready=True
                elif kind=='playback_started':self.state='speaking'
                elif kind=='playback_finished':
                    self.completed_chunks+=1;self.current_text=''
                    self.stream=None
                    self.service.finish(); self.ready=False
                    self._next()
                elif kind=='error':
                    code=event.get('code','local_tts_failed')
                    if code=='preview_output_unavailable' and getattr(self.service,'web_audio_published',False) is True:
                        notices.append(voice_error_notice(code));continue
                    if self.recover(code):
                        notices.append('Sintesis satu potongan diulang lebih pendek; bagian yang selesai tidak diputar ulang.');break
                    notices.append(voice_error_notice(code));self.failed_chunks+=1
                    self.stop(); break
            except (ValueError,OSError,RuntimeError):
                self.stop(); notices.append('Keluaran suara belum berhasil; jawaban teks tetap tersedia.'); break
        if self.ready and self.service.can_play:
            if self.service.play():self.ready=False; self.state='connecting'
        return notices

    def stop(self):
        self.cancel(keep_warm=False)

    def cancel(self,keep_warm=False):
        callback=getattr(self,'audio_cancel_callback',None)
        if callback:callback()
        self.pending.clear();self.utterances.clear();self.is_reaction=False;self.ready=False
        self.current_text=''
        if self.stream:self.stream.cancel();self.stream=None
        if keep_warm:self.service.reset(keep_warm=True)
        else:self.service.stop()
        self.state='idle';self.actual=None
