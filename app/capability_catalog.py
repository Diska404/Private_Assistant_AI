"""Provenance for installed adapters and curated procedures, not executable plugins."""
import json
from pathlib import Path


def catalog():
    from rea_analysis import ReaAnalysis
    from code_graph import CodeGraph
    from workflow_skills import WorkflowSkills
    try:
        rows = json.loads(Path(__file__).with_name('capability_sources.json').read_text('utf-8'))
    except (OSError, ValueError):
        rows = []
    return {'status': 'done', 'reply': 'Katalog membedakan adapter, panduan dan referensi. Status runtime bukan bukti semua task berhasil.',
            'sources': rows, 'rea': ReaAnalysis().status(), 'graph': CodeGraph().run({'action': 'status'}),
            'workflow_count': len(WorkflowSkills().rows()), 'external_hooks_executed': False, 'extra_model_loaded': False}
