"""Foreground UI for Windows location consent; users operate the OS permission prompt."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import tkinter as tk

root=tk.Tk();root.title('Leva — Lokasi perangkat');root.geometry('530x240')
notice=tk.StringVar(value='Windows menentukan apakah lokasi perangkat tersedia. Tekan tombol untuk meminta izin; Leva tidak mengubah pengaturan privasi Windows.')
tk.Label(root,textvariable=notice,wraplength=480,justify='left',padx=20,pady=24).pack(fill='x')
loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
async def locate():
    try:
        from winrt.windows.devices.geolocation import Geolocator,GeolocationAccessStatus
        access=await Geolocator.request_access_async()
        if access!=GeolocationAccessStatus.ALLOWED:
            notice.set('Lokasi tidak diizinkan. Cuaca tetap dapat memakai kota cadangan Cikarang atau kota pilihan Anda.');return
        locator=Geolocator();locator.desired_accuracy_in_meters=1000
        position=await asyncio.wait_for(locator.get_geoposition_async(),timeout=20)
        coordinate=position.coordinate;point=coordinate.point.position
        data={'latitude':point.latitude,'longitude':point.longitude,'accuracy_m':coordinate.accuracy,'source':'Windows Geolocator','updated':datetime.now(timezone.utc).isoformat()}
        path=Path('D:/AI/AI Lokal Asisten/Leva/cache/device-location.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data),encoding='utf-8')
        notice.set('Lokasi perangkat tersedia. Akurasi Windows sekitar '+str(round(coordinate.accuracy))+' meter. Leva dapat memakainya untuk cuaca; lokasi disimpan lokal di D.')
    except Exception as error:notice.set('Lokasi belum tersedia ('+type(error).__name__+'). Cuaca memakai kota cadangan; Anda dapat memeriksa izin lokasi Windows sendiri.')
def start():
    notice.set('Menunggu izin atau posisi dari Windows…');loop.create_task(locate())
tk.Button(root,text='Minta lokasi perangkat dari Windows',command=start,padx=12,pady=12).pack(pady=8)
def tick():
    loop.call_soon(loop.stop);loop.run_forever();root.after(30,tick)
root.after(30,tick);root.mainloop()
for task in asyncio.all_tasks(loop):task.cancel()
loop.run_until_complete(asyncio.sleep(0));loop.close()
