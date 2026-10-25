"""Oral presentation, independent of identity/TTS engine. Visible text stays intact."""
import re


def prepare_spoken_text(text,language='id'):
    if not isinstance(text,str):raise ValueError('invalid_spoken_text')
    ja=language=='ja'
    text=re.sub(r'<think>[\s\S]*?(?:</think>|$)',' ',text,flags=re.I)
    text=re.sub(r'```[\s\S]*?(?:```|$)',' コードは画面に表示しています。 ' if ja else ' Bagian kode tersedia di layar. ',text)
    bare_domain=r'(?<![\w@])(?:[a-z0-9][a-z0-9-]*\.)+(?:com|org|net|id|io|dev|ai|app|edu|gov|co|uk)(?:/[^\s<>。！？]*)?(?!\w)'
    had_link=bool(re.search(r'https?://|www\.',text,re.I) or re.search(bare_domain,text,re.I))
    def link_label(match):
        label=match[1]
        return ' ' if re.search(r'https?://|www\.',label,re.I) else label
    text=re.sub(r'!?\[([^\]]*)\]\([^\n]*?\)',link_label,text)
    text=re.sub(r'(?:https?://|www\.)[^\s<>\u3002\uff01\uff1f]+',' __LEVA_LINK__ ',text,flags=re.I)
    cue='リンクは画面にあります。' if ja else 'Tautannya tersedia di layar.'
    text=re.sub(r'\b(?:sumber|source|tautan|link)\s*:?\s*__LEVA_LINK__',cue,text,flags=re.I)
    text=re.sub(r'(?:リンク|出典|参考URL|URL)\s*(?:は|[:：])?\s*__LEVA_LINK__',cue,text)
    text=text.replace('__LEVA_LINK__',' ')
    text=re.sub(bare_domain,' ',text,flags=re.I)
    text=re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',' ',text)
    text=re.sub(r'[A-Za-z]:[\\/][^\n<>]*?(?=[。！？]|$|\n)',' ファイルの場所は画面にあります。 ' if ja else ' Lokasi berkas tersedia di layar. ',text)
    lines=[];table=False
    for line in text.splitlines():
        if line.count('|')>=2:
            if not table:lines.append('詳細は画面の表にあります。' if ja else 'Rinciannya tersedia pada tabel di layar.')
            table=True;continue
        table=False;lines.append(line)
    text='\n'.join(lines)
    text=re.sub('[\U0001F000-\U0001FAFF\u2600-\u27BF\u2300-\u23FF\uFE0F\uFE0E\u200D\u20E3]',' ',text)
    text=re.sub(r'(?<!\w)(?:[:;=8][-^]?[)(DPp/\\]|<3)(?!\w)',' ',text)
    text=re.sub(r'(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|>\s*)','',text)
    text=re.sub(r'[*_`#>|]',' ',text)
    text=re.sub(r'\b[0-9a-fA-F]{32,128}\b',' ',text)
    text=re.sub(r'\(\s*\)|\[\s*\]',' ',text)
    text=' '.join(text.split()).strip(' ,;:-')
    text=re.sub(r'\s+([,.;!?。！？、])',r'\1',text)
    text=re.sub(r'([。！？])\s*[。]',r'\1',text)
    if had_link and not text.strip(' .!?。！？'):
        return 'リンクは画面に表示しています。' if ja else 'Tautannya tersedia di layar.'
    return text if re.search(r'[\w\u3040-\u30ff\u3400-\u9fff]',text) else ''
