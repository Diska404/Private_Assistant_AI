"""Separate delivery style from voice identity, language, and reply length."""
import re

STYLES=('auto','assistant','personal')
LABELS={'auto':'Otomatis sesuai percakapan','assistant':'Asisten · tenang dan jelas','personal':'Personal · hangat dan ekspresif'}

def explicit_style(text):
    value=text.casefold()
    if not re.search(r'\b(ubah|ganti|gunakan|pakai|pilih|aktifkan|kembalikan|atur|jadikan)\b',value):return None
    if re.search(r'\b(terjemahkan|terjemahan|contoh|kutipan|artinya|mengapa)\b',value):return None
    if not re.search(r'\b(gaya|mode|nada|suara)\b.{0,35}(personal|asisten|assistant|otomatis|auto)',value):return None
    if re.search(r'jangan|tidak (?:mau|usah)|bukan',value):return None
    if re.search(r'otomatis|\bauto\b',value):return 'auto'
    return 'personal' if 'personal' in value else 'assistant'

class SpeechStylePolicy:
    def __init__(self):self.previous='assistant';self.personal_turns=0

    def choose(self,user_text='',hint='',receipts=(),mode='auto'):
        if mode not in STYLES:raise ValueError('invalid_speech_style')
        value=user_text.casefold()
        # Tool outputs and long/short replies never determine personal intimacy.
        work=any(r.get('name') not in ('respond','ask_user','recall_conversations','recall') for r in receipts)
        work=work or bool(re.search(r'\b(buka|jalankan|ketik|klik|steam|chrome|discord|artikel|riset|debug|kode|gpu|vram|cuaca|agenda|jam berapa|tugas|kerja)\b',value))
        personal=bool(re.search(r'\b(curhat|kesepian|sedih|temani|menemaniku|ngobrol|cerita santai|rindu|capek|lelah|senang sekali)\b',value))
        if mode!='auto':style,reason=mode,'pilihan manual pengguna'
        elif work:style,reason='assistant','tujuan tugas atau hasil alat'
        elif re.search(r'jangan.*(?:personal|mesra)|tidak usah.*(?:personal|mesra)',value):style,reason='assistant','batas pembawaan pengguna'
        elif personal:style,reason='personal','percakapan personal pengguna'
        elif hint in ('assistant','personal'):style,reason=hint,'penilaian konteks oleh model'
        elif self.personal_turns and re.search(r'^(iya|ya|boleh|lanjut|terima kasih|makasih|hmm|aku juga)\b',value):style,reason='personal','kelanjutan percakapan personal'
        else:style,reason='assistant','pembawaan awal sehari-hari'
        self.personal_turns=2 if style=='personal' and personal else max(0,self.personal_turns-1) if style=='personal' else 0
        self.previous=style
        return {'style':style,'reason':reason,'mode':mode}

def higgs_text(text,style):
    if style not in ('assistant','personal'):raise ValueError('invalid_speech_style')
    # Only host-owned tags; generated text cannot inject new control tokens.
    clean=re.sub(r'<\|[^\r\n]*?\|>','',text)
    return ('<|emotion:contentment|>' if style=='assistant' else '<|emotion:affection|>')+clean
