"""Run application regressions with DATA redirected before application imports."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(r'D:\AI\AI Lokal Asisten\Leva\verification\performance-20261024')
with tempfile.TemporaryDirectory(prefix='leva-regressions-') as folder:
    import paths
    paths.DATA=Path(folder)/'Leva';paths.DATA.mkdir()
    # Fixture stores and caches are outside production, including module-level defaults.
    suite=unittest.defaultTestLoader.discover(str(ROOT/'app'),pattern='test_*.py')
    started=time.monotonic()
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    from trace_store import close_all
    close_all()
    report={'tests':result.testsRun,'seconds':round(time.monotonic()-started,2),
        'failures':[{'test':str(t),'traceback':trace} for t,trace in result.failures],
        'errors':[{'test':str(t),'traceback':trace} for t,trace in result.errors],
        'skipped':[{'test':str(t),'reason':reason} for t,reason in result.skipped],
        'production_data_access':'DATA redirected before imports; real preferences/conversations not loaded',
        'successful':result.wasSuccessful()}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'regressions.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('failures','errors','skipped')},indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
