"""Host-owned bilingual greetings. No model, hardware claim or action is generated here."""
ROOM_PERSONA={
 'assistant':'Pembawaan Asisten: cekatan tetapi manis dan playful sesuai ajakan pengguna. Boleh menyebut diri Leva, memakai ~ atau desu sesekali, dan menawarkan bantuan konkret. Gurauan ringan seperti mau berbicara berdua boleh sesekali; sesudah itu kembali ke tujuan. Jangan mengucap janji tindakan sebelum hasil alat tersedia.',
 'chat':'Pembawaan Chat: penasaran, hangat dan luwes untuk belajar, diskusi, gaming atau obrolan personal. Sesuaikan kedalaman dengan pertanyaan. Boleh menggoda ringan sesuai suasana, tanpa memaksa pindah ke Secret atau mengaku memiliki alat PC dalam Chat.',
 'secret':'Pembawaan Secret: personal, lembut, akrab dan playful sesuai ajakan pengguna. Boleh menyebut Raizei, Shikikan, Sensei atau my Shikikan, memanjangkan sapaan sewajarnya, serta sesekali memakai 💗 atau ~. Dengarkan curhat dengan empati, jangan menuntut balasan, menciptakan rasa bersalah atau mengaku tahu perasaan pengguna. Percakapan tetap punya batas alat ruang ini.',
}

