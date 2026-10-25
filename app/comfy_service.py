"""Owned ComfyUI connector: inspect live schemas, prepare graphs, persist jobs, verify history."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import subprocess
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse
import uuid

from local_connectors import NoRedirect
from paths import DATA, ROOT


class ComfyError(ValueError):
    pass


class ComfyClient:
    def __init__(self, base='http://127.0.0.1:8188'):
        parsed = urlparse(base)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.strip('/')):
            raise ComfyError('comfy_loopback_url_required')
        self.base = base.rstrip('/')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, route, payload=None, timeout=8):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8') if payload is not None else None
        request = urllib.request.Request(self.base + route, data=data, headers={'Content-Type': 'application/json',**self.headers()})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(8_000_001)
        except urllib.error.HTTPError as error:
            # Return structured validation details, never an arbitrary HTML error page.
            try: detail = json.loads(error.read(16000))
            except (ValueError, OSError): detail = {}
            raise ComfyError('comfy_http_' + str(error.code) + ':' + json.dumps(detail, ensure_ascii=False)[:2000]) from None
        except OSError:
            raise ComfyError('comfy_service_unreachable') from None
        if len(raw) > 8_000_000: raise ComfyError('comfy_response_too_large')
        try: return json.loads(raw)
        except ValueError: raise ComfyError('comfy_invalid_json') from None

    def headers(self):return {}

    def schemas(self, names):
        result = {}
        for name in sorted(set(names)):
            row = self.request('/object_info/' + quote(name, safe=''))
            if name not in row: raise ComfyError('comfy_missing_node:' + name)
            result[name] = row[name]
        return result


def validate_graph(graph, schemas):
    """Validate links, cycles, required inputs, enum values and numeric ranges without queueing."""
    if not isinstance(graph, dict) or not 1 <= len(graph) <= 120: raise ComfyError('comfy_graph_size')
    errors = []; visited = set(); active = set(); has_output = False
    for ident, node in graph.items():
        if not isinstance(ident,str) or not ident.isdigit() or not isinstance(node,dict) or node.get('class_type') not in schemas:raise ComfyError('comfy_invalid_node_definition')
    for ident, node in graph.items():
        if not isinstance(ident, str) or not ident.isdigit() or not isinstance(node, dict):
            raise ComfyError('comfy_invalid_node_id')
        kind = node.get('class_type'); schema = schemas.get(kind)
        if not schema: raise ComfyError('comfy_missing_node:' + str(kind))
        if schema.get('api_node'): raise ComfyError('comfy_paid_api_node_requires_separate_connector')
        has_output |= bool(schema.get('output_node'))
        inputs = node.get('inputs')
        if not isinstance(inputs, dict): raise ComfyError('comfy_invalid_inputs')
        definitions = {**schema.get('input', {}).get('required', {}), **schema.get('input', {}).get('optional', {})}
        for required in schema.get('input', {}).get('required', {}):
            if required not in inputs: errors.append(ident + ':missing:' + required)
        for key, value in inputs.items():
            if key not in definitions: errors.append(ident + ':unknown_input:' + key); continue
            definition = definitions[key]; expected = definition[0]; options = definition[1] if len(definition) > 1 and isinstance(definition[1], dict) else {}
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int and value[0] in graph:
                source = graph[value[0]]; outputs = schemas[source['class_type']].get('output', [])
                if value[1] < 0 or value[1] >= len(outputs): errors.append(ident + ':bad_output_slot:' + key)
                elif isinstance(expected, list) or expected not in ('*', outputs[value[1]]) and outputs[value[1]] != '*': errors.append(ident + ':link_type:' + key)
            elif isinstance(expected, list):
                if value not in expected: errors.append(ident + ':not_available:' + key)
            elif expected in ('INT', 'FLOAT'):
                if type(value) not in (int, float) or not math.isfinite(value) or expected == 'INT' and type(value) is not int:
                    errors.append(ident + ':numeric_type:' + key)
                elif value < options.get('min', -math.inf) or value > options.get('max', math.inf): errors.append(ident + ':numeric_range:' + key)
            elif expected == 'STRING':
                if not isinstance(value, str): errors.append(ident + ':string_type:' + key)
            elif expected == 'BOOLEAN':
                if type(value) is not bool: errors.append(ident + ':boolean_type:' + key)
            else: errors.append(ident + ':missing_link:' + key)
    def visit(ident):
        if ident in active: raise ComfyError('comfy_graph_cycle')
        if ident in visited: return
        active.add(ident)
        for value in graph[ident]['inputs'].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int:
                if value[0] not in graph: raise ComfyError('comfy_missing_link_node')
                visit(value[0])
        active.remove(ident); visited.add(ident)
    for ident in graph: visit(ident)
    if not has_output: errors.append('no_output_node')
    if errors: raise ComfyError('comfy_graph_invalid:' + ';'.join(errors[:20]))
    return {'nodes': len(graph), 'links': sum(isinstance(v, list) for node in graph.values() for v in node['inputs'].values()), 'output_node': True}


def ui_workflow(graph, schemas):
    """Export importable LiteGraph v0.4 workflow, retaining live socket/widget order."""
    nodes = []; links = []; by_id = {}; count = 0
    for order, (ident, row) in enumerate(graph.items()):
        schema = schemas[row['class_type']]; widgets = []; inputs = []
        definitions = {**schema.get('input', {}).get('required', {}), **schema.get('input', {}).get('optional', {})}
        for key, definition in definitions.items():
            if key not in row['inputs']: continue
            value = row['inputs'][key]; kind = definition[0]; options = definition[1] if len(definition) > 1 and isinstance(definition[1], dict) else {}
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int:
                inputs.append({'name': key, 'type': kind, 'link': None})
            elif isinstance(kind, list) or kind in ('INT', 'FLOAT', 'STRING', 'BOOLEAN'):
                widgets.append(value)
                if options.get('control_after_generate'): widgets.append('fixed')
        outputs = [{'name': name, 'type': kind, 'links': [], 'slot_index': index} for index, (name, kind) in enumerate(zip(schema.get('output_name', schema.get('output', [])), schema.get('output', [])))]
        node = {'id': int(ident), 'type': row['class_type'], 'pos': [40 + (order % 4) * 380, 40 + (order // 4) * 380],
                'size': [340, 310], 'flags': {}, 'order': order, 'mode': 0, 'inputs': inputs, 'outputs': outputs,
                'properties': {'Node name for S&R': row['class_type']}, 'widgets_values': widgets}
        if row.get('_meta', {}).get('title'): node['title'] = row['_meta']['title']
        nodes.append(node); by_id[ident] = node
    for ident, row in graph.items():
        for index, socket in enumerate(by_id[ident]['inputs']):
            source, slot = row['inputs'][socket['name']]; count += 1
            socket['link'] = count; by_id[source]['outputs'][slot]['links'].append(count)
            links.append([count, int(source), slot, int(ident), index, socket['type']])
    return {'last_node_id': max(n['id'] for n in nodes), 'last_link_id': count, 'nodes': nodes, 'links': links,
            'groups': [], 'config': {}, 'extra': {'ds': {'scale': 0.7, 'offset': [20, 20]}}, 'version': 0.4}


class ComfyService:
    def __init__(self, root='', base='http://127.0.0.1:8188', storage=None):
        self.root = Path(root) if root else None; self.client = ComfyClient(base)
        self.storage = Path(storage) if storage else DATA / 'comfyui'
        self.storage.mkdir(parents=True, exist_ok=True)
        self.process = None; self.owner = None; self.lock = threading.RLock(); self.launch = {}
        self.process_lock=threading.Lock();self.generation=0;self.probe_owner=None
        self.gpu_mode='primary'

    def installation(self):
        root = self.root
        if root and (root / 'ComfyUI/main.py').is_file() and (root / 'python_embeded/python.exe').is_file():
            return root / 'ComfyUI', root / 'python_embeded/python.exe', root
        if root and (root / 'main.py').is_file() and (root / '.venv/Scripts/python.exe').is_file():
            return root, root / '.venv/Scripts/python.exe', root
        raise ComfyError('comfy_installation_not_configured')

    def gpu_query(self):
        return 'import torch,json;print(json.dumps([{"index":i,"name":torch.cuda.get_device_name(i),"total":torch.cuda.get_device_properties(i).total_memory} for i in range(torch.cuda.device_count())]))'

    def pick_gpu(self,devices):return max(devices,key=lambda row:row['total'])

    def server_command(self,code,python,cwd,gpu,port):
        worker=Path(sys._MEIPASS)/'assistant_runtime/comfy_worker.py' if getattr(sys,'frozen',False) else ROOT/'app/comfy_worker.py'
        command=[str(python),'-s',str(worker),'--root',str(code),'--listen','127.0.0.1','--port',str(port),'--disable-auto-launch','--cuda-device',str(gpu['index']),'--disable-pinned-memory']
        if self.gpu_mode=='dual':command[command.index('--cuda-device')]='--default-device'
        if (cwd/'python_embeded').is_dir():command.append('--windows-standalone-build')
        return command

    def server_environment(self,gpu):return os.environ.copy()

    def start(self,authorized=lambda:True):
        with self.lock:
            with self.process_lock: generation=self.generation
            if not authorized():return {'status':'cancelled','reply':'Pembukaan ComfyUI dibatalkan.'}
            try:
                stats = self.client.request('/system_stats', timeout=1)
                if not isinstance(stats, dict) or 'devices' not in stats: raise ComfyError('comfy_invalid_stats')
                return {'status': 'done', 'reply': 'ComfyUI sudah merespons; server yang ada tidak diambil alih.', 'url': self.client.base, 'owned': bool(self.process and self.process.poll() is None)}
            except ComfyError as error:
                if str(error) != 'comfy_service_unreachable': raise
            if self.process and self.process.poll() is None:
                return {'status': 'running', 'reply': 'Server ComfyUI milik Leva masih memulai. Periksa status, jangan start ulang.', 'url': self.client.base}
            code, python, cwd = self.installation()
            # CUDA enumeration differs from nvidia-smi on this laptop; query the actual embedded runtime.
            query = self.gpu_query()
            from windows_runtime import ProcessJob
            with self.process_lock:
                if generation!=self.generation or not authorized():return {'status':'cancelled','reply':'Pembukaan ComfyUI dibatalkan.'}
                probe=subprocess.Popen([str(python),'-s','-c',query],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=0x08000000)
                try:probe_owner=ProcessJob(probe)
                except OSError:probe.terminate();probe.wait(timeout=5);raise
                self.probe_owner=probe_owner
            try:stdout,_=probe.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                probe_owner.close();probe.communicate(timeout=5);raise ComfyError('comfy_cuda_probe_timeout') from None
            finally:
                probe_owner.close()
                with self.process_lock:
                    if self.probe_owner is probe_owner:self.probe_owner=None
            if generation!=self.generation or not authorized():return {'status':'cancelled','reply':'Pembukaan ComfyUI dibatalkan.'}
            if probe.returncode: raise ComfyError('comfy_cuda_probe_failed')
            devices = json.loads(stdout.strip().splitlines()[-1])
            if not devices: raise ComfyError('comfy_cuda_gpu_unavailable')
            gpu = self.pick_gpu(devices)
            parsed = urlparse(self.client.base); port = parsed.port or 80
            command = self.server_command(code,python,cwd,gpu,port)
            with self.process_lock:
                if generation!=self.generation or not authorized():return {'status':'cancelled','reply':'Pembukaan ComfyUI dibatalkan.'}
                with (self.storage / 'server.log').open('ab') as log:
                    process = subprocess.Popen(command, cwd=str(cwd), env=self.server_environment(gpu),stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=0x08000000)
                try: owner = ProcessJob(process)
                except OSError:
                    process.terminate(); process.wait(timeout=5); raise
                self.process = process; self.owner = owner
            self.launch = {'gpu': gpu['name'], 'cuda_index': gpu['index'], 'pid': process.pid}
            return {'status': 'running', 'reply': 'Server ComfyUI dimulai pada GPU terpilih. Belum siap sebelum status API merespons.', 'url': self.client.base, **self.launch}

    def stop(self):
        with self.process_lock:
            self.generation+=1
            if self.probe_owner:self.probe_owner.close();self.probe_owner=None
            if self.owner: self.owner.close(); self.owner = None
        return {'status': 'done', 'reply': 'Server ComfyUI yang dimiliki Leva dihentikan; server pengguna tidak dihentikan.'}

    def status(self):
        try:
            stats = self.client.request('/system_stats', timeout=2); queue = self.client.request('/queue', timeout=2)
        except ComfyError:
            return {'status': 'running' if self.process and self.process.poll() is None else 'failed',
                    'reply': 'ComfyUI belum siap. Periksa kembali status atau log server; belum ada workflow dijalankan.', 'url': self.client.base,
                    'server_exit_code': self.process.poll() if self.process else None, **self.launch}
        return {'status': 'done', 'reply': 'API ComfyUI merespons.', 'url': self.client.base,
                'devices': [{k: row.get(k) for k in ('name', 'vram_total', 'vram_free')} for row in stats.get('devices', [])],
                'queue': {'running': len(queue.get('queue_running', [])), 'pending': len(queue.get('queue_pending', []))}, **self.launch}

    def catalog(self, query='', category=''):
        categories = self.client.request('/models')
        if not isinstance(categories, list): raise ComfyError('comfy_invalid_model_catalog')
        category=category.strip().lower()
        if category in ('all','semua','*'):category=''
        wanted = [part.strip() for part in re.split(r'[,;]',category) if part.strip()] if category else [c for c in ('checkpoints', 'loras', 'vae', 'diffusion_models', 'text_encoders', 'controlnet', 'upscale_models') if c in categories]
        found = {}
        for name in wanted:
            if name not in categories: raise ComfyError('comfy_unknown_model_category:available='+','.join(categories))
            rows = self.client.request('/models/' + quote(name, safe=''))
            if not isinstance(rows, list): raise ComfyError('comfy_invalid_model_catalog')
            matches = [r for r in rows if isinstance(r, str) and query.casefold() in r.casefold()]
            found[name] = {'total': len(rows), 'matches': matches[:80], 'matched': len(matches)}
        return {'status': 'done', 'reply': 'Model yang dilaporkan instalasi ComfyUI; nama tidak sama dengan bukti kompatibilitas atau inferensi.', 'catalog': found, 'untrusted_data': True}

    def node_info(self, name):
        schema = self.client.schemas([name])[name]
        return {'status': 'done', 'reply': 'Schema node dari server aktif.', 'node': name,
                'schema': {k: schema[k] for k in ('input', 'output', 'output_name', 'output_node') if k in schema}, 'untrusted_data': True}

    def _record(self, ident):
        if not re.fullmatch(r'[0-9a-f]{12}', ident or ''): raise ComfyError('comfy_invalid_workflow_id')
        path = self.storage / ident / 'record.json'
        if not path.is_file(): raise ComfyError('comfy_workflow_not_found')
        record = json.loads(path.read_text('utf-8'))
        if record['base'] != self.client.base: raise ComfyError('comfy_workflow_server_mismatch')
        return record

    def _save(self, record):
        folder = self.storage / record['id']; folder.mkdir(exist_ok=True)
        temp = folder / 'record.tmp'
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8'); temp.replace(folder / 'record.json')

    def prepare(self, checkpoint, positive, negative='', loras=None, vae='', width=1024, height=1024, steps=20, seed=1, vae_device=''):
        if not positive.strip(): raise ComfyError('comfy_image_prompt_required')
        if not 64 <= int(width) <= 2048 or not 64 <= int(height) <= 2048 or int(width) % 8 or int(height) % 8: raise ComfyError('comfy_size_64_2048_multiple_8')
        if not 1 <= int(steps) <= 80: raise ComfyError('comfy_steps_1_80')
        loras = loras or []
        if not isinstance(loras, list) or len(loras) > 6: raise ComfyError('comfy_loras_list_max_6')
        graph = {'1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': checkpoint}}}
        model = ['1', 0]; clip = ['1', 1]; vae_link = ['1', 2]
        for row in loras:
            if not isinstance(row, dict) or set(row) - {'name', 'strength'} or not isinstance(row.get('name'), str): raise ComfyError('comfy_invalid_lora')
            strength = float(row.get('strength', 0.7))
            if not math.isfinite(strength) or not -2 <= strength <= 2: raise ComfyError('comfy_lora_strength')
            ident = str(len(graph) + 1)
            graph[ident] = {'class_type': 'LoraLoader', 'inputs': {'model': model, 'clip': clip, 'lora_name': row['name'], 'strength_model': strength, 'strength_clip': strength}}
            model = [ident, 0]; clip = [ident, 1]
        if vae:
            ident = str(len(graph) + 1); graph[ident] = {'class_type': 'VAELoader', 'inputs': {'vae_name': vae}}; vae_link = [ident, 0]
        def add(kind, values, title=''):
            ident = str(len(graph) + 1); graph[ident] = {'class_type': kind, 'inputs': values}
            if title: graph[ident]['_meta'] = {'title': title}
            return ident
        pos = add('CLIPTextEncode', {'text': positive, 'clip': clip}, 'Positive prompt')
        neg = add('CLIPTextEncode', {'text': negative, 'clip': clip}, 'Negative prompt')
        latent = add('EmptyLatentImage', {'width': int(width), 'height': int(height), 'batch_size': 1})
        sample = add('KSampler', {'seed': int(seed), 'steps': int(steps), 'cfg': 7.0, 'sampler_name': 'euler', 'scheduler': 'normal', 'denoise': 1.0,
                                 'model': model, 'positive': [pos, 0], 'negative': [neg, 0], 'latent_image': [latent, 0]})
        if vae_device:
            if vae_device not in ('rtx4050','rtx5070'):raise ComfyError('comfy_vae_device_invalid')
            schema=self.client.schemas(['LevaVAEDecodeDevice'])['LevaVAEDecodeDevice']
            choices=schema['input']['required']['device'][0]
            matches=[name for name in choices if vae_device[3:] in name.replace(' ','').lower()]
            if len(matches)!=1:raise ComfyError('comfy_vae_gpu_not_visible_start_dual_session')
            decode=add('LevaVAEDecodeDevice',{'samples':[sample,0],'vae':vae_link,'device':matches[0],'tile_size':256})
        else:decode = add('VAEDecode', {'samples': [sample, 0], 'vae': vae_link})
        add('SaveImage', {'images': [decode, 0], 'filename_prefix': 'Leva/workflow'})
        return self.prepare_graph(graph, 'Checkpoint + LoRA', {'checkpoint': checkpoint, 'loras': loras, 'vae': vae,
                      'width': int(width), 'height': int(height), 'steps': int(steps), 'vae_device':vae_device,'compatibility': 'schema_verified_inference_not_yet_tested'})

    def prepare_graph(self, graph, title='Imported API workflow', selection=None):
        if not isinstance(graph,dict) or not 1<=len(graph)<=120 or any(not isinstance(row,dict) or not isinstance(row.get('class_type'),str) for row in graph.values()):raise ComfyError('comfy_invalid_api_graph')
        self.check_vae(graph)
        schemas = self.client.schemas([row['class_type'] for row in graph.values()])
        verified = validate_graph(graph, schemas); workflow = ui_workflow(graph, schemas)
        ident = uuid.uuid4().hex[:12]; folder = self.storage / ident; folder.mkdir()
        api_bytes = json.dumps(graph, ensure_ascii=False, indent=2).encode('utf-8')
        (folder / 'api.json').write_bytes(api_bytes)
        ui_bytes=json.dumps(workflow,ensure_ascii=False,indent=2).encode('utf-8');(folder / 'workflow.json').write_bytes(ui_bytes)
        record = {'id': ident, 'base': self.client.base, 'title': title, 'state': 'prepared', 'sha256': hashlib.sha256(api_bytes).hexdigest(),
                  'ui_sha256':hashlib.sha256(ui_bytes).hexdigest(),
                  'selection': selection or {}, 'verified': verified, 'prompt_id': '', 'published': False, 'created': time.time()}
        self._save(record)
        return self.describe(ident)

    def check_vae(self,graph):
        # The simple SD/SDXL template has a four-channel latent. Flux AE is 16-channel.
        if not any(n.get('class_type')=='EmptyLatentImage' for n in graph.values()):return
        for node in graph.values():
            if node.get('class_type')!='VAELoader':continue
            name=node.get('inputs',{}).get('vae_name','')
            if Path(name).name.casefold()=='ae.safetensors':raise ComfyError('comfy_incompatible_flux_ae_with_sd_latent_use_checkpoint_vae')
            if not self.root or not name.endswith('.safetensors'):continue
            path=(self.root/'ComfyUI/models/vae'/name).resolve()
            if not path.is_relative_to((self.root/'ComfyUI/models/vae').resolve()) or not path.is_file():continue
            try:
                import struct
                with path.open('rb') as stream:
                    size=struct.unpack('<Q',stream.read(8))[0]
                    if size>2_000_000:continue
                    header=json.loads(stream.read(size))
                for key,value in header.items():
                    if key.endswith('decoder.conv_in.weight') and isinstance(value,dict):
                        shape=value.get('shape',[])
                        if len(shape)==4 and shape[1]!=4:raise ComfyError('comfy_external_vae_latent_mismatch:'+str(shape[1]))
            except (OSError,ValueError,KeyError,struct.error) as error:
                if isinstance(error,ComfyError):raise

    def describe(self, ident):
        record = self._record(ident); folder = self.storage / ident
        graph = json.loads((folder / 'api.json').read_text('utf-8'))
        return {'status': 'done', 'reply': 'Workflow tersimpan dan schema/link diperiksa. Belum menghasilkan gambar.' if record['state'] == 'prepared' else 'Keadaan workflow tersimpan dibaca.',
                'workflow_id': ident, 'workflow_state': record['state'], 'prompt_id': record.get('prompt_id', ''),
                'files': {'workflow': str(folder / 'workflow.json'), 'api': str(folder / 'api.json')},
                'selection': record['selection'], 'verified': record['verified'], 'published': record.get('published', False),
                'map': [{'id': key, 'node': row['class_type'], 'inputs': {k: v for k, v in row['inputs'].items() if isinstance(v, list)}} for key, row in graph.items()],
                'task_verified': True}

    def publish(self, ident):
        with self.lock:
            record = self._record(ident)
            if record.get('published'): return self.describe(ident)
            folder = self.storage / ident; data = json.loads((folder / 'workflow.json').read_text('utf-8'))
            if hashlib.sha256((folder/'workflow.json').read_bytes()).hexdigest()!=record['ui_sha256']:raise ComfyError('comfy_workflow_changed_after_prepare')
            route = '/userdata/' + quote('workflows/Leva/' + ident + '.json', safe='')
            try:self.client.request(route + '?overwrite=false', data)
            except ComfyError as error:
                if not str(error).startswith('comfy_http_409'):raise
                # A previous upload may have succeeded before its response was lost.
            observed = self.client.request(route)
            if observed != data: raise ComfyError('comfy_published_workflow_mismatch')
            record['published'] = True; self._save(record)
            result = self.describe(ident); result['reply'] = 'Workflow tersimpan dan terbaca kembali di pustaka ComfyUI: Leva/' + ident + '.json. Belum ada generation dijalankan.'
            return result

    def submit(self, ident, authorized=lambda:True):
        with self.lock:
            generation=self.generation
            record = self._record(ident)
            if record.get('submission_attempted'):
                # A lost response is not permission to duplicate a GPU job.
                result = self.poll(ident); result['reply'] += ' Pengiriman lama tidak diulang otomatis.'; return result
            folder = self.storage / ident; raw = (folder / 'api.json').read_bytes()
            if hashlib.sha256(raw).hexdigest() != record['sha256']: raise ComfyError('comfy_workflow_changed_after_prepare')
            if hashlib.sha256((folder/'workflow.json').read_bytes()).hexdigest()!=record['ui_sha256']:raise ComfyError('comfy_workflow_changed_after_prepare')
            graph = json.loads(raw); validate_graph(graph, self.client.schemas([row['class_type'] for row in graph.values()]))
            self.check_vae(graph)
            if generation!=self.generation or not authorized():return {'status':'cancelled','reply':'Generation dibatalkan sebelum dikirim ke ComfyUI.','workflow_id':ident}
            # Client-assigned id is supported by this installed ComfyUI; persisted BEFORE request.
            prompt = str(uuid.uuid4()); record.update(prompt_id=prompt, state='submission_unknown', submission_attempted=True); self._save(record)
            self.last_submission_id=ident
            try:
                answer = self.client.request('/prompt', {'prompt': graph, 'prompt_id': prompt, 'client_id': 'leva-' + ident,
                                                        'extra_data': {'extra_pnginfo': {'workflow': json.loads((folder / 'workflow.json').read_text('utf-8'))}}}, timeout=15)
            except ComfyError:
                # Even a timeout can have queued successfully. Recovery must observe queue/history.
                raise
            actual = answer.get('prompt_id')
            if not isinstance(actual, str) or not actual: raise ComfyError('comfy_missing_prompt_id')
            record.update(prompt_id=actual, state='queued'); self._save(record)
            return {'status': 'running', 'reply': 'Workflow masuk antrean. Poll workflow_id sampai history menunjukkan selesai dan output tersedia.', 'workflow_id': ident, 'prompt_id': actual, 'workflow_state': 'queued'}

    def poll(self, ident):
        with self.lock:
            record = self._record(ident); prompt = record.get('prompt_id')
            if not prompt: return self.describe(ident)
            history = self.client.request('/history/' + quote(prompt, safe=''))
            if prompt in history:
                entry = history[prompt]; status = entry.get('status', {}); outputs = []
                for node, values in entry.get('outputs', {}).items():
                    for image in values.get('images', []):
                        if all(isinstance(image.get(key, ''), str) for key in ('filename', 'subfolder', 'type')):
                            outputs.append({'node': node, 'filename': image['filename'], 'subfolder': image.get('subfolder', ''), 'type': image.get('type', 'output')})
                done = status.get('completed') is True and status.get('status_str') == 'success'
                record.update(state='completed' if done else 'failed', outputs=outputs); self._save(record)
                return {'status': 'done' if done else 'failed', 'reply': 'Eksekusi ComfyUI selesai; periksa daftar output.' if done else 'ComfyUI melaporkan kegagalan; workflow tidak dikirim ulang.',
                        'workflow_id': ident, 'prompt_id': prompt, 'workflow_state': record['state'], 'outputs': outputs, 'task_verified': done,
                        'errors': [message for message in status.get('messages', []) if isinstance(message, list) and message and message[0] in ('execution_error', 'execution_interrupted')][:2]}
            queue = self.client.request('/queue')
            state = next((key for key in ('queue_running', 'queue_pending') if any(len(row) > 1 and row[1] == prompt for row in queue.get(key, []))), None)
            if state:
                record['state'] = 'running' if state == 'queue_running' else 'queued'; self._save(record)
                return {'status': 'running', 'reply': 'Job ComfyUI masih ' + record['state'] + '; jangan kirim ulang.', 'workflow_id': ident, 'prompt_id': prompt, 'workflow_state': record['state']}
            record['state'] = 'unknown'; self._save(record)
            return {'status': 'unverified', 'reply': 'Job tidak ditemukan di queue/history. Tidak dikirim ulang otomatis; periksa server dan tugas sebelum memutuskan percobaan baru.', 'workflow_id': ident, 'prompt_id': prompt, 'workflow_state': 'unknown'}

    def recent(self):
        rows = []
        for path in sorted(self.storage.glob('*/record.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            try:
                row = json.loads(path.read_text('utf-8'))
                if row['base'] == self.client.base: rows.append({k: row.get(k) for k in ('id', 'title', 'state', 'prompt_id', 'selection')})
            except (OSError, ValueError, KeyError): continue
        return {'status': 'done', 'reply': 'Workflow dan job persisten milik Leva; status job dibuktikan lagi melalui poll.', 'workflows': rows}
