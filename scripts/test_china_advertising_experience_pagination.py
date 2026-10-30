import unittest
from china_advertising_v2 import read_price_experience
class Pages(unittest.TestCase):
 def test_loads_beyond_300_and_orders_pages(self):
  class IO:
   def __init__(self):self.paths=[]
   def db(self,path):
    self.paths.append(path)
    return [dict(action=dict(kind='price_change'),started_at='2026-10-30T01:00:00Z')]* (300 if 'offset=0' in path else 1)
  io=IO();self.assertEqual(len(read_price_experience(io)),301)
  self.assertIn('order=cache_key.asc',io.paths[0]);self.assertIn('offset=300',io.paths[1])
 def test_exact_page_requires_final_empty_page(self):
  class IO:
   def db(self,path):return [{}]*300 if 'offset=0' in path else []
  self.assertEqual(len(read_price_experience(IO())),300)
 def test_fail_closed_at_bound(self):
  class IO:
   def db(self,path):return [{}]*2
  with self.assertRaises(ValueError):read_price_experience(IO(),page_size=2,max_pages=2)
