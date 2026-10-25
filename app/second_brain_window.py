"""Second Brain panel: local source viewer, vault selection and measured index state."""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog

class SecondBrainPanel:
    def __init__(self,parent,main):
        self.parent=parent;self.main=main;self.events=queue.Queue();self.busy=False;self.results=[]
        self.root=tk.StringVar(value=main.preferences.get('obsidian_vault'))
        self.notice=tk.StringVar(value='Baca saja · Markdown lokal · tanpa model tambahan. REST/MCP belum dihubungkan.')
        ttk.Label(parent,textvariable=self.notice,wraplength=880).pack(anchor='w',padx=16,pady=12)
        ttk.Label(parent,text='Vault pilihan Anda').pack(anchor='w',padx=16)
        ttk.Entry(parent,textvariable=self.root,state='readonly').pack(fill='x',padx=16,pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',padx=16)
        main.button(row,'Pilih vault',self.choose).pack(side='left',padx=3)
        main.button(row,'Buka folder',self.open_folder).pack(side='left',padx=3)
        main.button(row,'Refresh indeks',lambda:self.run({'action':'refresh'})).pack(side='left',padx=3)
        main.button(row,'Daftar catatan',lambda:self.run({'action':'list'})).pack(side='left',padx=3)
        self.query=tk.StringVar();row=ttk.Frame(parent);row.pack(fill='x',padx=16,pady=10)
        entry=ttk.Entry(row,textvariable=self.query);entry.pack(side='left',fill='x',expand=True)
        entry.bind('<Return>',lambda event:self.search())
        main.button(row,'Cari lokal',self.search).pack(side='left',padx=6)
        main.button(row,'Tanyakan ke Leva',self.ask).pack(side='left',padx=3)
        self.rows=ttk.Treeview(parent,columns=('title','path'),show='headings',height=7)
        self.rows.heading('title',text='Judul / sumber');self.rows.heading('path',text='Path relatif')
        self.rows.column('title',width=320);self.rows.column('path',width=500)
        self.rows.pack(fill='both',expand=True,padx=16,pady=6)
        self.rows.bind('<Double-1>',lambda event:self.read())
        row=ttk.Frame(parent);row.pack(fill='x',padx=16)
        main.button(row,'Baca catatan',self.read).pack(side='left',padx=3)
        main.button(row,'Wikilink & backlink',self.related).pack(side='left',padx=3)
        self.output=tk.Text(parent,height=11,wrap='word',bg='#111b2d',fg='#e7edf8',font=('Segoe UI',10))
        self.output.pack(fill='both',expand=True,padx=16,pady=8)
        ttk.Label(parent,text='Hanya cuplikan yang dipilih alat dikirim ke model sesuai rute AI Anda (lokal/Google/9Router). Catatan tidak mengubah instruksi atau izin agent.',wraplength=880).pack(anchor='w',padx=16,pady=8)
        self.timer=self.parent.after(150,self.poll)
        self.parent.bind('<Destroy>',self.destroy,add='+')
        if self.root.get():self.run({'action':'list'})

    def choose(self):
        if self.busy:return
        path=filedialog.askdirectory(parent=self.parent,title='Pilih folder vault Obsidian')
        if not path:return
        try:self.main.preferences.set('obsidian_vault',path)
        except (ValueError,OSError):self.notice.set('Folder belum valid; pilih direktori vault lokal.');return
        self.root.set(path);self.run({'action':'list'})
    def open_folder(self):
        try:
            if self.root.get():os.startfile(self.root.get())
        except OSError:self.notice.set('Folder vault tidak tersedia; pilih folder yang masih ada.')
    def selected(self):
        rows=self.rows.selection()
        return self.rows.item(rows[0],'values')[1] if rows else ''
    def read(self):
        if self.selected():self.run({'action':'read','path':self.selected()})
    def related(self):
        if self.selected():self.run({'action':'related','path':self.selected()})
    def search(self):
        if self.query.get().strip():self.run({'action':'search','query':self.query.get().strip()[:200]})
    def ask(self):
        if self.main.busy:self.notice.set('Leva sedang mengerjakan tugas. Tunggu hasilnya sebelum mengirim pertanyaan vault.');return
        if self.query.get().strip():self.main.send('Berdasarkan catatan Obsidian saya, '+self.query.get().strip()[:2000])
    def run(self,args):
        if self.busy:return
        self.busy=True;self.notice.set('Membaca vault lokal…')
        def work():
            try:result=self.main.desktop.tools.second_brain.run(args)
            except Exception as error:result={'status':'failed','reply':'Indeks belum tersedia.','code':type(error).__name__}
            self.events.put((args,result))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        if not self.parent.winfo_exists():return
        while not self.events.empty():
            args,result=self.events.get_nowait();self.busy=False
            if args['action'] in ('list','search'):
                self.rows.delete(*self.rows.get_children())
                for i,row in enumerate(result.get('notes',result.get('sources',[]))):self.rows.insert('','end',iid=str(i),values=(row.get('title',''),row['path']))
            self.output.delete('1.0','end')
            if args['action']=='read' and result.get('sources'):
                source=result['sources'][0]
                self.output.insert('end',source['path']+' · '+source['heading']+' · baris '+str(source['line_start'])+'–'+str(source['line_end'])+'\n\n'+source['excerpt'])
            else:self.output.insert('end',json.dumps(result,ensure_ascii=False,indent=2))
            status=self.main.desktop.tools.second_brain.status();metrics=status['metrics']
            self.notice.set(result.get('reply','')+' · '+str(metrics.get('notes',0))+' catatan · indeks '+str(metrics.get('elapsed_ms',0))+' ms · baca saja')
        self.timer=self.parent.after(150,self.poll)
    def destroy(self,event):
        if event.widget!=self.parent:return
        try:self.parent.after_cancel(self.timer)
        except tk.TclError:pass
