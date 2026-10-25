"""Public internet read tools with bounded bodies, timeouts and redirect checks."""
import ipaddress
import json
import re
import socket
import urllib.request
from urllib.parse import urlparse,urlencode
import xml.etree.ElementTree as ET


def public_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('invalid_public_url')
    if parsed.port not in (None,80,443):raise ValueError('invalid_public_port')
    addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):raise ValueError('non_public_url')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,limit=1500000):
    public_url(url)
    request=urllib.request.Request(url,headers={'User-Agent':'LevaPersonalAssistant/0.12 (public page reader)'})
    with urllib.request.build_opener(Redirect()).open(request,timeout=4) as response:
        body=response.read(limit+1)
        if len(body)>limit:raise ValueError('web_response_too_large')
        return body,response.geturl()

def search(query):
    from ddgs import DDGS
    rows=DDGS(timeout=12).text(query,max_results=6)
    results=[]
    for row in rows:
        url=row.get('href') or row.get('url','')
        if urlparse(url).scheme in ('http','https'):results.append({'title':row.get('title',''),'url':url,'snippet':row.get('body','')[:600]})
    return {'status':'done','reply':'Hasil pencarian tersedia. Nilai relevansi dari judul dan isi, lalu baca beberapa sumber sebelum menyimpulkan.','sources':results,'untrusted_data':True}

def read(url):
    import trafilatura
    body,final=fetch(url)
    article=trafilatura.extract(body,include_comments=False,include_tables=True) or ''
    if not article:return {'status':'unverified','reply':'Halaman dapat diakses, tetapi isi artikel belum terbaca. Situs mungkin memerlukan login atau JavaScript.','url':final}
    return {'status':'done','reply':'Isi halaman dibaca untuk dianalisis; kutip sumber URL saat menjawab.','url':final,'content':article[:6500],'truncated':len(article)>6500,'untrusted_data':True}

def weather(city):
    if not city.strip():return {'status':'needs_input','reply':'Kota mana yang ingin digunakan untuk cuaca?'}
    raw,_=fetch('https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':city,'count':3,'language':'id','format':'json'}))
    candidates=json.loads(raw).get('results',[])
    if not candidates:return {'status':'needs_input','reply':'Nama kota belum ditemukan. Sebutkan kota dan negara.'}
    location=candidates[0]
    raw,_=fetch('https://api.open-meteo.com/v1/forecast?'+urlencode({'latitude':location['latitude'],'longitude':location['longitude'],'current':'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m','timezone':'auto'}))
    data=json.loads(raw)
    return {'status':'done','reply':'Cuaca terbaru dari Open-Meteo tersedia.','location':{k:location.get(k) for k in ('name','country','admin1')},'current':data['current'],'units':data['current_units'],'source':'https://open-meteo.com/','untrusted_data':True}

def news():
    url='https://feeds.bbci.co.uk/news/world/rss.xml';raw,_=fetch(url)
    rows=[]
    for item in ET.fromstring(raw).findall('./channel/item')[:6]:
        rows.append({'title':item.findtext('title'),'url':item.findtext('link'),'published':item.findtext('pubDate')})
    return {'status':'done','reply':'Headline BBC News; tanggal publikasi terlampir.','sources':rows,'source':url,'untrusted_data':True}

def weather_coordinates(latitude,longitude,accuracy):
    latitude=float(latitude);longitude=float(longitude)
    if not -90<=latitude<=90 or not -180<=longitude<=180:raise ValueError('invalid_coordinates')
    raw,_=fetch('https://api.open-meteo.com/v1/forecast?'+urlencode({'latitude':round(latitude,3),'longitude':round(longitude,3),'current':'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m','timezone':'auto'}))
    data=json.loads(raw)
    return {'status':'done','reply':'Cuaca berdasarkan lokasi perangkat Windows; koordinat dibulatkan untuk permintaan Open-Meteo.','location_source':'Windows Geolocator','accuracy_m':accuracy,'current':data['current'],'units':data['current_units'],'source':'https://open-meteo.com/','untrusted_data':True}
