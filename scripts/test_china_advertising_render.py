import tempfile,unittest
from pathlib import Path
from china_advertising_normalize import normalize
from china_advertising_png import render
from test_china_advertising_normalize import fixture
class RenderTests(unittest.TestCase):
 def test_dynamic_dates_and_unknown_budget_pair_renders(self):
  p=fixture();p['observations'][3]['data']['budget']=None
  b=normalize(p,'2026-10-20',{'3':'Товар-длинное-название'})
  with tempfile.TemporaryDirectory() as out:
   paths=render(b,out)
   from PIL import Image
   self.assertEqual([x.name for x in paths],['drr.png','budgets.png'])
   for path in paths:
    with Image.open(path) as im:
     self.assertEqual(im.width,1400);self.assertGreater(im.height,500)
     self.assertLess(im.width+im.height,10000)
if __name__=='__main__':unittest.main()
