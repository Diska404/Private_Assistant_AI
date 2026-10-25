"""Project search/chunked reads, strict unified patches and conflict-aware rollback."""
import base64
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import uuid
from file_workspace import checked_path,TEXT_TYPES
from conversation_memory import redact
from paths import DATA


def sha(data):return hashlib.sha256(data).hexdigest()


def patched_text(original,patch_lines):
    if any(line.strip()=='@@' for line in patch_lines):
        # Context-only hunks are common in agent output. Accept only unique exact
        # matches; never guess a location or apply a fuzzy replacement.
        text=original;index=0
        while index<len(patch_lines):
            if not patch_lines[index].strip():index+=1;continue
            if patch_lines[index].strip()!='@@':raise ValueError('mixed_patch_hunk_formats')
            index+=1;before=[];after=[]
            while index<len(patch_lines) and not patch_lines[index].startswith('@@'):
                row=patch_lines[index];index+=1
                if not row.strip():continue
                if row[0] not in ' +-':raise ValueError('invalid_patch_line')
                if row[0] in ' -':before.append(row[1:])
                if row[0] in ' +':after.append(row[1:])
            old=''.join(before);new=''.join(after)
            if old:
                if text.count(old)!=1:raise ValueError('patch_context_not_unique')
                text=text.replace(old,new,1)
            elif not text:text=new
            else:raise ValueError('patch_insert_location_ambiguous')
        return text
    source=original.splitlines(keepends=True);out=[];cursor=0;index=0
    while index<len(patch_lines):
        line=patch_lines[index]
        if not line.strip():index+=1;continue
        match=re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?',line)
        if not match:raise ValueError('invalid_patch_hunk')
        start=int(match[1]);old_count=int(match[2] or 1);new_count=int(match[4] or 1)
        target=max(0,start-1) if old_count else start
        if target<cursor or target>len(source):raise ValueError('patch_hunk_position_conflict')
        out.extend(source[cursor:target]);cursor=target;index+=1;old_used=new_used=0
        while old_used<old_count or new_used<new_count:
            if index>=len(patch_lines):raise ValueError('truncated_patch_hunk')
            row=patch_lines[index];index+=1
            if not row or row[0] not in ' +-':raise ValueError('invalid_patch_line')
            sign,content=row[0],row[1:]
            if index<len(patch_lines) and patch_lines[index].startswith('\\ No newline at end of file'):
                content=content.rstrip('\n');index+=1
            if sign in ' -':
                if cursor>=len(source) or source[cursor]!=content:raise ValueError('patch_context_conflict')
                cursor+=1;old_used+=1
            if sign in ' +':out.append(content);new_used+=1
            if old_used>old_count or new_used>new_count:raise ValueError('patch_hunk_count_conflict')
    out.extend(source[cursor:]);return ''.join(out)


