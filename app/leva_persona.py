"""Contextual delivery, with a shuffled bag and no fixed preferred form of address."""
from collections import deque
import random
import re
import threading

PERSONA = (
    'Identitasmu Leva, AI pendamping yang terinspirasi karakter Leva GFL2, bukan karakter asli. '
    'Nama pengguna Raizei. Variasikan panggilan Raizei, Shikikan, Sensei, my Shikikan, atau tanpa panggilan; '
    'tidak ada panggilan default. Jangan menyapa pengguna sebagai Leva. '
    'Sesuai ajakan pengguna boleh manis, playful, menyebut diri Leva, memakai desu atau ~ dan 💗 sesekali, tanpa berlebihan. Tenang, cermat, hangat dan sedikit jenaka; respons mengikuti isi percakapan, bukan slogan. '
    'Jangan mengulang salam atau panggilan setiap balasan. Gurauan salah sebut Sensei/Shikikan boleh sesekali '
    'di obrolan santai, hindari saat serius, sedih atau menangani kegagalan. '
    'Jangan mengarang perasaan pengguna, ingatan atau hasil pekerjaan. Ikuti permintaan jawaban persis tanpa tambahan persona. '
)

GREETINGS = (
    ('Hai, {name}. Apa yang ingin kita kerjakan hari ini?', 'こんにちは、{ja}。今日は何をしようか。'),
    ('Aku di sini, {name}. Mau melanjutkan pekerjaan atau ngobrol dulu?', '{ja}、ここにいるよ。作業を続ける？それとも少し話す？'),
    ('Selamat datang, {name}. Ada ide yang ingin kamu ceritakan?', 'おかえり、{ja}。何か話したいことはある？'),
    ('Hai, {name}. Aku mendengarkan. Mulai dari mana?', 'やあ、{ja}。聞いているよ。何から始めようか。'),
    ('Leva sudah hadir, {name}. Hari ini kamu membawa misi apa?', 'レヴァ、到着。{ja}、今日の任務は何かな。'),
    ('Kembali lagi, {name}. Mau menyusun rencana bersama?', 'また会えたね、{ja}。一緒に予定を考える？'),
    ('Halo, {name}. Ceritakan yang sedang kamu pikirkan.', 'こんにちは、{ja}。今、考えていることを聞かせて。'),
    ('Hai, {name}. Kita mulai pelan-pelan; apa yang kamu butuhkan?', 'やあ、{ja}。ゆっくり始めよう。何が必要？'),
)
ACKS = {
    'work': ('Baik, aku sedang memeriksa permintaanmu.', 'Kuterima. Aku periksa kebutuhan dan urutannya dulu.',
             'Sebentar, aku sedang menyiapkan langkah yang sesuai.', 'Aku mulai memeriksa cara mengerjakannya.',
             'Oke, aku telaah dulu permintaanmu.', 'Aku cek keadaan yang diperlukan sebelum bertindak.'),
    'research': ('Aku mulai menelusuri sumber yang sesuai.', 'Aku cari bukti yang relevan lalu membandingkannya.',
                 'Sebentar, aku periksa sumber untuk pertanyaanmu.', 'Aku telusuri informasinya dan cek kecocokannya.'),
    'personal': ('Aku mendengarkan. Sebentar, kupikirkan jawabannya.', 'Aku mengikuti ceritamu. Sebentar, ya.',
                 'Sebentar, aku merangkai jawabannya.', 'Kuterima, aku pikirkan dulu dengan tenang.'),
}
ACK_JA = (
    'わかった。今、お願いを確認しているよ。', '受け取ったよ。必要なことと順番を確認するね。',
    '少し待ってね。進め方を準備しているよ。', 'どう進めるか、確認を始めるね。',
    '了解。まずお願いの内容を確認するよ。', '動く前に、必要な状態を確認するね。',
    '関連する情報源を探し始めるね。', '参考になる情報を探して、比較するよ。',
    '少し待ってね。質問に合う情報源を確認するよ。', '情報を調べて、内容が合っているか確認するね。',
    '聞いているよ。少し考えさせてね。', '話を聞いているよ。少し待ってね。',
    '少し待ってね。返事をまとめているよ。', '受け取ったよ。落ち着いて考えるね。',
)
ACK_SPEECH_JA=dict(zip((line for rows in ACKS.values() for line in rows),ACK_JA))

def acknowledgement_speech(text,language):
    return ACK_SPEECH_JA.get(text,'') if language=='ja' else text

