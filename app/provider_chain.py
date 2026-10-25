"""Per-request provider failover; host receipts remain outside this routing layer."""
from hybrid_engine import EngineError,OnlineUnavailable


class InferenceRoute:
    def __init__(self,request):
        mode=request.get('mode','hybrid')
        self.providers={'local':['local'],'router':['9router','local'],
                        'cascade':['google','9router','local']}.get(mode,['google','local'])
        self.index=0;self.failures=[]
        self.google_paused=bool(request.get('online_paused'))
        if self.google_paused and self.providers[0]=='google':
            self.failures.append({'provider':'google','reason':'quota_or_rate_limit'})
            self.index=1

    def call(self,google,router,local):
        callbacks={'google':google,'9router':router,'local':local}
        while True:
            provider=self.providers[self.index]
            if provider=='local':return local(),provider
            try:return callbacks[provider](),provider
            except EngineError as error:
                if isinstance(error,OnlineUnavailable):reason=error.reason
                elif str(error)=='online_transport_failure' or str(error) in ('online_http_408','online_http_500','online_http_502','online_http_503','online_http_504'):
                    reason=str(error)
                else:raise
                self.failures.append({'provider':provider,'reason':reason})
                if provider=='google' and reason=='quota_or_rate_limit':self.google_paused=True
                self.index+=1

    def metadata(self):
        return {'fallback_reason':self.failures[-1]['reason'] if self.failures else None,
                'provider_failures':list(self.failures),'google_paused':self.google_paused}
