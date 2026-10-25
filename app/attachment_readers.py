"""Bounded document decoders; attachments are data and are never executed."""
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

LIMIT=12000

class PlainHTML(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('p','div','br','tr','h1','h2','h3','li'):self.rows.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,value):
        if not self.hidden:self.rows.append(value)

def xml(raw):
    if len(raw)>4_000_000 or re.search(br'<!\s*(DOCTYPE|ENTITY)',raw,re.I):raise ValueError('XML lampiran terlalu besar atau memiliki deklarasi entitas.')
    return ET.fromstring(raw)

def decode(raw):
    for encoding in (('utf-16',) if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-8-sig',)):
        try:value=raw.decode(encoding)
        except UnicodeDecodeError:continue
        if '\x00' not in value and sum(ord(c)<32 and c not in '\r\n\t\f' for c in value)<max(1,len(value)*.01):return value
    return None

def read_document(name,raw):
    suffix=Path(name).suffix.casefold()
    if suffix in ('.wav','.mp3','.m4a','.ogg','.flac','.mp4','.mkv','.mov','.webm'):
        detail=f'Berkas media {name}: {len(raw)} byte.'
        if suffix=='.wav':
            import wave
            with wave.open(io.BytesIO(raw)) as wav:detail+=f' {wav.getnchannels()} kanal, {wav.getframerate()} Hz, {wav.getnframes()/max(1,wav.getframerate()):.2f} detik.'
        return detail,'media_metadata','Transkrip dan isi audio/video belum dianalisis; gunakan pipeline ASR/video yang sesuai.'
    if suffix in ('.docx','.pptx','.xlsx','.odt','.ods','.odp','.epub','.zip','.jar'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist()
            if len(entries)>1500 or sum(r.file_size for r in entries)>40_000_000 or any(r.flag_bits&1 for r in entries):raise ValueError('Arsip terlalu besar atau terenkripsi.')
            if suffix in ('.zip','.jar'):
                return '\n'.join(f'{r.filename} · {r.file_size} byte' for r in entries[:200]),'archive_inventory','Daftar isi arsip; isi berkas di dalamnya belum dianalisis.'
            def load(path):
                info=archive.getinfo(path)
                if info.file_size>4_000_000:raise ValueError('Bagian dokumen terlalu besar.')
                return xml(archive.read(info))
            lines=[]
            if suffix=='.xlsx':
                shared=[]
                if 'xl/sharedStrings.xml' in archive.namelist():shared=[''.join(n.itertext()) for n in load('xl/sharedStrings.xml')]
                for path in sorted((n for n in archive.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)),key=lambda n:int(re.search(r'sheet(\d+)',n)[1]))[:12]:
                    lines.append('Lembar '+Path(path).stem)
                    for cell in load(path).iter():
                        if cell.tag.rsplit('}',1)[-1]!='c':continue
                        value=''.join(n.text or '' for n in cell.iter() if n.tag.rsplit('}',1)[-1] in ('v','t'))
                        if cell.get('t')=='s' and value.isdigit() and int(value)<len(shared):value=shared[int(value)]
                        if value:lines.append(cell.get('r','')+': '+value)
                        if sum(map(len,lines))>LIMIT:break
            else:
                names=archive.namelist()
                paths=['word/document.xml'] if suffix=='.docx' else ['content.xml'] if suffix in ('.odt','.ods','.odp') else sorted(n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))[:60] if suffix=='.pptx' else [n for n in names if n.lower().endswith(('.xhtml','.html','.htm'))][:40]
                for path in paths:
                    if suffix=='.epub':
                        info=archive.getinfo(path)
                        if info.file_size>4_000_000:continue
                        parser=PlainHTML();parser.feed(archive.read(path).decode('utf8','replace'));lines.append(''.join(parser.rows))
                    else:lines.append('\n'.join(n.text for n in load(path).iter() if n.text and n.text.strip()))
                    if sum(map(len,lines))>LIMIT:break
            return '\n'.join(lines),'document_text','Teks/nilai tersimpan; tata letak, gambar, formula aktif dan makro tidak dijalankan.'
    if suffix in ('.png','.jpg','.jpeg','.webp','.gif','.bmp','.tiff','.tif','.avif'):
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>20_000_000:raise ValueError('Gambar maksimal 20 MP.')
            text=f'Gambar {name}: {image.format}, {image.width}×{image.height}, mode {image.mode}.'
        return text,'image_metadata','Isi visual belum dianalisis oleh model vision/OCR; jangan menyimpulkan objek dari nama berkas.'
    text=decode(raw)
    if text is not None:
        if suffix in ('.html','.htm','.svg'):
            parser=PlainHTML();parser.feed(text);text=''.join(parser.rows)
        elif suffix=='.rtf':
            text=re.sub(r'\\u(-?\d+)\??',lambda m:chr(int(m[1])%65536),text)
            text=re.sub(r"\\'[0-9a-fA-F]{2}",' ',text);text=re.sub(r'\\[a-zA-Z]+-?\d* ?',' ',text);text=text.replace('{','').replace('}','')
        return text,'text',''
    # Every file can be attached, but an unknown binary must never be described as read.
    return f'Berkas {name} ({len(raw)} byte); signature {raw[:12].hex()}.','unsupported_binary','Parser isi belum tersedia. Minta ekspor ke PDF/teks atau alat khusus; isi belum dibaca.'
