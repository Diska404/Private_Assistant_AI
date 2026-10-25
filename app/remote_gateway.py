"""Private Tailscale Serve adapter. No Funnel, firewall rule or account credentials."""
import json
from pathlib import Path
import subprocess
import re
from web_bridge import remote_origin

class GatewayError(ValueError):
    def __init__(self,code,setup_url=''):super().__init__(code);self.setup_url=setup_url

def setup_link(output):
    if isinstance(output,bytes):output=output.decode('utf8',errors='replace')
    match=re.search(r'https://login\.tailscale\.com/f/serve\?[^\s]+',output or '')
    return match[0] if match else ''

class RemoteGateway:
    def __init__(self,binary=None):
        self.binary=Path(binary) if binary else Path('C:/Program Files/Tailscale/tailscale.exe')
    def run(self,args,timeout=12):
        if not self.binary.is_file():raise ValueError('tailscale_not_installed')
        try:result=subprocess.run([str(self.binary),*args],capture_output=True,text=True,timeout=timeout,creationflags=0x08000000)
        except subprocess.TimeoutExpired as error:
            link=setup_link(error.stdout) or setup_link(error.stderr)
            raise GatewayError('tailscale_enable_https_required' if link else 'tailscale_timeout',link) from None
        if result.returncode:
            link=setup_link(result.stdout+'\n'+result.stderr)
            if link:raise GatewayError('tailscale_enable_https_required',link)
            raise GatewayError('tailscale_command_not_ready')
        return result.stdout
    def status(self):
        status=json.loads(self.run(['status','--json']))
        state=status.get('BackendState','unknown')
        if state!='Running':return {'ready':False,'state':state,'detail':'Masuk ke Tailscale di laptop dan HP memakai akun yang sama.'}
        dns=status.get('Self',{}).get('DNSName','').rstrip('.')
        return {'ready':True,'state':state,'origin':remote_origin('https://'+dns)}
    def enable(self,port):
        state=self.status()
        if not state['ready']:raise ValueError('tailscale_login_required')
        config=json.loads(self.run(['serve','status','--json']) or '{}')
        if any(config.get('AllowFunnel',{}).values()):raise ValueError('public_funnel_must_be_disabled_before_leva_remote')
        expected='http://127.0.0.1:'+str(int(port))
        handlers=config.get('Web',{}).get(state['origin'][8:]+':443',{}).get('Handlers',{})
        if handlers and (set(handlers)!={'/'} or handlers['/'].get('Proxy')!=expected):raise ValueError('tailscale_serve_already_used_by_another_service')
        if not handlers:self.run(['serve','--bg','--https=443',expected],timeout=15)
        confirmed=json.loads(self.run(['serve','status','--json']))
        root=confirmed.get('Web',{}).get(state['origin'][8:]+':443',{}).get('Handlers',{}).get('/',{})
        if root.get('Proxy')!=expected:raise ValueError('tailscale_serve_not_verified')
        return state
    def disable(self,port):
        state=self.status()
        if not state['ready']:return
        config=json.loads(self.run(['serve','status','--json']) or '{}')
        handler=config.get('Web',{}).get(state['origin'][8:]+':443',{}).get('Handlers',{}).get('/',{})
        if handler.get('Proxy')=='http://127.0.0.1:'+str(int(port)):self.run(['serve','--https=443','off'])
