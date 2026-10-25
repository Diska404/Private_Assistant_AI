"""One pinned OmniVoice comparator; reuse the already verified audio.cpp runtime."""
import json
from prepare_higgs_sample import DATA, metadata, download

def main():
    repo=metadata('https://huggingface.co/api/models/audio-cpp/audio.cpp-gguf?blobs=true')
    name='OmniVoice-GGUF/omnivoice-q8_0.gguf'
    item=next(r for r in repo['siblings'] if r['rfilename']==name)
    target=DATA.parent/'AI Models/OmniVoice-GGUF'/name.split('/')[-1]
    row=download(('https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/'+repo['sha']+'/'+name,
                  target,item['lfs']['sha256'],item['lfs']['size']))
    (target.parent/'manifest.json').write_text(json.dumps({'repo':repo['id'],'revision':repo['sha'],'file':row},indent=2),encoding='utf-8')
    print(json.dumps({'verified':row}),flush=True)

if __name__=='__main__':main()
