import copy,unittest
from moysklad_warehouses import BASE,STORE_IDS,select_store,exact_store_entry
def row(role,name):
 identity=STORE_IDS[role]
 return dict(id=identity,name=name,archived=False,meta=dict(href=BASE+'/entity/store/'+identity))
class WarehouseIdentityTests(unittest.TestCase):
 def test_both_renamed_warehouses_keep_identity(self):
  rows=[row('msk','Arbitrary Moscow'),row('guangzhou','Arbitrary China')]
  for role in STORE_IDS:self.assertEqual(select_store(rows,role)['id'],STORE_IDS[role])
 def test_name_cannot_select_foreign_warehouse(self):
  fake=row('guangzhou','МСК')
  with self.assertRaises(ValueError):select_store([fake],'msk')
 def test_missing_duplicate_archived_and_href_mismatch_fail(self):
  good=row('msk','МСК')
  cases=[[],[good,good],[dict(good,archived=True)],[dict(good,meta=dict(href=BASE+'/entity/store/'+STORE_IDS['guangzhou']))]]
  for rows in cases:
   with self.subTest(rows=rows),self.assertRaises(ValueError):select_store(rows)
 def test_stock_entry_uses_identity_even_if_name_is_stale(self):
  store=row('msk','New name');entry=row('msk','Old name')
  self.assertTrue(exact_store_entry(entry,store))
  self.assertFalse(exact_store_entry(row('guangzhou','New name'),store))
 def test_no_unknown_role_fallback(self):
  with self.assertRaises(ValueError):select_store([row('msk','МСК')],'unknown')
if __name__=='__main__':unittest.main()
