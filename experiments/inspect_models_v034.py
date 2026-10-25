"""Read GGUF metadata/tensor descriptors without loading tensor data or model code."""
import json
from pathlib import Path
import struct

ROOT=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\model-expansion-v034')
FMT={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
def inspect(path):
    with path.open('rb') as f:
        def number(fmt):return struct.unpack('<'+fmt,f.read(struct.calcsize(fmt)))[0]
        def string():
            count=number('Q')
            if count>16*1024*1024:raise ValueError('invalid_gguf_string')
            return f.read(count).decode('utf8',errors='replace')
        def value(kind,keep=True):
            if kind in FMT:return number(FMT[kind])
            if kind==8:return string()
            if kind==9:
                subtype=number('I');count=number('Q')
                if count>2000000:raise ValueError('invalid_gguf_array')
                if subtype in FMT and not keep:f.seek(count*struct.calcsize(FMT[subtype]),1);return {'count':count}
                values=[value(subtype,keep) for _ in range(count)]
                return values if keep else {'count':count}
            raise ValueError('unknown_gguf_type_'+str(kind))
        if f.read(4)!=b'GGUF':raise ValueError('not_gguf')
        version=number('I');tensors=number('Q');entries=number('Q');meta={}
        for _ in range(entries):
            key=string();kind=number('I');keep=not key.startswith('tokenizer.ggml.')
            item=value(kind,keep)
            if keep:meta[key]=item
        infos=[]
        for _ in range(tensors):
            name=string();dims=number('I');shape=[number('Q') for _ in range(dims)];dtype=number('I');offset=number('Q')
            infos.append({'name':name,'shape':shape,'type':dtype,'offset':offset})
        return {'path':str(path),'bytes':path.stat().st_size,'version':version,'tensor_count':tensors,'metadata':meta,'tensor_examples':infos[:4],
          'largest_tensors':sorted(infos,key=lambda t:__import__('math').prod(t['shape']),reverse=True)[:5],
          'descriptor_end':f.tell()}
if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    paths=[*ROOT.glob('Qwen3.8-Flash-Next-*.gguf'),ROOT/'Qwen3.5-9B-Q6_K.gguf']
    records=[inspect(path) for path in paths]
    (OUT/'existing-gguf-inspection.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    for r in records:print(json.dumps({k:v for k,v in r.items() if k not in ('metadata','tensor_examples','largest_tensors')}|{'architecture':r['metadata'].get('general.architecture'),'name':r['metadata'].get('general.name'),'split':{k:v for k,v in r['metadata'].items() if k.startswith('split.')}},ensure_ascii=True))
