"""Preview a shared avatar locally; cancellation never writes the profile."""
import io
import tkinter as tk
from tkinter import messagebox
from profile_avatar import ProfileAvatar,frame_image,MAX_UPLOAD


def edit_avatar(parent,raw,on_saved):
    from PIL import Image,ImageOps,ImageTk
    if not 0<len(raw)<=MAX_UPLOAD:raise ValueError('Foto maksimal 5 MB.')
    with Image.open(io.BytesIO(raw)) as source:
        if source.format not in ('PNG','JPEG','WEBP') or source.width*source.height>16_000_000:raise ValueError('Gunakan PNG/JPEG/WebP maksimal 16 MP.')
        image=ImageOps.exif_transpose(source).convert('RGBA');image.thumbnail((1200,1200))
    win=tk.Toplevel(parent);win.title('Sesuaikan foto Leva');win.configure(bg='#0d1723');win.geometry('430x680');win.minsize(390,640);win.transient(parent)
    tk.Label(win,text='Geser foto, lalu konfirmasi',bg='#0d1723',fg='#e2efed',font=('Segoe UI',16)).pack(pady=15)
    canvas=tk.Canvas(win,width=320,height=320,bg='#080e17',highlightthickness=0);canvas.pack()
    values={k:tk.DoubleVar(value=v) for k,v in {'x':.5,'y':.5,'zoom':1.}.items()};photo=None;last=None
    def draw(*_):
        nonlocal photo
        framed=frame_image(image,{k:v.get() for k,v in values.items()}).resize((320,320))
        photo=ImageTk.PhotoImage(framed,master=win);canvas.delete('all');canvas.create_image(0,0,anchor='nw',image=photo)
        canvas.create_oval(2,2,318,318,outline='#90dacf',width=2);canvas.create_line(160,0,160,320,fill='#86a6aa',dash=(2,8));canvas.create_line(0,160,320,160,fill='#86a6aa',dash=(2,8))
    for key,label,limit in [('zoom','Zoom',4),('x','Posisi horizontal',1),('y','Posisi vertikal',1)]:
        tk.Scale(win,label=label,variable=values[key],from_=1 if key=='zoom' else 0,to=limit,resolution=.01,orient='horizontal',command=draw,bg='#0d1723',fg='#b5d4d6',highlightthickness=0,length=340).pack()
    def press(event):
        nonlocal last
        last=(event.x,event.y)
    def drag(event):
        nonlocal last
        if last is None:return
        side=min(image.size)/values['zoom'].get()
        for key,delta,size in [('x',event.x-last[0],image.width),('y',event.y-last[1],image.height)]:values[key].set(max(0,min(1,values[key].get()-delta/320*side/size)))
        last=(event.x,event.y);draw()
    canvas.bind('<ButtonPress-1>',press);canvas.bind('<B1-Motion>',drag)
    def confirm():
        try:ProfileAvatar().save(raw,{k:v.get() for k,v in values.items()});on_saved();win.destroy()
        except (OSError,ValueError) as error:messagebox.showerror('Foto Leva',str(error),parent=win)
    buttons=tk.Frame(win,bg='#0d1723');buttons.pack(pady=10);tk.Button(buttons,text='Batalkan',command=win.destroy).pack(side='left',padx=10);tk.Button(buttons,text='Gunakan foto',command=confirm,bg='#92d8ce').pack(side='left',padx=10)
    draw();win.focus_set();return win
