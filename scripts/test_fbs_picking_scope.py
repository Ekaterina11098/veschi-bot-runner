"""Picking scope must preserve physical handover despite later buyer refusal."""
import unittest
from fbs_document_chain import excluded_from_picking
class PickingScopeTests(unittest.TestCase):
 def test_handed_over_buyer_refusal_remains_in_shipment(self):
  self.assertFalse(excluded_from_picking({"supplierStatus":"complete","wbStatus":"canceled_by_client"}))
 def test_handed_over_status_not_reduced_by_later_cancellation(self):
  self.assertFalse(excluded_from_picking({"supplierStatus":"complete","wbStatus":"canceled"}))
 def test_delivered_or_sold_remains(self):
  for status in ("waiting","sorted","sold","ready_for_pickup"):
   with self.subTest(status=status):self.assertFalse(excluded_from_picking({"supplierStatus":"complete","wbStatus":status}))
 def test_seller_cancellation_before_handover_excluded(self):
  self.assertTrue(excluded_from_picking({"supplierStatus":"cancel","wbStatus":"canceled"}))
 def test_unshipped_cancelled_order_excluded(self):
  self.assertTrue(excluded_from_picking({"supplierStatus":"confirm","wbStatus":"canceled_by_client"}))
if __name__=="__main__":unittest.main()
