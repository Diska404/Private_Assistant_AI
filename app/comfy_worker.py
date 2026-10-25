"""Owned ComfyUI launcher with a bounded-memory checkpoint reader."""
import argparse
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    settings, remaining = parser.parse_known_args()
    root = Path(settings.root).resolve()
    if not (root / 'main.py').is_file(): raise ValueError('comfy_source_required')
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from image_tensor_io import install_stream_reader
    install_stream_reader()
    print('Leva: streaming CPU checkpoint reader enabled (no private whole-file mmap).', flush=True)
    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.argv = [str(root / 'main.py'), *remaining]
    runpy.run_path(str(root / 'main.py'), run_name='__main__')


if __name__ == '__main__': main()
