"""Small LAN connector for the user's observed Smarthome_IoT firmware.

No discovery scan, arbitrary URLs, Firebase secrets, or firmware updates.
"""
import ipaddress
import json
import re
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class RoomLamp:
    host='192.168.0.171'
    def __init__(self,transport=None):self.transport=transport or self.request
    def public(self):
        return {'id':'room_lamp','name':'Lampu kamar','host':self.host,'driver':'Smarthome_IoT ESP8266','actions':['status','on','off'],'executor':'laptop LAN','verification':'systemOn dari /quick/status, bukan observasi fisik'}
    def request(self,path):
        if not ipaddress.ip_address(self.host).is_private or path not in ('/quick/status','/on','/off'):raise ValueError('unregistered_device_endpoint')
        opener=build_opener(ProxyHandler({}),NoRedirect())
        try:
            with opener.open(Request('http://'+self.host+path,headers={'Accept':'application/json','User-Agent':'Leva-LAN/1'}),timeout=4) as response:
                raw=response.read(8193)
                if len(raw)>8192:raise ValueError('device_response_too_large')
                return response.status,raw
        except HTTPError as error:
            if path in ('/on','/off') and error.code in (301,302,303):return error.code,b''
            raise
    def status(self):
        status,raw=self.transport('/quick/status')
        if status!=200:raise ValueError('device_status_http_'+str(status))
        data=json.loads(raw)
        if type(data.get('systemOn')) is not bool:raise ValueError('device_status_schema_mismatch')
        return {'status':'done','device':self.public(),'on':data['systemOn'],'timer_active':bool(data.get('active')),'reply':'Status API lampu kamar: '+('menyala.' if data['systemOn'] else 'mati.'),'verified':'device_api'}
    def run(self,args,user_text,authorized=lambda:True):
        action=args['action']
        if action=='list':return {'status':'done','devices':[self.public()],'reply':'Lampu kamar terdaftar; periksa status untuk menguji koneksi.'}
        if action=='status':return self.status()
        if action not in ('on','off'):raise ValueError('invalid_iot_action')
        # Capability questions and instructions found in source files are not switch commands.
        subject=r'\b(?:lampu|light)\b'
        verb=r'\b(?:nyalakan|hidupkan|nyalain|hidupin|turn on)\b' if action=='on' else r'\b(?:matikan|padamkan|matiin|turn off)\b'
        if not re.search(subject,user_text,re.I) or not re.search(verb,user_text,re.I):
            return {'status':'needs_input','reply':'Koneksi bisa diperiksa sekarang. Sebutkan “nyalakan lampu kamar” atau “matikan lampu kamar” untuk mengubahnya.'}
        if re.search(r'\b(?:jangan|tidak usah|tanpa|don.t)\b',user_text,re.I):return {'status':'needs_input','reply':'Tidak mengubah lampu karena arahan mengandung larangan/negasi.'}
        before=self.status();desired=action=='on'
        if before['on']==desired:return {**before,'changed':False,'reply':'Lampu sudah '+('menyala.' if desired else 'mati.')+' Tidak mengirim perubahan ulang.'}
        if not authorized():return {'status':'cancelled','reply':'Perubahan lampu dibatalkan.'}
        code,_=self.transport('/on' if desired else '/off')
        if code not in (200,301,302,303):raise ValueError('device_write_http_'+str(code))
        after=self.status()
        return {**after,'status':'done' if after['on']==desired else 'unverified','changed':True,'reply':('API mengonfirmasi lampu '+('menyala.' if desired else 'mati.')) if after['on']==desired else 'Perintah dikirim, tetapi status API belum cocok.'}
