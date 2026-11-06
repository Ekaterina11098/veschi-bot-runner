import pathlib,sys,types,copy,unittest
P=pathlib.Path(__file__).parent;sys.path.insert(0,str(P));sys.modules.setdefault('analytics',types.ModuleType('analytics'));ps=types.ModuleType('analytics.payload_storage');ps.decode_rows=lambda rows:rows;sys.modules['analytics.payload_storage']=ps
from ip_daily_retained_review import review
DAY='2026-11-04'
def fixture():
 configs={}
 for cid,subject,ids in [(1,50,[101]),(2,61,[102,103,104]),(3,57,[105])]:
  configs[cid]=dict(id=cid,status=9,currency='RUB',bid_type='manual',settings={'payment_type':'cpc','placements':{'search':True,'recommendations':False}},restrictions={'can_change_nms':True},nm_settings=[dict(nm_id=nm,subject={'id':subject},bids_kopecks={'search':295 if subject==50 or nm==104 else 281 if subject==61 else 190,'recommendations':0}) for nm in ids])
 vals={101:(20,1,1000),102:(152,0,0),103:(12,1,1360),104:(149,0,0),105:(2,1,1000)}
 view=dict(period=DAY,campaigns=[dict(campaign_id=cid,sku_rows=[dict(nm_id=nm,ac_spending_sum=vals[nm][0],ac_orders=vals[nm][1],ac_orders_sum=vals[nm][2]) for nm in [n['nm_id'] for n in c['nm_settings']]]) for cid,c in configs.items()])
 own=[]
 for nm,sub in [(101,50),(102,61),(103,61),(104,61),(105,57),(106,50),(107,50)]:own.append(dict(nm_id=nm,sa_name='SKU'+str(nm),subject_id=sub,orders_count=1 if nm not in (102,104) else 0,orders_sum=1000 if nm not in (102,104) else 0,stock_api_stock_count=0 if nm==105 else 1,fbs_stock=100 if nm==105 else 0))
 daily=dict(period_to=DAY,campaign_review={'sku_profit_index':{str(nm):{'status':'preliminary','period_to':DAY,'after_ads':100} for nm in (101,105,106,107)}},full_pair_analysis=[])
 minima=[dict(subject=sub,payment_type='cpc',placement='search',currency='RUB',bid_type='manual',minimum_minor=rate) for sub,rate in [(50,295),(61,281),(57,190)]]
 class Store:
  def db(self,method,table,params):return [{'payload':[{'daily':daily}]}] if params['source'].startswith('in.') else [{'payload':own}]
  def cache_get(self,k):return {'category_minimum_reuse':minima}
 return Store(),view,configs,daily,own
class WholeReview(unittest.TestCase):
 def test_four_directions_and_single_order_research(self):
  t,v,c,d,o=fixture();a,cov=review(t,v,c,set(),{107});pairs={(r['kind'],r['nm']):r for r in a};self.assertIn(('raise_bid',101),pairs);self.assertEqual(pairs['raise_bid',101]['target_bid_minor'],309);self.assertIn(('remove',102),pairs);self.assertEqual(pairs['lower_bid',104]['target_bid_minor'],281);self.assertIn(('add',106),pairs);self.assertEqual(set(cov['directions']),{'raise','add','reduce','exclude'});self.assertTrue(pairs['raise_bid',101]['research_test'])
 def test_fbo_only_stock_and_owner_removal(self):
  t,v,c,d,o=fixture();a,_=review(t,v,c,set(),{107});self.assertNotIn(105,[r['nm'] for r in a]);self.assertNotIn(107,[r['nm'] for r in a])
 def test_pending_not_new_command(self):
  t,v,c,d,o=fixture();a,_=review(t,v,c,{(1,101)},set(),{106});self.assertNotIn(101,[r['nm'] for r in a]);self.assertNotIn(106,[r['nm'] for r in a])
 def test_no_shop_profit_substitution(self):
  t,v,c,d,o=fixture();d['campaign_review']['sku_profit_index']={}
  for r in o:r['profit']=9999
  a,cov=review(t,v,c,set());self.assertFalse(any(r['kind'] in ('raise_bid','add') for r in a));self.assertFalse(cov['financial_model_available'])
 def test_no_duplicate_advertising_addition(self):
  t,v,c,d,o=fixture();v['campaigns'][0]['sku_rows'].append(dict(nm_id=106,ac_spending_sum=1,ac_orders=0,ac_orders_sum=0));a,_=review(t,v,c,set());self.assertFalse(any(r['nm']==106 and r['kind']=='add' for r in a))
 def test_change_day_not_used_for_new_effect_recommendation(self):
  t,v,c,d,o=fixture();a,_=review(t,v,c,set(),pair_changes={(1,101):DAY},sku_changes={104:DAY});self.assertFalse(any(r['nm'] in (101,104) for r in a))
 def test_first_completed_day_after_change_remains_available(self):
  t,v,c,d,o=fixture();a,_=review(t,v,c,set(),pair_changes={(1,101):'2026-11-03'});self.assertTrue(any(r['nm']==101 and r['kind']=='raise_bid' for r in a))
 def test_dated_conditional_unit_model_is_explicit_not_period_profit(self):
  t,v,c,d,o=fixture();d['campaign_review']['sku_profit_index']={'101':{'status':'preliminary','period_to':DAY,'after_ads':-100}};native=t.cache_get
  t.cache_get=lambda k:{'models':{'101':{'scenario_one_buyout_after_assumed_5pct_ad':100,'historical_order_price':1000,'period_to':'2026-11-01','source':'saved own cost and tax reserve scenario'}}} if k=='advertising:ip:saved-unit-economics:v1' else native(k)
  a,_=review(t,v,c,set());row=next(r for r in a if r['nm']==101);self.assertEqual(row['kind'],'raise_bid');self.assertTrue(row['economic_basis']['buyout_rate_unknown']);self.assertTrue(row['economic_basis']['not_current_period_profit']);self.assertIn('доля выкупа неизвестна',row['criterion'])
  o[0]['orders_sum']=900;a,_=review(t,v,c,set());self.assertFalse(any(r['nm']==101 and r['kind']=='raise_bid' for r in a))
if __name__=='__main__':unittest.main()
