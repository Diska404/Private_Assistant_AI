"""Bounded file operations with recorded paths, overwrite backups and conflict-aware undo."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import time
import unicodedata
from conversation_memory import redact
from paths import DATA

TEXT_TYPES={'.txt','.md','.csv','.json','.yaml','.yml','.log','.py','.html','.css','.js','.ts','.ini','.toml','.xml','.srt'}
READ_TYPES=TEXT_TYPES|{'.ino','.c','.h','.cpp','.hpp','.cc','.rst'}
PROTECTED=re.compile(r'^(?:\.env(?:\..*)?|credentials?|secrets?|api[ _-]?keys?|passwords?|kata[ _-]?sandi)(?:\.[^.]*)?$',re.I)


def checked_path(value):
    if not isinstance(value,str) or not value or len(value)>1200 or any(c in value for c in '\r\n\x00'):raise ValueError('invalid_file_path')
    path=Path(value).expanduser()
    if not path.is_absolute() or str(path).startswith(('\\\\','//')):raise ValueError('local_absolute_path_required')
    path=path.resolve()
    if any(p.casefold() in ('windows','program files','program files (x86)','.ssh','.aws','.azure','.codex','credentials','system volume information','$recycle.bin') for p in path.parts):raise ValueError('protected_file_path')
    if PROTECTED.fullmatch(path.name) or path.name.casefold() in ('login data','cookies','local state','web data','preferences.sqlite3'):raise ValueError('credential_file_not_readable')
    return path


def digest(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def known_folders():
    """Read Windows known-folder locations; one offline drive must not hide the rest."""
    home=Path.home();one=Path(os.environ.get('OneDrive',str(home)))
    result={'documents':one/'Documents','downloads':home/'Downloads','desktop':home/'Desktop'}
    if os.name=='nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                for name,reg in [('documents','Personal'),('downloads','{374DE290-123F-4565-9164-39C4925E467B}'),('desktop','Desktop')]:
                    try:result[name]=Path(os.path.expandvars(winreg.QueryValueEx(key,reg)[0]))
                    except OSError:pass
        except OSError:pass
    return result


def normalized_name(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',value).casefold() if c.isalnum())


def source_redact(value):
    # C/C++ preprocessor and configuration literals often contain credentials.
    value=re.sub(r'(?im)^(\s*#define\s+\w*(?:auth|token|secret|password|passwd|ssid|api_?key)\w*\s+).*$',r'\1"[REDACTED]"',value)
    value=re.sub(r'(?im)(\b\w*(?:auth|token|secret|password|passwd|ssid|api_?key)\w*\s*[:=]\s*)(["\x27])[^\r\n]*?\2',r'\1"[REDACTED]"',value)
    # Keep the shared redactor's credential patterns without its historical 8k cap.
    return ''.join(redact(value[i:i+6000]) for i in range(0,len(value),6000))


class FileWorkspace:
    def __init__(self,storage=None):
        self.storage=Path(storage) if storage else DATA/'file-history'
        self.observed=set()

    def roots(self):
        import psutil
        paths=list(known_folders().values())+[DATA/'workspace']
        try:paths.extend(Path(r.mountpoint) for r in psutil.disk_partitions())
        except OSError:pass
        rows=[]
        for p in dict.fromkeys(paths):
            try:
                if p.exists() or p==DATA/'workspace':self.observed.add(str(p.resolve()));rows.append(str(p))
            except OSError:continue
        return {'status':'done','reply':'Folder lokal tersedia. Gunakan search untuk nama yang belum pasti; drive offline dilewati.','paths':rows,'known_folders':{k:str(v) for k,v in known_folders().items()}}

    def resolve_read_path(self,value):
        aliases={'dokumen':'documents','documents':'documents','document':'documents','unduhan':'downloads','downloads':'downloads','download':'downloads','desktop':'desktop'}
        pieces=re.split(r'[>/\\]+',value.strip())
        if pieces and pieces[0].casefold() in aliases:
            value=str(known_folders()[aliases[pieces[0].casefold()]].joinpath(*(p.strip() for p in pieces[1:] if p.strip())))
        path=checked_path(value)
        if not path.exists() and path.parent.is_dir():
            matches=[p for p in path.parent.iterdir() if normalized_name(p.name)==normalized_name(path.name)]
            if len(matches)>1:raise ValueError('ambiguous_file_name_use_search')
            if len(matches)==1:path=checked_path(str(matches[0]))
        return path

    def allowed(self,path,user_text):
        if str(path) in self.observed:return
        # Explicit path or a child of a folder inspected during this active request.
        if str(path).casefold() in user_text.casefold() or any(path.parent==Path(p) for p in self.observed):return
        raise ValueError('file_path_not_observed')

    def record(self,operation,path,dest=None,backup=None,after=None):
        self.storage.mkdir(parents=True,exist_ok=True);ident=uuid.uuid4().hex[:12]
        row={'id':ident,'operation':operation,'path':str(path),'destination':str(dest) if dest else '',
             'backup':str(backup) if backup else '', 'after_sha256':after,'undone':False}
        (self.storage/(ident+'.json')).write_text(json.dumps(row,ensure_ascii=False),encoding='utf-8')
        return ident

    def run(self,args,user_text,authorized=lambda:True):
        action=args['action']
        if action=='roots':return self.roots()
        if action=='undo':return self.undo(args.get('operation_id',''),authorized)
        reading=action in ('list','search','read')
        if action=='search' and not args.get('path'):
            found=[];scanned=0
            for folder in known_folders().values():
                try:
                    result=self.run({**args,'path':str(folder)},user_text,authorized);found.extend(result['paths']);scanned+=result['scanned']
                except OSError:continue
            return {'status':'done','reply':'Pencarian folder pengguna selesai.','paths':list(dict.fromkeys(found))[:50],'scanned':scanned,'untrusted_data':True}
        path=self.resolve_read_path(args.get('path','')) if reading else checked_path(args.get('path',''))
        if not (reading and any(path.is_relative_to(p.resolve()) for p in known_folders().values())):self.allowed(path,user_text)
        if action=='list':
            rows=[]
            for item in sorted(path.iterdir(),key=lambda p:(not p.is_dir(),p.name.casefold())):
                try:
                    item=checked_path(str(item));self.observed.add(str(item))
                    rows.append({'path':str(item),'directory':item.is_dir(),'bytes':item.stat().st_size if item.is_file() else None})
                    if len(rows)>=100:break
                except (ValueError,OSError):continue
            return {'status':'done','reply':'Isi folder dibaca, maksimal 100 entri.','files':rows,'untrusted_data':True}
        if action=='search':
            query=args.get('query') or args.get('text','');query=query.casefold()
            if not query or len(query)>150:raise ValueError('invalid_file_search')
            rows=[];seen=0;started=time.monotonic();needle=normalized_name(query)
            for base,dirs,files in os.walk(path):
                dirs[:]=[d for d in dirs if not d.startswith('.') and d.casefold() not in ('node_modules','venv','site-packages','windows','program files','program files (x86)','system volume information','$recycle.bin') and not (Path(base)/d).is_symlink() and not (hasattr(Path,'is_junction') and (Path(base)/d).is_junction())]
                for name in dirs+files:
                    seen+=1
                    if query in name.casefold() or needle and needle in normalized_name(name):
                        try:p=checked_path(str(Path(base)/name));self.observed.add(str(p));rows.append(str(p))
                        except (ValueError,OSError):pass
                    if seen>=5000 or len(rows)>=50 or time.monotonic()-started>3 or not authorized():break
                if seen>=5000 or len(rows)>=50 or time.monotonic()-started>3 or not authorized():break
            return {'status':'done','reply':'Pencarian nama berkas selesai dalam batas 5.000 entri.','paths':rows,'scanned':seen,'untrusted_data':True}
        if action=='read':
            if path.suffix.casefold()=='.pdf':
                from pypdf.errors import PyPdfError
                try:return self.read_pdf(path,args)
                except PyPdfError:raise ValueError('pdf_cannot_parse_or_extract') from None
            if path.suffix.casefold() not in READ_TYPES:
                from conversation_attachments import extract_upload,MAX_BYTES
                if path.stat().st_size>MAX_BYTES:raise ValueError('attachment_max_6mb')
                result=extract_upload(path.name,path.read_bytes())
                return {'status':'done','reply':'Bahan dibaca sesuai parser: '+result['kind']+'. '+result['limitation'],
                        'path':str(path),'content':source_redact(result['text']),'truncated':result['truncated'],
                        'kind':result['kind'],'limitation':result['limitation'],'untrusted_data':True,
                        'content_status':'metadata_only' if result['kind'] in ('unsupported_binary','image_metadata','media_metadata') else 'text_or_inventory'}
            if path.stat().st_size>1_000_000:raise ValueError('supported_text_or_pdf_required')
            from attachment_readers import decode
            content=decode(path.read_bytes())
            if content is None:raise ValueError('file_text_encoding_required')
            lines=source_redact(content).splitlines()
            start=max(1,int(args.get('start_line') or 1));count=max(1,min(160,int(args.get('line_count') or 100)))
            selected=[];chars=0
            for line in lines[start-1:start-1+count]:
                if chars+len(line)>10000:break
                selected.append(line);chars+=len(line)+1
            if not selected and start<=len(lines):selected=[lines[start-1][:10000]]
            next_line=start+len(selected)
            return {'status':'done','reply':'Berkas teks dibaca; kredensial disamarkan. Lanjutkan dengan next_line bila perlu.','path':str(path),'content':'\n'.join(selected),'start_line':start,'total_lines':len(lines),'next_line':next_line if next_line<=len(lines) else None,'truncated':next_line<=len(lines),'untrusted_data':True}
        if not authorized():return {'status':'cancelled','reply':'Operasi berkas dibatalkan.'}
        if action=='open':
            if not path.exists() or path.is_file() and path.suffix.casefold() not in TEXT_TYPES|{'.pdf','.png','.jpg','.jpeg','.webp','.wav','.mp3','.mp4','.docx','.xlsx','.pptx'}:raise ValueError('document_path_required')
            os.startfile(str(path));return {'status':'dispatched','reply':'Berkas/folder dikirim ke aplikasi default. Jendela dan isi belum diverifikasi.','path':str(path)}
        if action=='mkdir':
            if path.exists():return {'status':'done','reply':'Folder sudah tersedia.','path':str(path)}
            path.mkdir();ident=self.record('mkdir',path);self.observed.add(str(path))
        elif action=='write':
            if path.suffix.casefold() not in TEXT_TYPES or path.exists() and (not path.is_file() or path.stat().st_size>1_000_000):raise ValueError('text_file_required_max_1mb')
            text=args.get('text','')
            if len(text)>3000 or redact(text)!=text:raise ValueError('invalid_or_sensitive_file_text')
            self.storage.mkdir(parents=True,exist_ok=True);backup=None
            if path.exists():backup=self.storage/(uuid.uuid4().hex+'.backup');shutil.copy2(path,backup)
            with path.open('w',encoding='utf-8',newline='') as handle:handle.write(text)
            ident=self.record('write',path,backup=backup,after=digest(path));self.observed.add(str(path))
        elif action in ('copy','move'):
            dest=checked_path(args.get('destination',''));self.allowed(dest,user_text)
            if not path.is_file() or dest.exists() or path.stat().st_size>100_000_000:raise ValueError('file_copy_move_requires_unused_destination_max_100mb')
            if action=='copy':shutil.copy2(path,dest)
            else:path.rename(dest)
            ident=self.record(action,path,dest,after=digest(dest));self.observed.add(str(dest))
        else:raise ValueError('invalid_file_action')
        return {'status':'done','reply':'Operasi '+action+' selesai dan dicatat untuk undo.','path':str(path),'operation_id':ident}

    def read_pdf(self,path,args):
        if path.stat().st_size>50_000_000:raise ValueError('pdf_max_50mb')
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted:raise ValueError('pdf_encrypted_requires_unlocked_copy')
        start=max(1,int(args.get('start_page') or 1));count=max(1,min(3,int(args.get('page_count') or 1)))
        pages=[];chars=0
        for number in range(start,min(len(reader.pages)+1,start+count)):
            page=reader.pages[number-1];stream=page.get_contents()
            if stream is not None and len(stream.get_data())>8_000_000:raise ValueError('pdf_page_stream_too_large')
            content=source_redact(page.extract_text() or '')
            if chars+len(content)>14000 and pages:break
            pages.append({'page':number,'text':content[:14000],'truncated':len(content)>14000});chars+=len(content)
        next_page=start+len(pages)
        return {'status':'done','reply':'Teks PDF diekstrak per halaman; tata letak/gambar belum dianalisis.','path':str(path),'total_pages':len(reader.pages),'pages':pages,'next_page':next_page if next_page<=len(reader.pages) else None,'ocr_required':bool(pages) and not any(p['text'].strip() for p in pages),'untrusted_data':True}

    def undo(self,ident,authorized):
        if not re.fullmatch(r'[0-9a-f]{12}',ident):raise ValueError('invalid_file_operation_id')
        record=self.storage/(ident+'.json');row=json.loads(record.read_text('utf-8'))
        if row['undone']:return {'status':'done','reply':'Operasi ini sudah dibatalkan sebelumnya.'}
        path=checked_path(row['path']);dest=checked_path(row['destination']) if row['destination'] else None
        affected=dest or path
        if row['after_sha256'] and (not affected.is_file() or digest(affected)!=row['after_sha256']):raise ValueError('undo_conflict_file_changed')
        if not authorized():return {'status':'cancelled','reply':'Undo dibatalkan.'}
        if row['operation']=='mkdir':path.rmdir()
        elif row['operation']=='write':
            if row['backup']:
                backup=Path(row['backup']).resolve()
                if not backup.is_relative_to(self.storage.resolve()):raise ValueError('invalid_undo_backup')
                shutil.copy2(backup,path)
            else:path.unlink()
        elif row['operation']=='copy':dest.unlink()
        elif row['operation']=='move':
            if path.exists():raise ValueError('undo_conflict_original_exists')
            dest.rename(path)
        row['undone']=True;record.write_text(json.dumps(row,ensure_ascii=False),encoding='utf-8')
        return {'status':'done','reply':'Operasi berkas dibatalkan; keadaan sebelumnya dipulihkan.','operation_id':ident}
