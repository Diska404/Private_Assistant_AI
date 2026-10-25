"""Host evidence for explicit development requests; never grants extra actions."""
import re
import ntpath

def knowledge_question(text):
    return bool(re.search(r'obsidian|vault|second brain|catatan saya',text,re.I) and
        not re.search(r'\b(?:buat\w*|membuat|ubah\w*|tulis\w*|hapus\w*|buka\w*|jalankan|eksekusi|pasang|install|lanjut\w*)\b',text,re.I))

def briefing_request(text):
    return bool(re.search(r'\bbriefing\b',text,re.I) and not re.search(r'\b(?:ingatkan|jadwalkan|pengingat|reminder|buka\w*|jalankan|simpan|tulis\w*|hapus\w*|ubah\w*)\b',text,re.I))

def website_creation(text):
    if re.search(r'\b(?:jelaskan|apa itu|bagaimana cara|contoh kalimat|terjemahkan)\b',text,re.I):return False
    if re.search(r'\b(?:jangan|belum|tidak usah)\s+(?:buat|bangun|kerjakan)',text,re.I):return False
    if re.search(r'\b(?:jangan simpan|tanpa (?:berkas|file)|(?:hanya|cukup)\s+(?:tampilkan|kirim|tulis)?\s*(?:kode\s+)?(?:di |ke )?(?:chat|percakapan))\b',text,re.I):return False
    return bool(re.search(r'\b(?:buat\w*|membuat|bangun\w*|membangun|kembangkan|mengembangkan|siapkan|menyiapkan|hasilkan|menghasilkan|kerjakan)\b.*\b(?:website|web|html|landing page|ui)\b',text,re.I))

def development_evidence(receipts):
    written=False;pending=set();terminal=False;terminal_checked=False
    def key(root,path):return ntpath.normcase(ntpath.normpath(ntpath.join(root,path)))
    for row in receipts:
        name=row['name'];args=row['args'];result=row['result']
        if result.get('status')!='done':continue
        if name=='project_action' and args.get('action')=='apply':
            written=True
            for path in result.get('paths',[]):pending.add(key(result.get('root',''),path))
            if not result.get('paths'):pending.add('<unknown-output>')
        if name=='file_action' and args.get('action')=='write':
            written=True;pending.add(key('',result.get('path') or args.get('path','<unknown-output>')))
        if name=='terminal' and result.get('exit_code')==0:terminal=True
        if name in ('project_action','file_action') and args.get('action')=='read':
            path=result.get('path') or args.get('path','')
            pending.discard(key(result.get('root',args.get('root','')),path))
            if terminal and re.search(r'\.(?:html|css|js|jsx|tsx|vue|svelte)$',path,re.I):terminal_checked=True
    return written or terminal_checked,(written and not pending) or terminal_checked

def correction_goal(text,previous):
    """Keep the correction verbatim and attach, rather than silently rewrite, its goal."""
    if re.search(r'\b(?:batalkan|hentikan|tidak jadi)\b',text,re.I):return text
    if not previous or not re.match(r'^\s*(?:eh\s+)?(?:bukan\b|maksud(?:ku| saya)\b|koreksi\b|yang saya maksud\b)',text,re.I):return text
    return 'Permintaan sebelumnya:\n'+previous+'\n\nKoreksi pengguna yang harus diutamakan:\n'+text
