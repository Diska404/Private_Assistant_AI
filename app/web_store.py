"""Durable delivery receipts and revocable device sessions; no automatic task replay."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid
from conversation_memory import redact

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def delivery_status(result):
    status=result.get('status')
    if result.get('error') or status=='failed':return 'failed'
    if result.get('cancelled') or status=='cancelled':return 'cancelled'
    if result.get('incomplete') or result.get('needs_input') or status=='needs_input':return 'needs_input'
    if status in ('unverified','blocked'):return 'unverified'
    if result.get('image_job_active'):return 'submitted'
    return 'completed'

class WebStore:
    def __init__(self,path=None):
        if path:Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.db=sqlite3.connect(str(path) if path else ':memory:',check_same_thread=False,timeout=3)
        self.db.row_factory=sqlite3.Row
        with self.transaction() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT,token_hash TEXT UNIQUE,created REAL,expires REAL,seen REAL,revoked INTEGER DEFAULT 0);'
                'CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY,owner TEXT,fingerprint TEXT,kind TEXT,goal TEXT,status TEXT,detail TEXT,task_id TEXT,created REAL,updated REAL);'
                'CREATE INDEX IF NOT EXISTS delivery_created ON deliveries(created DESC);')
            # Never silently re-run a possibly completed desktop action after restart.
            db.execute("UPDATE deliveries SET status='interrupted',detail='Server dimulai ulang; periksa hasil sebelum melanjutkan.',updated=? WHERE status IN ('queued','running','dispatched')",(time.time(),))
    @contextmanager
    def transaction(self):
        with self.lock:
            with self.db:yield self.db
    def device(self,name):
        if not isinstance(name,str) or not 1<=len(name.strip())<=40 or any(ord(c)<32 for c in name):raise ValueError('invalid_device_name')
        token=secrets.token_urlsafe(32);ident=uuid.uuid4().hex;now=time.time()
        with self.transaction() as db:db.execute('INSERT INTO devices VALUES(?,?,?,?,?,?,0)',(ident,name.strip(),digest(token),now,now+30*86400,now))
        return ident,token
    def authenticate(self,token):
        with self.transaction() as db:
            row=db.execute('SELECT id,name,expires FROM devices WHERE token_hash=? AND revoked=0 AND expires>?',(digest(token),time.time())).fetchone()
            if row:db.execute('UPDATE devices SET seen=? WHERE id=? AND seen<?',(time.time(),row['id'],time.time()-60))
        return dict(row) if row else None
    def active(self,ident):
        if ident=='desktop':return True
        with self.transaction() as db:return db.execute('SELECT 1 FROM devices WHERE id=? AND revoked=0 AND expires>?',(ident,time.time())).fetchone() is not None
    def devices(self):
        with self.transaction() as db:return [dict(r) for r in db.execute('SELECT id,name,created,expires,seen,revoked FROM devices ORDER BY created DESC')]
    def revoke(self,ident):
        with self.transaction() as db:db.execute('UPDATE devices SET revoked=1 WHERE id=?',(ident,))
    def reserve(self,job,owner):
        fingerprint=digest(json.dumps([job['kind'],job.get('value')],ensure_ascii=False,sort_keys=True));now=time.time()
        with self.transaction() as db:
            old=db.execute('SELECT * FROM deliveries WHERE id=?',(job['id'],)).fetchone()
            if old:
                if old['owner']!=owner or old['fingerprint']!=fingerprint:raise ValueError('idempotency_conflict')
                return self.public(old)
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?,?,?)',(job['id'],owner,fingerprint,job['kind'],redact(str(job.get('value','')))[:3000],'queued','','',now,now))
            # Keep a bounded delivery ledger; the full task journal is separate.
            db.execute("DELETE FROM deliveries WHERE id IN (SELECT id FROM deliveries ORDER BY created DESC LIMIT -1 OFFSET 3000) AND status NOT IN ('queued','running')")
        return None
    @staticmethod
    def public(row):return {k:row[k] for k in ('id','kind','goal','status','detail','task_id','created','updated')}
    def finish(self,ident,status,detail='',task_id=''):
        with self.transaction() as db:db.execute('UPDATE deliveries SET status=?,detail=?,task_id=?,updated=? WHERE id=?',(status,redact(str(detail))[:8000],task_id,time.time(),ident))
    def recent(self,owner=None):
        with self.transaction() as db:
            rows=db.execute('SELECT * FROM deliveries '+('WHERE owner=? ' if owner else '')+'ORDER BY created DESC LIMIT 30',(owner,) if owner else ()).fetchall()
        return [self.public(r) for r in rows]
    def close(self):
        with self.lock:self.db.close()

class PairingGate:
    def __init__(self):self.lock=threading.Lock();self.code_hash='';self.expires=0;self.attempts=0
    def begin(self):
        code=f'{secrets.randbelow(100000000):08d}'
        with self.lock:self.code_hash=digest(code);self.expires=time.time()+300;self.attempts=0
        return code
    def consume(self,code):
        import hmac
        with self.lock:
            if not self.code_hash or time.time()>self.expires or self.attempts>=5:return False
            self.attempts+=1
            ok=isinstance(code,str) and hmac.compare_digest(digest(code),self.code_hash)
            if ok:self.code_hash=''
            return ok
