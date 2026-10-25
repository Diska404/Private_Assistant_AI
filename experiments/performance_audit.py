"""Read-only discovery and isolated, bounded benchmarks; no microphone or inference."""
import argparse
import ast
from collections import Counter
import cProfile
import hashlib
import io
import json
from pathlib import Path
import pstats
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\performance-20261024')
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]


def stats(values):
    ordered=sorted(values)
    return {'n':len(values),'median_ms':statistics.median(values),
        'p95_ms':ordered[int((len(ordered)-1)*.95)] if len(values)>=20 else None,
        'min_ms':min(values),'max_ms':max(values)}


def discovery():
    import psutil
    OUT.mkdir(parents=True,exist_ok=True)
    files=[p for base in ('app','experiments') for p in (ROOT/base).rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and 'graphify-out' not in p.parts
        and p.suffix in ('.py','.ps1','.js','.mjs','.css','.html','.json','.txt')
        and p.stat().st_size<4*1024**2]
    checkpoint=OUT/'source-before.zip'
    if not checkpoint.exists():
        with zipfile.ZipFile(checkpoint,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in files:archive.write(path,path.relative_to(ROOT).as_posix())
    modules=[]
    for path in (ROOT/'app').glob('*.py'):
        tree=ast.parse(path.read_text('utf-8-sig'))
        modules.append({'file':str(path.relative_to(ROOT)),'lines':len(path.read_text('utf-8-sig').splitlines()),
            'imports':sorted({n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
                |{a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    fields=('provider','agent_provider','agent_local_model','agent_gpu','asr_model','asr_gpu','tts_gpu',
        'keep_models_warm','animation','speech_language','target_voice_pack','always_listen','web_port')
    dbpath=Path(r'D:\AI\AI Lokal Asisten\Leva\preferences.sqlite3')
    with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
        config={key:json.loads(value) for key,value in db.execute('SELECT key,value FROM settings') if key in fields}
    processes=[]
    for process in psutil.process_iter(['pid','name','exe','memory_info','num_threads']):
        try:
            info=process.info
            if info['name'].lower() in ('leva.exe','llama-server.exe','tailscale.exe','tailscaled.exe','rustdesk.exe','anydesk.exe','parsecd.exe','mstsc.exe'):
                processes.append({'pid':info['pid'],'name':info['name'],'exe':info['exe'],
                    'rss_bytes':info['memory_info'].rss,'threads':info['num_threads']})
        except (psutil.AccessDenied,psutil.NoSuchProcess):pass
    def git(*args):
        r=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,timeout=5)
        return r.stdout.strip() if not r.returncode else 'NOT_A_GIT_REPOSITORY'
    graph=json.loads((ROOT/'graphify-out/graph.json').read_text('utf8'))
    nodes=graph['nodes'];edges=graph.get('links',graph.get('edges',[]))
    seeds=[n['id'] for n in nodes if n.get('label') in ('LevaWindow','ChatService','DesktopWebHost','session_worker()')]
    adjacent=[e for e in edges if e.get('source') in seeds or e.get('target') in seeds]
    report={'application':json.loads((ROOT/'LEVA_PROJECT.json').read_text('utf8')),'runtime_configuration':config,
        'live_processes':processes,'actual_source_git':git('rev-parse','--show-toplevel'),
        'export_git_branch':git('-C','github-export','branch','--show-current'),
        'export_git_commit':git('-C','github-export','rev-parse','HEAD'),
        'export_git_working_tree':git('-C','github-export','status','--porcelain'),
        'checkpoint':str(checkpoint),'modules':modules,
        'graph_navigation':{'nodes':len(nodes),'edges':len(edges),'seeds':seeds,'adjacent':adjacent[:40]},
        'physical_ram_bytes':psutil.virtual_memory().total,'cpu_logical':psutil.cpu_count(),
        'no_production_mutation':True}
    (OUT/'discovery.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('modules','graph_navigation')},ensure_ascii=True))


def benchmarks(phase):
    OUT.mkdir(parents=True,exist_ok=True)
    from preferences import Preferences
    from conversation_rooms import ConversationRooms
    from web_host import DesktopWebHost
    from profile_avatar import ProfileAvatar
    from pipeline_routing import route_spec
    from mic_indicator import MicTelemetry
    proof={'phase':phase,'method':'Synthetic isolated Tk/host algorithm cost, not display FPS or production latency.',
        'microphone_opened':False,'models_loaded':False,'results':{}}
    with tempfile.TemporaryDirectory(prefix='leva-perf-') as folder:
        folder=Path(folder);prefs=Preferences(folder/'preferences.sqlite3');rooms=ConversationRooms(folder/'rooms.sqlite3')
        main=Mock();main.preferences=prefs;main.rooms=rooms;main._web_log=[];main._web_tool='';main.busy=False
        main.remote_control_active=False;main.entry.get.return_value='';main._web_last_error='';main.workspace='assistant'
        main.mode.get.return_value='RTX 5070';main.dual.get.return_value=False;main.spoken_replies.get.return_value=True
        main.desktop.paused=False;main.desktop.sleeping=False;main.local_mic.active=False
        main.local_mic.telemetry=MicTelemetry();main.reply_voice.active=False;main.reply_voice.service.output_level=0
        main.reply_voice.progress.return_value={'state':'idle'};main.activity.get.return_value='Siap'
        main.hardware=None;main._translation_pending=False;main.translation_progress={};main.last_text_ms=None
        main.companion_last={};main.task_progress=None
        host=DesktopWebHost(main);host.bridge.avatar=ProfileAvatar(folder/'avatar')
        trace=[];prefs.db.set_trace_callback(trace.append)
        profile=cProfile.Profile();profile.enable();samples=[]
        try:
            for i in range(60):
                host.last_update=0
                t=time.perf_counter();host.poll();samples.append((time.perf_counter()-t)*1000)
            profile.disable()
            proof['results']['host_publish']=stats(samples)
            proof['results']['host_publish']['sqlite_statements_per_60_ticks']=len(trace)
            proof['results']['host_publish']['serialized_state_bytes']=len(json.dumps(host.bridge.state,ensure_ascii=False).encode())
            stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(18)
            proof['host_profile']=stream.getvalue()
            # Unchanged /api/state currently builds a full snapshot before replying 204.
            for i in range(120):host.bridge.log('Anda' if i%2 else 'Leva','Synthetic fixture '+('x'*1400))
            snapshot=[]
            for _ in range(40):
                t=time.perf_counter();host.bridge.snapshot();snapshot.append((time.perf_counter()-t)*1000)
            proof['results']['snapshot']=stats(snapshot)
            proof['results']['snapshot']['full_response_bytes']=len(json.dumps(host.bridge.snapshot(),ensure_ascii=False).encode())
        finally:
            prefs.db.set_trace_callback(None);host.stop();rooms.close();prefs.close()
    import tkinter as tk
    from neural_orb import NeuralOrb
    root=tk.Tk();root.withdraw();orb=NeuralOrb(root,width=640,height=420)
    orb.after_cancel(orb.after_id);orb.after_id=None;orb.after=lambda *args:None
    orb.winfo_viewable=lambda:True;orb.winfo_width=lambda:640;orb.winfo_height=lambda:420
    try:
        for state in ('idle','thinking','listening','speaking'):
            orb.mode=state;orb.input_level=.35;orb.output_level=.35
            times=[]
            for _ in range(80):
                t=time.perf_counter();orb.animate();times.append((time.perf_counter()-t)*1000)
            proof['results']['orb_'+state]=stats(times)
    finally:root.destroy()
    (OUT/(phase+'.json')).write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(proof['results'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('discover','baseline','after'))
    args=parser.parse_args()
    discovery() if args.action=='discover' else benchmarks(args.action)
