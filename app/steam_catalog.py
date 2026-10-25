"""Read installed Steam metadata. Launch only verified local app IDs, never shell text."""
import os
from datetime import datetime
from pathlib import Path
import re
import subprocess
import time

from command_resolution import normalized


def steam_executable():
    candidates=[]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:
            candidates.append(Path(winreg.QueryValueEx(key,'SteamExe')[0]))
    except (ImportError,OSError):pass
    candidates.append(Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Steam/steam.exe')
    return next((p for p in candidates if p.is_file()),None)


def pairs(text):
    return dict(re.findall(r'"([A-Za-z_]+)"\s+"([^"\r\n]*)"',text))


class SteamCatalog:
    def __init__(self,executable=None):
        self.executable=Path(executable) if executable else steam_executable()
        self.games={}
        if not self.executable:return
        roots={self.executable.parent}
        folders=self.executable.parent/'steamapps/libraryfolders.vdf'
        try:
            for path in re.findall(r'"path"\s+"([^"\r\n]+)"',folders.read_text(encoding='utf-8-sig')):
                roots.add(Path(path.replace('\\\\','\\')))
        except (OSError,UnicodeError):pass
        for root in sorted(roots):
            for manifest in sorted((root/'steamapps').glob('appmanifest_*.acf')):
                try:
                    fields=pairs(manifest.read_text(encoding='utf-8-sig'))
                    appid=fields.get('appid','');name=fields.get('name','');folder=fields.get('installdir','')
                    if not re.fullmatch(r'[0-9]{1,12}',appid) or manifest.stem!='appmanifest_'+appid:continue
                    if not name or not folder or '/' in folder or '\\' in folder or folder in ('.','..'):continue
                    install=(root/'steamapps/common'/folder).resolve()
                    if not install.is_relative_to((root/'steamapps/common').resolve()) or not install.is_dir():continue
                    if int(fields.get('StateFlags','0'))!=4:continue
                    aliases={normalized(name)}
                    if 'frontline 2' in normalized(name):aliases.update(('gfl2','gfl2 exilium','girls frontline 2','exilium'))
                    self.games[appid]={'id':appid,'name':name,'path':str(install),'aliases':sorted(aliases),'manifest':str(manifest)}
                except (OSError,UnicodeError,ValueError):continue

    def public(self):return [{'id':r['id'],'name':r['name'],'aliases':r['aliases']} for r in self.games.values()]

    def resolve(self,value):
        if value in self.games:return self.games[value]
        key=normalized(value).strip(' .!?')
        rows=[r for r in self.games.values() if key in r['aliases']]
        return rows[0] if len(rows)==1 else None

    def tracked_processes(self,appid):
        """Steam can hand off to another installation. Use its tracked PID receipts,
        checked against the live process creation time to reject recycled PIDs.
        Do not inspect process command lines, account files or environment values.
        """
        if not self.executable:return []
        import psutil
        log=self.executable.parent/'logs/gameprocess_log.txt'
        tracked={}
        try:
            with log.open('rb') as stream:
                stream.seek(0,2);stream.seek(max(0,stream.tell()-1024*1024))
                lines=stream.read().decode('utf-8',errors='replace').splitlines()
            pattern=r'^\[([^]]+)\] AppID '+re.escape(appid)+r' (adding PID|no longer tracking PID) (\d+)\b'
            for line in lines:
                match=re.match(pattern,line)
                if not match:continue
                stamp,action,pid=match.groups();pid=int(pid)
                if action.startswith('no longer'):tracked.pop(pid,None)
                else:tracked[pid]=datetime.strptime(stamp,'%Y-%m-%d %H:%M:%S').timestamp()
        except (OSError,ValueError):return []
        verified=[]
        for pid,stamp in list(tracked.items())[-32:]:
            try:
                created=psutil.Process(pid).create_time()
                if stamp-120<=created<=stamp+5:verified.append(pid)
            except (psutil.Error,OSError):pass
        return verified

    def launch(self,value,authorized=lambda:True):
        row=self.resolve(value)
        if not row:return {'status':'needs_input','reply':'Game itu belum ditemukan sebagai instalasi Steam yang siap dijalankan. Pilih game dari inventaris Steam.','games':self.public()}
        if not authorized():return {'status':'cancelled','reply':'Peluncuran game dibatalkan.'}
        from windows_runtime import application_windows,raise_window
        observed=application_windows(row['name'],install_root=row['path'],process_ids=self.tracked_processes(row['id']))
        if observed:
            raised=raise_window(observed[0])
            return {'status':'done' if raised else 'unverified','reply':row['name']+' sudah berjalan'+('; jendelanya kubawa ke depan.' if raised else '; jendelanya belum bisa dibawa ke depan.'),'game_id':row['id'],'window_observed':True}
        if not self.executable or not self.executable.is_file() or not Path(row['path']).is_dir():
            return {'status':'failed','reply':'Instalasi Steam atau direktori game sudah tidak tersedia.'}
        try:
            subprocess.Popen([str(self.executable),'-applaunch',row['id']],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        except OSError:return {'status':'failed','reply':'Permintaan menjalankan game gagal dikirim ke Steam.'}
        until=time.monotonic()+40
        while time.monotonic()<until and authorized():
            if application_windows(row['name'],install_root=row['path'],process_ids=self.tracked_processes(row['id'])):
                return {'status':'done','reply':'Jendela '+row['name']+' terdeteksi. Login dan lobby belum diverifikasi.','game_id':row['id'],'window_observed':True,'lobby_verified':False}
            time.sleep(.25)
        if not authorized():return {'status':'cancelled','reply':'Pengamatan dihentikan. Permintaan sudah dikirim ke Steam; game mungkin masih melanjutkan peluncuran.','game_id':row['id']}
        return {'status':'unverified','reply':'Permintaan menjalankan '+row['name']+' sudah dikirim ke Steam, tetapi jendela game belum terkonfirmasi. Steam mungkin memerlukan login atau pembaruan.','game_id':row['id'],'window_observed':False,'lobby_verified':False}
