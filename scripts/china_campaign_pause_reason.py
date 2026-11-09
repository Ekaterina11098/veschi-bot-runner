"""Pause provenance from verified commands and dated state transitions, never balance alone."""
from datetime import datetime

def at(v):
 try:return datetime.fromisoformat(v.replace('Z','+00:00'))
 except (ValueError,TypeError,AttributeError):return None

def attach_previous(cache,source):
 """Read one exact private snapshot pointer; never call WB or mutate the source."""
 import copy
 s=copy.deepcopy(source);pointer=cache.get('china_agent:hourly_sales_api:v1:latest')or{}
 s['budget_pause_transitions']=(cache.get('china_agent:campaign_pause_transitions:v1')or{}).get('campaigns',{})
 key=pointer.get('source_key');previous=cache.get(key)if key else None
 if not previous or previous.get('cabinet')!='token_3':return s
 before=at(previous.get('completed_at')or previous.get('observed_at'));now=at(s.get('observed_at'))
 if not before or not now or not 0<(now-before).total_seconds()<=80*60:return s
 balances={str(r['advertId']):r.get('total')for r in previous.get('budgets',{}).get('rows',[])if r.get('currency')=='CNY'}
 s['budget_previous_states']={str(cid):dict(status=c.get('status'),balance=balances.get(str(cid)),source_key=key,observed_at=before.isoformat(),current_observed_at=s['observed_at'])for cid,c in previous.get('advertising',{}).get('campaigns',{}).items()}
 s['budget_previous_causes']={cid:r['pause_reason']for cid,r in previous.get('budget_audit',{}).get('campaigns',{}).items()if r.get('pause_reason')}
 return s

def classify(state,balance,records=(),previous=None,previous_audit=None,transition=None):
 if state.get('status')!=11:return dict(cause='not_paused',confidence='observed')
 cid=state['id'];started=at(state.get('timestamps',{}).get('started'));commands=[]
 previous=previous or{}
 active_seen=at(previous.get('observed_at'))if previous.get('status')==9 else None
 def walk(x,root,key):
  if not isinstance(x,dict):return
  after=x.get('after');when=x.get('verified_at')or root.get('verified_at')or root.get('completed_at')
  action=x.get('action')or{};request=x.get('request')or{}
  path=x.get('path')or request.get('path')or''
  is_pause=action.get('kind')=='pause_campaign' or x.get('kind')=='pause_campaign' or path in('/adv/v0/pause?id='+str(cid),'/adv/v0/pause')
  owner=(x.get('owner_id')or root.get('owner_id'))==5122667182 or bool(x.get('approval_key')or root.get('approval_key'))
  t=at(when)
  if x.get('status')=='verified'and isinstance(after,dict)and after.get('id')==cid and after.get('status')==11 and is_pause and owner and t and(not started or t>=started)and(not active_seen or t>active_seen):commands.append((t,key,when))
  for k in('items','groups','campaigns'):
   xs=x.get(k,[])
   for child in xs.values()if isinstance(xs,dict)else xs if isinstance(xs,list)else[]:walk(child,root,key)
 for r in records:
  x=r.get('payload',r);walk(x,x,r.get('cache_key'))
 if commands:
  _,key,when=max(commands)
  return dict(cause='owner_paused',confidence='verified_command',receipt_key=key,observed_at=when)
 transition=transition or{}
 if balance==0 and transition.get('state_started_at')==state.get('timestamps',{}).get('started') and transition.get('before_status')==9 and transition.get('after_status')==11 and transition.get('after_balance')==0 and transition.get('source_keys') and at(transition.get('observed_at'))and(not active_seen or at(transition['observed_at'])>active_seen):
  return dict(transition,cause='budget_exhaustion_observed',confidence='probable')
 previous=previous or{};old=previous_audit or{}
 if previous.get('status')==11 and old.get('cause')in('owner_paused','budget_exhaustion_observed'):
  return dict(old)
 if balance==0 and previous.get('status')==9 and previous.get('balance')is not None:
  return dict(cause='budget_exhaustion_observed',confidence='probable',observed_at=previous.get('current_observed_at'),before_source=previous.get('source_key'),before_status=9,before_balance=previous['balance'],after_balance=0,limitation='Пауза последовала за исчерпанием бюджета; отдельная ручная команда не подтверждена, причина WB напрямую не указана.')
 return dict(cause='unknown',confidence='unknown',reason='Нет подтверждённой команды паузы или сохранённого перехода состояния; нулевой баланс сам по себе не доказывает причину.')
