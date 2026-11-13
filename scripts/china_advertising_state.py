"""Retry only idempotent report-state traffic; never Telegram or marketplace writes."""
import time
import requests
from china_price_apply import IO

class AdvertisingIO(IO):
    def _completion(self,key,p):
        if isinstance(p,dict) and p.get('completion_notice'):
            from china_execution_notice import deliver_registered
            deliver_registered(self,key,p)

    def create(self,key,p):
        created=super().create(key,p)
        if created:self._completion(key,p)
        return created

    def put(self,key,p):
        from urllib.parse import quote
        from datetime import datetime,timezone
        self.db('telegram_api_cache?cache_key=eq.'+quote(key,safe=''),'PATCH',dict(payload=p,updated_at=datetime.now(timezone.utc).isoformat()),'return=minimal')
        if self.get(key)!=p:raise RuntimeError('State readback mismatch')
        self._completion(key,p)

    def db(self,path,method="GET",body=None,prefer=None):
        safe=method in ('GET','PATCH') and path.startswith('telegram_api_cache?')
        for attempt in range(3):
            try:
                return super().db(path,method,body,prefer)
            except (requests.Timeout,requests.ConnectionError,RuntimeError) as error:
                transient=isinstance(error,(requests.Timeout,requests.ConnectionError)) or str(error) in {
                    "State HTTP 429","State HTTP 500","State HTTP 502","State HTTP 503","State HTTP 504"}
                if not safe or not transient or attempt==2:
                    raise
                time.sleep((2,5)[attempt])

