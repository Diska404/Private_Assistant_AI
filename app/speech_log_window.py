"""Inspectable full transcripts, including utterances that never reached an agent."""
import tkinter as tk
from tkinter import ttk
from speech_turns import STATUS_LABELS


class SpeechLogWindow:
    def __init__(self,main):
        self.main=main;self.journal=main.speech_inbox();self.rows={};self.signature=None
        self.window=tk.Toplevel(main.root);self.window.title('Leva — Catatan input suara');self.window.geometry('920x640')
        self.window.minsize(760,480)
        tk.Label(self.window,text='Teks hasil ASR disimpan penuh di D; audio tidak disimpan. 200 ucapan terbaru ditampilkan.',anchor='w').pack(fill='x',padx=12,pady=8)
        frame=tk.Frame(self.window);frame.pack(fill='both',expand=True,padx=12)
        self.tree=ttk.Treeview(frame,columns=('time','state','preview'),show='headings',height=8)
        for key,label,width in [('time','Waktu',145),('state','Status',260),('preview','Pratinjau · teks lengkap di bawah',420)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width)
        self.tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',lambda _:self.show())
        self.text=tk.Text(self.window,wrap='word',height=10)
        self.text.pack(fill='both',expand=True,padx=12,pady=8)
        self.message=tk.StringVar(value='Pilih ucapan untuk melihat teks lengkap dan alasan pemrosesannya.')
        tk.Label(self.window,textvariable=self.message,anchor='w',wraplength=860).pack(fill='x',padx=12)
        controls=tk.Frame(self.window);controls.pack(fill='x',padx=12,pady=10)
        tk.Button(controls,text='Gunakan ucapan terpilih sebagai perintah',command=self.use).pack(side='left')
        tk.Button(controls,text='Terima perintah · 45 dtk',command=main.arm_local_mic).pack(side='left',padx=8)
        tk.Button(controls,text='Batalkan antrean',command=self.cancel).pack(side='right')
        tk.Button(controls,text='Hapus catatan selesai',command=self.clear).pack(side='right',padx=8)
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():return
        from datetime import datetime
        rows=self.journal.recent(200);signature=[(r['id'],r['updated'],r['state'],r['text']) for r in rows]
        if signature!=self.signature:
            selected=self.tree.selection();self.rows={r['id']:r for r in rows}
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                when=datetime.fromisoformat(row['created']).astimezone().strftime('%d/%m %H:%M:%S')
                self.tree.insert('', 'end',iid=row['id'],values=(when,STATUS_LABELS[row['state']],row['text'][:100]))
            if selected and selected[0] in self.rows:self.tree.selection_set(selected[0]);self.show()
            self.signature=signature
        self.window.after(1000,self.refresh)

    def selected(self):
        ids=self.tree.selection()
        return self.journal.get(ids[0]) if ids else None

    def show(self):
        row=self.selected()
        if not row:return
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',row['text']);self.text.configure(state='disabled')
        self.message.set(STATUS_LABELS[row['state']]+(' · '+row['detail'] if row['detail'] else ''))

    def use(self):
        row=self.selected()
        if not row:return
        if row['state'] in ('collecting','running','queued','waiting_draft'):
            self.message.set('Ucapan masih dikumpulkan atau sudah berada dalam antrean.');return
        text=row['command'] or row['text']
        if not text or len(text)>3000:
            self.message.set('Pilih ucapan berisi 1–3.000 karakter. Teks lengkap tetap tersimpan.');return
        if self.main.desktop.paused or self.main.desktop.sleeping:
            self.message.set('Aktifkan kembali Leva sebelum menjalankan perintah.');return
        self.main.receive_voice({'kind':'local_heard','text':row['text'],'command':text,'accepted':True,'reason':'followup','final':True})
        self.main.dispatch_voice();self.signature=None

    def cancel(self):
        self.journal.cancel_pending();self.signature=None
        self.message.set('Antrean dibatalkan; tugas yang sudah berjalan tetap berjalan.')

    def clear(self):
        self.journal.clear();self.signature=None
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.configure(state='disabled')
        self.message.set('Catatan selesai dihapus; ucapan aktif dan antrean dipertahankan.')
