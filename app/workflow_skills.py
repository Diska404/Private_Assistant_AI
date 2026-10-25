"""Small curated procedural guides, loaded on demand; never a Python plugin loader."""
import json
from pathlib import Path
from paths import DATA


class WorkflowSkills:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA/'skills/curated_workflows.json'
        self.include_bundled=path is None
    def rows(self):
        result=[];seen=set()
        # Bundled extensions work in the desktop package and web host. Existing local guides win by ID.
        for path in ((self.path,Path(__file__).with_name('capability_workflows.json')) if self.include_bundled else (self.path,)):
            try:
                if path.stat().st_size>128000:continue
                rows=json.loads(path.read_text('utf-8'))
                if not isinstance(rows,list):continue
                for r in rows:
                    if not isinstance(r,dict) or set(r)!={'id','title','description','triggers','instructions','source'}:continue
                    if any(not isinstance(r[k],str) or not r[k] or len(r[k])>3000 for k in ('id','title','description','instructions','source')):continue
                    if not isinstance(r['triggers'],list) or not 0<len(r['triggers'])<=30 or any(not isinstance(t,str) or not t.strip() or len(t)>100 for t in r['triggers']):continue
                    if r['id'] in seen:continue
                    seen.add(r['id']);result.append(r)
            except (OSError,ValueError,TypeError):continue
        return result[:48]
    def public(self):return [{k:r[k] for k in ('id','title','description','source')} for r in self.rows()]
    def get(self,ident):
        row=next((r for r in self.rows() if r['id']==ident),None)
        if not row:raise ValueError('unknown_workflow')
        return row
    def relevant(self,text):
        value=text.casefold()
        rows=[(max((len(t) for t in r['triggers'] if t.casefold() in value),default=0),r) for r in self.rows()]
        return [r for score,r in sorted(rows,key=lambda pair:-pair[0]) if score][:2]