class ProjectWorkspace:
    def __init__(self,storage=None):
        self.storage=Path(storage) if storage else DATA/'project-history'
        self.lock=threading.RLock()

    def root(self,value):
        path=checked_path(str(value))
        if not path.is_dir():raise ValueError('project_root_not_directory')
        return path

    def target(self,root,relative):
        if not relative or Path(relative).is_absolute() or ':' in relative:raise ValueError('relative_project_path_required')
        path=checked_path(str(root/relative))
        if not path.is_relative_to(root):raise ValueError('project_path_escape')
        if any(p in ('.git','.venv','node_modules') for p in Path(relative).parts):raise ValueError('protected_project_metadata')
        if path.suffix.casefold() not in TEXT_TYPES and path.name not in ('.gitignore','.gitattributes','.editorconfig','Dockerfile','Makefile'):raise ValueError('project_text_file_required')
        return path

    def read(self,root,path,start=1,limit=80):
        root=self.root(root);target=self.target(root,path);raw=target.read_bytes()
        if len(raw)>10_000_000:raise ValueError('project_file_max_10mb')
        start=max(1,int(start));limit=max(1,min(200,int(limit)));lines=raw.decode('utf-8-sig').splitlines()
        content='\n'.join(f'{i+1}: {line}' for i,line in enumerate(lines) if start-1<=i<start-1+limit)
        return {'status':'done','reply':'Bagian berkas proyek dibaca.','path':path,'root':str(root),'sha256':sha(raw),'total_lines':len(lines),'start':start,'content':redact(content),'untrusted_data':True}

    def search(self,root,query):
        root=self.root(root)
        if not query or len(query)>200:raise ValueError('invalid_project_search')
        rows=[];scanned=0
        import os,time
        began=time.monotonic()
        for base,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if not d.startswith('.') and d not in ('node_modules','venv','__pycache__','program','vendor')]
            for name in files:
                scanned+=1
                try:
                    path=self.target(root,str((Path(base)/name).relative_to(root)))
                    if path.stat().st_size>1_000_000:continue
                    for number,line in enumerate(path.read_text('utf-8-sig',errors='replace').splitlines(),1):
                        if query.casefold() in line.casefold():rows.append({'path':str(path.relative_to(root)),'line':number,'text':redact(line)[:180]})
                        if len(rows)>=60:break
                except (OSError,ValueError):pass
                if scanned>=2000 or len(rows)>=60 or time.monotonic()-began>3:break
            if scanned>=2000 or len(rows)>=60 or time.monotonic()-began>3:break
        return {'status':'done','reply':'Pencarian isi proyek selesai dalam batas waktu/entri.','matches':rows,'scanned':scanned,'untrusted_data':True}

    def preview(self,root,patch):
        root=self.root(root)
        if not isinstance(patch,str) or len(patch)>12000 or not patch.strip():raise ValueError('invalid_project_patch')
        patch=re.sub(r'^```(?:diff|patch)?\s*\n|\n```\s*$','',patch.strip())+'\n' if patch.strip().startswith('```') else patch
        if patch.startswith('*** Begin Patch'):
            converted=[]
            for line in patch.splitlines(keepends=True):
                if line.startswith(('*** Begin Patch','*** End Patch','*** End of File')):continue
                if line.startswith('*** Update File: '):
                    path=line[len('*** Update File: '):].strip();converted.extend(['--- a/'+path+'\n','+++ b/'+path+'\n'])
                elif line.startswith('*** '):raise ValueError('only_update_file_directive_supported')
                else:converted.append(line)
            patch=''.join(converted)
        lines=patch.replace('\r\n','\n').splitlines(keepends=True);index=0;files=[]
        while index<len(lines):
            if lines[index].startswith(('diff --git ','index ')) or not lines[index].strip():index+=1;continue
            if not lines[index].startswith('--- '):raise ValueError('patch_file_header_required')
            old=lines[index][4:].strip().split('\t')[0];index+=1
            if index>=len(lines) or not lines[index].startswith('+++ '):raise ValueError('patch_new_header_required')
            new=lines[index][4:].strip().split('\t')[0];index+=1
            if new=='/dev/null':raise ValueError('patch_file_delete_not_supported')
            relative=new[2:] if new.startswith('b/') else new
            old_relative=old[2:] if old.startswith('a/') else old
            if old!='/dev/null' and old_relative!=relative:raise ValueError('patch_rename_not_supported')
            path=self.target(root,relative)
            if any(r['path']==relative for r in files):raise ValueError('duplicate_patch_target')
            before=path.read_bytes() if path.exists() else None
            if old=='/dev/null' and before is not None or old!='/dev/null' and before is None:raise ValueError('patch_creation_conflict')
            if before and len(before)>2_000_000:raise ValueError('patch_file_max_2mb')
            first=index
            while index<len(lines) and not lines[index].startswith('diff --git ') and not (lines[index].startswith('--- ') and index+1<len(lines) and lines[index+1].startswith('+++ ')):index+=1
            # Headers inside removed content are distinguishable by the following +++ header.
            hunks=lines[first:index]
            text=(before or b'').decode('utf-8-sig').replace('\r\n','\n')
            changed=patched_text(text,hunks)
            newline='\r\n' if before and b'\r\n' in before else '\n'
            after=changed.replace('\n',newline).encode('utf-8')
            if before and before.startswith(b'\xef\xbb\xbf'):after=b'\xef\xbb\xbf'+after
            files.append({'path':relative,'before':base64.b64encode(before).decode() if before is not None else None,'after':base64.b64encode(after).decode(),'before_sha256':sha(before) if before is not None else None,'after_sha256':sha(after)})
            if len(files)>8:raise ValueError('patch_max_8_files')
        if not files:raise ValueError('empty_patch')
        ident=uuid.uuid4().hex[:12];self.storage.mkdir(parents=True,exist_ok=True)
        (self.storage/(ident+'.json')).write_text(json.dumps({'id':ident,'root':str(root),'state':'preview','files':files}),encoding='utf-8')
        return {'status':'done','reply':'Preview patch siap. Apply patch_id untuk menerapkan setelah pemeriksaan konflik host.','patch_id':ident,'root':str(root),'files':[{'path':r['path'],'before_sha256':r['before_sha256'],'after_sha256':r['after_sha256']} for r in files],'diff':redact(patch)}

    def change(self,ident,rollback=False,protected=(),expected_root=None):
        if not re.fullmatch(r'[0-9a-f]{12}',ident):raise ValueError('invalid_patch_id')
        with self.lock:
            record=self.storage/(ident+'.json');job=json.loads(record.read_text('utf-8'));root=self.root(job['root'])
            if expected_root is not None and root!=self.root(expected_root):raise ValueError('patch_workspace_mismatch')
            expected='applied' if rollback else 'preview'
            if job['state']!=expected:raise ValueError('patch_state_conflict')
            targets=[]
            for row in job['files']:
                if any(row['path'].casefold()==name.casefold() or Path(row['path']).name.casefold()==name.casefold() for name in protected):raise ValueError('patch_user_protected_file')
                path=self.target(root,row['path']);current=path.read_bytes() if path.exists() else None
                wanted=row['after_sha256'] if rollback else row['before_sha256']
                if (sha(current) if current is not None else None)!=wanted:raise ValueError('patch_changed_since_preview' if not rollback else 'rollback_file_changed')
                targets.append((path,current,row))
            applied=[]
            try:
                for path,current,row in targets:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    value=row['before'] if rollback else row['after']
                    if value is None:path.unlink()
                    else:
                        temporary=path.with_name(path.name+'.leva-'+ident+'.tmp')
                        try:temporary.write_bytes(base64.b64decode(value));temporary.replace(path)
                        finally:temporary.unlink(missing_ok=True)
                    applied.append((path,current))
                    expected_value=row['before'] if rollback else row['after']
                    if expected_value is not None and path.read_bytes()!=base64.b64decode(expected_value):raise OSError('patch_post_write_verification_failed')
                job['state']='rolled_back' if rollback else 'applied';record.write_text(json.dumps(job),encoding='utf-8')
            except Exception:
                for path,current in reversed(applied):
                    if current is None:path.unlink(missing_ok=True)
                    else:path.write_bytes(current)
                raise
        return {'status':'done','reply':'Patch dibatalkan dan isi dipulihkan.' if rollback else 'Patch diterapkan; hash isi akhir cocok dengan preview.','patch_id':ident,'root':str(root),'paths':[r['path'] for r in job['files']],'task_verified':True}

    def git(self,root,checkpoint=False):
        root=self.root(root)
        def run(*args):
            result=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise ValueError('git_repository_or_command_unavailable')
            return result.stdout.strip()
        head=run('rev-parse','HEAD');status=run('status','--porcelain')
        result={'status':'done','reply':'Keadaan Git dibaca.','head':head,'changes':redact(status),'root':str(root)}
        if checkpoint:
            commit=run('stash','create','Leva checkpoint') or head
            ref='refs/leva/checkpoints/'+uuid.uuid4().hex[:12];run('update-ref',ref,commit)
            result.update(reply='Checkpoint Git untuk berkas tracked disimpan tanpa mengganti branch/working tree. Berkas untracked tidak tercakup.',checkpoint_ref=ref,commit=commit)
        return result
