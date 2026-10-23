"""Publish an allowlisted graph snapshot without machine paths or runtime data."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def write_utf8(path, text):
    # Stable bytes across Windows, Git checkout and Linux CI.
    path.write_bytes((text.replace('\r\n', '\n').rstrip() + '\n').encode('utf-8'))


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"\b[A-Za-z]:[\\/][^\r\n\"<>|]*", "[local-path]", value)
    value = re.sub(r"https?://[\w.-]+\.ts\.net[^\s\"<>)]*", "[private-network]", value)
    value = re.sub(r"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)\b", "[private-address]", value)
    return value


def export(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    selected = ['graph.json', 'graph-health.json', 'cohesion.json', '.graphify_labels.json']
    for name in selected:
        value = clean(json.loads((source / name).read_text(encoding='utf-8')))
        write_utf8(destination / name, json.dumps(value, ensure_ascii=False, indent=2))
    for name in ['GRAPH_REPORT.md', 'benchmark.txt']:
        write_utf8(destination / name, clean((source / name).read_text(encoding='utf-8')))
    trace = source / 'queries' / 'levawindow-flow-20261023.md'
    write_utf8(destination / 'LEVAWINDOW_FLOW.md', clean(trace.read_text(encoding='utf-8')))
    graph = json.loads((destination / 'graph.json').read_text(encoding='utf-8'))
    import networkx as nx
    from graphify.export import to_html
    network = nx.node_link_graph(graph, edges='links')
    communities = {}
    for node in graph['nodes']:
        communities.setdefault(int(node['community']), []).append(node['id'])
    labels = {int(k): v for k, v in json.loads((destination / '.graphify_labels.json').read_text(encoding='utf-8')).items()}
    if not to_html(network, communities, str(destination / 'graph.html'), community_labels=labels):
        raise RuntimeError('HTML graph export did not produce an output')
    write_utf8(destination / 'graph.html', (destination / 'graph.html').read_text(encoding='utf-8'))
    provenance = {
        'snapshot_date': '2026-10-23', 'application_snapshot': '0.28.0',
        'repository_source_snapshot': '0.3.0',
        'scope': 'app/; static structural extraction and semantic documentation analysis',
        'files_detected': 167, 'nodes': len(graph['nodes']), 'edges': len(graph['links']),
        'communities': 106, 'directed': False,
        'limits': ['Not runtime acceptance evidence.', 'Repository source remains the historical 0.3.0 import; graph describes the separate 0.28.0 development snapshot.', 'voice_packs.json, two CSS files and one web manifest lack graph representation.', 'Inferred links and unresolved extraction references require source verification.'],
        'privacy': 'Allowlisted derived artifacts only; machine paths and private network addresses redacted. No databases, API keys, audio, model weights, extraction logs or conversation history exported.',
        'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.iterdir()) if p.is_file() and p.name != 'SNAPSHOT.json'},
    }
    write_utf8(destination / 'SNAPSHOT.json', json.dumps(provenance, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    export(args.source.resolve(), args.output.resolve())
