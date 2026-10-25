"""Isolated browser QA for the capability catalog; no model or personal database."""
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'experiments')]
from web_bridge import WebBridge
from web_data import WebData
from web_store import WebStore
from profile_avatar import ProfileAvatar
from workflow_skills import WorkflowSkills

OUT = Path('D:/AI/AI Lokal Asisten/Leva/verification/capabilities-v031')
stop = OUT / 'stop-preview'; stop.unlink(missing_ok=True)
with tempfile.TemporaryDirectory(prefix='leva-capability-ui-') as folder:
    base = Path(folder)
    tools = SimpleNamespace(workflows=WorkflowSkills())
    data = WebData(tools)
    reader = SimpleNamespace(panel=data.panel, graph=lambda: {'nodes': [], 'edges': [], 'errors': [], 'provenance': 'Fixture only'})
    bridge = WebBridge(reader, port=8779, store=WebStore(base / 'web.db'), avatar=ProfileAvatar(base / 'avatar'))
    bridge.bootstrap = 'capabilities-v031-fixture-only'
    bridge.update({'verification_mode': True, 'phase': 'idle', 'route': 'Tanpa AI', 'route_choices': ['Tanpa AI'],
                   'workspace': 'assistant', 'language': 'id', 'busy': False, 'activity': 'UJI KATALOG · tanpa model atau data percakapan pribadi', 'version': '0.31.0'})
    bridge.log('Info', 'Uji antarmuka katalog kemampuan; tidak menjalankan agent atau model suara.')
    bridge.start()
    print(json.dumps({'url': 'http://127.0.0.1:8779/#session=capabilities-v031-fixture-only'}), flush=True)
    try:
        start = time.monotonic()
        while not stop.exists() and time.monotonic() - start < 900:
            time.sleep(.2)
    finally:
        bridge.stop()
        bridge.store.db.close()
