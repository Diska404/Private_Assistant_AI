"""Authenticated, expiring UI presence; user-agent is a display label, never authority."""
import time


class WebPresence:
    def __init__(self,clock=time.monotonic,ttl=25):self.clock=clock;self.ttl=ttl;self.rows={}
    def touch(self,session,ua,remote):
        if not remote:return
        kind='android' if 'Android' in ua else 'ios' if 'iPhone' in ua or 'iPad' in ua else 'web'
        self.rows[session['id']]={'kind':kind,'name':session['name'][:40],'seen':self.clock()}
    def active(self,is_active=lambda owner:True):
        now=self.clock()
        for key in list(self.rows):
            if now-self.rows[key]['seen']>self.ttl or not is_active(key):del self.rows[key]
        return [{'kind':v['kind'],'name':v['name']} for v in self.rows.values()]
    @staticmethod
    def client(session,ua,remote):
        return {'kind':('android' if 'Android' in ua else 'ios' if 'iPhone' in ua or 'iPad' in ua else 'web') if remote else 'desktop_web','name':session['name'][:40],'executor':'laptop Windows','microphone':'push_to_talk_draft'}
