"""Durable action receipts; interrupted operations are observed again, never replayed."""
from datetime import datetime,timezone
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import sqlite3
import uuid
from conversation_memory import redact
from paths import DATA

class TaskJournal:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA/'tasks.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,goal TEXT,status TEXT,owner INTEGER,updated TEXT);'
                'CREATE TABLE IF NOT EXISTS steps(task TEXT,call_id INTEGER,tool TEXT,args TEXT,result TEXT,status TEXT,PRIMARY KEY(task,call_id));')
            db.execute('CREATE TABLE IF NOT EXISTS checkpoints(task TEXT PRIMARY KEY,parent TEXT,question TEXT DEFAULT "",plan TEXT DEFAULT "")')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        try:
            with db:yield db
        finally:db.close()
    def now(self):return datetime.now(timezone.utc).isoformat()

    def begin(self,goal,parent=''):
        ident=uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?)',(ident,redact(goal)[:8000],'running',os.getpid(),self.now()))
            db.execute('INSERT INTO checkpoints(task,parent) VALUES(?,?)',(ident,parent))
        return ident

    def intent(self,ident,call_id,tool,args):
        values={k:redact(v)[:3000] if isinstance(v,str) else v for k,v in args.items()}
        with self.connect() as db:
            db.execute('INSERT INTO steps VALUES (?,?,?,?,?,?)',(ident,call_id,tool,json.dumps(values,ensure_ascii=False),'{}','dispatching'))
            db.execute('UPDATE tasks SET updated=? WHERE id=?',(self.now(),ident))

    def receipt(self,ident,call_id,result):
        # No screenshots, full documents, page bodies, or credentials in receipts.
        summary={k:result[k] for k in ('status','code','window','input_dispatched','task_verified','process_id','command_id','patch_id','operation_id','exit_code','root','path','cursor','retryable','workflow_id','job_id','engine','prompt_id','workflow_state','published','files','outputs') if k in result}
        summary['reply']=redact(str(result.get('reply','')))[:500]
        with self.connect() as db:
            db.execute('UPDATE steps SET result=?,status=? WHERE task=? AND call_id=?',
                (json.dumps(summary,ensure_ascii=False),str(result.get('status','unknown')),ident,call_id))

    def finish(self,ident,status):
        if status not in ('completed','incomplete','failed','waiting_input','continued','interrupted'):raise ValueError('invalid_task_status')
        with self.connect() as db:db.execute('UPDATE tasks SET status=?,updated=? WHERE id=?',(status,self.now(),ident))

    def recent(self):
        with self.connect() as db:
            rows=db.execute('SELECT id,goal,status,updated FROM tasks ORDER BY updated DESC LIMIT 20').fetchall()
        return [{'id':r[0],'goal':r[1][:300],'status':r[2],'updated':r[3]} for r in rows]

    def get(self,ident):
        if not isinstance(ident,str) or len(ident)!=12 or any(c not in '0123456789abcdef' for c in ident):raise ValueError('invalid_task_id')
        with self.connect() as db:
            task=db.execute('SELECT goal,status FROM tasks WHERE id=?',(ident,)).fetchone()
            rows=db.execute('SELECT tool,args,result,status FROM steps WHERE task=? ORDER BY call_id',(ident,)).fetchall()
            checkpoint=db.execute('SELECT parent,question,plan FROM checkpoints WHERE task=?',(ident,)).fetchone()
        if not task:raise ValueError('task_not_found')
        return {'id':ident,'goal':task[0],'status':task[1],
                'steps':[{'tool':r[0],'args':json.loads(r[1]),'result':json.loads(r[2]),'status':r[3]} for r in rows],
                'parent':checkpoint[0] if checkpoint else '', 'question':checkpoint[1] if checkpoint else '', 'plan':checkpoint[2] if checkpoint else '',
                'requires_fresh_observation':True,'automatic_replay':False}

    def wait_for_input(self,ident,question):
        with self.connect() as db:
            db.execute('UPDATE checkpoints SET question=? WHERE task=?',(redact(question)[:1200],ident))
            db.execute("UPDATE tasks SET status='waiting_input',updated=? WHERE id=?",(self.now(),ident))

    def save_plan(self,ident,plan):
        with self.connect() as db:db.execute('UPDATE checkpoints SET plan=? WHERE task=?',(redact(plan)[:3000],ident))

    def continuation(self,text):
        value=text.casefold().strip();explicit=re.search(r'\b(?:lanjut(?:kan)?|teruskan|resume|pulihkan)\s+(?:tugas\s+)?([0-9a-f]{12})\b',value)
        if explicit:
            try:return self.get(explicit[1])
            except ValueError:return None
        if not value or len(value)>400 or re.match(r'^(?:leva[, ]*)?(?:hai|halo|hello|selamat|terima kasih|makasih|jam berapa|apa kabar)\b',value):return None
        with self.connect() as db:
            row=db.execute("SELECT id,updated FROM tasks WHERE status='waiting_input' ORDER BY updated DESC LIMIT 1").fetchone()
        if not row:return None
        if (datetime.now(timezone.utc)-datetime.fromisoformat(row[1])).total_seconds()>86400:return None
        task=self.get(row[0]);question=task['question'].casefold()
        fresh=re.sub(r'^\s*leva[, ]*','',value).strip()
        if not re.match(r'^[a-z]:[\\/]',fresh) and re.match(r'^(?:apa\b|bagaimana\b|berapa\b|mengapa\b|kenapa\b|menurut\b|berdasarkan\b|bisakah\b|apakah\b|briefing\b)',fresh):return None
        if re.search(r'workflow|sesi gambar|fooocus|comfyui',question) and re.match(r'^(?:(?:buat|bikin)(?:kan)?\s+)?(?:baru(?: saja)?|workflow baru|proyek baru|lanjut(?:kan)?(?: yang)?(?: sudah)?(?: ada)?|pakai|gunakan|pilih)\b',value):return task
        if re.match(r'^(?:leva[, ]*)?(?:(?:tolong|coba|sekarang)\s+)*(?:buka|buat|cari|jalankan|ubah|atur|hapus|jeda|matikan|ingatkan|tampilkan|jelaskan)\b',value):return None
        if any(word in question for word in ('profil','nama','folder','path','pilih','mana','waktu','jam')) or re.match(r'^(?:ya|iya|tidak|pakai|gunakan|pilih|lanjut|boleh|di |ke )\b',value):return task
        return None

    def recover_dead_owners(self):
        import psutil
        count=0
        with self.connect() as db:
            for ident,owner in db.execute("SELECT id,owner FROM tasks WHERE status='running'").fetchall():
                if not psutil.pid_exists(owner):
                    db.execute("UPDATE tasks SET status='interrupted',updated=? WHERE id=?",(self.now(),ident));count+=1
        return count
