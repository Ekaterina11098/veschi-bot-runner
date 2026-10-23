"""Bounded model errors: transient limits defer, billing failures never retry blindly."""
import os,re,math
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime

class ModelResponseError(RuntimeError):
 def __init__(self,status,details,retry_after=180):
  self.status=status;self.details=details;self.retry_after=retry_after
  code=details.get('code') or 'unknown'
  billing=any(x in str(code).lower() for x in ['quota','billing','spend','budget','credit'])
  self.retryable=status in [429,500,502,503,504] and not billing
  super().__init__('Model HTTP '+str(status)+' '+str(code))

def seconds(value,default=180):
 try:
  delay=float(value)
  if not math.isfinite(delay):raise ValueError()
 except (ValueError,TypeError):
  try:delay=(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()
  except (ValueError,TypeError,OverflowError):return default
 return max(60,math.ceil(delay))+3

def request(body):
 import requests
 r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json=body,timeout=150)
 if not r.ok:
  try:err=r.json().get('error') or {}
  except (ValueError,TypeError):err={}
  code=str(err.get('code') or '')[:100];code=code if re.fullmatch(r'[A-Za-z0-9_\-]*',code) else 'unclassified'
  # Messages and token counters stay in the private diagnostic, never public logs.
  details=dict(code=code,type=str(err.get('type') or '')[:100],message=str(err.get('message') or '')[:2000],headers={k:r.headers.get(k) for k in ['retry-after','x-ratelimit-limit-tokens','x-ratelimit-remaining-tokens','x-ratelimit-reset-tokens','x-ratelimit-limit-project-tokens','x-ratelimit-reset-project-tokens'] if r.headers.get(k)})
  raise ModelResponseError(r.status_code,details,seconds(r.headers.get('retry-after')))
 return r.json()
