"""Exact per-product placement minimum through an existing, verified campaign membership."""
import time
class MinimumMembershipUnavailable(ValueError):
 """A checked structural blocker, not a transient API failure or a zero bid."""
 pass
def read_quote(io,inputs,item):
 from china_advertising_v2 import http
 nm=item['nm_id'];target=item['campaign_id']
 valid=[c for c in inputs['campaigns']if c['status']in[9,11]and c['currency']=='CNY'and c['settings']['payment_type']=='cpc'and any(n['nm_id']==nm and n['subject']['id']==item['subject_id']for n in c['nm_settings'])]
 if not valid:raise MinimumMembershipUnavailable('No verified membership context for exact per-product minimum')
 context=next((c for c in valid if c['id']==target),min(valid,key=lambda c:c['id']))
 typ='search'if item['placement']=='search'else'recommendation'
 time.sleep(1.6)
 q=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=context['id'],nm_ids=[nm],payment_type='cpc',placement_types=[typ]))
 values=[b['value']for row in q.get('bids',[])if row['nm_id']==nm for b in row['bids']if b['type']==typ and b['currency']=='CNY']
 if len(values)!=1 or type(values[0])is not int or values[0]<=0:raise ValueError('Exact per-product placement minimum missing')
 return dict(q,quote_campaign_id=context['id'],quote_basis='exact_product_payment_placement_existing_membership_v1')
