"""Rebuild using the previously installed, pinned official npm dependencies. No npm install."""
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parents[1]
DEPS=Path(r'D:\AI\AI Lokal Asisten\Github\Leva-Avatar-Renderer')
if __name__=='__main__':
 config=json.loads((DEPS/'package.json').read_text())
 if config['dependencies']!={'@pixiv/three-vrm':'3.5.5','esbuild':'0.28.2','three':'0.186.1'}:raise RuntimeError('unexpected_vendor_versions')
 entry=DEPS/'avatar-vendor-entry-r2.mjs';entry.write_bytes((ROOT/'app/leva_web/avatar-vendor-entry.mjs').read_bytes())
 subprocess.run([str(DEPS/'node_modules/@esbuild/win32-x64/esbuild.exe'),str(entry),'--bundle','--format=esm','--minify','--legal-comments=eof','--outfile='+str(ROOT/'app/leva_web/avatar-vendor.js')],check=True,timeout=30)
