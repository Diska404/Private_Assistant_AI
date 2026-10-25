import argparse
import json
from pathlib import Path
from action_contract import tool_definitions
from hybrid_engine import DEFAULT_DATA, DEFAULT_SERVER, LocalEngine, EngineError

parser = argparse.ArgumentParser()
parser.add_argument("--model", type=Path, required=True)
args = parser.parse_args()
mini = "minicpm" in args.model.name.lower()
sampling = {"temperature": 1.0, "top_p": 0.95, "min_p": 0.0} if mini else {"temperature": 0.2}
engine = LocalEngine(DEFAULT_SERVER, args.model, DEFAULT_DATA / ("native-probe-" + args.model.stem),
    system="Kamu Leva. Gunakan satu fungsi yang tersedia untuk mengusulkan langkah yang diminta. Ini simulasi, jangan mengaku tindakan telah selesai.",
    max_output_tokens=512, context_size=4096, sampling=sampling)
try:
    result = engine.propose_tool([{"role": "user", "content": "Pengguna sudah memilih profil Diska. Tolong buka profil Diska."}],
        [t for t in tool_definitions() if t["function"]["name"] in ["open_profile", "ask_profile"]])
    print(json.dumps({"model": args.model.name, "result": result, "devices": engine.devices}, ensure_ascii=False, indent=2))
except EngineError as error:
    print(json.dumps({"model": args.model.name, "error": str(error)}))
finally:
    engine.close()
