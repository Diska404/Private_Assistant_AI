"""Durable reminders and user-authorized goals; no shell code or automatic replay."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import re
import sqlite3
import uuid
from pathlib import Path
from command_resolution import WIB, normalized
from conversation_memory import redact
from paths import DATA

NUMBERS={'satu':1,'dua':2,'tiga':3,'empat':4,'lima':5,'enam':6,'tujuh':7,'delapan':8,'sembilan':9,'sepuluh':10}
NUMBER=r'(?:\d+|'+'|'.join(NUMBERS)+')'
RELATIVE=r'\b(?:dalam|lagi)\s+('+NUMBER+r')\s*(detik|menit|jam)\b|\b('+NUMBER+r')\s*(detik|menit|jam)\s+lagi\b'

def without_not_yet(text):
    # Only a narrowly recognized delay guard; other negations retain their meaning.
    return re.sub(r'\bjangan\s+(?:buka(?:kan)?|jalankan)\s+(?:(?:kedua\s+)?browser|aplikasi|keduanya|apa\s+pun)?\s*(?:sekarang|sebelum\s+waktunya)\b[.!]?\s*$','',text,flags=re.I).strip()


def deferred_request(text):
    value = normalized(without_not_yet(text))
    if re.search(r'\b(jangan|bukan perintah|contoh|terjemahkan|seandainya)\b', value):
        return False
    return bool(re.search(r'\b(ingatkan|ingetin|pengingat|reminder|jadwalkan)\b', value)
                or re.search(r'\b(?:buat|buatkan|catat|tambahkan)\s+(?:(?:saya|sebuah|satu)\s+)*(?:jadwal|memo|agenda)\b', value)
                or (re.search(r'\b(?:jam|pukul)\s*\d{1,2}(?:[:.]\d{2})?\b', value)
                    and re.search(r'\b(?:buka|bukakan|jalankan)\b',value)))


def parse_schedule(text, now=None):
    now = (now or datetime.now(WIB)).astimezone(WIB)
    text=without_not_yet(text)
    value = normalized(text)
    if re.search(r'\b(setiap|berulang|mingguan|harian)\b', value):
        raise ValueError('Jadwal berulang belum tersedia. Sebutkan satu tanggal dan jam terlebih dahulu.')
    relatives=list(re.finditer(RELATIVE,value))
    if len(relatives)>1:raise ValueError('Ada lebih dari satu waktu. Sebutkan satu waktu pengingat.')
    relative=relatives[0] if relatives else None
    clock = list(re.finditer(r'\b(?:jam|pukul)\s*(\d{1,2})(?:[:.](\d{2}))?\b', value))
    if relative:
        if clock:raise ValueError('Ada lebih dari satu waktu. Sebutkan satu waktu pengingat.')
        number=relative[1] or relative[3];unit=relative[2] or relative[4]
        count=int(number) if number.isdigit() else NUMBERS[number]
        seconds = count * {'detik':1,'menit':60,'jam':3600}[unit]
        if not 1 <= seconds <= 366*86400:raise ValueError('Rentang pengingat belum valid.')
        due = now + timedelta(seconds=seconds); span = relative.span()
    elif len(clock) == 1:
        hour, minute = int(clock[0][1]), int(clock[0][2] or 0)
        if hour > 23 or minute > 59:raise ValueError('Gunakan jam 00.00–23.59 WIB.')
        dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', value)
        if len(dates)>1:raise ValueError('Sebutkan satu tanggal pengingat.')
        if dates:
            try:day = datetime.fromisoformat(dates[0]).date()
            except ValueError:raise ValueError('Tanggal pengingat belum valid.') from None
        elif re.search(r'\blusa\b', value):day = (now+timedelta(days=2)).date()
        elif re.search(r'\bbesok\b', value):day = (now+timedelta(days=1)).date()
        else:
            if re.search(r'\b(tanggal|senin|selasa|rabu|kamis|jumat|sabtu|minggu|pekan)\b',value):
                raise ValueError('Sebutkan tanggal dalam format YYYY-MM-DD agar waktu tidak tertukar.')
            day = now.date()
        due = datetime.combine(day,datetime.min.time(),tzinfo=WIB).replace(hour=hour,minute=minute)
        span = clock[0].span()
    else:
        raise ValueError('Jam pengingat belum jelas. Contoh: ingatkan belajar besok jam 19:00.')
    if due <= now:
        raise ValueError('Jam tersebut sudah lewat untuk tanggal itu. Sebutkan besok atau tanggal lain; aku belum membuka aplikasi apa pun.')
    # The execution goal is a literal part of the user's request, never model-invented.
    action = re.search(r'\b(?:buka(?:kan|in)?|jalankan|siapkan|ketik|klik|cari(?:kan)?)\b',text,re.I)
    goal = text[action.start():].strip(' ,;.') if action else ''
    # Remove scheduling words from the deferred goal; the host runs it only when due.
    if goal:
        goal = re.sub(r'\b(?:pada\s+)?(?:jam|pukul)\s*\d{1,2}(?:[:.]\d{2})?\b','',goal,flags=re.I)
        goal = re.sub(r'\b(?:hari ini|malam ini|besok|lusa)\b|\b\d{4}-\d{2}-\d{2}\b','',goal,flags=re.I)
        goal = re.sub(RELATIVE,'',goal,flags=re.I).strip(' ,;.')
    title = text[:action.start()] if action else text
    title = re.sub(r'^\s*(?:leva[, ]*)?(?:tolong\s+)?','',title,flags=re.I)
    title = re.sub(r'\b(?:buatkan|buat|jadwal|memo|pengingat|reminder|ingatkan|ingetin|saya|agar|yaitu|jadwalkan)\b','',title,flags=re.I)
    title = re.sub(r'\b(?:jam|pukul)\s*\d{1,2}(?:[:.]\d{2})?\b|\b(?:habis itu|setelah itu|lalu|langsung|langung)\b','',title,flags=re.I)
    title = re.sub(r'\s+',' ',title).strip(' ,;.')
    return {'title': title[:300] or 'Pengingat tugas', 'when':due.isoformat(),'goal':goal}


class ScheduleStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA/'scheduled-tasks.sqlite3'

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=3)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,title TEXT,due REAL,goal TEXT,status TEXT,notified INTEGER DEFAULT 0,result TEXT DEFAULT "")')
            db.row_factory=sqlite3.Row
            with db:yield db
        finally:db.close()

    def add(self,title,when,goal='',now=None):
        now=now or datetime.now(WIB);due=datetime.fromisoformat(when)
        if due.tzinfo is None or due<=now:raise ValueError('schedule_future_timezone_required')
        if not isinstance(title,str) or not title.strip() or len(title)>300 or len(goal)>3000:raise ValueError('invalid_schedule')
        ident=uuid.uuid4().hex[:12]
        with self.connection() as db:db.execute('INSERT INTO jobs(id,title,due,goal,status) VALUES(?,?,?,?,?)',(ident,redact(title),due.timestamp(),redact(goal),'pending'))
        return {'id':ident,'title':title,'when':due.astimezone(WIB).isoformat(),'goal':goal,'status':'pending'}

    def recent(self):
        with self.connection() as db:rows=db.execute('SELECT * FROM jobs ORDER BY due DESC LIMIT 100').fetchall()
        return [{**dict(r),'when':datetime.fromtimestamp(r['due'],WIB).isoformat()} for r in rows]

    def cancel(self,ident):
        with self.connection() as db:
            return db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status IN ('pending','needs_input')",(ident,)).rowcount==1

    def recover(self):
        with self.connection() as db:
            return db.execute("UPDATE jobs SET status='interrupted',result='Leva terhenti saat tugas berjalan; periksa hasil sebelum melanjutkan.' WHERE status='running'").rowcount

    def notifications(self,now=None):
        now=now or datetime.now(WIB)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT * FROM jobs WHERE status='pending' AND notified=0 AND due<=? ORDER BY due",(now.timestamp(),)).fetchall()
            for row in rows:db.execute('UPDATE jobs SET notified=1 WHERE id=?',(row['id'],))
        return [dict(r) for r in rows]

    def claim(self,now=None):
        now=now or datetime.now(WIB)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM jobs WHERE status='pending' AND due<=? ORDER BY due LIMIT 1",(now.timestamp(),)).fetchone()
            if not row:return None
            status='running' if not row['goal'] or now.timestamp()-row['due']<=900 else 'needs_input'
            db.execute('UPDATE jobs SET status=? WHERE id=?',(status,row['id']))
            return {**dict(row),'status':status}

    def finish(self,ident,status,result=''):
        if status not in ('completed','incomplete','failed','interrupted'):raise ValueError('invalid_schedule_status')
        with self.connection() as db:db.execute("UPDATE jobs SET status=?,result=? WHERE id=? AND status='running'",(status,redact(result)[:1000],ident))


def completion_status(result):
    if result.get('cancelled') or result.get('cancel_ai'):return 'interrupted'
    if result.get('error'):return 'failed'
    receipts=result.get('tool_receipts',[])
    from receipt_state import unresolved_receipts
    if result.get('incomplete') or unresolved_receipts(receipts):return 'incomplete'
    if result.get('status')=='done' or receipts:return 'completed'
    return 'incomplete'
