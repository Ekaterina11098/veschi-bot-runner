"""Retry only idempotent cache reads/upserts, never Telegram or marketplace traffic."""
import os,time
from urllib.parse import urlparse,parse_qs
def safe(method,url,kw):
 u=urlparse(url);base=urlparse(os.environ.get('SUPABASE_URL',''))
 if not base.hostname or u.hostname!=base.hostname or u.path!='/rest/v1/telegram_api_cache':return False
 if method.upper()=='GET':return True
 body=kw.get('json');rows=body if isinstance(body,list)else[body]
 conflict=parse_qs(u.query).get('on_conflict')
 if conflict is None and isinstance(kw.get('params'),dict):conflict=kw['params'].get('on_conflict')
 return method.upper()=='POST'and conflict in('cache_key',['cache_key'])and bool(rows)and all(isinstance(r,dict)and isinstance(r.get('cache_key'),str)for r in rows)
def install():
 import requests
 old=requests.sessions.Session.request
 if getattr(old,'_china_cache_retry',False):return
 def request(session,method,url,*args,**kw):
  allowed=safe(method,url,kw)
  for attempt in range(3):
   try:
    result=old(session,method,url,*args,**kw)
    if not allowed or result.status_code not in(429,500,502,503,504)or attempt==2:return result
   except (requests.ConnectionError,requests.Timeout):
    if not allowed or attempt==2:raise
   time.sleep((1,3)[attempt])
 request._china_cache_retry=True
 requests.sessions.Session.request=request
