"""VIDEO_001: bounded, read-only Markdown retrieval; independent of LLM/GPU/Obsidian."""
from contextlib import contextmanager
from datetime import datetime,timezone
import fnmatch
import hashlib
import json
import ntpath
import os
from pathlib import Path,PurePosixPath
import re
import sqlite3
import threading
import time
from urllib.parse import quote

from conversation_memory import redact
from file_workspace import checked_path,PROTECTED
from paths import DATA

MAX_NOTES=2000
MAX_FILE_BYTES=128000
EXCLUDED={'node_modules','venv','__pycache__','attachments'}

def vault_root(value):
    try:root=checked_path(str(value))
    except RuntimeError:raise ValueError('vault_folder_required') from None
    if not root.is_dir() or root==Path(root.anchor) or any(p.startswith('.') for p in root.parts):raise ValueError('vault_folder_required')
    return root

def relative_note(value):
    if not isinstance(value,str) or not value or len(value)>1000 or any(c in value for c in '\x00\r\n:'):raise ValueError('invalid_note_path')
    value=value.replace('\\','/')
    path=PurePosixPath(value)
    if path.is_absolute() or ntpath.isabs(value) or any(p in ('.','..') or p.startswith('.') or PROTECTED.fullmatch(p) for p in value.split('/')):raise ValueError('note_outside_vault_or_excluded')
    if path.suffix.casefold()!='.md':raise ValueError('markdown_note_required')
    return path.as_posix()

def clean_note(text):
    # Reuse the existing secret redactor without its per-message 8k truncation
    # discarding the rest of a long note. Oversized individual lines remain capped.
    return ''.join(redact(line) for line in text.splitlines(keepends=True))

def metadata(text,path):
    lines=text.splitlines();front={};end=0
    if lines and lines[0].strip()=='---':
        end=next((i for i,row in enumerate(lines[1:101],1) if row.strip()=='---'),0)
        current=''
        for row in lines[1:end]:
            match=re.match(r'^(title|tags|aliases):\s*(.*)$',row,re.I)
            if match:
                current=match[1].lower();front[current]=match[2].strip(' \"\'[]')
            elif current and re.match(r'^\s+-\s+',row):front[current]+=', '+re.sub(r'^\s+-\s+','',row).strip(' \"\'')
    headings=[];fenced=False
    for i,row in enumerate(lines,1):
        if i<=end+1 and end:continue
        if re.match(r'^\s*(```|~~~)',row):fenced=not fenced;continue
        match=re.match(r'^(#{1,6})\s+(.+?)\s*#*$',row)
        if match and not fenced:headings.append({'text':match[2][:200],'level':len(match[1]),'line':i})
    tags=set(re.findall(r'(?<!\w)#([^\W\d][\w/-]*)',text,re.UNICODE))
    tags.update(t.strip(' #\"\'') for t in re.split(r'[,\s]+',front.get('tags','')) if t.strip())
    aliases=[v.strip(' \"\'')[:100] for v in front.get('aliases','').split(',') if v.strip()]
    links=list(dict.fromkeys(re.findall(r'(?<!!)\[\[([^\]\n]{1,1000})\]\]',text)))
    return {'title':(front.get('title') or (headings[0]['text'] if headings else PurePosixPath(path).stem))[:200],
            'tags':sorted(t[:60] for t in tags)[:40],'aliases':aliases[:20],'headings':headings[:200],'links':links[:100]}

