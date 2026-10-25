"""External Piper process. File synthesis only: no microphone, playback, cloud or RVC."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import wave

def diagnostic_error(error,request):
    """Persist actionable metadata without prompt text, keys, or reference audio."""
    try:
        from paths import DATA
        folder=DATA/'status';folder.mkdir(parents=True,exist_ok=True)
        row={'at':time.time(),'type':type(error).__name__,'http_status':getattr(error,'code',None),
             'pack':request.get('actual_pack'),'language':request.get('language'),'characters':len(request.get('text','')),
             'request_id':request.get('request_id'),'streaming':bool(request.get('stream_audio'))}
        path=folder/'tts-errors.jsonl'
        if path.exists() and path.stat().st_size>256000:path.replace(folder/'tts-errors.previous.jsonl')
        with path.open('a',encoding='utf8') as stream:stream.write(json.dumps(row)+'\n')
    except (OSError,TypeError):pass


def run(request,cache=None,emit=None):
    from voice_packs import DATA, PREVIEWS, PIPER, validate_text, verify_piper, validate_preview
    actual=request.get('actual_pack')
    modern=actual in ('higgs_leva','higgs_native','higgs_jp_identity','omnivoice_leva','omnivoice_native')
    if actual not in ('neutral_id','leva_gfl2') and not modern:
        raise ValueError("voice_adapter_unavailable")
    text = validate_text(request.get("text"))
    language=request.get('language','id')
    if language not in ('id','ja'):raise ValueError('unsupported_voice_language')
    if not modern and request.get('tts_gpu','auto') not in ('auto','rtx4050') and (actual!='neutral_id' or language!='id'):
        raise ValueError('voice_gpu_unsupported_for_engine')
    output = Path(request["output"]).resolve()
    if not output.is_relative_to(PREVIEWS.resolve()) or output.suffix != ".wav":
        raise ValueError("invalid_preview_path")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Caller uses a fresh random session directory. Never replace existing audio/proofs.
    if output.exists():
        raise ValueError("preview_already_exists")
    if modern:
        from audio_cpp_voice import synthesize
        started=time.perf_counter()
        result=synthesize(actual,text,output,language,request.get('voice_style','assistant'),cache,gpu_preference=request.get('tts_gpu','auto'),emit=emit if request.get('stream_audio') else None,early_audio=request.get('early_audio') is True)
        _,duration=validate_preview(output)
        elapsed=time.perf_counter()-started
        return {'kind':'generated','actual_pack':actual,'path':str(output),'duration_seconds':round(duration,4),
                'total_seconds':round(elapsed,4),'load_seconds':round(max(0,elapsed-result['engine_request_seconds']),4),
                'synthesis_seconds':result['engine_request_seconds'],'language':language,'microphone_opened':False,
                'speaker_opened':False,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),**result}
    signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in (PIPER,PIPER.with_suffix('.onnx.json')))
    reused=cache is not None and 'piper' in cache and cache.get('piper_stamp')==signature
    if language=='id' and not reused:verify_piper()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(DATA / "cache/hf-voice-proof")
    os.environ["OMP_NUM_THREADS"] = "4"
    os.environ["OPENBLAS_NUM_THREADS"] = "4"
    os.environ["TEMP"] = os.environ["TMP"] = str(output.parent)
    started = time.perf_counter()
    voice=None
    if language=='id':
        from piper import PiperVoice
        voice=cache['piper'] if reused else PiperVoice.load(str(PIPER),use_cuda=False)
        if cache is not None:cache.update(piper=voice,piper_stamp=signature)
    loaded = time.perf_counter()
    partial = output.with_suffix(".partial.wav")
    try:
        base={}
        if language=='ja':
            from japanese_voice import synthesize_japanese
            base=synthesize_japanese(text,partial,cache if cache is not None else {})
        else:
            with wave.open(str(partial), "wb") as stream:voice.synthesize_wav(text, stream)
        conversion={}
        if actual=='leva_gfl2':
            from seed_voice_adapter import convert
            import soundfile as sf
            import numpy as np
            converted,conversion=convert(partial,output.parent)
            samples,rate=sf.read(converted,dtype='float32')
            if not np.isfinite(samples).all():raise ValueError('invalid_preview_audio')
            sf.write(partial,samples,rate,subtype='PCM_16')
        _, duration = validate_preview(partial)
        # Exclusive name checked above; the directory belongs only to this request.
        partial.rename(output)
    finally:
        partial.unlink(missing_ok=True)
    done = time.perf_counter()
    result = {"kind": "generated", "actual_pack": actual, "path": str(output),
              "duration_seconds": round(duration, 4), "load_seconds": round(loaded-started, 4),
              "synthesis_seconds": round(done-loaded, 4), "total_seconds": round(done-started, 4),
              "backend": ("Kokoro Jepang" if language=='ja' else 'Piper Indonesia')+(' + Seed-VC RTX 4050' if actual=='leva_gfl2' else ''), "microphone_opened": False, "speaker_opened": False,
              "streaming": False, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    # No text is persisted. Preview WAVs are retained only until the UI is closed/stopped.
    return {**result,**conversion,**base,'piper_reused':reused if language=='id' else False,'language':language}


def session(protocol,idle_seconds=120):
    import queue
    import threading
    commands=queue.Queue(maxsize=2)
    ready=threading.Event()
    def read():
        try:
            while True:
                ready.wait();ready.clear()
                line=sys.stdin.readline()
                if not line:break
                try:commands.put_nowait(json.loads(line))
                except (ValueError,queue.Full):pass
        finally:
            try:commands.put_nowait({'kind':'stop'})
            except queue.Full:pass
    threading.Thread(target=read,daemon=True).start()
    cache={}
    while True:
        # A blocked Windows CRT stdin read can stall native DLL initialization.
        # Read only while idle, never while Piper/NumPy/Torch initialize or run.
        ready.set()
        try:request=commands.get(timeout=idle_seconds)
        except queue.Empty:break
        if request.get('kind')=='stop':break
        try:
            def emit_delta(row):
                protocol.write(json.dumps({**row,'request_id':request.get('request_id'),'actual_pack':request.get('actual_pack')})+'\n');protocol.flush()
            with contextlib.redirect_stdout(sys.stderr):result=run(request,cache,emit_delta)
        except Exception as error:
            diagnostic_error(error,request)
            code=str(error) if isinstance(error,ValueError) and str(error) in ('voice_gpu_unsupported_for_engine','voice_gpu_headroom_unavailable','voice_model_hash_mismatch','voice_reference_hash_mismatch') else 'local_tts_failed'
            result={'kind':'error','code':code}
        result['request_id']=request.get('request_id')
        protocol.write(json.dumps(result,ensure_ascii=True)+'\n');protocol.flush()
        if result['kind']=='error':break
    if cache.get('audio_cpp'):cache['audio_cpp'].close()
    protocol.write(json.dumps({'kind':'stopped','microphone_open':False})+'\n');protocol.flush()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    protocol = sys.stdout
    if '--session' in sys.argv:
        session(protocol)
        raise SystemExit(0)
    try:
        request = json.loads(sys.stdin.readline())
        with contextlib.redirect_stdout(sys.stderr):
            def emit_delta(row):
                protocol.write(json.dumps({**row,'request_id':request.get('request_id'),'actual_pack':request.get('actual_pack')})+'\n');protocol.flush()
            result = run(request,emit=emit_delta)
    except Exception as error:
        diagnostic_error(error,request if 'request' in locals() else {})
        import traceback
        traceback.print_exc(file=sys.stderr)
        allowed = {"voice_adapter_unavailable", "invalid_preview_text", "invalid_preview_path",
                   'voice_gpu_unsupported_for_engine','voice_gpu_headroom_unavailable',
                   "preview_already_exists", "piper_asset_missing", "piper_asset_hash_mismatch",
                   "invalid_preview_file", "invalid_preview_audio", "silent_preview_audio"}
        code = str(error) if isinstance(error, ValueError) and str(error) in allowed else "local_tts_failed"
        result = {"kind": "error", "code": code}
    protocol.write(json.dumps(result, ensure_ascii=True) + "\n")
    protocol.write(json.dumps({"kind": "stopped", "microphone_open": False}) + "\n")
    protocol.flush()
