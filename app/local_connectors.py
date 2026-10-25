"""Read-only local service adapters; not a public remote-access listener or MCP client."""
import json
import urllib.request
from urllib.parse import urlparse


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def comfyui(action,base='http://127.0.0.1:8188'):
    parsed=urlparse(base)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.strip('/'):
        raise ValueError('comfyui_loopback_base_required')
    route={'stats':'/system_stats','queue':'/queue','models':'/models'}.get(action)
    if route is None:raise ValueError('unsupported_comfyui_read_action')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(base.rstrip('/')+route,timeout=4) as response:raw=response.read(500001)
        if len(raw)>500000:raise ValueError('connector_response_too_large')
        data=json.loads(raw)
        if action in ('queue','stats') and not isinstance(data,dict):raise ValueError('invalid_connector_response')
    except (OSError,ValueError) as error:
        return {'status':'failed','code':str(error) if isinstance(error,ValueError) else 'service_unreachable','reply':'ComfyUI lokal belum merespons dengan format yang sesuai. Server tidak dinyalakan atau diubah otomatis.'}
    if action=='queue':
        data={'running_count':len(data.get('queue_running',[])),'pending_count':len(data.get('queue_pending',[]))}
    elif action=='stats':
        system=data.get('system',{})
        data={'system':{k:system[k] for k in ('os','python_version','pytorch_version','ram_total','ram_free') if k in system},'devices':[{k:row[k] for k in ('name','type','index','vram_total','vram_free','torch_vram_total','torch_vram_free') if k in row} for row in data.get('devices',[])[:4]]}
    return {'status':'done','reply':'Status ComfyUI dibaca melalui API lokal; tidak ada workflow dijalankan.','action':action,'data':data,'untrusted_data':True}