class VaultIndex:
    def __init__(self,root,storage=None):
        self.root=vault_root(root);self.storage=Path(storage) if storage else DATA/'second-brain'
        identity=hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:20]
        self.db_path=self.storage/(identity+'.sqlite3');self.lock=threading.RLock();self.last={}

    @contextmanager
    def connection(self):
        self.storage.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.db_path,timeout=5);db.row_factory=sqlite3.Row
        try:
            db.executescript('''CREATE TABLE IF NOT EXISTS notes(path TEXT PRIMARY KEY,mtime INTEGER,size INTEGER,sha TEXT,body TEXT,meta TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS note_search USING fts5(path UNINDEXED,title,tags,headings,body);''')
            with db:yield db
        finally:db.close()

    def path(self,relative):
        relative=relative_note(relative);target=self.root/relative
        try:resolved=target.resolve()
        except RuntimeError:raise ValueError('note_invalid_link') from None
        if not resolved.is_relative_to(self.root):raise ValueError('note_outside_vault_or_excluded')
        if resolved!=target:raise ValueError('note_link_not_allowed')
        if any(p.casefold() in EXCLUDED for p in PurePosixPath(relative).parts):raise ValueError('note_outside_vault_or_excluded')
        rules=[];parts=PurePosixPath(relative).parts;folder=self.root
        for i,part in enumerate(parts):
            base='/'.join(parts[:i]);rules.extend((base,p) for p in self.rules(folder))
            if self.ignored('/'.join(parts[:i+1]),i<len(parts)-1,rules):raise ValueError('note_excluded_by_rules')
            folder/=part
        return target

    @staticmethod
    def read_bytes(path):
        with path.open('rb') as f:raw=f.read(MAX_FILE_BYTES+1)
        if len(raw)>MAX_FILE_BYTES:raise ValueError('note_too_large')
        return raw

    @staticmethod
    def rules(folder):
        result=[]
        for name in ('.gitignore','.levaignore'):
            p=folder/name
            if p.is_symlink() or getattr(p,'is_junction',lambda:False)():continue
            if p.is_file() and p.stat().st_size<=32000:
                result.extend(row.strip() for row in p.read_text('utf-8-sig',errors='replace').splitlines() if row.strip() and not row.lstrip().startswith('#'))
        return result

    @staticmethod
    def ignored(relative,is_dir,rules):
        """Common gitignore globs; local .levaignore may provide explicit exclusions."""
        ignored=False
        for base,pattern in rules:
            negate=pattern.startswith('!');pattern=pattern[1:] if negate else pattern
            if pattern.endswith('/') and not is_dir:continue
            pattern=pattern.rstrip('/');local=relative[len(base)+1:] if base else relative
            if base and not relative.startswith(base+'/'):continue
            anchored=pattern.startswith('/');pattern=pattern.lstrip('/')
            match=fnmatch.fnmatchcase(local,pattern) if '/' in pattern or anchored else any(fnmatch.fnmatchcase(p,pattern) for p in local.split('/'))
            if pattern.startswith('**/'):match=match or fnmatch.fnmatchcase(local,pattern[3:])
            if match:ignored=not negate
        return ignored

    def scan(self,authorized):
        found={};skipped=0;errors=0;truncated=False;rules={};seen=0
        def walk_error(error):
            nonlocal errors
            errors+=1
        for base,dirs,files in os.walk(self.root,followlinks=False,onerror=walk_error):
            folder=Path(base);relative=folder.relative_to(self.root).as_posix();relative='' if relative=='.' else relative
            inherited=rules.get(folder.parent,[])
            try:current=[*inherited,*[(relative,p) for p in self.rules(folder)]]
            except OSError:current=inherited;errors+=1
            rules[folder]=current
            keep=[]
            for d in dirs:
                p=folder/d;rel=p.relative_to(self.root).as_posix()
                try:resolved=p.resolve();valid=resolved==p and resolved.is_relative_to(self.root)
                except (OSError,RuntimeError):valid=False
                if d.startswith('.') or d.casefold() in EXCLUDED or PROTECTED.fullmatch(d) or not valid or self.ignored(rel,True,current):skipped+=1;continue
                keep.append(d)
            dirs[:]=keep
            for name in files:
                seen+=1
                if not authorized():raise ValueError('vault_scan_cancelled')
                if seen>20000 or len(found)>=MAX_NOTES:truncated=True;break
                if not name.lower().endswith('.md'):continue
                rel=(folder/name).relative_to(self.root).as_posix()
                try:
                    p=self.path(rel)
                    if self.ignored(rel,False,current):skipped+=1;continue
                    stat=p.stat()
                    if stat.st_size>MAX_FILE_BYTES:skipped+=1;continue
                    found[rel]=(stat.st_mtime_ns,stat.st_size)
                except (OSError,ValueError):errors+=1
            if truncated:break
        return found,{'skipped':skipped,'errors':errors,'scan_truncated':truncated}

    def refresh(self,force=False,authorized=lambda:True):
        began=time.perf_counter()
        with self.lock:
            found,info=self.scan(authorized);changed=0;removed=0
            with self.connection() as db:
                existing={r['path']:r for r in db.execute('SELECT path,mtime,size FROM notes')}
                valid=set(found)
                for relative,stat in found.items():
                    if not force and relative in existing and (existing[relative]['mtime'],existing[relative]['size'])==stat:continue
                    try:
                        raw=self.read_bytes(self.path(relative))
                        text=clean_note(raw.decode('utf-8-sig'));meta=metadata(text,relative)
                    except (OSError,ValueError):info['errors']+=1;valid.discard(relative);continue
                    digest=hashlib.sha256(raw).hexdigest()
                    db.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?,?,?)',(relative,*stat,digest,text,json.dumps(meta,ensure_ascii=False)))
                    db.execute('DELETE FROM note_search WHERE path=?',(relative,))
                    db.execute('INSERT INTO note_search VALUES(?,?,?,?,?)',(relative,meta['title'],' '.join(meta['tags']),' '.join(h['text'] for h in meta['headings']),text));changed+=1
                for relative in set(existing)-valid:
                    db.execute('DELETE FROM notes WHERE path=?',(relative,));db.execute('DELETE FROM note_search WHERE path=?',(relative,));removed+=1
                count=db.execute('SELECT count(*) FROM notes').fetchone()[0]
            self.last={**info,'notes':count,'updated':changed,'removed':removed,'elapsed_ms':round((time.perf_counter()-began)*1000,2),'cache_bytes':self.db_path.stat().st_size}
            self.audit('refresh',self.last['elapsed_ms'],count)
            return self.last

    def audit(self,action,elapsed,count):
        # No query, note text, token, or absolute vault path is written to audit.
        self.storage.mkdir(parents=True,exist_ok=True)
        log=self.storage/'audit.jsonl'
        if log.exists() and log.stat().st_size>1000000:log.replace(self.storage/'audit.previous.jsonl')
        with log.open('a',encoding='utf8') as f:f.write(json.dumps({'video_id':'VIDEO_001','at':datetime.now(timezone.utc).isoformat(),'action':action,'elapsed_ms':elapsed,'count':count})+'\n')

    def source(self,path,body,meta,sha,mtime,start=1,limit=60):
        lines=body.splitlines();start=max(1,min(int(start),max(1,len(lines))));limit=max(1,min(int(limit),120))
        content='\n'.join(lines[start-1:start-1+limit])[:6000]
        heading=next((h['text'] for h in reversed(meta['headings']) if h['line']<=start),meta['title'])
        return {'path':path,'title':meta['title'],'heading':heading,'line_start':start,'line_end':start+len(content.splitlines())-1,
            'excerpt':content,'truncated':start-1+limit<len(lines) or len('\n'.join(lines[start-1:start-1+limit]))>6000,
            'sha256':sha,'modified_at':datetime.fromtimestamp(mtime/1e9,timezone.utc).isoformat(),
            'uri':'obsidian://open?vault='+quote(self.root.name,safe='')+'&file='+quote(path,safe='')}

    def read(self,path,start=1,limit=60):
        p=self.path(path);raw=self.read_bytes(p)
        text=clean_note(raw.decode('utf-8-sig'));meta=metadata(text,path)
        return self.source(relative_note(path),text,meta,hashlib.sha256(raw).hexdigest(),p.stat().st_mtime_ns,start,limit)

    def notes(self,limit=30):
        self.refresh()
        with self.connection() as db:
            rows=[];budget=6000
            for r in db.execute('SELECT path,meta FROM notes ORDER BY path LIMIT ?',(max(1,min(int(limit),100)),)):
                row={'path':r['path'],**{k:v for k,v in json.loads(r['meta']).items() if k in ('title','tags')}}
                size=len(json.dumps(row,ensure_ascii=False))
                if size>budget:break
                rows.append(row);budget-=size
            return rows

    def search(self,query,limit=5):
        began=time.perf_counter();self.refresh()
        terms=re.findall(r'\w+',query,re.UNICODE)[:20]
        if not terms:return []
        expression=' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
        with self.connection() as db:
            rows=db.execute('SELECT n.* FROM note_search s JOIN notes n ON n.path=s.path WHERE note_search MATCH ? ORDER BY bm25(note_search,0,8,5,3,1),n.path LIMIT ?',
                (expression,max(1,min(int(limit),8)))).fetchall()
        result=[];budget=6000
        for row in rows:
            lines=row['body'].splitlines();positions=[i for i,line in enumerate(lines) if any(t.casefold() in line.casefold() for t in terms)]
            start=max(1,(positions[0]+1 if positions else 1)-2)
            source=self.source(row['path'],row['body'],json.loads(row['meta']),row['sha'],row['mtime'],start,12)
            allowance=min(1800,budget);original=source['excerpt'];source['excerpt']=original[:allowance]
            source['truncated']=source['truncated'] or len(original)>allowance
            source['line_end']=source['line_start']+len(source['excerpt'].splitlines())-1
            budget-=len(source['excerpt']);result.append(source)
            if budget<=0:break
        self.audit('search',round((time.perf_counter()-began)*1000,2),len(result));return result

    @staticmethod
    def targets(link,origin,notes):
        target=link.split('|',1)[0].split('#',1)[0].strip().replace('\\','/')
        if not target:return [origin]
        if target.startswith('/') or '..' in target.split('/'):return []
        target=re.sub(r'\.md$','',target,flags=re.I).casefold();near=(PurePosixPath(origin).parent/target).as_posix()
        exact=[p for p in notes if re.sub(r'\.md$','',p,flags=re.I).casefold() in (target,near)]
        if exact:return exact
        return [p for p,m in notes.items() if PurePosixPath(p).stem.casefold()==target or target in [a.casefold() for a in m['aliases']]]

    def related(self,path):
        path=relative_note(path);self.path(path);self.refresh()
        with self.connection() as db:notes={r['path']:json.loads(r['meta']) for r in db.execute('SELECT path,meta FROM notes')}
        if path not in notes:raise ValueError('note_not_found')
        links=[]
        for link in notes[path]['links']:
            targets=self.targets(link,path,notes)
            links.append({'link':link,'targets':targets[:8],'target_count':len(targets),'targets_truncated':len(targets)>8})
        backlinks=[p for p,m in notes.items() if any(path in self.targets(link,p,notes) for link in m['links'])]
        data={'path':path,'links':links[:30],'backlinks':backlinks[:30],'ambiguous_links':[r['link'] for r in links if r['target_count']>1][:30],'truncated':False}
        while len(json.dumps(data,ensure_ascii=False))>8000:
            data['truncated']=True
            field=next((f for f in ('backlinks','links','ambiguous_links') if data[f]),None)
            if field is None:break
            data[field].pop()
        return data

