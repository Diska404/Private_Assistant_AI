"""Local automatic conversation memory. Summaries are source-linked, not model facts."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid

from paths import DATA


def redact_export(text):
    text=re.sub(r'(?i)(api[ _-]?key|password|kata sandi|secret|access[ _-]?token)\s*[:=]\s*\S+',r'\1: [disamarkan]',str(text))
    return re.sub(r'\bAIza[\w-]{25,}\b|\bsk-[\w-]{20,}\b|\bgh[pousr]_[\w]{25,}\b|\bgithub_pat_[\w]{25,}\b','[kredensial disamarkan]',text)

def redact(text):return redact_export(text)[:8000]


class ConversationMemory:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA/'conversation-memory.sqlite3'
        self.session=uuid.uuid4().hex

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=5)
        try:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY,session TEXT,user TEXT,assistant TEXT,created TEXT,receipts TEXT);
                CREATE TABLE IF NOT EXISTS summaries(session TEXT PRIMARY KEY,summary TEXT,first_id INTEGER,last_id INTEGER,updated TEXT);
                CREATE TABLE IF NOT EXISTS agenda(id INTEGER PRIMARY KEY,title TEXT,when_iso TEXT,done INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS watches(id INTEGER PRIMARY KEY,query TEXT UNIQUE,last_checked REAL DEFAULT 0,fingerprint TEXT DEFAULT '');
                CREATE VIRTUAL TABLE IF NOT EXISTS turn_search USING fts5(user,assistant,content='turns',content_rowid='id');
                CREATE TRIGGER IF NOT EXISTS turn_insert AFTER INSERT ON turns BEGIN INSERT INTO turn_search(rowid,user,assistant) VALUES(new.id,new.user,new.assistant);END;
                CREATE TRIGGER IF NOT EXISTS turn_delete AFTER DELETE ON turns BEGIN INSERT INTO turn_search(turn_search,rowid,user,assistant) VALUES('delete',old.id,old.user,old.assistant);END;
            ''')
            with db:yield db
        finally:db.close()

    def record(self,user,assistant,receipts=()):
        if not user.strip() or not assistant.strip():return
        now=datetime.now(timezone.utc).isoformat()
        evidence=[{'name':r.get('name'),'status':r.get('result',{}).get('status')} for r in receipts]
        with self.connection() as db:
            db.execute('INSERT INTO turns(session,user,assistant,created,receipts) VALUES(?,?,?,?,?)',(self.session,redact(user),redact(assistant),now,json.dumps(evidence)))
            rows=db.execute('SELECT id,user,assistant FROM turns WHERE session=? ORDER BY id DESC LIMIT 20',(self.session,)).fetchall()[::-1]
            # An extractive summary preserves the question/answer distinction.
            summary='\n'.join(f'[{r[0]}] Pengguna: {r[1][:180]} | Leva: {r[2][:180]}' for r in rows)
            db.execute('INSERT OR REPLACE INTO summaries VALUES(?,?,?,?,?)',(self.session,summary,rows[0][0],rows[-1][0],now))
            db.execute('DELETE FROM summaries WHERE session NOT IN (SELECT DISTINCT session FROM turns)')

    def recent(self,limit=8):
        with self.connection() as db:rows=db.execute('SELECT user,assistant FROM turns ORDER BY id DESC LIMIT ?',(min(int(limit),20),)).fetchall()[::-1]
        return [message for user,assistant in rows for message in ({'role':'user','content':user},{'role':'assistant','content':assistant})]

    def recall(self,query,limit=5):
        stop={'apa','saya','yang','dan','ini','itu','pernah','kamu','anda','sebelumnya','kemarin','gunakan','memakai','tentang','dengan','tolong','ingat','percakapan','tersimpan'}
        terms=[t for t in re.findall(r'[\w]{3,}',query.casefold()) if t not in stop][:12]
        if not terms:return []
        expression=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
        with self.connection() as db:
            rows=db.execute('SELECT t.id,t.user,t.assistant,t.created FROM turn_search JOIN turns t ON t.id=turn_search.rowid WHERE turn_search MATCH ? ORDER BY rank LIMIT ?',(expression,min(int(limit),10))).fetchall()
        return [dict(zip(('id','user','assistant','created'),r)) for r in rows]

    def overview(self):
        with self.connection() as db:return [{'session':r[0],'summary':r[1],'first_id':r[2],'last_id':r[3],'updated':r[4]} for r in db.execute('SELECT * FROM summaries ORDER BY updated DESC LIMIT 10')]

    def clear(self):
        with self.connection() as db:
            db.execute('DELETE FROM turns');db.execute('DELETE FROM summaries')
            if db.execute("SELECT name FROM sqlite_master WHERE name='semantic_vectors'").fetchone():db.execute('DELETE FROM semantic_vectors')

    def agenda(self):
        with self.connection() as db:return [dict(zip(('id','title','when','done'),r)) for r in db.execute('SELECT * FROM agenda ORDER BY when_iso LIMIT 100')]

    def add_agenda(self,title,when):
        parsed=datetime.fromisoformat(when)
        if parsed.tzinfo is None:raise ValueError('agenda_timezone_required')
        if not title.strip() or len(title)>300:raise ValueError('invalid_agenda')
        with self.connection() as db:ident=db.execute('INSERT INTO agenda(title,when_iso) VALUES(?,?)',(redact(title),parsed.isoformat())).lastrowid
        return {'id':ident,'title':title,'when':parsed.isoformat()}

    def watch(self,query):
        if not 2<=len(query.strip())<=200:raise ValueError('invalid_watch')
        with self.connection() as db:db.execute('INSERT OR IGNORE INTO watches(query) VALUES(?)',(query.strip(),))

    def watches(self):
        with self.connection() as db:return [dict(zip(('id','query','last_checked','fingerprint'),r)) for r in db.execute('SELECT * FROM watches LIMIT 10')]

    def checked(self,ident,stamp,fingerprint):
        with self.connection() as db:db.execute('UPDATE watches SET last_checked=?,fingerprint=? WHERE id=?',(stamp,fingerprint,int(ident)))
