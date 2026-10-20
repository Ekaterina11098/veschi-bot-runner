import unittest
import fbs_document_chain as m
from test_fbs_chain import Cache,ref
class Matching(unittest.TestCase):
 def check(self,duplicate=False,cancelled=False):
  products=[dict(article="595-NoelBag-zblack",variantsCount=0,trackingType="NOT_TRACKED",**ref("product","p"))]
  if duplicate:products.append(dict(products[0],**ref("product","other")))
  class T:
   def request(self,base,path,**kw):
    ids=list(range(1,222)) if cancelled else [1]
    if path.endswith("/order-ids"):return {"orderIds":ids}
    if path=="api/v3/orders/status":return {"orders":[{"id":i,"supplierStatus":"complete","wbStatus":"canceled_by_client" if cancelled and i==1 else "waiting"} for i in kw["body"]["orders"]]}
    if path=="api/v3/orders":return {"orders":[{"id":i,"article":"595-Noelbag-zblack"} for i in ids],"next":0}
    return {"rows":products,"meta":{"size":len(products)}}
  return m.Worker(T(),Cache(),{}).positions({"id":"WB-GI-1","closedAt":"2026-10-20T00:00:00Z"})
 def test_case_only_unique(self):
  positions,ids=self.check();self.assertEqual(positions[0]["quantity"],1);self.assertEqual(ids,[1])
 def test_duplicate_blocks(self):
  with self.assertRaises(m.Stop):self.check(True)
 def test_221_raw_with_one_cancelled_is_220_picked(self):
  positions,raw_ids=self.check(cancelled=True)
  self.assertEqual(len(raw_ids),221)
  self.assertEqual(sum(p["quantity"] for p in positions),220)
if __name__=="__main__":unittest.main()

