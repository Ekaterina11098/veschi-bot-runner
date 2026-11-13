"""Exact per-product placement minimum through an existing, verified campaign membership."""
import time,copy
from datetime import datetime,timezone
CATEGORY_BASIS='same_subject_cpc_placement_owner_verified_v1'

def category_context(inputs,item):
 typ='search'if item['placement']=='search'else'recommendations'
 choices=[]
 for cp in inputs['campaigns']:
  if cp.get('status')not in[9,11]or cp.get('currency')!='CNY'or cp.get('bid_type')!='manual'or cp['settings']['payment_type']!='cpc'or not cp['settings']['placements'].get(typ):continue
  for member in cp['nm_settings']:
   if member['subject']['id']==item['subject_id']:choices.append((cp['id']!=item['campaign_id'],cp['id'],member['nm_id']))
 if not choices:raise MinimumMembershipUnavailable('No current same-category CPC placement quote context')
 _,cid,nm=min(choices)
 return cid,nm
class MinimumMembershipUnavailable(ValueError):
 """A checked structural blocker, not a transient API failure or a zero bid."""
 pass
def read_quote(io,inputs,item):
 from china_advertising_v2 import http
 nm=item['nm_id'];target=item['campaign_id']
 valid=[c for c in inputs['campaigns']if c['status']in[9,11]and c['currency']=='CNY'and c['settings']['payment_type']=='cpc'and any(n['nm_id']==nm and n['subject']['id']==item['subject_id']for n in c['nm_settings'])]
 if not valid:
  cid,representative=category_context(inputs,item)
  typ='search'if item['placement']=='search'else'recommendation'
  cache=inputs.setdefault('category_minimum_quotes',{});key=str(item['subject_id'])+':CNY:cpc:'+typ
  saved=cache.get(key)or{};q=None
  try:
   age=(datetime.now(timezone.utc)-datetime.fromisoformat(saved['observed_at'])).total_seconds()
   context=next(c for c in inputs['campaigns']if c['id']==saved['quote_campaign_id'])
   if 0<=age<=900 and context['status']in[9,11]and context['currency']=='CNY'and context['settings']['payment_type']=='cpc'and context['settings']['placements'].get(item['placement'])and any(n['nm_id']==saved['quote_nm_id']and n['subject']['id']==item['subject_id']for n in context['nm_settings']):q=copy.deepcopy(saved)
  except (KeyError,ValueError,TypeError,StopIteration):pass
  if q is None:
   raw=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[representative],payment_type='cpc',placement_types=[typ]))
   values=[b['value']for row in raw.get('bids',[])if row['nm_id']==representative for b in row['bids']if b['type']==typ and b['currency']=='CNY']
   if len(values)!=1 or type(values[0])is not int or values[0]<=0:raise ValueError('Same-category placement minimum missing')
   q=dict(quote_campaign_id=cid,quote_nm_id=representative,quote_subject_id=item['subject_id'],quote_basis=CATEGORY_BASIS,minimum_minor=values[0],raw_quote=raw,observed_at=datetime.now(timezone.utc).isoformat());cache[key]=copy.deepcopy(q)
  # Normalized candidate quote retains explicit representative provenance; not a personal WB quote.
  q['bids']=[dict(nm_id=nm,bids=[dict(type=typ,value=q['minimum_minor'],currency='CNY')])]
  return q
 context=next((c for c in valid if c['id']==target),min(valid,key=lambda c:c['id']))
 typ='search'if item['placement']=='search'else'recommendation'
 time.sleep(1.6)
 q=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=context['id'],nm_ids=[nm],payment_type='cpc',placement_types=[typ]))
 values=[b['value']for row in q.get('bids',[])if row['nm_id']==nm for b in row['bids']if b['type']==typ and b['currency']=='CNY']
 if len(values)!=1 or type(values[0])is not int or values[0]<=0:raise ValueError('Exact per-product placement minimum missing')
 return dict(q,quote_campaign_id=context['id'],quote_basis='exact_product_payment_placement_existing_membership_v1')


