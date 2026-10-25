"""Reproducible lexical diagnostics, never an LLM semantic-success score."""
import math
import re
import unicodedata

VERSION='asr-lab-metrics-1'
CONTEXT='Leva, Diska, Chrome, ChatGPT, EdLink, ComfyUI, Fooocus, matematika diskrit'
PROMPTS=[
    {'id':'wake','category':'nama','text':'Leva, kamu mendengarkanku?','critical':[{'name':'Leva','variants':['leva']}]},
    {'id':'chrome','category':'aplikasi','text':'Leva, buka Chrome profil Diska untuk ChatGPT.','critical':[{'name':'profil Diska','variants':['diska']},{'name':'ChatGPT','variants':['chatgpt','chat gpt']}]},
    {'id':'edge','category':'aplikasi','text':'Buka Microsoft Edge lalu masuk ke EdLink.','critical':[{'name':'Edge','variants':['edge']},{'name':'EdLink','variants':['edlink','ed link']}]},
    {'id':'relative','category':'waktu','text':'Dua menit lagi ingatkan saya mengerjakan matematika diskrit.','critical':[{'name':'dua menit','variants':['dua menit','2 menit']},{'name':'diskrit','variants':['diskrit']}]},
    {'id':'time','category':'waktu','text':'Ingatkan saya malam ini jam sembilan belas untuk belajar.','critical':[{'name':'jam 19','variants':['sembilan belas','19','19:00','19.00']}]},
    {'id':'negation','category':'larangan','text':'Jangan buka Chrome sekarang, buka nanti setelah saya selesai.','critical':[{'name':'larangan','variants':['jangan']},{'name':'ditunda','variants':['nanti']}]},
    {'id':'comfy','category':'workflow','text':'Buka ComfyUI dan periksa model yang tersedia, jangan generate gambar.','critical':[{'name':'ComfyUI','variants':['comfyui','comfy ui']},{'name':'larangan','variants':['jangan']}]},
    {'id':'fooocus','category':'workflow','text':'Gunakan Fooocus untuk membuat satu gambar, pilih model yang sudah saya unduh.','critical':[{'name':'Fooocus','variants':['fooocus','foocus','foo cus']}]},
    {'id':'multi','category':'bertahap','text':'Buka Chrome Diska untuk ChatGPT, lalu buka Edge untuk EdLink.','critical':[{'name':'Diska','variants':['diska']},{'name':'Edge','variants':['edge']},{'name':'EdLink','variants':['edlink','ed link']}]},
    {'id':'pause','category':'sistem','text':'Leva, jedakan sistemmu karena saya mau berbicara di Discord.','critical':[{'name':'jeda','variants':['jedakan','jeda']},{'name':'Discord','variants':['discord']}]},
    {'id':'long','category':'panjang','text':'Leva, dua menit lagi ingatkan saya mengerjakan tugas matematika diskrit. Setelah waktunya tiba, buka Chrome profil Diska untuk ChatGPT dan buka Microsoft Edge untuk EdLink. Jangan membuka browser sekarang.','critical':[{'name':'dua menit','variants':['dua menit','2 menit']},{'name':'Diska','variants':['diska']},{'name':'EdLink','variants':['edlink','ed link']},{'name':'larangan','variants':['jangan']}]},
    {'id':'silence','category':'kontrol','text':'','critical':[],'instruction':'Diam selama 3–5 detik. Hasil teks idealnya kosong; ini kontrol false speech.'},
    {'id':'custom','category':'bebas','text':'','critical':[]},
]

def tokens(text):
    return re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',text).casefold(),re.UNICODE)

def alignment(reference,hypothesis):
    """Levenshtein with deterministic tie order and inspectable word operations."""
    a,b=reference,hypothesis
    dp=[[0]*(len(b)+1) for _ in range(len(a)+1)]
    for i in range(len(a)+1):dp[i][0]=i
    for j in range(len(b)+1):dp[0][j]=j
    for i in range(1,len(a)+1):
        for j in range(1,len(b)+1):
            dp[i][j]=min(dp[i-1][j-1]+(a[i-1]!=b[j-1]),dp[i-1][j]+1,dp[i][j-1]+1)
    edits=[];i=len(a);j=len(b)
    while i or j:
        if i and j and a[i-1]==b[j-1] and dp[i][j]==dp[i-1][j-1]:
            edits.append({'op':'equal','reference':a[i-1],'hypothesis':b[j-1]});i-=1;j-=1
        elif i and j and dp[i][j]==dp[i-1][j-1]+1:
            edits.append({'op':'substitution','reference':a[i-1],'hypothesis':b[j-1]});i-=1;j-=1
        elif i and dp[i][j]==dp[i-1][j]+1:
            edits.append({'op':'deletion','reference':a[i-1],'hypothesis':''});i-=1
        else:edits.append({'op':'insertion','reference':'','hypothesis':b[j-1]});j-=1
    return list(reversed(edits))

