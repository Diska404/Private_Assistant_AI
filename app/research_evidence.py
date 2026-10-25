"""Relevance-first, bounded public research. No desktop/browser execution."""
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import re
import time
from input_normalization import research_query

STOP={'leva','bisakah','saya','anda','coba','tolong','untuk','dengan','apa','yang','dari','saat','ini','versi','cerita','story','part','build','tim','team','guide','wiki','global','china','terbaru','informasi','sedang','event','gfl2','girls','frontline','exilium','sekarang','saatini','bisa','cari','tentang','current','latest','how','what','hari','adalah','memiliki'}
GAME=re.compile(r'gfl\s?2|girls.?\s*frontline\s*2|少女前线|iopwiki|exilium',re.I)

def query_plan(text):
    query=research_query(text)
    game=bool(GAME.search(query));cn=bool(re.search(r'\bcn\b|china|tiongkok',query,re.I))
    if game:query=re.sub(r'gfl\s?2',"Girls Frontline 2 Exilium",query,flags=re.I)
    plans=[query]
    if game:
        topic=re.sub(r'Girls Frontline 2 Exilium','',query,flags=re.I).strip()
        if cn:
            now=datetime.now(timezone(timedelta(hours=7)))
            plans.append(f'少女前线2 追放 {now.year}年{now.month}月 活动 剧情')
        plans.append('site:iopwiki.com '+topic+' Girls Frontline 2')
    return list(dict.fromkeys(plans))[:3]

def relevance(row,query):
    value=' '.join(str(row.get(k,'')) for k in ('title','url','snippet','content'))
    words=set(re.findall(r'\w{3,}',query.casefold()))-STOP
    words={w for w in words if w not in ('cari','internet','aphelionpart')}
    hits=sum(1 for word in words if re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',value,re.I))
    game=bool(GAME.search(query))
    if game and not GAME.search(value):return 0
    if game and re.search(r'\bcn\b',query,re.I) and not re.search(r'\bcn\b|china|chinese|少女前线|追放|国服',value,re.I):return 0
    if re.search(r'terbaru|saat ini|sekarang|latest',query,re.I):
        dates=[int(y) for y in re.findall(r'\b(20\d{2})\b',value)]
        if dates and max(dates)<datetime.now(timezone.utc).year-1:return 0
    anchors={w for w in words if len(w)>=4 and w not in ('apakah','bagaimana','terkini','latest','informasi','karakter')}
    if anchors and not any(re.search(re.escape(w),value,re.I) for w in anchors):return 0
    if not game and not hits:return 0
    return hits*3+(3 if game else 0)+(2 if 'iopwiki.com' in value or re.search(r'official|sunborn|haoplay',value,re.I) else 0)

def gather(text,bridge,authorized=lambda:True):
    urls=[u.rstrip('"\'.,)') for u in re.findall(r'https?://[^\s<>]+',text)][:2]
    report={'status':'insufficient','query':research_query(text),'queries':[],'sources':[],'pages':[],
            'rejected_count':0,'search_attempts':[],'access':'public_read_only','untrusted_data':True,
            'freshness':'Waktu pengambilan bukan tanggal publikasi. Snippet saja tidak membuktikan event/story terkini.',
            'retrieved_at':datetime.now(timezone.utc).isoformat()}
    candidates={};began=time.monotonic()
    if urls:
        candidates={u:{'url':u,'title':'URL pengguna','relevance':'user_url'} for u in urls}
    else:
        for query in query_plan(text):
            if not authorized():return {**report,'status':'cancelled'}
            if time.monotonic()-began>55:break
            result=bridge.run('web_search',{'query':query},authorized,timeout=20)
            report['queries'].append(query)
            report['search_attempts'].append({'query':query,'status':result.get('status','unverified'),'code':result.get('code',''),'detail':str(result.get('reply',''))[:180]})
            for row in result.get('sources',[])[:8]:
                score=relevance(row,report['query'])
                if not score:report['rejected_count']+=1;continue
                value={**row,'relevance':score}
                if value.get('url'):candidates[value['url']]=value
            if len(candidates)>=3:break
        candidates=dict(sorted(candidates.items(),key=lambda p:p[1].get('relevance',0),reverse=True)[:4])
    report['sources']=[{k:str(v)[:350] for k,v in r.items() if k in ('title','url','snippet','relevance')} for r in candidates.values()]
    for url,row in list(candidates.items())[:3]:
        if not authorized():return {**report,'status':'cancelled'}
        try:page=bridge.run('read_webpage',{'url':url},authorized,timeout=12)
        except Exception:page={'url':url,'status':'unverified'}
        if page.get('content') and (urls or relevance({**row,'content':page['content']},report['query'])):
            report['pages'].append({k:(v[:1800] if k=='content' else v) for k,v in page.items() if k in ('url','content','status','published','content_kind','truncated')})
    report['status']='pages_read' if any(p.get('content') for p in report['pages']) else 'snippets_only' if report['sources'] else 'insufficient'
    report['instruction']='Gunakan hanya sumber relevan yang benar-benar tersedia. Jangan rangkum hasil yang ditolak. Bila belum cukup, jelaskan kekurangan spesifik dan jangan mengarang build, plot atau tanggal. Halaman video bukan transkrip dan tidak berarti video sudah ditonton.'
    return report
