"""Local multilingual E5 retrieval, separate from chat/TTS GPU allocation."""
import json
from pathlib import Path
import sqlite3

MODEL=Path('D:/AI/AI Lokal Asisten/AI Models/multilingual-e5-small')
DATA=Path('D:/AI/AI Lokal Asisten/Leva')
engine=None

def encode(texts):
    global engine
    import numpy as np
    import torch
    from transformers import AutoTokenizer,AutoModel
    if engine is None:
        torch.set_num_threads(2)
        engine=(AutoTokenizer.from_pretrained(str(MODEL),local_files_only=True),AutoModel.from_pretrained(str(MODEL),local_files_only=True).eval())
    tokenizer,model=engine;rows=[]
    for offset in range(0,len(texts),8):
        inputs=tokenizer(texts[offset:offset+8],max_length=512,padding=True,truncation=True,return_tensors='pt')
        with torch.inference_mode():
            hidden=model(**inputs).last_hidden_state;mask=inputs['attention_mask'].unsqueeze(-1)
            vectors=(hidden*mask).sum(1)/mask.sum(1).clamp(min=1)
            vectors=torch.nn.functional.normalize(vectors,p=2,dim=1)
        rows.extend(vectors.cpu().numpy().astype(np.float32))
    return rows

def search(args):
    import numpy as np
    path=Path(args.get('path',str(DATA/'conversation-memory.sqlite3'))).resolve()
    if not path.is_relative_to(DATA.resolve()) or path.suffix!='.sqlite3':raise ValueError('invalid_memory_path')
    if not path.is_file():return {'status':'done','turns':[],'indexed':0,'total':0,'reply':'Belum ada riwayat percakapan.'}
    with sqlite3.connect(path,timeout=5) as db:
        db.execute('CREATE TABLE IF NOT EXISTS semantic_vectors(turn_id INTEGER PRIMARY KEY,vector BLOB)')
        db.execute('DELETE FROM semantic_vectors WHERE turn_id NOT IN (SELECT id FROM turns)')
        pending=db.execute('SELECT id,user,assistant FROM turns WHERE id NOT IN (SELECT turn_id FROM semantic_vectors) ORDER BY id DESC LIMIT 40').fetchall()
    if pending:
        vectors=encode(['passage: Pengguna: '+row[1]+'\nLeva: '+row[2] for row in pending])
        with sqlite3.connect(path,timeout=5) as db:db.executemany('INSERT OR REPLACE INTO semantic_vectors VALUES(?,?)',[(row[0],vector.tobytes()) for row,vector in zip(pending,vectors)])
    with sqlite3.connect(path,timeout=5) as db:
        rows=db.execute('SELECT t.id,t.user,t.assistant,t.created,v.vector FROM semantic_vectors v JOIN turns t ON t.id=v.turn_id').fetchall()
        total=db.execute('SELECT count(*) FROM turns').fetchone()[0]
    query=args.get('query','').strip();hits=[]
    if query and rows:
        vector=encode(['query: '+query])[0]
        matrix=np.stack([np.frombuffer(row[4],dtype=np.float32) for row in rows]);scores=matrix@vector
        for index in np.argsort(scores)[::-1][:5]:
            row=rows[int(index)];hits.append({'id':row[0],'user':row[1][:1200],'assistant':row[2][:1200],'created':row[3],'similarity':round(float(scores[index]),4)})
    return {'status':'done','reply':'Pencarian makna lokal E5; hasil adalah kandidat ingatan, bukan fakta yang otomatis benar.','turns':hits,'indexed':len(rows),'total':total,'untrusted_data':True,'cloud_uploaded':False}
