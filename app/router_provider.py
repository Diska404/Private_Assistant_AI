"""9Router loopback client. It proposes tools; the host remains the executor."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from hybrid_engine import OnlineUnavailable
from paths import DATA
from provider_urls import base_url

KEY_FILE=DATA/'credentials/9router-key.dpapi'


def _protect(raw,decrypt=False):
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.windll.crypt32
    if decrypt:ok=crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:ok=crypt.CryptProtectData(ctypes.byref(source),'Leva 9Router',None,None,None,1,ctypes.byref(target))
    if not ok:raise OSError('router_key_protection_failed')
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)


def save_key(value,path=KEY_FILE):
    if not isinstance(value,str) or not value.strip() or len(value)>4096 or any(c in value for c in '\r\n\x00'):raise ValueError('router_invalid_key')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_bytes(_protect(value.strip().encode()));temporary.replace(path)


def load_key(path=KEY_FILE):
    try:return _protect(Path(path).read_bytes(),True).decode()
    except FileNotFoundError:return ''
    except (OSError,UnicodeError):raise OnlineUnavailable('router_key_unavailable') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class RouterClient:
    def __init__(self,url,model='',key_loader=load_key):
        try:self.url=base_url(url)
        except ValueError:raise OnlineUnavailable('router_invalid_configuration') from None
        if not isinstance(model,str) or len(model)>200 or any(c in model for c in '\r\n\x00'):raise OnlineUnavailable('router_invalid_configuration')
        self.model=model.strip();self.key_loader=key_loader

    def request(self,path,payload=None,timeout=35):
        key=self.key_loader();headers={'Accept':'application/json','Content-Type':'application/json'}
        if key:headers['Authorization']='Bearer '+key
        request=urllib.request.Request(self.url+path,headers=headers,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode())
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            with opener.open(request,timeout=timeout) as response:
                raw=response.read(2_000_001)
                if len(raw)>2_000_000:raise OnlineUnavailable('router_response_too_large')
        except urllib.error.HTTPError as error:
            # Never forward upstream response bodies, request headers or credentials.
            reason={401:'authentication',403:'authentication',408:'timeout',429:'rate_limit',400:'model_or_request',404:'model_unavailable'}.get(error.code,'http_'+str(error.code))
            error.close()
            raise OnlineUnavailable('router_'+reason) from None
        except (OSError,TimeoutError,urllib.error.URLError):raise OnlineUnavailable('router_unreachable') from None
        try:
            body=json.loads(raw)
            if not isinstance(body,dict):raise ValueError()
            return body
        except (ValueError,TypeError):raise OnlineUnavailable('router_invalid_response') from None

    def models(self):
        rows=self.request('/models',timeout=8).get('data',[])
        if not isinstance(rows,list):raise OnlineUnavailable('router_invalid_response')
        # Listing is not evidence of zero pricing or successful inference.
        return sorted({r['id'] for r in rows if isinstance(r,dict) and isinstance(r.get('id'),str) and len(r['id'])<=200 and not re.search(r'[\r\n\x00]',r['id'])})

    def completion(self,messages,system,tools=None):
        if not self.model:raise OnlineUnavailable('router_model_not_selected')
        complex_tools=any(row.get('function',{}).get('name') in ('comfy_action','image_action','project_action','terminal') for row in tools or [])
        payload={'model':self.model,'messages':[{'role':'system','content':system},*messages],'stream':False,'max_tokens':2048 if complex_tools else 512}
        if tools:payload.update(tools=tools,tool_choice='required',parallel_tool_calls=False)
        body=self.request('/chat/completions',payload)
        try:
            choice=body['choices'][0]
            if choice.get('finish_reason')=='length':raise OnlineUnavailable('router_output_limit')
            if choice.get('finish_reason') not in ('stop','tool_calls'):raise ValueError()
            return choice['message']
        except (KeyError,IndexError,TypeError,ValueError):raise OnlineUnavailable('router_incomplete_response') from None

    def propose_tool(self,messages,system,tools):
        message=self.completion(messages,system,tools)
        try:
            call=message['tool_calls'][0]['function'];args=call['arguments']
            if isinstance(args,str):args=json.loads(args)
            if not isinstance(call['name'],str) or not isinstance(args,dict):raise ValueError()
            return {'action':call['name'],'args':args}
        except (KeyError,IndexError,TypeError,ValueError):
            # Some routed providers return the required call as JSON text. It is
            # still data: accept exactly one declared function, never execute code.
            try:
                text=message.get('content','').strip()
                if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
                obj=json.loads(text)
                name=obj.get('action',obj.get('name'));values=obj.get('args',obj.get('arguments'))
                allowed={t['function']['name'] for t in tools}
                if not isinstance(obj,dict) or name not in allowed or not isinstance(values,dict):raise ValueError()
                from assistant_tools import validate_call
                validate_call(name,values)
                return {'action':name,'args':values,'textual_tool_json':True}
            except (ValueError,TypeError,AttributeError):raise OnlineUnavailable('router_tool_call_unsupported') from None

    def generate(self,messages,system):
        text=self.completion(messages,system).get('content')
        if not isinstance(text,str) or not text.strip():raise OnlineUnavailable('router_empty_response')
        return text.strip()


def configured_client(config=None):
    if config is not None:
        if not isinstance(config,dict):raise OnlineUnavailable('router_invalid_configuration')
        return RouterClient(config.get('url',''),config.get('model',''))
    from preferences import Preferences
    p=Preferences()
    try:return RouterClient(p.get('router_url'),p.get('router_model'))
    finally:p.close()
