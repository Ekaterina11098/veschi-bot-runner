import unittest,copy
from china_advertising_v2 import history
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
if __name__=='__main__':unittest.main()
