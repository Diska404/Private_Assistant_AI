"""Run offline regression suites without writing fixture tasks to user history."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'experiments')]
import task_journal


def main():
    original = task_journal.TaskJournal
    with tempfile.TemporaryDirectory(prefix='leva-regression-') as folder:
        active=[0]
        def isolated_journal(path=None):
            return original(Path(folder)/('tasks-'+str(active[0])+'.sqlite3') if path is None else path)
        class IsolatedResult(unittest.TextTestResult):
            def startTest(self,test):
                active[0]+=1
                super().startTest(test)
        with patch('task_journal.TaskJournal', side_effect=isolated_journal),patch.dict(os.environ,{'LEVA_AUDIO_DIAGNOSTICS':'0'}):
            suite = unittest.TestSuite()
            for directory in ('app', 'experiments'):
                loader = unittest.TestLoader()
                suite.addTests(loader.discover(str(ROOT / directory), pattern='test*.py'))
            result = unittest.TextTestRunner(verbosity=1,resultclass=IsolatedResult).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
