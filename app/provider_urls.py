"""Gateway URL validation independent from inference engine imports."""
import urllib.parse


def base_url(value):
    p=urllib.parse.urlsplit(value)
    try:port=p.port
    except ValueError:raise ValueError('router_invalid_url') from None
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost','::1') or p.username or p.password or p.query or p.fragment or p.path.rstrip('/') not in ('','/v1') or port is not None and not 1<=port<=65535:
        raise ValueError('router_requires_loopback_url')
    return urllib.parse.urlunsplit((p.scheme,p.netloc,'/v1','',''))
