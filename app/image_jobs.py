"""Small persistent image-job observer; no LLM and no automatic submission/replay."""
from pathlib import Path
import json
import sqlite3
from contextlib import contextmanager
from paths import DATA


class ImageJobs:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA/'image-jobs.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS jobs(engine TEXT,id TEXT,state TEXT,noticed INTEGER DEFAULT 0,result TEXT DEFAULT "{}",PRIMARY KEY(engine,id))')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        try:
            with db:yield db
        finally:db.close()
    def track(self,engine,ident):
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO jobs(engine,id,state) VALUES(?,?,"pending")',(engine,ident))
    def pending(self):
        with self.connect() as db:return db.execute('SELECT engine,id FROM jobs WHERE noticed=0 LIMIT 5').fetchall()
    def observe(self,tools):
        updates=[]
        for engine,ident in self.pending():
            try:
                service=tools.fooocus_service if engine=='fooocus' else tools.comfy_service
                result=service.poll(ident)
            except (OSError,ValueError):continue  # An offline server is not a reason to replay a job.
            if result.get('status') not in ('done','failed','unverified','cancelled'):continue
            with self.connect() as db:db.execute('UPDATE jobs SET state=?,result=? WHERE engine=? AND id=?',(result['status'],json.dumps(result,ensure_ascii=False),engine,ident))
            updates.append({'engine':engine,'id':ident,'result':result})
        return updates
    def acknowledge(self,engine,ident):
        with self.connect() as db:db.execute('UPDATE jobs SET noticed=1 WHERE engine=? AND id=?',(engine,ident))
