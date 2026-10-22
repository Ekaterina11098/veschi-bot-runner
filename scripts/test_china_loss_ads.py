import copy,unittest
from unittest.mock import patch
from china_loss_ads import operation,check,execute,results
from china_loss_control import digest
class Memory:
 def __init__(self):self.data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def validate_owner(self,a):pass
def c(ids):return dict(status=9,currency='CNY',settings=dict(payment_type='cpc',placements=dict(search=False,recommendations=True)),nm_settings=[dict(nm_id=i,bids_kopecks=dict(search=0,recommendations=28)) for i in ids])
class Tests(unittest.TestCase):
 def test_only_selected_sku_removed_other_campaign_untouched(self):
  p=dict(items=[dict(kind='ad_exclude_sku',campaign_id=10,nm_id=1)]);b={10:c([1,2,3]),119:c([119])};body=operation(p,b)
  self.assertEqual(body,{'nms':[{'advert_id':10,'nms':{'add':[],'delete':[1]}}]})
  a={10:c([2,3]),119:c([119])};self.assertTrue(check(p,b,a));a[10]['nm_settings'][0]['bids_kopecks']['recommendations']=30;self.assertFalse(check(p,b,a))
 def test_cannot_empty_campaign(self):
  with self.assertRaises(ValueError):operation(dict(items=[dict(kind='ad_exclude_sku',campaign_id=10,nm_id=1)]),{10:c([1])})
 def test_repeated_approvals_single_write(self):
  io=Memory();p=dict(plan_id='same',items=[dict(kind='ad_exclude_sku',campaign_id=10,nm_id=1)]);p['plan_sha256']=digest(p['items']);a=dict(job_id=67,plan_sha256=p['plan_sha256']);b={10:c([1,2])};after={10:c([2])}
  with patch('china_loss_ads.current',side_effect=[b,after]),patch('china_loss_ads.http',return_value={}) as h:
   first=execute(io,a,p);a['job_id']=68;second=execute(io,a,p);self.assertEqual(h.call_count,1);self.assertEqual(first['status'],'verified');self.assertEqual(first,second)
 def test_timeout_not_retried(self):
  io=Memory();p=dict(plan_id='same',items=[dict(kind='ad_exclude_sku',campaign_id=10,nm_id=1)]);p['plan_sha256']=digest(p['items']);a=dict(job_id=67,plan_sha256=p['plan_sha256'])
  with patch('china_loss_ads.current',return_value={10:c([1,2])}),patch('china_loss_ads.http',side_effect=TimeoutError) as h:
   first=execute(io,a,p);execute(io,a,p);self.assertEqual(h.call_count,1);self.assertEqual(first['status'],'uncertain')
 def test_unselected_sku_disappearance_fails_readback(self):
  p=dict(items=[dict(kind='ad_exclude_sku',campaign_id=10,nm_id=1)]);self.assertFalse(check(p,{10:c([1,2,3])},{10:c([3])}))
if __name__=='__main__':unittest.main()
