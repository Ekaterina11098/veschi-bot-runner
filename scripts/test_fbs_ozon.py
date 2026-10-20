import unittest
from unittest.mock import patch
import fbs_document_chain as m
import fbs_ozon_chain as oz
from test_fbs_chain import Cache,ref
from test_fbs_annotation import AnnotatedFake

class OzonTests(unittest.TestCase):
 def test_complete_chain_date_names_and_same_posting_comment(self):
  t=AnnotatedFake();db=Cache()
  common={"organization":ref("organization","org"),"agent":ref("counterparty","ozon"),"store":ref("store","msk")}
  c={"templates":{kind:dict(common) for kind in m.TYPES},"document_prefix":"fbs-ozon","order_annotation":{"state_name":"Возврат на ФБО"}}
  c["templates"]["salesreturn"]["store"]=ref("store","ozon")
  act={"id":5,"departure_date":"2026-10-20","created_at":"2026-10-20T08:00:00Z"}
  scope={"included":["a-1","b-1"],"all_numbers":["a-1","b-1"],"counts":{"p":3},"ready":True,"movement_at":"2026-10-20T10:00:00Z"}
  w=oz.OzonWorker(t,db,c,act,scope)
  state={"supply":oz.virtual_supply(act,scope),"positions":[{"assortment":ref("product","p"),"quantity":3,"price":0}],"order_ids":["a-1","b-1"]}
  with patch.object(oz,"snapshot",return_value=scope):
   w.process(state);w.process(state)
  self.assertEqual(t.docs["customerorder"][0]["name"],"201026")
  for kind in m.TYPES:self.assertEqual(t.docs[kind][0]["description"],"a-1, b-1")
  self.assertEqual(len(t.writes),4)
  self.assertEqual(state["status"],"complete")
 def snapshot(self,first_status="delivering",after_ship=False):
  products=[{"offer_id":"ART","quantity":1}]
  rows=[{"posting_number":"a","status":"success","products":products},{"posting_number":"b","status":"success","products":products}]
  def api(path,body):
   if path.endswith("get-postings"):return {"result":rows}
   n=body["posting_number"]
   return {"result":{"posting_number":n,"status":first_status if n=="a" else "cancelled","cancellation":{"cancelled_after_ship":after_ship if n=="b" else False},"products":products}}
  with patch.object(oz,"ozon",side_effect=api):return oz.snapshot({"id":1})
 def test_cancelled_before_shipping_excluded(self):
  s=self.snapshot();self.assertEqual(s["included"],["a"]);self.assertEqual(s["counts"],{"art":1});self.assertTrue(s["ready"])
 def test_cancelled_after_shipping_keeps_physical_goods(self):
  s=self.snapshot(after_ship=True);self.assertEqual(s["counts"],{"art":2});self.assertTrue(s["ready"])
 def test_awaiting_shipping_is_not_trigger(self):
  self.assertFalse(self.snapshot(first_status="awaiting_deliver")["ready"])

if __name__=="__main__":unittest.main()