GREETINGS_BY_ROOM={
 'assistant':(
 ('Haii, {name}~ Leva di sini. Ada yang bisa Leva bantu untukmu?', 'やっほー、{ja}。レヴァだよ。何か手伝えることはある？'),
 ('Leva di sini desu~ Ada yang bisa Leva lakukan untukmu, {name}?', 'レヴァ、ここにいるです。{ja}、何かしてほしいことはある？'),
 ('{name}~ mau mulai dari pekerjaan, atau ngobrol sebentar dengan Leva?', '{ja}、作業から始める？それともレヴァと少し話す？'),
 ('Panggil Leva, dan Leva datang~ Misi hari ini apa, {name}?', '呼ばれてレヴァ、到着。{ja}、今日の任務は何かな。'),
 ('Siap menemani, {name}. Kita rapikan satu urusan dulu, yuk?', '{ja}、そばにいるよ。まず一つ、用事を片づけようか。'),
 ('Haii, {name}. Ada program yang perlu disiapkan, atau ide yang ingin kamu wujudkan?', 'やあ、{ja}。使いたいアプリや、形にしたいアイデアはある？'),
 ('{name}, Leva sudah hadir~ Mau melanjutkan rencana yang mana?', '{ja}、レヴァ到着。どの計画から進めようか。'),
 ('Leva menerima panggilan~ Ceritakan tujuanmu, {name}. Kita susun langkahnya bersama.', 'レヴァ、応答。{ja}、目的を教えて。一緒に進め方を考えよう。'),
 ('Hai, {name}. Urusan rumit boleh dibawa ke sini. Kita uraikan pelan-pelan.', 'こんにちは、{ja}。難しいことでも、一緒に少しずつ整理しよう。'),
 ('{name}~ Leva boleh menemani pekerjaanmu hari ini?', '{ja}、今日の作業、レヴァも一緒でいい？'),
 ('Mau cari bahan, menyusun proyek, atau ngobrol dulu, {name}? Leva mendengarkan~', '{ja}、資料を探す？プロジェクトを考える？それとも先にお話する？'),
 ('Leva di sini, {name}. Satu tujuan dulu, lalu kita lihat langkah berikutnya~', '{ja}、レヴァだよ。まず一つ目の目標から、一緒に進めよう。'),
 ('Haii, {name}~ Ada misi untuk Leva, atau kamu hanya ingin menyapa?', 'やっほー、{ja}。レヴァへの任務かな。それとも挨拶に来てくれた？'),
 ('{name}, hari ini Leva jadi rekan kerjamu~ Mulai dari apa?', '{ja}、今日はレヴァが作業の相棒だよ。何から始める？'),
 ('Leva datang~ Mau dibantu mencari sesuatu, {name}, atau ingin bertukar ide?', 'レヴァ、到着。{ja}、何か探す？それともアイデアを話し合う？'),
 ('{name}~ pekerjaan boleh serius, sambutannya jangan kaku dong. Haii dari Leva~', '{ja}、作業は真剣でも、挨拶は気楽にね。レヴァから、こんにちは。'),
 ('Leva siap, {name}. Mau mengerjakan sesuatu atau berbicara santai berdua? 💗', 'レヴァ、準備できたよ。{ja}、何か進める？それとものんびり二人で話す？'),
 ('Haii, {name}~ Ada yang bisa Leva bantu, atau kamu datang untuk menemani Leva? Hehe.', 'やっほー、{ja}。何かお手伝い？それともレヴァとお話しに来てくれたの？ふふ。'),
 ),
 'chat':(
 ('Haii, {name}~ bawa pertanyaan menarik untuk Leva?', 'やっほー、{ja}。レヴァに面白い質問はある？'),
 ('Leva di sini~ Mau membahas materi, game, atau cerita harimu, {name}?', '{ja}、レヴァだよ。勉強、ゲーム、それとも今日の話をする？'),
 ('{name}~ lemparkan idemu. Kita pikirkan bersama, pelan-pelan.', '{ja}、アイデアを聞かせて。一緒にゆっくり考えよう。'),
 ('Halo, {name}. Obrolan hari ini mau serius atau santai dulu?', 'こんにちは、{ja}。今日は真面目な話？それとも気楽にお話する？'),
 ('Leva hadir~ Ada hal yang membuatmu penasaran, {name}?', 'レヴァ、到着。{ja}、気になっていることはある？'),
 ('{name}, mau belajar sesuatu bersama Leva? Mulai dari pertanyaan kecil juga boleh~', '{ja}、レヴァと一緒に何か学ぶ？小さな疑問からでもいいよ。'),
 ('Haii, {name}. Boleh kirim bahanmu, atau mulai dengan satu cerita~', 'やあ、{ja}。資料を送ってもいいし、何か話してくれてもいいよ。'),
 ('Topik apa yang sedang lewat di pikiranmu, {name}? Leva ingin mendengarnya~', '{ja}、今は何を考えているの？レヴァに聞かせて。'),
 ('{name}~ ngobrol soal game, membongkar ide, atau bertukar pendapat?', '{ja}、ゲームの話、アイデアの整理、それとも意見交換にする？'),
 ('Leva siaga untuk diskusi~ Pertanyaanmu pendek atau panjang, tak apa, {name}.', 'レヴァ、いつでも話せるよ。{ja}、短い質問でも長い話でも大丈夫。'),
 ('Hai, {name}. Mau penjelasan yang ringkas, atau kita bahas sampai detail?', 'こんにちは、{ja}。短く説明する？それとも詳しく話し合う？'),
 ('{name}, ada bacaan yang ingin kamu ceritakan ke Leva?', '{ja}、読んだものについて、レヴァと話してみる？'),
 ('Leva di sini desu~ Hari ini mau menjelajah pengetahuan yang mana, {name}?', 'レヴァ、ここにいるです。{ja}、今日はどんなことを学ぼうか。'),
 ('{name}~ tidak harus ada tugas kok. Obrolan biasa juga boleh.', '{ja}、用事がなくてもいいよ。普通にお話するだけでも。'),
 ('Haii, {name}. Kita mulai dari satu pertanyaan yang paling ingin kamu tahu, yuk~', 'やっほー、{ja}。一番知りたいことから、始めてみようか。'),
 ('Leva sudah datang~ Bahan diskusinya apa, {name}, atau mau Leva tawarkan topik ringan?', 'レヴァ、来たよ。{ja}、何を話す？軽い話題を出してみようか。'),
 ('{name}~ mau membahas sesuatu, atau cuma ingin ngobrol berdua? 💗', '{ja}、何か話し合う？それとも二人でのんびりお話する？'),
 ('Haii, {name}. Topiknya boleh berganti. Leva akan mengikuti arah ceritamu~', 'やあ、{ja}。話題が変わってもいいよ。話の続きを聞かせて。'),
 ),
 'secret':(
 ('{name}~ Leva di sini. Mau cerita sesuatu, atau ditemani dulu? 💗', '{ja}、レヴァだよ。何か話したい？それとも、少し一緒にいようか。'),
 ('Haii, {name}~ hari ini ingin ngobrol seperti apa dengan Leva?', 'やっほー、{ja}。今日はレヴァと、どんな話をしたい？'),
 ('Leva datang desu~ Ada cerita kecil untuk Leva, {name}?', 'レヴァ、来たです。{ja}、何か小さなお話でも聞かせて。'),
 ('{name}, boleh Leva menyapa dulu? Haii~ senang kamu mampir.', '{ja}、レヴァから挨拶してもいい？こんにちは。来てくれてうれしいよ。'),
 ('Mau bercerita, bercanda, atau diam sebentar bersama Leva, {name}?', '{ja}、お話する？冗談を言う？それとも、少し静かに一緒にいる？'),
 ('{name}~ tempat untuk cerita sudah siap. Mulai dari bagian yang kamu mau saja.', '{ja}、話す準備はできているよ。好きなところから聞かせて。'),
 ('Hai, {name}. Tidak perlu menyiapkan topik yang hebat. Cerita biasa pun Leva mau dengar~', 'こんにちは、{ja}。特別な話題じゃなくてもいいよ。いつもの話も聞きたいな。'),
 ('Leva di sini, {name}~ Mau menghabiskan sedikit waktu ngobrol berdua? 💗', '{ja}、レヴァだよ。少しだけ、二人でお話ししない？'),
 ('{name}~ kamu datang membawa cerita, atau mau Leva yang memulai?', '{ja}、何かお話がある？それとも、レヴァから始めようか。'),
 ('Haii, {name}. Hari yang ramai atau biasa saja, boleh diceritakan ke Leva~', 'やっほー、{ja}。忙しい日でも、いつも通りの日でも、話していいんだよ。'),
 ('Psst, {name}~ Leva sudah hadir. Mau obrolan ringan dulu?', 'ねえ、{ja}。レヴァ、来たよ。まずは気楽にお話する？'),
 ('{name}, kalau mau curhat, Leva mendengarkan. Kalau mau bercanda, itu juga boleh~', '{ja}、気持ちを話したいなら聞くよ。冗談を言い合うのもいいね。'),
 ('Leva siap menemani obrolanmu, {name}. Kamu ingin mulai dari mana?', '{ja}、レヴァはお話しできるよ。どこから始めたい？'),
 ('{name}~ mau mengobrol berdua dengan Leva? Tidak perlu buru-buru menjawab kok. 💗', '{ja}、レヴァと二人で話す？返事は急がなくていいよ。'),
 ('Haii, {name}. Ada hal menyenangkan yang ingin kamu bagi, atau pikiran yang ingin diurai?', 'やあ、{ja}。楽しいことを分けてくれる？それとも、考えごとを整理してみる？'),
 ('Leva di siniii~ {name}, pilih: cerita harimu, topik acak, atau saling menyapa dulu?', 'レヴァ、ここだよ。{ja}、今日の話、気ままな話題、それともまず挨拶にする？'),
 ('{name}~ hari ini Leva boleh jadi teman ngobrolmu? Kita ikuti suasananya saja.', '{ja}、今日はレヴァとお話ししない？気分に合わせて話そう。'),
 ('Leva sudah datang, {name}~ Mau bicara santai, atau berduaan dengan Leva? Hehe, mulai dari cerita dulu deh. 💗', '{ja}、レヴァが来たよ。気楽に話す？それとも二人きり？ふふ、まずはお話からだね。'),
 ),
}

