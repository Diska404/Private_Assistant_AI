"""Full ASR turns and durable command inbox; no audio is persisted."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import time
import uuid


def unfinished_utterance(text):
    """Conservative endpoint hint; never fills in missing words or permissions."""
    import re
    return bool(re.search(r'\b(?:dan|atau|lalu|kemudian|dengan|untuk|yang|seperti|misalnya|karena|agar|menggunakan|gunakan|memakai|pakai|tentang|berupa)\s*[,.;:!?]*$',text,re.I))


class TurnWindow:
    """Join short ASR segments until a genuine pause, or explicit dictation stop."""
    def __init__(self,ident):
        self.ident=ident;self.started=None;self.last_voice=None;self.pending=0;self.parts=0;self.text=''
        self.lock=threading.RLock()
    def voiced(self,now):
        with self.lock:
            if self.started is None:self.started=now
            self.last_voice=now
    def submitted(self):
        with self.lock:self.pending+=1;self.parts+=1
    def recognized(self,ident,text):
        with self.lock:
            if ident==self.ident:self.pending=max(0,self.pending-1);self.text=text
    def finish(self,now,manual=False):
        with self.lock:
            if manual or not self.parts or self.pending or self.last_voice is None:return None
            quiet=now-self.last_voice
            if quiet<2:return None
            if unfinished_utterance(self.text):return 'incomplete' if quiet>=15 else None
            return 'complete'


class TurnAssembler:
    """Length-limited ASR chunks are never separate executable commands."""
    def __init__(self):self.parts={}

    def append(self,ident,text,final,asr_ms=0,incomplete=False):
        row=self.parts.setdefault(ident,{'texts':[],'asr_ms':0,'incomplete':False})
        if text:row['texts'].append(text)
        row['asr_ms']+=asr_ms;row['incomplete']|=incomplete
        result={'turn_id':ident,'text':' '.join(row['texts']),'asr_ms':round(row['asr_ms'],1),
                'incomplete':row['incomplete'],'final':final}
        if final:self.parts.pop(ident,None)
        return result


class SpeechJournal:
    STATES={'collecting','awaiting_wake','wake_only','echo','empty','incomplete','queued','waiting_draft',
            'running','completed','failed','interrupted','cancelled','needs_input','too_long'}
    def __init__(self,path=None):
        if path is None:
            from paths import DATA
            path=DATA/'speech-input.sqlite3'
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS utterances(
                id TEXT PRIMARY KEY, created TEXT, updated TEXT, text TEXT, command TEXT,
                reason TEXT, state TEXT, asr_ms REAL, detail TEXT)''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def capture(self,event):
        ident=event.get('turn_id') or uuid.uuid4().hex
        reason=event.get('reason','awaiting_wake');text=str(event.get('text',''))
        command=str(event.get('command',''))
        accepted=bool(event.get('accepted'))
        state='queued' if accepted and command else 'wake_only' if accepted else reason
        if event.get('final') is False:state='collecting'
        if state not in self.STATES:state='awaiting_wake'
        if event.get('incomplete'):state='incomplete'
        if len(command)>3000:state='too_long'
        now=datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('''INSERT INTO utterances VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,text=excluded.text,
                command=excluded.command,reason=excluded.reason,state=excluded.state,asr_ms=excluded.asr_ms
                WHERE utterances.state='collecting' ''',
                       (ident,now,now,text,command,reason,state,event.get('asr_ms',0),''))
        return self.get(ident)

    def update(self,ident,state,detail=''):
        if state not in self.STATES:raise ValueError('invalid_speech_state')
        with self.connect() as db:
            db.execute('UPDATE utterances SET state=?,detail=?,updated=? WHERE id=?',
                       (state,detail,datetime.now(timezone.utc).isoformat(),ident))

    def get(self,ident):
        with self.connect() as db:row=db.execute('SELECT * FROM utterances WHERE id=?',(ident,)).fetchone()
        return dict(row) if row else None

    def recent(self,limit=100):
        with self.connect() as db:rows=db.execute('SELECT * FROM utterances ORDER BY created DESC LIMIT ?', (limit,)).fetchall()
        return [dict(row) for row in rows]

    def pending(self):
        with self.connect() as db:rows=db.execute("SELECT * FROM utterances WHERE state IN ('queued','waiting_draft') ORDER BY created").fetchall()
        return [dict(row) for row in rows]

    def recover(self):
        # Never replay desktop actions automatically after a restart.
        with self.connect() as db:
            db.execute("UPDATE utterances SET state='interrupted',detail='Sesi berakhir; periksa sebelum menjalankan ulang.' WHERE state IN ('collecting','queued','waiting_draft','running')")

    def cancel_pending(self):
        with self.connect() as db:db.execute("UPDATE utterances SET state='cancelled' WHERE state IN ('queued','waiting_draft')")

    def fail_collecting(self,detail):
        with self.connect() as db:db.execute("UPDATE utterances SET state='incomplete',detail=? WHERE state='collecting'",(detail,))

    def clear(self):
        with self.connect() as db:db.execute("DELETE FROM utterances WHERE state NOT IN ('collecting','queued','waiting_draft','running')")


STATUS_LABELS={'collecting':'Menyusun ucapan lengkap · belum dijalankan','awaiting_wake':'Belum dijalankan · nama Leva belum dikenali',
    'wake_only':'Panggilan diterima · menunggu perintah','echo':'Diabaikan · kemungkinan gema',
    'empty':'Tidak ada teks dikenali','incomplete':'Audio tidak lengkap · tidak dijalankan',
    'queued':'Mengantre · belum dijalankan','waiting_draft':'Menunggu draf ketikan dikirim/dikosongkan',
    'running':'Sedang diproses','completed':'Sudah ditanggapi','failed':'Pemrosesan gagal',
    'interrupted':'Terputus · perlu diperiksa','cancelled':'Dibatalkan','needs_input':'Memerlukan arahan',
    'too_long':'Tersimpan penuh · pecah perintah menjadi bagian di bawah 3.000 karakter'}


def stop_request(text):
    import re
    return bool(re.fullmatch(r'(?:tolong\s+)?(?:hentikan|batalkan|stop)(?:\s+(?:tugas|proses|permintaan))(?:\s+(?:ini|sekarang|yang sedang berjalan))?[.!?]*',text.strip(),re.I))
