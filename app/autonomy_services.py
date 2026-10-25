"""Bounded background services, declarative plugins and per-user startup."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from paths import DATA

PLUGIN_SKILLS={'web_search':('query',),'get_weather':('city',),'get_news':(),'get_time':(),'get_metrics':(),'get_agenda':()}

class PluginManager:
    def __init__(self,folder=None):
        self.folder=Path(folder) if folder else DATA/'plugins'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.plugins={};self.errors=[];self.reload()

    def reload(self):
        self.plugins={};self.errors=[]
        for path in sorted(self.folder.glob('*.json'))[:30]:
            try:
                data=json.loads(path.read_text(encoding='utf-8-sig'))
                if set(data)-{'name','description','skill','args'} or data['skill'] not in PLUGIN_SKILLS:raise ValueError('unsupported_plugin')
                if not isinstance(data['name'],str) or not 1<=len(data['name'])<=60:raise ValueError('invalid_plugin_name')
                if set(data.get('args',{}))!=set(PLUGIN_SKILLS[data['skill']]):raise ValueError('invalid_plugin_arguments')
                if any(not isinstance(value,str) or len(value)>500 for value in data['args'].values()):raise ValueError('invalid_plugin_arguments')
                self.plugins[data['name']]=data
            except (OSError,ValueError,KeyError,TypeError) as error:self.errors.append({'file':path.name,'error':type(error).__name__})
        return self.public()

    def public(self):return [{'name':p['name'],'description':str(p.get('description',''))[:200],'skill':p['skill']} for p in self.plugins.values()]

    def resolve(self,name,text):
        plugin=self.plugins.get(name)
        if not plugin:raise ValueError('unknown_plugin')
        return plugin['skill'],{key:value.replace('{input}',text[:500]) for key,value in plugin['args'].items()}


def startup(enabled,exe=None):
    import winreg
    path=Path(exe or sys.executable).resolve()
    if enabled and (path.name.casefold()!='leva.exe' or not path.is_file()):raise ValueError('startup_requires_packaged_leva')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'LevaAssistant',0,winreg.REG_SZ,'"'+str(path)+'" --background')
        else:
            try:winreg.DeleteValue(key,'LevaAssistant')
            except FileNotFoundError:pass
    return {'status':'done','reply':'Startup Leva '+('diaktifkan; aplikasi akan dimulai diminimalkan saat login Windows.' if enabled else 'dinonaktifkan.')}


class HardwareMonitor:
    def __init__(self):self.value={};self.stop_event=threading.Event();self.thread=None
    def start(self):
        if self.thread and self.thread.is_alive():self.stop_event.clear();return
        self.stop_event.clear()
        def run():
            import psutil
            while not self.stop_event.is_set():
                ram=psutil.virtual_memory();gpus=[]
                try:
                    result=subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,clocks.current.sm','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=0x08000000)
                    for line in result.stdout.splitlines():
                        values=[p.strip() for p in line.split(',')]
                        if len(values)==6:gpus.append(dict(zip(('name','used_mib','total_mib','utilization','temperature_c','sm_clock_mhz'),values)))
                except (OSError,subprocess.TimeoutExpired):pass
                self.value={'status':'done','reply':'Metrik perangkat aktual.','cpu_percent':psutil.cpu_percent(),'ram_used_gib':round(ram.used/2**30,1),'ram_total_gib':round(ram.total/2**30,1),'gpus':gpus,'measured_at':time.time()}
                self.stop_event.wait(2)
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
    def stop(self):self.stop_event.set()


class ProactiveService:
    """No autonomous UI actions. Read-only watches emit only changed results."""
    def __init__(self,memory,bridge):self.memory=memory;self.bridge=bridge;self.busy=False;self.last_tick=0
    def tick(self,emit,allowed):
        if self.busy or not allowed() or time.time()-self.last_tick<60:return
        self.last_tick=time.time();self.busy=True
        def run():
            try:
                for watch in self.memory.watches():
                    if not allowed() or time.time()-watch['last_checked']<1800:continue
                    result=self.bridge.run('web_search',{'query':watch['query']},authorized=allowed,timeout=20)
                    if result.get('status')!='done':continue
                    sources=result.get('sources',[])[:3]
                    fingerprint=hashlib.sha256(json.dumps([r['url'] for r in sources],sort_keys=True).encode()).hexdigest()
                    self.memory.checked(watch['id'],time.time(),fingerprint)
                    if sources and fingerprint!=watch['fingerprint'] and allowed():emit('Pantauan “'+watch['query']+'”: '+ '\n'.join(r['title']+' — '+r['url'] for r in sources))
                if allowed():self.bridge.run('semantic_search',{'query':'','path':str(self.memory.path)},authorized=allowed,timeout=45)
            finally:self.busy=False
        threading.Thread(target=run,daemon=True).start()
