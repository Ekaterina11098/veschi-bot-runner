"""Offline regression: one request must spill eligible additions into other campaigns."""
import ast, sys, types, unittest
from unittest.mock import patch
from datetime import date,timedelta
from pathlib import Path
from china_growth_placements import placement_candidates, addition_key

# Execute the real selection function without importing network transports.
tree=ast.parse(Path(__file__).with_name('china_advertising_full_growth.py').read_text(encoding='utf8'))
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='addition_actions')
ns={'date':date,'timedelta':timedelta,'addition_key':addition_key,'ROOT':'test:','finite_number':lambda v:type(v) in (int,float)}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<real addition_actions>','exec'),ns)
select=ns['addition_actions']

def discover(s,v):
 stub=types.SimpleNamespace(history=lambda rows:rows,event_time=lambda value:__import__('datetime').datetime.fromisoformat(value))
 with patch.dict(sys.modules,{'china_advertising_v2':stub}):
  return placement_candidates(s,v)

def campaign(cid,count):
 return dict(id=cid,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements={'search':True}),restrictions={'can_change_nms':True},nm_settings=[dict(nm_id=1000+cid*100+i,subject={'id':50}) for i in range(count)])

def source(campaigns):
 ids=[1,2,3,4]
 v=dict(campaigns=campaigns,excluded_nm_ids=[],screened_nm_ids=ids,own=dict(period_from='2026-10-01',rows=[dict(nm_id=n,subject_id=50,is_payed=4,open_card_count=100,funnel_orders_count=4) for n in ids]),economics={'rows':{str(n):dict(sample_size=10,expected_margin_before_ads_cny=20,stock_free=10,published_stock=10,seller_price_cny=200) for n in ids}},prices={'rows':[dict(nm_id=n,article=str(n)) for n in ids]},config={'cpcStep':1,'cpcMaxBid':100},budgets={'adverts':[dict(advertId=c['id'],total=0)for c in campaigns]},observed_at='2026-11-12T09:00:00+00:00')
 s=dict(period_to='2026-11-11',executions=[],full_growth_inputs=v,batches={'all':{'stats':[dict(advertId=c['id'],days=[dict(date='2026-11-11',sum=5)])for c in campaigns]}})
 v['addition_candidates']=discover(s,v)
 s['addition_bid_quotes']={addition_key(r):dict(campaign_id=r['campaign_id'],placement=r['placement'],target_minor=28,bid_verified=True)for r in v['addition_candidates']}
 return s

class Spillover(unittest.TestCase):
 def test_all_candidates_in_one_plan_and_shared_capacity(self):
  s=source([campaign(1,49),campaign(2,48),campaign(3,49)])
  items=select(s,[])
  self.assertEqual([(i['nm_id'],i['campaign_id'])for i in items],[(1,1),(2,2),(3,2),(4,3)])
  self.assertEqual(len({i['nm_id']for i in items}),4)
 def test_missing_exact_quote_falls_back_without_claiming_bid(self):
  s=source([campaign(1,49),campaign(2,40)])
  s['addition_bid_quotes'].pop('1:1:search')
  self.assertEqual(select(s,[])[0]['campaign_id'],2)
 def test_already_advertised_products_are_not_repeated(self):
  a=campaign(1,49);a['nm_settings'][0]['nm_id']=1
  s=source([a,campaign(2,40)])
  self.assertNotIn(1,[i['nm_id']for i in select(s,[])])
 def test_full_campaign_and_wrong_category_are_not_targets(self):
  full=campaign(1,50);wrong=campaign(2,1);wrong['nm_settings'][0]['subject']['id']=136
  s=source([full,wrong,campaign(3,40)])
  self.assertEqual({i['campaign_id']for i in select(s,[])},{3})
 def test_same_day_verified_change_stays_excluded(self):
  s=source([campaign(1,40)])
  s['executions']=[dict(kind='added',nm=1,at='2026-11-12T08:00:00+00:00')]
  self.assertNotIn(1,[r['nm_id']for r in discover(s,s['full_growth_inputs'])])

if __name__=='__main__':unittest.main()
