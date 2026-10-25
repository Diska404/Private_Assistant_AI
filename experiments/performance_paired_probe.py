"""Paired old/new CPU and HTTP fixtures from the saved source checkpoint."""
import io
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import types
import urllib.request
from unittest.mock import Mock,patch
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\performance-20261024')
from performance_audit import stats

def old_module(file):
    module=types.ModuleType('baseline_'+file.removesuffix('.py'))
    with zipfile.ZipFile(OUT/'source-before.zip') as archive:code=archive.read('app/'+file)
    exec(compile(code,'baseline-checkpoint/'+file,'exec'),module.__dict__)
    return module

def main():
    from neural_orb import NeuralOrb
    import tkinter as tk
    old=old_module('neural_orb.py');results={}
    root=tk.Tk();root.withdraw();orbs=[old.NeuralOrb(root,width=640,height=420),NeuralOrb(root,width=640,height=420)]
    for orb in orbs:
        orb.after_cancel(orb.after_id);orb.after_id=None;orb.after=lambda *a:None
        orb.winfo_viewable=lambda:True;orb.winfo_width=lambda:640;orb.winfo_height=lambda:420;orb.started=0
    try:
        for state in ('idle','thinking','listening','speaking'):
            rows=[[],[]]
            for orb in orbs:orb.mode=state;orb.input_level=orb.output_level=.35
            for frame in range(100):
                with patch.object(old.time,'monotonic',return_value=frame*.05):
                    for i in ([0,1] if frame%2==0 else [1,0]):
                        t=time.perf_counter();orbs[i].animate();elapsed=(time.perf_counter()-t)*1000
                        if frame>=20:rows[i].append(elapsed)
                root.update_idletasks()
            for old_item,new_item in zip(orbs[0].nodes,orbs[1].nodes):
                assert orbs[0].coords(old_item)==orbs[1].coords(new_item),state
                assert orbs[0].itemcget(old_item,'fill')==orbs[1].itemcget(new_item,'fill'),state
            results['orb_'+state]={'before':stats(rows[0]),'after':stats(rows[1]),'node_positions_colors_identical':True}
    finally:root.destroy()
    from web_bridge import WebBridge
    from web_store import WebStore
    from profile_avatar import ProfileAvatar
    old_bridge=old_module('web_bridge.py').WebBridge
    def http_probe(Type,folder):
        bridge=Type(Mock(),port=0,store=WebStore(),avatar=ProfileAvatar(folder/'avatar'))
        bridge.update({'phase':'idle','fixture_padding':'x'*5000})
        for i in range(120):bridge.log('Anda' if i%2 else 'Leva','Synthetic '+('x'*1400))
        cursor=bridge.logs[-1]['id'];bridge.start();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));rows=[];sizes=[]
        recent_calls=0;original=bridge.store.recent
        def recent():
            nonlocal recent_calls
            recent_calls+=1;return original()
        bridge.store.recent=recent
        def get(since):
            request=urllib.request.Request(bridge.origin+'/api/state?since='+str(since)+'&instance='+bridge.instance+'&messages_since='+str(cursor),
                headers={'Cookie':'leva_session='+bridge.cookie})
            t=time.perf_counter()
            with opener.open(request,timeout=3) as response:raw=response.read();status=response.status
            return (time.perf_counter()-t)*1000,len(raw),status
        try:
            revision=bridge.revision
            for i in range(35):
                bridge.update({'phase':'idle','fixture_padding':'x'*5000,'hardware_tick':i})
                ms,size,status=get(revision);assert status==200
                revision=bridge.revision
                if i>=5:rows.append(ms);sizes.append(size)
            changed_recent=recent_calls
            unchanged=[]
            for i in range(35):
                ms,size,status=get(revision);assert status==204 and size==0
                if i>=5:unchanged.append(ms)
            return {'changed':stats(rows),'unchanged':stats(unchanged),'median_changed_bytes':statistics.median(sizes),
                'unchanged_delivery_queries':recent_calls-changed_recent,'changed_samples':len(rows)}
        finally:bridge.stop();bridge.store.close()
    with tempfile.TemporaryDirectory(prefix='leva-http-perf-') as folder:
        folder=Path(folder)
        results['http']={'before':http_probe(old_bridge,folder/'old'),'after':http_probe(WebBridge,folder/'new')}
    report={'method':'Same process, alternating old/new Tk frames; withdrawn Tk Canvas, not display FPS. Loopback authenticated HTTP with synthetic 120-message history and 5 KB state.',
        'results':results,'microphone_opened':False,'production_restarted':False}
    (OUT/'paired.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
