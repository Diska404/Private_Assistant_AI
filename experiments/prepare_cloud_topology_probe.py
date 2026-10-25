"""Create an inspectable notebook; never authenticates, uploads, or starts cloud workers."""
import json
from pathlib import Path

OUT=Path(r'D:\AI\AI Lokal Asisten\Github\Leva-Distributed-Lab')
OUT.mkdir(parents=True,exist_ok=True)
cells=[]
def cell(kind,text):
    value={'cell_type':kind,'metadata':{},'source':text.splitlines(keepends=True)}
    if kind=='code':value.update(execution_count=None,outputs=[])
    cells.append(value)
cell('markdown',"""# Leva — pemeriksaan cloud untuk benchmark GPU/RPC
Notebook ini hanya memeriksa environment. Tidak memasang paket, tidak membuka port,
tidak mengunggah model/data, dan tidak menghubungkan jaringan laptop.

Colab gratis belum dapat digunakan sebagai distributed computing worker menurut FAQ resminya.
Saldo compute unit tidak dapat dibuktikan oleh pemeriksaan Python ini: konfirmasi akun dilakukan
melalui dashboard pengguna sebelum tahap worker. Kaggle perlu ditinjau sesuai penggunaan notebook
dan batas akun. Satu notebook Colab yang terhubung ke server Kaggle memakai sesi Kaggle yang sama.

Untuk RPC berikutnya diperlukan build llama.cpp yang kompatibel dengan b11721/protokol v8,
transport privat yang terautentikasi, GPU yang dipilih secara eksplisit, serta endpoint yang tidak
terbuka ke internet. Jangan menjalankan RPC melalui URL publik atau menonaktifkan autentikasi Leva.
""")
cell('code',"""import json, platform, shutil, subprocess, importlib.util
from pathlib import Path
try:
    is_colab = importlib.util.find_spec('google.colab') is not None
except ModuleNotFoundError:
    is_colab = False
is_kaggle = Path('/kaggle').is_dir()
report = {'platform': platform.platform(), 'python': platform.python_version(),
          'provider': 'colab' if is_colab else 'kaggle' if is_kaggle else 'other',
          'distributed_worker_started': False, 'packages_installed': False,
          'model_uploaded': False, 'account_compute_units': 'verify_in_dashboard'}
if shutil.which('nvidia-smi'):
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.free,driver_version',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=15)
    report['gpu_report'] = result.stdout.strip()
else:
    report['gpu_report'] = 'No NVIDIA GPU assigned'
output = Path('/kaggle/working') if is_kaggle else Path.cwd()
path = output / 'leva-cloud-preflight.json'
path.write_text(json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report, indent=2))
print('Saved:', path.name)
""")
cell('markdown',"""## Sesudah pemeriksaan
Bandingkan GPU aktual, VRAM bebas, batas sesi, dan opsi internet pada dashboard.
Jangan menampilkan API key, token Tailscale, isi Drive, atau data pribadi dalam output notebook.
Pengujian WAN belum dimulai oleh notebook ini. Uji lokal laptop merupakan kontrol, bukan simulasi
angka latensi WAN. Hasil benchmark laptop berada di folder verification/topology-benchmark-20261023.

Sumber: https://research.google.com/colaboratory/faq.html
https://www.kaggle.com/docs/notebooks
https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md
""")
notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':5}
path=OUT/'Leva_Cloud_Preflight.ipynb'
path.write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf8')
print(path)
