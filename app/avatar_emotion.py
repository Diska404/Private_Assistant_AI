"""Conservative reply-tag calibration; no neural training and no conversation storage."""
import re

def expression_for_reply(text):
    value=str(text)[:4000].casefold()
    if re.search(r'\b(belum|tidak)\s+berhasil\b|\bgagal\b',value):return 'thinking'
    if re.search(r'\b(tidak yakin|belum yakin|belum jelas|perlu memastikan)\b',value):return 'thinking'
    if re.search(r'\b(ikut sedih|aku paham|aku mengerti|berat untukmu|kesepian|melelahkan)\b',value):return 'soft_smile'
    if re.search(r'\b(selamat|berhasil|senang sekali|hore|kabar baik)\b',value):return 'happy'
    if re.search(r'\b(hehe|hihi|bercanda|canda deh)\b',value):return 'playful'
    if re.search(r'\b(istirahat|selamat tidur|mimpi indah)\b',value):return 'soft_smile'
    if re.search(r'\b(hai|halo|menemanimu|di sini untukmu)\b',value):return 'soft_smile'
    return 'neutral'

def observe_reply(main,speaker,text):
    if getattr(main,'workspace',None)!='companion_avatar' or not str(speaker).startswith('Leva') or 'Proses' in speaker:return
    main._avatar_reply_emotion={'generation':getattr(main,'generation',0),'expression':expression_for_reply(text),'source':'reply_pattern_calibration'}