class SecondBrain:
    def __init__(self,preferences,storage=None):self.preferences=preferences;self.storage=storage;self.index=None
    def configured_root(self):return self.preferences.get('obsidian_vault') if self.preferences else ''
    def vault(self):
        root=self.configured_root()
        if not root:raise ValueError('vault_not_configured')
        if self.index is None or self.index.root!=Path(root).resolve():self.index=VaultIndex(root,self.storage)
        return self.index
    def status(self):
        return {'configured':bool(self.configured_root()),'mode':'filesystem_read_only','vault':Path(self.configured_root()).name if self.configured_root() else '',
            'rest_mcp_connected':False,'metrics':self.index.last if self.index else {}}
    def run(self,args,authorized=lambda:True):
        action=args['action']
        if not authorized():return {'status':'cancelled','reply':'Pembacaan catatan dibatalkan.'}
        try:
            if action=='status':return {'status':'done','reply':'Status Second Brain.','knowledge':self.status()}
            if action not in ('list','read','search','related','refresh'):raise ValueError('second_brain_read_only')
            index=self.vault()
            if action=='refresh':data={'metrics':index.refresh(force=True,authorized=authorized)}
            elif action=='list':data={'notes':index.notes(args.get('limit') or 30)}
            elif action=='search':
                if not args.get('query','').strip():raise ValueError('knowledge_query_required')
                data={'sources':index.search(args['query'],args.get('limit') or 5)}
            elif action=='read':data={'sources':[index.read(args['path'],args.get('start') or 1,args.get('limit') or 60)]}
            else:data=index.related(args['path'])
            if not authorized():return {'status':'cancelled','reply':'Pembacaan catatan dibatalkan.'}
            return {'status':'done','reply':'Catatan dibaca dari vault lokal.' if data.get('sources') else 'Permintaan vault selesai; hasil kosong berarti tidak ditemukan.',
                'vault':index.root.name,'read_only':True,'untrusted_data':True,**data}
        except (OSError,ValueError,sqlite3.Error) as error:
            code=str(error) if isinstance(error,ValueError) else type(error).__name__
            return {'status':'needs_input' if code=='vault_not_configured' else 'failed','code':code,
                'reply':'Pilih folder vault melalui Pusat → Second Brain / Obsidian.' if code=='vault_not_configured' else 'Catatan belum dapat dibaca; periksa path dan kode kesalahan. Tidak ada berkas vault diubah.'}
