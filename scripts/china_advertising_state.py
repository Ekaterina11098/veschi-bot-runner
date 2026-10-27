"""Retry only idempotent report-state traffic; never Telegram or marketplace writes."""
import time
import requests
from china_price_apply import IO

class AdvertisingIO(IO):
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

