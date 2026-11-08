import copy,unittest
from unittest.mock import patch
from china_new_ad_reports import choose,quote_groups
from china_new_ads import validate_plan
from china_loss_control import CHAT,BOT,digest
from datetime import datetime,timezone
def source():
 return dict(period_to='2026-11-07',memory_used=True,campaigns={},protected=[],experience={},prices=[dict(nmID=1,sizes=[dict(discountedPrice=200)]),dict(nmID=2,sizes=[dict(discountedPrice=200)])],stock=[dict(article='A',stock=10,reserve=0,price=10000),dict(article='B',stock=10,reserve=0,price=10000)],orders=[dict(nmId=1,createdAt='2026-11-06T12:00:00Z'),dict(nmId=2,createdAt='2026-11-06T12:00:00Z')],policy=dict(logistics_by_nm={'1':dict(delivery_cny=10),'2':dict(delivery_cny=10)},category_minimum_minor={'50':28}),products=[dict(nm_id=n,sa_name=a,finished_orders=10,is_payed=8,open_card_count=100,funnel_orders_count=2,price_after_spp=200,price_after_discount=200,advertisement=500,subject_id=50)for n,a in [(1,'A'),(2,'B')]],config=dict(cpcStep=1,cpcMaxBid=1000))
class Tests(unittest.TestCase):
 def test_two_qualified_candidates_returned_for_twenty_without_demand_group(self):
  groups,_=choose(source(),20,manual_review=True);self.assertEqual(2,len(groups['orders']));self.assertEqual([],groups['demand'])
 def test_manual_history_review_does_not_remove_protection_or_recent_holds(self):
  s=source();self.assertEqual([],choose(s,20)[0]['orders'])
  s['protected']=[1];s['experience']['recent_changed_nm_ids']=[2]
  self.assertEqual([],choose(s,20,manual_review=True)[0]['orders'])
 def test_one_campaign_plan_valid_without_changing_legacy_two_campaign_contract(self):
  items=[dict(kind='ad_create_campaign',group='orders',name='test',payment_type='cpc',bid_type='manual',placements=['recommendations'],budget_cny=100,daily_limit_minor=10000,carry_over_enabled=False,auto_topup=False,skus=[dict(nm_id=1,article='A',bid_minor=28)])]
  p=dict(execution_kind='ad_create_campaigns',chat_id=CHAT,bot_id=BOT,price_changes=False,items=items,plan_sha256=digest(items),group_policy='available_qualified_groups')
  self.assertEqual(items,validate_plan(p));del p['group_policy']
  with self.assertRaises(ValueError):validate_plan(p)
 def test_negative_economics_and_missing_values_not_padded(self):
  s=source();s['stock'][0]['price']=99999999;s['stock'][1]['reserve']=None
  self.assertEqual([],choose(s,20,manual_review=True)[0]['orders'])
 def test_moysklad_free_stock_and_current_minimum_used(self):
  s=source();s['campaigns']={'9':dict(id=9,status=9,currency='CNY',settings=dict(placements=dict(search=False,recommendations=True)),nm_settings=[dict(subject=dict(id=50))])}
  groups={'orders':[dict(nm_id=1,subject_id=50,stock=10),dict(nm_id=2,subject_id=50,stock=0)]}
  class IO:
   def get(self,k):return dict(cabinet='token_3',minimums={'9':{'bids':[dict(nm_id=100,bids=[dict(type='recommendation',currency='CNY',value=30)])]}})
  s['campaigns']['9']['nm_settings'][0]['nm_id']=100
  with patch('china_new_ad_reports.Transport')as t:
   out,blocked=quote_groups(IO(),s,groups);t.assert_not_called()
  self.assertEqual(30,out['orders'][0]['bid_minor']);self.assertTrue(out['orders'][0]['minimum_verified']);self.assertEqual(1,len(blocked))
if __name__=='__main__':unittest.main()