def score(reference,hypothesis,critical=()):
    ref,hyp=tokens(reference),tokens(hypothesis)
    edits=alignment(ref,hyp)
    counts={name:sum(e['op']==name for e in edits) for name in ('substitution','deletion','insertion')}
    errors=sum(counts.values())
    chars_a=list(''.join(ref));chars_b=list(''.join(hyp))
    # Bound quadratic CER work for pasted text; references are capped by the server.
    last=list(range(len(chars_b)+1))
    for i,a in enumerate(chars_a,1):
        current=[i]
        for j,b in enumerate(chars_b,1):current.append(min(last[j]+1,current[-1]+1,last[j-1]+(a!=b)))
        last=current
    char_errors=last[-1]
    normalized=' '+' '.join(hyp)+' '
    normalized_reference=' '+' '.join(ref)+' '
    slots=[{'name':row['name'],'variants':row['variants'],
            'expected':any(' '+' '.join(tokens(v))+' ' in normalized_reference for v in row['variants']),
            'present':any(' '+' '.join(tokens(v))+' ' in normalized for v in row['variants'])} for row in critical]
    return {'version':VERSION,'reference_words':len(ref),'hypothesis_words':len(hyp),
            'word_errors':errors,**counts,'wer':errors/len(ref) if ref else None,
            'reference_characters':len(chars_a),'character_errors':char_errors,
            'cer':char_errors/len(chars_a) if chars_a else None,
            'normalized_exact':ref==hyp,'false_speech':not ref and bool(hyp),
            'critical':slots,'critical_missing':sum(s['expected'] and not s['present'] for s in slots),'alignment':edits,
            'note':'WER/CER lexical, case/punctuation ignored; angka dan sinonim tidak disamakan. Slot adalah kecocokan varian, bukan penilaian pemahaman agent.'}

def percentile(values,q):
    values=sorted(v for v in values if isinstance(v,(int,float)) and math.isfinite(v))
    if not values:return None
    pos=(len(values)-1)*q;lo=int(pos);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)

def summary(rows):
    groups={}
    for row in rows:
        if row['status']!='done':continue
        metrics=row.get('metrics',{});result=row.get('result',{})
        capture=row.get('capture',{});dsp=capture.get('settings',{})
        if not isinstance(dsp,dict):dsp={}
        profile='/'.join(k+('1' if dsp[v] else '0') if v in dsp else k+'?' for k,v in [('EC','echoCancellation'),('NS','noiseSuppression'),('AGC','autoGainControl')])
        name=' | '.join([result.get('gpu_name',row.get('gpu','?')),str(result.get('model','?')),
            'cold' if not result.get('model_reused') else 'warm',row.get('audio_origin','human'),row.get('condition','quiet'),
            row.get('language','id'),row.get('equipment','unknown'),str(capture.get('device_label','file / unknown'))[:200],profile,
            'context' if row.get('context') else 'no-context'])
        groups.setdefault(name,[]).append(row)
    output=[]
    for name,items in groups.items():
        scored=[r for r in items if r.get('reference_confirmed')]
        word_rows=[r for r in scored if r.get('metrics',{}).get('reference_words')]
        words=sum(r['metrics']['reference_words'] for r in word_rows)
        times=[r['result'].get('asr_ms') for r in items]
        output.append({'group':name,'runs':len(items),'confirmed_references':len(scored),
            'wer_micro':sum(r['metrics']['word_errors'] for r in word_rows)/words if words else None,
            'asr_p50_ms':percentile(times,.5),'asr_p95_ms':percentile(times,.95),
            'manual_miscommunications':sum(r.get('review')=='miss' for r in items),
            'manual_reviewed':sum(r.get('review') in ('correct','miss','uncertain') for r in items),
            'critical_missing':sum(r['metrics']['critical_missing'] for r in scored),
            'false_speech_runs':sum(r['metrics']['false_speech'] for r in scored),
            'small_sample':len(items)<20})
    return output
