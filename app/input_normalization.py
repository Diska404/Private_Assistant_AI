"""Small lexical corrections; preserve names, numbers, negation, URLs and paths."""
import re
import unicodedata

CORRECTIONS={
 'tolomg':'tolong','tolng':'tolong','tlong':'tolong','biskah':'bisakah','bisakha':'bisakah',
 'jangna':'jangan','jagan':'jangan','janagn':'jangan','tidka':'tidak','bkan':'bukan','blum':'belum',
 'bukakn':'bukakan','bukakan':'bukakan','bukakna':'bukakan','bukakanlah':'bukakanlah',
 'jelasakn':'jelaskan','jelaskna':'jelaskan','jelasin':'jelaskan','analisi':'analisis',
 'sekrang':'sekarang','sebenrnya':'sebenarnya','sebenernya':'sebenarnya',
 'percakpan':'percakapan','percakpaaan':'percakapan','suaraa':'suara','pengingta':'pengingat',
 'ingetkan':'ingatkan','inget':'ingat','jepagn':'jepang','indonesai':'indonesia',
 'apliksi':'aplikasi','aplikais':'aplikasi','jalankna':'jalankan','jalankn':'jalankan',
 'simpanakn':'simpankan','programnyaa':'programnya','gfl 2':'gfl2',
}

def normalize_input(value):
    if not isinstance(value,str):raise ValueError('invalid_input_text')
    original=value
    protected=re.compile(r'```[\s\S]*?```|https?://[^\s<>]+|(?:[A-Za-z]:[\\/]|\\\\)[^\n]+|`[^`]*`',re.I)
    edits=[];parts=[];start=0
    def correct(text):
        def word(m):
            before=m[0];after=CORRECTIONS.get(before.casefold(),before)
            if after!=before:
                if before[0].isupper():after=after[0].upper()+after[1:]
                edits.append({'from':before,'to':after})
            return after
        return re.sub(r'\b[^\W\d_]+\b',word,unicodedata.normalize('NFC',text))
    for m in protected.finditer(value):
        parts.extend((correct(value[start:m.start()]),m[0]));start=m.end()
    parts.append(correct(value[start:]))
    return {'original':original,'text':''.join(parts),'edits':edits,'method':'lexical_allowlist','meaning_expanded':False}

def research_query(text):
    text=normalize_input(text)['text']
    text=re.sub(r'\bleva\b[, ]*',' ',text,flags=re.I)
    text=re.sub(r'\b(?:bisakah|bisa|tolong|coba|anda|kamu|saya|untuk|bagaimana dengan|menurut|apakah|di internet|cari(?:kan)?|akses)\b',' ',text,flags=re.I)
    return ' '.join(text.split()).strip(' ,.?')[:280]
