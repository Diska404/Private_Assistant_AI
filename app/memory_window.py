"""Inspectable explicit notes. No passive recording of chat or audio."""
import tkinter as tk
import sqlite3
from tkinter import ttk,messagebox
from gui import BG,PANEL,CARD,INK,ACCENT

class MemoryWindow:
    def __init__(self,main):
        self.main=main;self.store=main.desktop.tools.memory
        self.window=tk.Toplevel(main.root);self.window.title('Leva — Memori pribadi');self.window.geometry('820x600');self.window.configure(bg=BG)
        main.label(self.window,'Memori pribadi',bg=BG,font=('Segoe UI',22,'bold')).pack(anchor='w',padx=24,pady=20)
        main.label(self.window,'Catatan eksplisit. Riwayat dan ringkasan otomatis tersedia di Pusat → Memori otomatis; audio mentah tidak disimpan.',bg=BG,fg=ACCENT,wraplength=760).pack(anchor='w',padx=24)
        self.rows=ttk.Treeview(self.window,columns=('note','created'),show='headings',selectmode='browse')
        self.rows.heading('note',text='Catatan');self.rows.heading('created',text='Disimpan (UTC)');self.rows.column('note',width=540);self.rows.column('created',width=150)
        self.rows.pack(fill='both',expand=True,padx=24,pady=16)
        self.entry=tk.Entry(self.window,bg=CARD,fg=INK,insertbackground=ACCENT,relief='flat',font=('Segoe UI',11));self.entry.pack(fill='x',padx=24,ipady=10)
        bar=tk.Frame(self.window,bg=BG);bar.pack(fill='x',padx=24,pady=16)
        main.button(bar,'Simpan catatan',self.save,primary=True).pack(side='left')
        main.button(bar,'Hapus catatan pilihan',self.forget).pack(side='right')
        self.notice=tk.StringVar(value=str(self.store.path));main.label(self.window,'',textvariable=self.notice,bg=BG,wraplength=760,justify='left').pack(anchor='w',padx=24,pady=(0,18))
        self.refresh()
    def refresh(self):
        for ident in self.rows.get_children():self.rows.delete(ident)
        try:
            for row in self.store.recall():self.rows.insert('', 'end',iid=str(row['id']),values=(row['note'],row['created']))
        except (OSError,sqlite3.Error):self.notice.set('Memori belum dapat dibaca. Periksa penyimpanan lokal di D.')
    def save(self):
        try:self.store.remember(self.entry.get());self.entry.delete(0,'end');self.refresh();self.notice.set('Catatan tersimpan lokal.')
        except (ValueError,OSError,sqlite3.Error):self.notice.set('Gunakan catatan 1–600 karakter tanpa kata sandi/API key dan periksa penyimpanan D.')
    def forget(self):
        selected=self.rows.selection()
        if selected and messagebox.askyesno('Hapus catatan','Hapus catatan pilihan dari memori lokal?',parent=self.window):
            self.store.forget(selected[0]);self.refresh()
