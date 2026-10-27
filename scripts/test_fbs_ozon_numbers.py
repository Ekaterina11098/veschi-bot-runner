import unittest
from unittest.mock import patch
import fbs_document_chain as m
import fbs_ozon_chain as oz
class OzonNumberTests(unittest.TestCase):
 def worker(self):
  return oz.OzonWorker(None,None,{"document_prefix":"fbs-ozon"},{"id":11,"departure_date":"2026-10-20"},{"included":["posting-a"]})
 def run_case(self,base,unique=None):
  w=self.worker()
  def rows(path,params):
   return base if params["filter"]=="name=201026 Озон" else (unique or [])
  state={"supply":{"id":"OZON-ACT-11"}}
  with patch.object(w,"ms_rows",side_effect=rows),patch.object(m.Worker,"ensure",return_value={}) as parent:
   w.ensure("customerorder",{},state,"key")
   return parent.call_args.args[1]["name"]
 def test_first_act_keeps_date_name(self):
  self.assertEqual(self.run_case([]),"201026 Озон")
 def test_second_act_has_stable_act_suffix(self):
  existing=[{"name":"201026 Озон","externalCode":"fbs-ozon:OZON-ACT-10:customerorder","description":"posting-b"}]
  self.assertEqual(self.run_case(existing),"201026 Озон 11")
  self.assertEqual(self.run_case(existing),"201026 Озон 11")
 def test_existing_own_base_keeps_its_number(self):
  self.assertEqual(self.run_case([{"externalCode":"fbs-ozon:OZON-ACT-11:customerorder","description":"posting-a"}]),"201026 Озон")
 def test_manual_same_postings_are_not_duplicated(self):
  with self.assertRaises(m.Stop):self.run_case([{"externalCode":"manual","description":"posting-a"}])
 def test_manual_suffix_collision_stops(self):
  with self.assertRaises(m.Stop):self.run_case([{"externalCode":"other","description":"posting-b"}],[{"externalCode":"manual"}])
if __name__=="__main__":unittest.main()
