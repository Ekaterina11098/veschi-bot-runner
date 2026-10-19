import json,tempfile,unittest,ast
from pathlib import Path
from PIL import Image
from advertising_daily_png import render_daily_png
class DailyPng(unittest.TestCase):
 def view(self):
  return dict(period='2026-10-19',observed_day='2026-10-20',campaigns=[
   dict(campaign_id=37363108,metrics_complete=True,spend=1100,revenue=11840,direct_orders=0,sku_order_basis='direct_only',above5=[],budget=dict(balance=8807,observed_at='2026-10-20T04:45:00Z',today_observation=True,valid=True)),
   dict(campaign_id=39410834,metrics_complete=True,spend=15101,revenue=227432,sku_order_basis='direct_only',above5=[dict(article='534-NoelBag-emerald',drr=11.51)],within5_count=9,budget={}),
   dict(campaign_id=40428505,metrics_complete=True,spend=761,revenue=0,direct_orders=0,sku_order_basis='direct_only',status_id=11,budget=dict(balance=27816,observed_at='2026-10-19T05:21:00Z',today_observation=False,valid=True))])
 def test_two_png_in_order(self):
  with tempfile.TemporaryDirectory() as d:
   images=render_daily_png(self.view(),d)
   self.assertEqual([x['kind'] for x in images],['drr','budgets'])
   for image in images:
    with Image.open(image['path']) as im:
     self.assertEqual(im.format,'PNG');self.assertEqual(im.width,1200);self.assertGreater(im.height,300);self.assertLess(im.height,3000)
 def test_missing_and_zero_are_renderable(self):
  v=self.view();v['campaigns']=[dict(campaign_id=1,metrics_complete=False,spend=None,revenue=None,budget={}),dict(campaign_id=2,metrics_complete=True,spend=0,revenue=0,budget={})]
  with tempfile.TemporaryDirectory() as d:self.assertEqual(len(render_daily_png(v,d)),2)
 def test_campaigns_paginate_drr_before_budgets(self):
  v=self.view();v['campaigns']=[dict(v['campaigns'][0],campaign_id=i) for i in range(25)]
  with tempfile.TemporaryDirectory() as d:
   images=render_daily_png(v,d);self.assertEqual([x['kind'] for x in images],['drr']*3+['budgets']*3)
 def test_empty_scope_is_error(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):render_daily_png(dict(self.view(),campaigns=[]),d)
 def test_renderer_has_dynamic_dates(self):
  text=Path(__file__).resolve().parents[1].joinpath('advertising_daily_png.py').read_text(encoding='utf-8')
  self.assertNotIn('18 октября 2026',text);self.assertNotIn('19 октября 2026',text)
 def test_live_entry_photo_only(self):
  text=Path(__file__).resolve().parents[1].joinpath('advertising_daily_tables_owner.py').read_text(encoding='utf-8')
  ast.parse(text);self.assertIn('/sendPhoto',text);self.assertNotIn('/sendMessage',text);self.assertIn('deliver_daily_tables(store,messages',text)
 def test_spend_per_campaign_and_total(self):
  from unittest.mock import patch
  from PIL import ImageDraw
  original=ImageDraw.ImageDraw.text;seen=[]
  def record(draw,xy,text,*args,**kwargs):
   seen.append(str(text));return original(draw,xy,text,*args,**kwargs)
  with tempfile.TemporaryDirectory() as d:
   with patch.object(ImageDraw.ImageDraw,'text',record):render_daily_png(self.view(),d)
  self.assertIn('Расход всех РК: 16 962 ₽',seen);self.assertIn('15 101 ₽',seen);self.assertIn('1 100 ₽',seen)
if __name__=='__main__':unittest.main()
