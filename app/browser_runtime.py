"""On-demand DOM controls for a Leva-owned browser; no CDP into personal profiles."""
from pathlib import Path
import re
import time
import uuid
from urllib.parse import urlparse

DATA=Path(r'D:\AI\AI Lokal Asisten\Leva')
SENSITIVE=re.compile(r'\b(send|kirim|delete|hapus|buy|beli|pay|bayar|purchase|submit|publish|install|sign in|log in|login)\b',re.I)


def checked_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or len(url)>2000 or any(ord(c)<33 for c in url):raise ValueError('invalid_browser_url')
    return url


class BrowserRuntime:
    def __init__(self,headless=False,profile=None):
        self.driver=None;self.context=None;self.tabs={};self.snapshots={}
        self.headless=headless;self.profile=Path(profile) if profile else DATA/'browser-profile'

    def start(self,browser='edge'):
        if self.context:return
        from playwright.sync_api import sync_playwright
        self.profile.mkdir(parents=True,exist_ok=True)
        self.driver=sync_playwright().start()
        try:
            self.context=self.driver.chromium.launch_persistent_context(str(self.profile),channel='msedge' if browser=='edge' else 'chrome',headless=self.headless,
                accept_downloads=False,args=['--no-first-run'],viewport=None)
            self.context.set_default_timeout(6000)
            self.context.on('page',self.register)
            for page in self.context.pages:self.register(page)
        except Exception:
            self.stop();raise

    def register(self,page):
        for ident,item in self.tabs.items():
            if item is page:return ident
        ident=uuid.uuid4().hex[:8];self.tabs[ident]=page;return ident

    def fooocus_open(self,args):
        parsed=urlparse(args['url'])
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.path.strip('/') or parsed.query or parsed.fragment:raise ValueError('fooocus_loopback_url_required')
        self.start('edge');page=self.context.new_page();ident=self.register(page)
        page.goto(args['url'],wait_until='domcontentloaded',timeout=25000)
        if urlparse(page.url).netloc!=parsed.netloc:raise ValueError('fooocus_frontend_redirected')
        page.locator('#generate_button').wait_for(state='visible',timeout=20000)
        return {'status':'done','reply':'Antarmuka Fooocus terbuka dan tombol Generate teramati; belum menjalankan generation.','tab':ident,'url':page.url,'task_verified':True,'browser_active':True}

    def comfy_current(self):
        ident=getattr(self,'comfy_tab','');page=self.page(ident)
        observed=page.evaluate("""async () => {const {app}=await import('/scripts/app.js');return {workflow:(app.rootGraph||app.graph).serialize(),graph:(await app.graphToPrompt()).output};}""")
        return {'status':'done','reply':'Graph yang sedang terbuka di tab ComfyUI Leva dibaca; belum diubah atau dijalankan.','tab':ident,**observed,'browser_active':True}

    def comfy_canvas(self, args):
        """Fixed application adapter, no model-authored JavaScript or arbitrary selectors."""
        from urllib.parse import urlparse
        base=args['url'];parsed=urlparse(base)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.path.strip('/') or parsed.query or parsed.fragment:raise ValueError('comfy_loopback_url_required')
        workflow=args.get('workflow')
        if workflow is not None and (not isinstance(workflow,dict) or not 1<=len(workflow.get('nodes',[]))<=120):raise ValueError('invalid_comfy_workflow')
        self.start('edge');page=self.context.new_page();ident=self.register(page);self.comfy_tab=ident
        page.goto(base,wait_until='domcontentloaded',timeout=25000)
        if urlparse(page.url).netloc!=parsed.netloc:raise ValueError('comfy_frontend_redirected')
        # Keep the polling predicate synchronous: a Promise itself can be truthy
        # before the dynamically imported frontend has finished setup.
        page.wait_for_function("() => !!(window.app?.rootGraph || window.app?.graph) && !!window.app?.canvas && !window.app.configuringGraph",timeout=25000)
        if workflow is None:return {'status':'done','reply':'Halaman dan canvas ComfyUI terbuka di tab Leva; belum ada workflow baru atau generation dijalankan.','tab':ident,'url':base,'browser_active':True,'task_verified':True}
        observed=page.evaluate("""async data => {
            const {app}=await import('/scripts/app.js');
            if (!app.rootGraph && !app.graph) throw new Error('comfy_frontend_not_ready');
            await app.loadGraphData(data.workflow, true, true, 'Leva workflow');
            const root=app.rootGraph||app.graph;
            const nodes=root._nodes||[];
            if(nodes.length && app.canvas?.ds){
                const minX=Math.min(...nodes.map(n=>n.pos[0])), minY=Math.min(...nodes.map(n=>n.pos[1]));
                const maxX=Math.max(...nodes.map(n=>n.pos[0]+n.size[0])), maxY=Math.max(...nodes.map(n=>n.pos[1]+n.size[1]));
                const width=app.canvas.canvas.clientWidth, height=app.canvas.canvas.clientHeight;
                const scale=Math.max(0.1,Math.min(0.85,(width-200)/(maxX-minX+80),(height-160)/(maxY-minY+80)));
                app.canvas.ds.scale=scale;
                app.canvas.ds.offset=[(width/scale-(maxX-minX))/2-minX,(height/scale-(maxY-minY))/2-minY];
            }
            app.canvas?.setDirty(true, true);
            const graph=(app.rootGraph||app.graph).serialize();
            const generated=await app.graphToPrompt();
            return {node_types:graph.nodes.map(n=>n.type),node_count:graph.nodes.length,
                    link_count:Array.isArray(graph.links)?graph.links.length:Object.keys(graph.links||{}).length,
                    output:generated.output};
        }""",args)
        expected=args['expected']
        matched=len(observed.get('output',{}))==len(expected) and all(observed['output'].get(key,{}).get('class_type')==row['class_type'] and observed['output'][key].get('inputs')==row['inputs'] for key,row in expected.items())
        return {'status':'done' if matched else 'unverified','reply':'Peta dimuat pada canvas ComfyUI dan graph keluaran frontend diperiksa.' if matched else 'Peta dimuat, tetapi graph keluaran frontend belum cocok; jangan jalankan sebelum diperiksa.',
                'tab':ident,'node_count':observed['node_count'],'link_count':observed['link_count'],'node_types':observed['node_types'],
                'task_verified':matched,'browser_active':True,'url':base}

    def stop(self):
        try:
            if self.context:self.context.close()
        finally:
            if self.driver:self.driver.stop()
            self.context=None;self.driver=None;self.tabs={};self.snapshots={}

    def page(self,ident):
        page=self.tabs.get(ident)
        if not page or page.is_closed():raise ValueError('browser_tab_not_observed')
        return page

    def inspect(self,ident):
        page=self.page(ident);token=uuid.uuid4().hex[:12];controls={};rows=[]
        # ElementHandles remain tied to their node; DOM changes do not retarget nth().
        for element in page.query_selector_all('a[href],button,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]')[:160]:
            try:
                if not element.is_visible():continue
                meta=element.evaluate('e => ({tag:e.tagName.toLowerCase(),type:e.getAttribute("type")||"",label:e.getAttribute("aria-label")||e.labels?.[0]?.innerText||e.innerText||e.getAttribute("placeholder")||e.getAttribute("name")||"",href:e.getAttribute("href")||""})')
                if meta['type'].lower() in ('password','hidden','file'):continue
                if re.search(r'password|kata sandi|api.?key|secret|access.?token',meta['label'],re.I):continue
                if meta['tag'] in ('input','textarea','select'):meta['value']=element.input_value()[:500]
                key=str(len(controls));controls[key]=element
                rows.append({'element':token+':'+key,**{k:str(v)[:200] for k,v in meta.items()},'enabled':element.is_enabled()})
                if len(rows)>=70:break
            except Exception:continue
        self.snapshots[token]={'time':time.monotonic(),'tab':ident,'url':page.url,'controls':controls}
        while len(self.snapshots)>8:self.snapshots.pop(next(iter(self.snapshots)))
        body=page.locator('body').inner_text(timeout=5000)
        # Do not export password input values, HTML, cookies, local storage, or screenshots.
        return {'status':'done','reply':'Halaman dan elemen browser dibaca.','tab':ident,'url':page.url,'title':page.title(),'content':body[:6500],'elements':rows,'untrusted_data':True,'browser_active':True}

    def run(self,args):
        action=args['action'];ident=args.get('tab','')
        if action=='open':
            url=checked_url(args.get('url',''));self.start(args.get('browser','edge'))
            page=self.context.new_page();ident=self.register(page)
            page.goto(url,wait_until='domcontentloaded',timeout=25000)
            return self.inspect(ident)
        if action=='tabs':
            rows=[{'tab':i,'url':p.url,'title':p.title()} for i,p in self.tabs.items() if not p.is_closed()]
            return {'status':'done','reply':'Tab browser terkelola Leva. Ini sesi terpisah dari Chrome/Edge pribadi.','tabs':rows,'browser_active':bool(rows),'untrusted_data':True}
        if action=='stop':self.stop();return {'status':'done','reply':'Browser terkelola Leva ditutup.','browser_active':False}
        page=self.page(ident)
        if action=='inspect':return self.inspect(ident)
        if action=='close':
            page.close();self.tabs.pop(ident,None)
            return {'status':'done','reply':'Tab ditutup.','browser_active':any(not p.is_closed() for p in self.tabs.values())}
        if action in ('back','forward'):
            (page.go_back if action=='back' else page.go_forward)(wait_until='domcontentloaded')
            return self.inspect(ident)
        if action=='navigate':
            page.goto(checked_url(args.get('url','')),wait_until='domcontentloaded',timeout=25000)
            return self.inspect(ident)
        token,key=args.get('element','').split(':',1);snapshot=self.snapshots.get(token)
        if not snapshot or snapshot['tab']!=ident or snapshot['url']!=page.url or time.monotonic()-snapshot['time']>60:raise ValueError('stale_browser_snapshot')
        element=snapshot['controls'].get(key)
        if not element or not element.evaluate('e=>e.isConnected') or not element.is_visible() or not element.is_enabled():raise ValueError('browser_element_unavailable')
        meta=element.evaluate('e=>({type:e.getAttribute("type"),tag:e.tagName.toLowerCase(),label:e.getAttribute("aria-label")||e.innerText||"",href:e.getAttribute("href")||"",form:!!e.form,role:e.getAttribute("role")})')
        if meta['type'] in ('password','file','hidden'):raise ValueError('protected_browser_field')
        if action=='click':
            if SENSITIVE.search(meta['label']) or meta['type']=='submit' or meta['tag']=='button' and meta['form'] and meta['type']!='button':
                return {'status':'needs_input','reply':'Tombol ini mengirim, mengubah akun, atau melakukan tindakan eksternal. Selesaikan langsung pada browser; Leva dapat menyiapkan isi sebelumnya.','browser_active':True}
            if meta['tag']=='a':
                href=element.evaluate('e=>e.href');checked_url(href)
            element.click(timeout=6000)
        elif action=='fill':
            if len(args.get('text',''))>3000:raise ValueError('browser_text_too_long')
            element.fill(args.get('text',''))
        elif action=='select':element.select_option(args.get('text',''))
        elif action=='press':
            keyname=args.get('text','')
            if keyname not in ('Tab','Escape','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','PageDown','PageUp','Home','End'):raise ValueError('unsupported_browser_key')
            element.press(keyname)
        else:raise ValueError('invalid_browser_action')
        self.snapshots.pop(token,None)
        return {'status':'dispatched','reply':'Input pada elemen halaman dikirim. Inspect tab kembali untuk memverifikasi hasil.','tab':ident,'input_dispatched':True,'task_verified':False,'browser_active':True}


runtime=BrowserRuntime()
