"""Persistent, explicitly started Qwen baseline for the text-only duplex laboratory."""
from datetime import datetime
import json
import queue
import sys
import threading
import time

from hybrid_engine import LocalEngine, DEFAULT_MODEL, DEFAULT_SERVER, EngineError
from paths import ROOT, DATA
from live_voice import LiveVoiceService

BASELINE_PROMPT=(
    "Kamu Leva dalam eksperimen micro-turn teks berbahasa Indonesia. Setiap pesan pengguna adalah "
    "fragmen ucapan baru, atau <no voice> bila tick ini tidak memiliki kata baru. "
    "Jawab hanya <listen> jika pengguna belum menyelesaikan gagasan, masih mencari kata, "
    "atau kamu perlu menunggu. Jika sudah tepat untuk berbicara, keluarkan maksimal tiga kata "
    "baru untuk kelanjutan jawaban. Jangan mengulang kata jawaban sebelumnya. "
    "Jangan menulis JSON, penjelasan keputusan, tag lain, atau perintah komputer. "
    "Ini baseline prompt saja, tanpa adapter LoRA."
)


def baseline_messages(history,heard):
    if not isinstance(heard,str) or not heard.strip() or len(heard)>600:
        raise ValueError("invalid_tick_input")
    if not isinstance(history,list) or len(history)>64:
        raise ValueError("invalid_tick_history")
    messages=[]
    for pair in history:
        if not isinstance(pair,(tuple,list)) or len(pair)!=2 or not all(isinstance(v,str) and len(v)<=600 for v in pair):
            raise ValueError("invalid_tick_history")
        messages.extend([{"role":"user","content":pair[0]},{"role":"assistant","content":pair[1]}])
    messages.append({"role":"user","content":heard})
    return messages


def duplex_worker(emit):
    commands=queue.Queue(maxsize=2)
    def read():
        try:
            for line in sys.stdin:
                try:commands.put_nowait(json.loads(line))
                except (ValueError,queue.Full):pass
        finally:
            try:commands.put_nowait({"kind":"stop"})
            except queue.Full:pass
    threading.Thread(target=read,daemon=True).start()
    engine=None
    try:
        # Parent sends an explicit start message; no inference starts just by importing a module.
        start=commands.get(timeout=10)
        if start.get("kind")!="start":raise ValueError("invalid_lab_start")
        backend=start.get('backend','baseline')
        if backend not in ('baseline','microturn','saluki'):raise ValueError('invalid_lab_backend')
        folder=DATA/'duplex-lab'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        if backend=='microturn':
            from microturn_backend import MicroTurnEngine
            engine=MicroTurnEngine(folder)
            placement='RTX 4050 + RTX 5070 + RAM' if engine.mode=='dual' else 'RTX 5070 + RAM'
            label='Qwen 35B + MicroTurn LoRA · '+placement
        elif backend=='saluki':
            from saluki_backend import SalukiEngine
            engine=SalukiEngine(folder,acceleration=start.get('acceleration','auto'),system=BASELINE_PROMPT,max_output_tokens=32)
            label='Saluki 27B · '+engine.acceleration+' · prompt saja'
        else:
            engine=LocalEngine(DEFAULT_SERVER,DEFAULT_MODEL,folder,mode='gpu4050',system=BASELINE_PROMPT,
                max_output_tokens=32,context_size=4096,sampling={'temperature':0})
            label='Qwen 4B prompt-only'
        emit({"kind":"loading"})
        engine.start()
        emit({"kind":"ready","backend":label,"backend_id":backend,"lora_loaded":backend=='microturn',"load_seconds":engine.load_seconds,
              "devices":engine.devices,"gpu_snapshot_loaded":engine.gpu_snapshot_loaded,
              "microphone_open":False,"speaker_open":False})
        while True:
            try:command=commands.get(timeout=180)
            except queue.Empty:
                emit({"kind":"notice","code":"lab_idle_timeout"})
                break
            if command.get("kind")=="stop":break
            if command.get("kind")!="tick":continue
            if backend=='microturn':
                result=engine.tick(command.get('history'),command.get('heard'))
                emit({'kind':'result','id':command['id'],**result})
                continue
            messages=baseline_messages(command.get("history"),command.get("heard"))
            started=time.monotonic()
            response=engine.request("/v1/chat/completions",{
                "messages":[{"role":"system","content":BASELINE_PROMPT}]+messages,
                "max_tokens":32,"temperature":0,"chat_template_kwargs":{"enable_thinking":False}},timeout=30)
            choice=response["choices"][0]
            if choice.get("finish_reason")!="stop":raise EngineError("local_incomplete_response")
            text=choice["message"].get("content","").strip()
            emit({"kind":"result","id":command["id"],"text":text,
                  "backend_ms":round((time.monotonic()-started)*1000,2),"timings":response.get("timings",{})})
    except EngineError as error:
        emit({"kind":"error","code":str(error)})
    except Exception:
        emit({"kind":"error","code":"duplex_baseline_runtime_error"})
    finally:
        if engine:engine.close()
        emit({"kind":"stopped","microphone_open":False})


class DuplexService(LiveVoiceService):
    """Reuse the existing bounded IPC reader and Windows Job Object ownership."""
    def __init__(self):
        command=[sys.executable,"--duplex-worker"] if getattr(sys,"frozen",False) else [sys.executable,"-B",str(ROOT/"app/main.py"),"--duplex-worker"]
        super().__init__(worker_command=command)

    def start_lab(self,backend='baseline',acceleration='auto'):
        if backend not in ('baseline','microturn','saluki'):raise ValueError('invalid_lab_backend')
        message={'kind':'start'}
        if backend!='baseline':message['backend']=backend
        if backend=='saluki':message['acceleration']=acceleration
        self.start(0,0,initial_message=message)
