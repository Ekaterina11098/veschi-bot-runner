import unittest,copy
from china_advertising_v2 import history,collect,compact_execution_records
class VerifiedPriceHistoryTests(unittest.TestCase):
 def receipt(self,status='done'):
  return {'status':status,'completed_at':'2026-10-28T18:31:00+00:00','items':[{
   'status':'applied','selection':{'nm_id':'123','current_cny':'100.1','target_cny':'105.16','seller_discount':56},
   'request':{'nmID':123,'price':239,'discount':56},
   'readback':{'nmID':123,'discount':56,'currencyIsoCode4217':'CNY','sizes':[{'price':239,'discountedPrice':105.16}]}}]}
 def test_exact_price_receipt_excludes_change_day(self):
  h=history([self.receipt()]);self.assertEqual([(r['nm'],r['kind'],r['at']) for r in h],[(123,'price','2026-10-28T18:31:00+00:00')])
 def test_partial_batch_preserves_verified_item(self):
  self.assertEqual(len(history([self.receipt('partial')])),1)
 def test_verified_price_after_seller_discount_change_is_still_an_event(self):
  r=self.receipt();i=r['items'][0];i['selection']['seller_discount']=60;self.assertEqual(len(history([r])),1)
 def test_uncertain_never_becomes_verified(self):
  self.assertEqual(history([self.receipt('uncertain')]),[])
 def test_mismatched_readback_not_history(self):
  for field,value in [('discount',55),('nmID',999),('currencyIsoCode4217','RUB')]:
   r=self.receipt();r['items'][0]['readback'][field]=value;self.assertEqual(history([r]),[])
 def test_missing_or_different_target_not_proof(self):
  r=self.receipt();r['items'][0]['selection']['target_cny']='106';self.assertEqual(history([r]),[])
  r=self.receipt();r['items'][0].pop('request');self.assertEqual(history([r]),[])
class ReceiptCompactionTests(unittest.TestCase):
 def test_price_history_and_identity_preserved_without_raw_journals(self):
  import json
  receipt=VerifiedPriceHistoryTests().receipt('partial');receipt.update(original_jobs='x'*1000000,baseline_fullstats={'unused':'y'*100000})
  full=[{'cache_key':'fixture:canonical:execution','payload':receipt}];small=compact_execution_records(full)
  self.assertEqual(history(full),history(small));self.assertEqual(small[0]['cache_key'],full[0]['cache_key'])
  self.assertLess(len(json.dumps(small)),2000);self.assertIn('original_jobs',full[0]['payload'])
 def test_campaign_diffs_and_verified_funding_steps_unchanged(self):
  receipt={'status':'verified','verified_at':'2026-10-28T12:00:00Z','before':{'id':1,'nm_settings':[{'nm_id':123}]},'after':{'id':1,'nm_settings':[]},
   'steps':{'funding':{'status':'verified','path':'/adv/v1/budget/deposit?id=1','body':{'sum':100},'submitted_at':'2026-10-28T12:00:00Z'}},'baseline_fullstats':{'unused':'x'}}
  small=compact_execution_records([{'payload':receipt}]);self.assertEqual(history([receipt]),history(small));self.assertEqual(small[0]['payload']['steps'],receipt['steps'])
 def test_unanchored_legacy_records_are_not_pruned(self):
  receipt={'legacy':{'original_jobs':{'status':'unknown'}},'scalar':'keep'}
  self.assertEqual(compact_execution_records([receipt]),[receipt])

class DailySourceSizeTests(unittest.TestCase):
 def test_only_fields_consumed_from_experience_are_persisted(self):
  import json
  source={'status':'collecting','ids':[1],'batches':{'0':{'campaigns':{},'budgets':{},'stats':[]}},'config':{'currency':'CNY'},'executions':[]}
  projected={'action':{'kind':'price_change','nm_ids':[123],'before':100,'after':110},'started_at':'2026-10-28T09:00:00Z'}
  class Fake:
   def __init__(self):self.saved=copy.deepcopy(source)
   def get(self,key):
    if key=='china_agent:advertising_format:v2':return {'status':'approved','version':'grouped_campaigns_v2'}
    if key=='china_agent:prices:v1':return {'cabinet':'token_3','rows':[]}
    if key.startswith('china_agent:advertising_source:'):return copy.deepcopy(self.saved)
    return None
   def put(self,key,value):self.saved=copy.deepcopy(value)
   def db(self,path):
    if 'select=payload' in path:return [{'payload':dict(projected,unrelated_evaluation='x'*2000000)}]
    return [copy.deepcopy(projected)]
  io=Fake();result=collect(io,'2026-10-29')
  self.assertEqual(result['status'],'complete');self.assertEqual(result['experience'],[projected])
  self.assertLess(len(json.dumps(io.saved)),10000)
if __name__=='__main__':unittest.main()

