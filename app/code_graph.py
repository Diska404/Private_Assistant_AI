"""Read Graphify node-link artifacts on demand; never import target-project code."""
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import threading

from file_workspace import checked_path, source_redact
from paths import ROOT, DATA


class CodeGraph:
    def __init__(self, root=None):
        self.root = Path(root) if root else ROOT / 'app'
        generated = DATA / 'analysis/code-map/graphify-out/graph.json'
        self.path = generated if root is None and generated.is_file() else self.root / 'graphify-out/graph.json'
        self.lock = threading.RLock()
        self.signature = None

    def load(self):
        stat = self.path.stat()
        if stat.st_size > 32_000_000:
            raise ValueError('graph_too_large')
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature == self.signature:
            return
        raw = self.path.read_bytes()
        graph = json.loads(raw)
        rows, edges = graph.get('nodes'), graph.get('links', graph.get('edges'))
        if not isinstance(rows, list) or not isinstance(edges, list) or len(rows) > 100_000 or len(edges) > 300_000:
            raise ValueError('invalid_graph')
        nodes = {}
        for node in rows:
            if not isinstance(node, dict) or not isinstance(node.get('id'), str):
                raise ValueError('invalid_graph_node')
            nodes[node['id']] = node
        adjacency = {ident: [] for ident in nodes}
        for edge in edges:
            if not isinstance(edge, dict):
                raise ValueError('invalid_graph_edge')
            a, b = edge.get('source'), edge.get('target')
            if a in nodes and b in nodes:
                adjacency[a].append((b, edge))
                adjacency[b].append((a, edge))
        self.nodes, self.adjacency = nodes, adjacency
        self.sha = hashlib.sha256(raw).hexdigest()
        self.signature = signature
        self.edge_count = len(edges)
        self.source_hashes = graph.get('source_sha256', {})

    def public_node(self, ident):
        node = self.nodes[ident]
        result = {'id': ident, 'label': source_redact(str(node.get('label', ident)))[:250]}
        for key in ('source_file', 'source_location', 'type', 'community'):
            if key in node:
                result[key] = source_redact(str(node[key]))[:300]
        # Graph evidence is historical. Compare source timestamps, never infer current behavior.
        source = node.get('source_file')
        result['source_check'] = 'external_or_unspecified'
        if isinstance(source, str) and source:
            try:
                path = checked_path(str(self.root / source))
                if path.is_relative_to(self.root.resolve()) and path.is_file():
                    result['source_path'] = str(path)
                    expected = self.source_hashes.get(source) if isinstance(self.source_hashes, dict) else None
                    if expected:
                        result['source_check'] = 'hash_matches' if path.stat().st_size <= 2_000_000 and hashlib.sha256(path.read_bytes()).hexdigest() == expected else 'changed_after_graph'
                    else:
                        result['source_check'] = 'changed_after_graph' if path.stat().st_mtime_ns > self.signature[0] else 'timestamp_not_newer'
            except (OSError, ValueError):
                pass
        return result

    def matches(self, value):
        if value.strip() in self.nodes:
            return [value.strip()]
        value = value.strip().casefold()
        if not value:
            return []
        if value in self.nodes:
            return [value]
        exact = [ident for ident, node in self.nodes.items() if str(node.get('label', '')).casefold() == value]
        if exact:
            return exact[:12]
        terms = set(re.findall(r'\w{3,}', value))
        ranked = [(sum(t in str(n.get('label', '')).casefold() for t in terms), ident) for ident, n in self.nodes.items()]
        return [ident for score, ident in sorted(ranked, key=lambda row: (-row[0], row[1])) if score][:12]

    def run(self, args, authorized=lambda: True):
        if not authorized():
            return {'status': 'cancelled', 'reply': 'Pembacaan graf dibatalkan.'}
        try:
            with self.lock:
                self.load()
                base = {'status': 'done', 'reply': 'Graf kode dibaca. Verifikasi source terbaru sebelum mengubah atau menyimpulkan perilaku aplikasi.',
                        'graph_sha256': self.sha, 'graph_path': str(self.path), 'source_root': str(self.root), 'untrusted_data': True,
                        'stale_marker': (self.path.parent / '.needs_update').exists(), 'node_count': len(self.nodes), 'edge_count': self.edge_count}
                action = args['action']
                if action == 'status':
                    return base
                seeds = self.matches(args.get('query', ''))
                if not seeds:
                    return {**base, 'nodes': [], 'edges': [], 'reply': 'Tidak ada simpul cocok pada graf. Cari nama modul/simbol dari source; jangan mengarang hubungan.'}
                if action == 'path':
                    targets = self.matches(args.get('target', ''))
                    if len(seeds) != 1 or len(targets) != 1:
                        return {**base, 'status': 'needs_input', 'reply': 'Pilih ID simpul asal dan tujuan yang tepat dari kandidat graf.',
                                'source_candidates': [self.public_node(n) for n in seeds], 'target_candidates': [self.public_node(n) for n in targets]}
                    queue = deque([seeds[0]]); prior = {seeds[0]: None}; via = {}
                    while queue and targets[0] not in prior and len(prior) < 10_000:
                        current = queue.popleft()
                        for other, edge in self.adjacency[current]:
                            if other not in prior:
                                prior[other] = current; via[other] = edge; queue.append(other)
                    if targets[0] not in prior:
                        return {**base, 'nodes': [], 'edges': [], 'reply': 'Jalur tidak ditemukan dalam batas penelusuran 10.000 simpul.', 'search_limited': len(prior) >= 10_000}
                    chain = []; node = targets[0]
                    while node is not None:
                        chain.append(node); node = prior[node]
                    chain.reverse()
                    if len(chain) > 30:
                        return {**base, 'status': 'needs_input', 'reply': 'Jalur melebihi 30 simpul; pilih modul perantara.'}
                    chosen = chain; links = [via[n] for n in chain[1:]]
                elif action in ('query', 'explain'):
                    chosen = seeds[:4]; links = []
                    for ident in list(chosen):
                        for other, edge in self.adjacency[ident]:
                            if len(links) >= 24:
                                break
                            if other not in chosen:
                                chosen.append(other)
                            links.append(edge)
                else:
                    raise ValueError('unknown_graph_action')
                safe_edges = [{k: source_redact(str(e[k]))[:300] for k in ('source', 'target', 'relation', 'confidence', 'source_location') if k in e} for e in links]
                if not authorized():
                    return {'status': 'cancelled', 'reply': 'Pembacaan graf dibatalkan.'}
                return {**base, 'nodes': [self.public_node(n) for n in chosen], 'edges': safe_edges,
                        'direction': 'undirected_connectivity; retain original source/target in edges', 'limits': {'seed_nodes': 4, 'edges': 24, 'path_nodes': 30}}
        except (OSError, ValueError, TypeError, KeyError) as error:
            return {'status': 'failed', 'code': type(error).__name__, 'reply': 'Graf belum tersedia atau formatnya tidak valid. Source proyek tetap bisa dibaca melalui project_action.'}
