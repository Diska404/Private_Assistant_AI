"""Pinned, on-demand REA static JavaScript analysis. Targets are never launched."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import re
import threading
import time
import uuid

from file_workspace import checked_path, source_redact
from paths import DATA


def scrub(value):
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if re.search(r'password|passwd|api[_ -]?key|access[_ -]?token|secret|authorization', str(k), re.I) else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return source_redact(value) if isinstance(value, str) else value


class ReaAnalysis:
    def __init__(self, config=None, storage=None):
        self.config = Path(config) if config else DATA / 'skills/rea-runtime.json'
        self.storage = Path(storage) if storage else DATA / 'analysis/rea'

    def runtime(self):
        if self.config.stat().st_size > 8000:
            raise ValueError('invalid_rea_config')
        row = json.loads(self.config.read_text('utf-8'))
        for name in ('node', 'entry'):
            path = checked_path(row[name])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row[name + '_sha256']:
                raise ValueError('rea_runtime_changed')
        return row

    def status(self):
        try:
            row = self.runtime()
            return {'status': 'done', 'reply': 'Runtime REA statis terpasang; analisis hanya berjalan saat diminta.', 'version': row['version'],
                    'capabilities': ['static_javascript_electron'], 'native_analysis': False, 'generic_mcp': False, 'always_running': False}
        except (OSError, ValueError, KeyError, TypeError):
            return {'status': 'needs_input', 'reply': 'Runtime REA belum siap atau berubah. Periksa instalasi terpisah Leva; tidak ada installer dijalankan otomatis.'}

    def run(self, args, allowed, authorized=lambda: True, timeout=60):
        if not authorized():
            return {'status': 'cancelled', 'reply': 'Analisis dibatalkan.'}
        if args['action'] == 'status':
            return self.status()
        if args['action'] != 'javascript':
            raise ValueError('unsupported_rea_action')
        target = checked_path(args.get('path', ''))
        allowed(target)
        if not target.is_dir() and target.suffix.casefold() != '.asar':
            raise ValueError('rea_directory_or_asar_required')
        # Narrow projects only: inspecting an entire drive/home is not a meaningful analysis target.
        if target in (Path(target.anchor), Path.home()) or len(target.parts) < 3:
            raise ValueError('rea_project_target_required')
        try:
            runtime = self.runtime()
        except (OSError, ValueError, KeyError, TypeError):
            return self.status()
        self.storage.mkdir(parents=True, exist_ok=True)
        ident = uuid.uuid4().hex[:12]
        output = self.storage / (ident + '.json')
        projection = ','.join(('evidence_id', 'subject', 'operation', 'confidence', 'authority', 'limitations',
            'normalized_result.input_path', 'normalized_result.statistics', 'normalized_result.summary', 'normalized_result.limitations',
            'normalized_result.graph.coverage', 'normalized_result.graph.graph_id',
            'normalized_result.graph.nodes[0,30]', 'normalized_result.graph.edges[0,40]'))
        argsv = [runtime['node'], runtime['entry'], 'analyze-javascript-application', str(target), '--json',
                 '--max-heap-mb', '512', '--analysis-timeout-ms', '45000', '--max-semantic-nodes', '20000',
                 '--max-semantic-unknowns', '10000', '--filter-output', projection]
        # Do not inherit provider keys or inject target packages via NODE_OPTIONS/NODE_PATH.
        env = {k: v for k, v in os.environ.items() if not any(w in k.upper() for w in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')) and k.upper() not in ('NODE_OPTIONS', 'NODE_PATH')}
        env['PATH'] = str(Path(runtime['node']).parent) + os.pathsep + env.get('PATH', '')
        start = time.monotonic(); chunks = [bytearray(), bytearray()]; limit = threading.Event()
        proc = subprocess.Popen(argsv, cwd=str(self.storage), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, creationflags=0x08000000 if os.name == 'nt' else 0)
        def drain(pipe, index):
            try:
                while raw := pipe.read(8192):
                    remaining = 2_000_000 - len(chunks[index])
                    chunks[index].extend(raw[:max(remaining, 0)])
                    if len(raw) > remaining:
                        limit.set()
            finally:
                pipe.close()
        threads = [threading.Thread(target=drain, args=(pipe, i), daemon=True) for i, pipe in enumerate((proc.stdout, proc.stderr))]
        for thread in threads:
            thread.start()
        reason = None
        try:
            while proc.poll() is None:
                if not authorized(): reason = 'cancelled'
                elif limit.is_set(): reason = 'output_limit'
                elif time.monotonic() - start > timeout: reason = 'timeout'
                if reason:
                    break
                time.sleep(.05)
        finally:
            if proc.poll() is None:
                import psutil
                try:
                    owner = psutil.Process(proc.pid)
                    children = owner.children(recursive=True)
                    for child in reversed(children):
                        try: child.kill()
                        except psutil.Error: pass
                    owner.kill()
                except psutil.Error:
                    pass
            proc.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=2)
        if reason or limit.is_set() or not authorized():
            return {'status': 'cancelled' if reason == 'cancelled' or not authorized() else 'failed', 'code': reason or 'output_limit',
                    'reply': 'Analisis tidak selesai; hasil parsial tidak dianggap bukti keberhasilan.', 'elapsed_s': round(time.monotonic() - start, 3)}
        if proc.returncode:
            return {'status': 'failed', 'code': 'rea_exit_' + str(proc.returncode), 'reply': 'REA belum berhasil menganalisis target.',
                    'diagnostic': source_redact(chunks[1].decode('utf-8', 'replace'))[:1800]}
        try:
            data = json.loads(chunks[0].decode('utf-8'))
            if not isinstance(data, dict): raise ValueError('invalid_rea_response')
        except (ValueError, UnicodeError):
            return {'status': 'failed', 'code': 'invalid_rea_json', 'reply': 'Keluaran REA tidak dapat dibaca sebagai bukti terstruktur.'}
        # Store the redacted projected report, not the potentially huge complete evidence graph.
        data = scrub(data)
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        output.write_bytes(raw.encode('utf-8'))
        normalized = data.get('normalized_result')
        if not isinstance(normalized, dict):
            return {'status': 'failed', 'code': 'rea_missing_evidence', 'reply': 'REA belum mengembalikan hasil analisis dengan struktur bukti yang dikenali.'}
        return {'status': 'done', 'reply': 'Analisis statis selesai dengan laporan ringkasan dan sampel hubungan. Laporan ini menjelaskan kode, bukan bukti perilaku saat aplikasi berjalan.',
                'target': str(target), 'report_path': str(output), 'report_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
                'elapsed_s': round(time.monotonic() - start, 3), 'exit_code': proc.returncode, 'untrusted_data': True, 'report_redacted': True,
                'report_projection': {'full_evidence_saved': False, 'nodes': 30, 'edges': 40, 'semantic_nodes_limit': 20000, 'worker_heap_mib': 512},
                'summary': source_redact(json.dumps(normalized.get('summary', {}), ensure_ascii=False))[:2200],
                'statistics': source_redact(json.dumps(normalized.get('statistics', {}), ensure_ascii=False))[:1800],
                'limitations': [source_redact(str(x))[:300] for x in data.get('limitations', [])[:8]],
                'evidence_id': str(data.get('evidence_id', ''))[:200],
                'evidence_excerpt': raw[:6500], 'excerpt_truncated': len(raw) > 6500, 'version': runtime['version']}
