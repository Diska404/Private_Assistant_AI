"""Offline reference-video ASR. Run only in the separate research environment."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--audio",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--model-dir",type=Path,required=True)
    parser.add_argument("--device",choices=["cpu","cuda"],default="cpu")
    args=parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["HF_HUB_DISABLE_XET"]="1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"]="1"
    os.environ["HF_HOME"]=str(args.model_dir.parent/"hf-cache")
    dll_handles=[]
    if args.device=="cuda":
        listing=subprocess.check_output(["nvidia-smi","--query-gpu=uuid,name","--format=csv,noheader"],text=True)
        selected=next(line.split(",")[0].strip() for line in listing.splitlines() if "RTX 4050" in line)
        os.environ["CUDA_VISIBLE_DEVICES"]=selected
        # Reuse existing libraries, scoped to this research child process only.
        cuda=Path(os.environ["LOCALAPPDATA"])/"hermes/runtimes/llamacpp/b10964/cuda"
        if cuda.is_dir():
            dll_handles.append(os.add_dll_directory(str(cuda)))
            os.environ["PATH"]=str(cuda)+os.pathsep+os.environ["PATH"]
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model
    args.out.mkdir(parents=True,exist_ok=True)
    if not (args.model_dir/"model.bin").is_file():
        print("Downloading the small multilingual ASR model to the specified model directory.",flush=True)
        download_model("small",output_dir=str(args.model_dir))
    started=time.monotonic()
    model=WhisperModel(str(args.model_dir),device=args.device,
                       compute_type="int8" if args.device=="cpu" else "int8_float16",cpu_threads=6,num_workers=1)
    # No prompt containing the narrative: preserve an independent, unseeded transcription.
    segments,info=model.transcribe(str(args.audio),language="en",beam_size=5,
                                   vad_filter=False,condition_on_previous_text=True)
    rows=[]
    with (args.out/"transcript-asr-raw.jsonl").open("w",encoding="utf-8") as stream:
        for segment in segments:
            row=asdict(segment)
            rows.append(row)
            stream.write(json.dumps(row,ensure_ascii=False)+"\n");stream.flush()
            if len(rows)%12==0:
                print(json.dumps({"segments":len(rows),"audio_through_seconds":round(segment.end,1)}),flush=True)
    def stamp(seconds):
        total=int(seconds*1000);return f"{total//3600000:02d}:{total//60000%60:02d}:{total//1000%60:02d},{total%1000:03d}"
    (args.out/"transcript-asr-raw.srt").write_text("\n\n".join(f"{i+1}\n{stamp(r['start'])} --> {stamp(r['end'])}\n{r['text'].strip()}" for i,r in enumerate(rows)),encoding="utf-8")
    (args.out/"transcript-asr-raw.md").write_text("# Reference video — raw ASR, not a verified verbatim transcript\n\n"+
        "Generated locally from the supplied video audio. Model names, figures and overlapping speech require review.\n\n"+
        "\n\n".join(f"[{int(r['start'])//60:02d}:{int(r['start'])%60:02d}–{int(r['end'])//60:02d}:{int(r['end'])%60:02d}] {r['text'].strip()}" for r in rows),encoding="utf-8")
    proof={"source_audio_sha256":hashlib.sha256(args.audio.read_bytes()).hexdigest(),"audio_duration_seconds":info.duration,
           "model":"faster-whisper-small","device":args.device,"segments":len(rows),
           "transcribed_through_seconds":max((r["end"] for r in rows),default=0),"elapsed_seconds":round(time.monotonic()-started,2),
           "microphone_opened":False,"cloud_audio_upload":False,"verbatim_verified":False}
    (args.out/"asr-provenance.json").write_text(json.dumps(proof,indent=2),encoding="utf-8")
    print(json.dumps(proof),flush=True)


if __name__=="__main__":main()
