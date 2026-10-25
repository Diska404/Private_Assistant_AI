"""One normalized profile image shared by desktop and authenticated companion clients."""
from pathlib import Path
import io
import threading
import warnings
from paths import DATA

MAX_UPLOAD=5*1024*1024
AVATAR_LOCK=threading.RLock()

def frame_image(image,framing=None):
    import math
    from PIL import Image
    values=framing or {'x':.5,'y':.5,'zoom':1.}
    if not isinstance(values,dict) or set(values)!={'x','y','zoom'} or any(type(v) not in (int,float) or not math.isfinite(v) for v in values.values()):raise ValueError('avatar_invalid_framing')
    x,y,zoom=values['x'],values['y'],values['zoom']
    if not 0<=x<=1 or not 0<=y<=1 or not 1<=zoom<=4:raise ValueError('avatar_invalid_framing')
    side=min(image.size)/zoom
    left=max(0,min(image.width-side,x*image.width-side/2));top=max(0,min(image.height-side,y*image.height-side/2))
    return image.convert('RGBA').resize((512,512),resample=Image.Resampling.LANCZOS,box=(left,top,left+side,top+side))

class ProfileAvatar:
    def __init__(self,folder=None):
        self.folder=Path(folder) if folder is not None else DATA/'profile'
        self.path=self.folder/'avatar.png';self.lock=AVATAR_LOCK
    def metadata(self):
        with self.lock:
            try:revision=str(self.path.stat().st_mtime_ns)
            except FileNotFoundError:return {'revision':'','url':''}
            return {'revision':revision,'url':'/api/avatar?v='+revision}
    def read(self):
        with self.lock:
            try:return self.path.read_bytes()
            except FileNotFoundError:return None
    def save(self,raw,framing=None):
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_UPLOAD:raise ValueError('avatar_max_5mb')
        from PIL import Image,ImageOps,UnidentifiedImageError
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16_000_000:raise ValueError('avatar_png_jpeg_webp_max_16mp')
                    image=ImageOps.exif_transpose(image)
                    image=frame_image(image,framing)
                    output=io.BytesIO();image.save(output,format='PNG')
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):raise ValueError('avatar_invalid_image') from None
        with self.lock:
            self.folder.mkdir(parents=True,exist_ok=True)
            temporary=self.folder/'avatar.tmp';temporary.write_bytes(output.getvalue());temporary.replace(self.path)
            return self.metadata()
