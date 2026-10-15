"""Whitelisted WB rate diagnostics for an already-authorized request. Makes no requests."""
from urllib.parse import urlsplit
import os,re
HEADERS=('x-ratelimit-retry','x-ratelimit-reset','x-ratelimit-limit','x-ratelimit-remaining','retry-after')
def summarize(response,method,path,secret_values=()):
    result={'method':method.upper(),'path':path,'status':int(response.status_code),'headers':{}}
    for name,value in response.headers.items():
        if name.lower() in HEADERS:
            # Headers are numeric/date metadata, never Authorization/cookies.
            text=str(value)
            if re.fullmatch(r'[0-9A-Za-z,: .+/-]{1,120}',text):result['headers'][name.lower()]=text
    if response.status_code==429:
        try:body=response.json()
        except Exception:body={}
        if isinstance(body,dict):
            result['error']={}
            for key in ('title','detail','code','status'):
                if isinstance(body.get(key),(str,int,float)):
                    value=str(body[key])[:1500]
                    for secret in secret_values:
                        if secret:value=value.replace(secret,'[REDACTED]')
                    result['error'][key]=value
    return result
def install(report,target_id):
    import requests
    original=requests.sessions.Session.request
    secrets=tuple(v for k,v in os.environ.items() if k.startswith('WB_') and v)
    def observed(session,method,url,*args,**kwargs):
        response=original(session,method,url,*args,**kwargs)
        parsed=urlsplit(url)
        exact=(parsed.hostname=='feedbacks-api.wildberries.ru' and (
            (method.upper()=='POST' and parsed.path=='/api/v1/feedbacks/answer' and (kwargs.get('json') or {}).get('id')==target_id)
            or (method.upper()=='GET' and parsed.path=='/api/v1/feedback' and (kwargs.get('params') or {}).get('id')==target_id)))
        if exact:
            try:
                summary=summarize(response,method,parsed.path,secrets)
                if target_id=='FCFR5A3pNgvsDFnWShPZ' and method.upper()=='GET' and response.status_code==200:
                    body=response.json()
                    data=body.get('data') if isinstance(body,dict) else None
                    answer=data.get('answer') if isinstance(data,dict) else None
                    summary['shape']={'body_type':type(body).__name__,'error_true':isinstance(body,dict) and body.get('error') is True,'data_type':type(data).__name__,'id_matches':isinstance(data,dict) and str(data.get('id',''))==target_id,'answer_type':type(answer).__name__,'answer_text_present':isinstance(answer,dict) and isinstance(answer.get('text'),str),'answer_text_nonempty':isinstance(answer,dict) and isinstance(answer.get('text'),str) and bool(answer['text'].strip())}
                report.setdefault('http_rate_diagnostic',[]).append(summary)
            except Exception:report['diagnostic_capture_error']=True
        return response
    requests.sessions.Session.request=observed
    return lambda:setattr(requests.sessions.Session,'request',original)
