"""Dedicated Graphify structural index; keep the original visual/semantic graph intact."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app'
OUT = Path('D:/AI/AI Lokal Asisten/Leva/analysis/code-map/graphify-out')
OUT.mkdir(parents=True, exist_ok=True)
from graphify.extract import extract
files = sorted(p for p in SOURCE.rglob('*') if p.is_file() and p.suffix in ('.py', '.js', '.html', '.css')
               and not any(part in ('graphify-out', '__pycache__', 'node_modules') for part in p.relative_to(SOURCE).parts))
if len(files) > 500:
    raise RuntimeError('narrow_structural_scope_required')
start = time.monotonic()
data = extract(files, cache_root=OUT.parent, root=SOURCE, parallel=False)
graph = {'directed': True, 'multigraph': True, 'graph': {'producer': 'graphifyy', 'version': importlib.metadata.version('graphifyy'),
         'mode': 'structural_only', 'source_root': str(SOURCE), 'semantic_extraction': False},
         'nodes': data['nodes'], 'links': data['edges'],
         'source_sha256': {p.relative_to(SOURCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(OUT / 'graph.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf8')
proof = {'files': len(files), 'nodes': len(graph['nodes']), 'edges': len(graph['links']), 'elapsed_s': round(time.monotonic()-start, 3),
         'source_root': str(SOURCE), 'output': str(OUT / 'graph.json'), 'producer': graph['graph'], 'extra_model_loaded': False}
(OUT / 'build-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf8')
print(json.dumps(proof))
