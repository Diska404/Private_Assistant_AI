"""Factual graph adapters; edges only wikilinks and journal tool-call relationships."""
import json
import threading
import time
from second_brain import VaultIndex
from task_journal import TaskJournal
from assistant_tools import SKILLS

class WebData:
    def __init__(self,tools,journal_factory=None):self.tools=tools;self.journal_factory=journal_factory or TaskJournal;self.lock=threading.RLock();self.cached=None;self.cached_at=0
    def graph(self):
        with self.lock:
            if self.cached and time.monotonic()-self.cached_at<3:return self.cached
            nodes=[];edges=[];errors=[]
            def node(ident,label,category,detail,source):nodes.append({'id':ident,'label':label[:100],'category':category,'detail':detail,'source':source})
            try:
                service=self.tools.second_brain
                if service.status()['configured']:
                    index=service.vault();index.refresh()
                    with index.connection() as db:rows=db.execute('SELECT path,meta,sha FROM notes ORDER BY path LIMIT 120').fetchall()
                    notes={r['path']:json.loads(r['meta']) for r in rows}
                    for row in rows:
                        p=row['path'];meta=notes[p]
                        node('note:'+p,meta['title'],'document',{'path':p,'tags':meta['tags'],'sha256':row['sha']},{'kind':'vault_note','path':p})
                        for link in meta['links']:
                            targets=VaultIndex.targets(link,p,notes)
                            if len(targets)==1 and targets[0] in notes:edges.append({'source':'note:'+p,'target':'note:'+targets[0],'relation':'wikilink','provenance':{'note':p,'link':link}})
                else:errors.append('Vault belum dipilih.')
            except Exception as error:errors.append('Vault: '+type(error).__name__)
            for skill in SKILLS:node('skill:'+skill.name,skill.name,'skill',{'description':skill.description},{'kind':'tool_registry','name':skill.name})
            try:
                journal=self.journal_factory()
                for task in journal.recent()[:12]:
                    node('task:'+task['id'],task['goal'][:55],'task',task,{'kind':'task_journal','id':task['id']})
                    detail=journal.get(task['id'])
                    for i,step in enumerate(detail['steps'][-6:],max(0,len(detail['steps'])-6)):
                        ident='step:'+task['id']+':'+str(i)
                        node(ident,step['tool'],'activity',{'tool':step['tool'],'status':step['status']},{'kind':'task_receipt','task':task['id'],'step':i})
                        edges.append({'source':'task:'+task['id'],'target':ident,'relation':'contains_step','provenance':{'task':task['id'],'step':i}})
                        if any(s.name==step['tool'] for s in SKILLS):edges.append({'source':ident,'target':'skill:'+step['tool'],'relation':'calls_tool','provenance':{'task':task['id'],'step':i}})
                for row in self.tools.conversations.overview():
                    node('conversation:'+row['session'],row['summary'][:55],'conversation',{'summary':row['summary'][:2000],'updated':row['updated']},{'kind':'conversation_summary','session':row['session']})
            except Exception as error:errors.append('Riwayat: '+type(error).__name__)
            self.cached={'nodes':nodes,'edges':edges,'errors':errors,'provenance':'Wikilink note dan hubungan task/receipt/alat tersimpan. Tidak ada relasi semantic buatan.','limits':{'notes':120,'tasks':12,'steps_per_task':6},'generated_at':time.time()}
            self.cached_at=time.monotonic();return self.cached
    def panel(self,name):
        if name=='skills':
            from capability_catalog import catalog
            sources=catalog()
            rows=[{'name':s.name,'description':s.description} for s in SKILLS]
            rows += [{'name':'Panduan · '+r['title'],'description':r['description']+' Sumber: '+r['source']} for r in self.tools.workflows.rows()]
            rows += [{'name':'Repo · '+r['repo'],'description':r['integration']+' · '+r['detail']+' · '+r['commit'][:7]} for r in sources['sources']]
            return {'title':'Skill, panduan & sumber kemampuan','rows':rows}
        if name=='memory':return {'title':'Memori percakapan','rows':[{**r,'summary':r['summary'][:1500]} for r in self.tools.conversations.overview()]}
        if name=='tasks':return {'title':'Tugas tersimpan','rows':self.journal_factory().recent()}
        if name=='knowledge':return {'title':'Second Brain','rows':self.tools.second_brain.run({'action':'list','limit':'30'}),'mode':'Baca saja; detail dibaca melalui pertanyaan pada agent yang sama.'}
        if name=='voice':return {'title':'Voice Packs','active_pack':self.tools.desktop.preferences.get('target_voice_pack'),'language':self.tools.desktop.preferences.get('speech_language'),
            'output':self.tools.desktop.preferences.get('output_device_name'),'detail':'Sintesis dan playback menggunakan layanan desktop yang sama. Pratinjau/pemilihan pack lanjutan tersedia di desktop.'}
        if name=='settings':return {'title':'Pengaturan bersama','gpu_route':self.tools.desktop.preferences.get('provider'),'dual_gpu':self.tools.desktop.preferences.get('dual_gpu'),'detail':'Rute, bahasa dan jawaban suara dapat diubah pada footer. Pengaturan perangkat lanjutan dibuka di desktop.'}
        if name=='center':return {'title':'Pusat kendali','knowledge':self.tools.second_brain.status(),'rows':self.journal_factory().recent()[:6]}
        raise ValueError('unknown_panel')
