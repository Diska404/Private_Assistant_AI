"""Install explicit image launchers without changing user launchers or dependencies."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COMFY=Path(r'F:\AI\ComfyUI_windows_portable')
FOO=Path(r'F:\AI\Fooocus_win64_2-5-0')
UUID4050='GPU-a8b960f0-d02d-524f-a5fb-94148aa57596'
UUID5070='GPU-79515cd8-597d-8b79-8bfb-97ce69cb46e1'


def write(path,mask,command):
    text='\r\n'.join(['@echo off','setlocal','set "CUDA_VISIBLE_DEVICES='+mask+'"',
                      'cd /d "%~dp0"',command,'if errorlevel 1 pause','endlocal',''])
    path.write_bytes(text.encode('utf8'))
    print(path)


if __name__=='__main__':
    for name,mask in [('run_leva_rtx5070.bat',UUID5070),('run_leva_dual_gpu.bat',UUID5070+','+UUID4050)]:
        write(COMFY/name,mask,f'"%~dp0python_embeded\\python.exe" -s -u "{ROOT / "app/comfy_worker.py"}" --root "%~dp0ComfyUI" --listen 127.0.0.1 --port 8188 --disable-auto-launch --disable-pinned-memory')
    write(FOO/'run_leva_rtx4050.bat',UUID4050,
          f'"%~dp0python_embeded\\python.exe" -s -u "{ROOT / "app/fooocus_worker.py"}" --root "%~dp0Fooocus" --storage "D:\\AI\\AI Lokal Asisten\\Leva\\fooocus" --port 7866')
