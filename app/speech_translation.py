"""Bounded speech translation, isolated from conversation history and cancellable."""
import re
from hybrid_engine import EngineError
from spoken_text import prepare_spoken_text

def translation_chunks(text,limit=300):
    prose=prepare_spoken_text(text,'id')
    if len(prose)>20000:raise ValueError('speech_translation_too_long')
    chunks=[]
    while len(prose)>limit:
        ends=[m.end() for m in re.finditer(r'[.!?;]\s+',prose[:limit])]
        cut=ends[-1] if ends and ends[-1]>limit//4 else prose.rfind(' ',0,limit)
        if cut<1:cut=limit
        chunks.append(prose[:cut].strip());prose=prose[cut:].strip()
    if prose:chunks.append(prose)
    return chunks

def translate_speech(service,text,gpu,authorized=lambda:True,mode='local',router_config=None,progress=None):
    parts=translation_chunks(text);translated=[];attempts=0
    def one(source,depth=0):
        nonlocal attempts
        if not authorized():raise EngineError('speech_translation_cancelled')
        attempts+=1
        try:
            result=service.ask(source,mode,gpu,local_model='qwen4b',purpose='translate',keep_warm=True,router_config=router_config)
            if result.get('cancelled') or not authorized():raise EngineError('speech_translation_cancelled')
            answer=prepare_spoken_text(result.get('response',''),'ja')
            if not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',answer):raise EngineError('translation_script_mismatch')
            return [answer]
        except EngineError as error:
            if str(error) not in ('local_incomplete_response','translation_script_mismatch','empty_chat_response') or depth>=2 or len(source)<70:raise
            middle=len(source)//2;cut=source.rfind(' ',max(1,middle//2),middle+1)
            if cut<1:cut=middle
            return one(source[:cut].strip(),depth+1)+one(source[cut:].strip(),depth+1)
    try:
        for i,part in enumerate(parts):
            translated.extend(one(part))
            if progress:progress({'completed':i+1,'total':len(parts),'attempts':attempts})
        return {'text':' '.join(translated),'parts':len(parts),'completed':len(parts),'attempts':attempts}
    finally:
        # Translator owns no conversation context; release it before TTS needs VRAM.
        service.cancel()