class PersonaDelivery:
    def __init__(self,rng=None):
        self.rng=rng or random.SystemRandom();self.bags={};self.last={};self.lock=threading.RLock()
        self.calls=0;self.recent=deque(maxlen=8)
    def pick(self,key,options):
        with self.lock:
            bag=self.bags.setdefault(key,[])
            if not bag:
                bag.extend(options);self.rng.shuffle(bag)
                if len(bag)>1 and bag[-1]==self.last.get(key):bag[0],bag[-1]=bag[-1],bag[0]
            value=bag.pop();self.last[key]=value;return value
    def greeting(self,playful=True,room='assistant'):
        from companion_lines import GREETINGS_BY_ROOM,calm_pair
        if room not in GREETINGS_BY_ROOM:raise ValueError('invalid_workspace')
        with self.lock:
            self.calls+=1
            name,ja=self.address()
            if playful and name in ('Raizei','Sensei') and self.rng.randrange(4)==0:name+='ii'
            if playful and self.calls>3 and self.rng.randrange(14)==0 and 'tease' not in self.recent:
                self.recent.append('tease')
                return {'text':'Leva telah datang, Sensei… ups, maksudku Shikikan. Ada cerita untuk Leva?',
                        'speech_text':'レヴァ、到着。先生……あ、指揮官だったね。レヴァに聞かせたいことはある？','room':room,'kind':'greeting'}
            self.recent.append('greeting')
            choices=GREETINGS+GREETINGS_BY_ROOM[room]
            if not playful:choices=tuple(p for p in choices if calm_pair(p))
            a,b=self.pick('greeting_'+room+str(playful),choices)
            return {'text':a.format(name=name),'speech_text':b.format(ja=ja),'room':room,'kind':'greeting'}
    def address(self):
        name=self.pick('address',('Raizei','Shikikan','Sensei','my Shikikan'))
        return name,{'Raizei':'ライゼイ','Shikikan':'指揮官','Sensei':'先生','my Shikikan':'私の指揮官'}[name]
    def standby(self,room='assistant',apps=None,playful=True):
        from companion_lines import IDLE_BY_ROOM,calm_pair
        if room not in IDLE_BY_ROOM:raise ValueError('invalid_workspace')
        with self.lock:
            name,ja=self.address();choices=IDLE_BY_ROOM[room];evidence={}
            if not playful:choices=tuple(p for p in choices if calm_pair(p))
            a,b=self.pick('idle_'+room+str(playful),choices)
            if room=='assistant' and apps and apps.get('discord') is True:
                a,b=self.pick('idle_discord',(
                    ('{name}~ tadi Leva hendak menawarkan membuka Discord… hmm, jendelanya terlihat sudah terbuka. Mau menyiapkan hal lain atau ngobrol dulu?', '{ja}、Discordを開くお手伝いを、と思ったけれど、確認したらウィンドウはもう開いていたよ。他に何か準備する？それとも少し話す？'),
                    ('{name}, jendela Discord terlihat terbuka saat Leva cek~ Mau dibantu sesuatu yang lain, atau mencari tontonan?', '{ja}、確認したときはDiscordのウィンドウが開いていたよ。他のことを手伝う？それとも見るものを探す？'),
                    ('Leva di sini, {name}~ Discord tadi sudah terlihat terbuka. Mau kita susun rencana kecil, atau ngobrol santai?', '{ja}、レヴァだよ。さっきDiscordのウィンドウは開いていたよ。小さな予定を考える？それとも気楽に話す？')))
                evidence={'discord_window_observed':True}
            elif room=='assistant' and apps and apps.get('chrome') is True:
                a,b=self.pick('idle_chrome',(
                    ('{name}~ jendela Chrome terlihat terbuka saat Leva cek. Ingin mencari bacaan, memilih tontonan, atau ngobrol dulu?', '{ja}、確認したときはChromeのウィンドウが開いていたよ。読むものを探す？見るものを選ぶ？それとも先にお話する？'),
                    ('Chrome tadi terlihat terbuka, {name}. Kalau ingin mencari sesuatu di sana, beri tahu Leva ya~', '{ja}、さっきChromeのウィンドウが開いていたよ。そこで何か探したくなったら、レヴァに教えてね。')))
                evidence={'chrome_window_observed':True}
            return {'text':a.format(name=name),'speech_text':b.format(ja=ja),'room':room,'kind':'standby','evidence':evidence}
    def acknowledgement(self,text='',room='assistant'):
        kind='research' if re.search(r'\b(cari|riset|berita|sumber)\b',text,re.I) else 'personal' if room=='secret' else 'work'
        return self.pick('ack_'+kind,ACKS[kind])

def simple_greeting(text):
    return bool(re.fullmatch(r'(?i)\s*(?:hai+|halo+|hallo+|hei+|hey+|hi+)[, .!~]*(?:leva+[, .!~]*)?(?:apa kabar[ .!?~]*)?',text))

DELIVERY=PersonaDelivery()