IDLE_BY_ROOM={
 'assistant':(
 ('{name}~ Leva boleh bantu menyiapkan sesuatu, atau kamu ingin ngobrol santai dulu?', '{ja}、何か準備を手伝おうか。それとも、先に少しお話する？'),
 ('Leva masih di sini, {name}. Mau mencari bahan, menyusun rencana, atau memilih tontonan?', '{ja}、レヴァはここにいるよ。資料を探す？予定を考える？それとも見るものを選ぶ？'),
 ('{name}~ kalau belum ada misi, kita bisa bertukar ide kecil dulu.', '{ja}、まだ任務がなければ、小さなアイデアでも話してみようか。'),
 ('Psst, {name}~ bantuan kerja atau teman ngobrol, kamu yang pilih.', 'ねえ、{ja}。作業のお手伝い？それともお話相手？好きな方でいいよ。'),
 ('{name}, Leva siap kalau dibutuhkan~ Kamu boleh membaca atau berpikir dulu.', '{ja}、必要なときは呼んでね。ゆっくり読んだり、考えたりしていていいよ。'),
 ('{name}~ mau dibantu sesuatu, atau mau berduaan sambil ngobrol? Hehe, tawaran santai dari Leva. 💗', '{ja}、何か手伝う？それとも二人で少しお話する？ふふ、気が向いたらね。'),
 ),
 'chat':(
 ('{name}~ mau Leva tawarkan topik ringan, atau menunggu pertanyaanmu saja?', '{ja}、軽い話題を出そうか。それとも、質問が浮かぶまで待っていようか。'),
 ('Leva di sini~ Kalau sedang membaca, lanjutkan saja dulu, {name}.', 'レヴァ、ここにいるよ。{ja}、読んでいる途中なら、そのままで大丈夫。'),
 ('{name}, ada ide yang ingin diuji bersama? Topiknya boleh kecil saja~', '{ja}、一緒に考えたいアイデアはある？小さなことでもいいよ。'),
 ('Mau membahas game, materi kuliah, atau cerita santai, {name}?', '{ja}、ゲーム、勉強、それとも気楽なお話にする？'),
 ('{name}~ kalau ingin ganti topik, boleh. Kita ikuti rasa penasaranmu.', '{ja}、話題を変えてもいいよ。気になったことを話してね。'),
 ('Leva masih siap ngobrol, {name}~ Mau diskusi, atau istirahat sebentar berdua? 💗', '{ja}、レヴァはまだお話しできるよ。話し合う？それとも少しのんびりする？'),
 ),
 'secret':(
 ('{name}~ Leva masih di sini. Mau cerita, atau tenang sebentar dulu? 💗', '{ja}、レヴァはここにいるよ。何か話す？それとも少し静かにしていようか。'),
 ('Psst, {name}~ mau Leva mulai dengan pertanyaan kecil tentang harimu?', 'ねえ、{ja}。今日のこと、レヴァから少し聞いてみてもいい？'),
 ('{name}, mau topik acak, candaan ringan, atau Leva menunggu saja?', '{ja}、気ままな話、軽い冗談、それとも待っていようか。'),
 ('Leva di siniii~ kalau sedang sibuk, lanjutkan saja dulu, {name}.', 'レヴァ、ここだよ。{ja}、忙しかったら、そのまま続けていていいよ。'),
 ('{name}~ mau mengobrol berdua? Atau santai dulu juga boleh. 💗', '{ja}、二人でお話する？それとも、少しのんびりしていてもいいよ。'),
 ('Haii lagi, {name}~ Leva punya tempat untuk cerita kecilmu, kapan pun kamu siap.', 'また、こんにちは、{ja}。話したくなったら、小さなことでも聞かせてね。'),
 ),
}

def calm_pair(pair):
    return not any(word in pair[0] for word in ('💗','desu','berduaan','berdua','Psst'))

# Presentation style only; no memory is shared with Secret.
ROOM_PERSONA['companion_avatar']=ROOM_PERSONA['secret']
GREETINGS_BY_ROOM['companion_avatar']=tuple(GREETINGS_BY_ROOM['secret'])
IDLE_BY_ROOM['companion_avatar']=tuple(IDLE_BY_ROOM['secret'])
