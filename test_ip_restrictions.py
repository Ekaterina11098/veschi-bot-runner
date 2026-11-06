import copy,unittest
from test_full_retained_review import fixture,DAY
from ip_daily_retained_review import restriction_signal,review
from ip_report_analysis import screen
class Restrictions(unittest.TestCase):
 def test_near_old_cliff_is_not_allowed_an_extra_order(self):
  # Anonymised regression: below the old 1000 threshold despite two zero-order days.
  data={'2026-11-02':dict(spend=450,orders=1,revenue=10000,clicks=150),'2026-11-03':dict(spend=330,orders=0,revenue=0,clicks=110),'2026-11-04':dict(spend=214,orders=0,revenue=0,clicks=71)}
  r=restriction_signal(data,10000);self.assertTrue(r['candidate']);self.assertAlmostEqual(r['drr_pct'],9.94);self.assertEqual(r['no_order_spend_days'],2)
 def test_same_rule_without_a_product_price(self):
  data={DAY:dict(spend=400,orders=1,revenue=3000), '2026-11-03':dict(spend=80,orders=0,revenue=0)}
  self.assertTrue(restriction_signal(data)['candidate'])
 def test_four_clicks_and_small_spend_remain_observation(self):
  data={DAY:dict(spend=6,orders=0,revenue=0,clicks=2), '2026-11-03':dict(spend=6,orders=0,revenue=0,clicks=2)}
  r=restriction_signal(data,5000,100);self.assertFalse(r['candidate']);self.assertEqual(r['reason'],'limited_sample_or_isolated_ratio')
 def test_zero_orders_material_traffic_has_no_cash_cliff(self):
  data={DAY:dict(spend=90,orders=0,revenue=0,clicks=30),'2026-11-03':dict(spend=90,orders=0,revenue=0,clicks=30)}
  self.assertTrue(restriction_signal(data,10000,50)['candidate']);self.assertFalse(restriction_signal(data,10000,None)['candidate'])
 def test_single_excursion_does_not_overrule_acceptable_period(self):
  data={DAY:dict(spend=10,orders=1,revenue=100),'2026-11-03':dict(spend=1,orders=10,revenue=1000)}
  self.assertFalse(restriction_signal(data,100)['candidate'])
 def test_at_floor_exclusion_and_above_floor_reduction(self):
  st,v,c,d,own=fixture();actions,cov=review(st,v,c,set());k={(a['kind'],a['nm'])for a in actions}
  self.assertIn(('remove',102),k);self.assertIn(('lower_bid',104),k);self.assertEqual(len(cov['restriction_audit']),cov['existing_pairs'])
 def test_missing_minimum_cannot_create_a_made_up_numeric_bid(self):
  st,v,c,d,own=fixture();native=st.cache_get;st.cache_get=lambda k:{}if k=='ip_agent:expanded98:2026-11-02:v1:execution:optimized2'else native(k)
  actions,_=review(st,v,c,set());self.assertFalse(any(a['kind']=='lower_bid'for a in actions));self.assertTrue(any(a['kind']=='remove'for a in actions))
 def test_historical_expense_of_a_removed_member_is_not_a_new_action(self):
  st,v,c,d,own=fixture();c[2]['nm_settings']=[n for n in c[2]['nm_settings']if n['nm_id']!=102]
  a,_=review(st,v,c,set());self.assertNotIn(102,[x['nm']for x in a])
 def test_pending_exclusion_is_not_registered_again(self):
  st,v,c,d,own=fixture();a,cov=review(st,v,c,set(),pending_nms={102});self.assertNotIn(102,[x['nm']for x in a]);self.assertTrue(any(x['nm']==102 and x['status']=='owner_protected_pending_or_own_label_missing'for x in cov['restriction_audit']))
 def test_paused_campaign_not_reactivated_or_changed(self):
  st,v,c,d,own=fixture();c[2]['status']=11;a,_=review(st,v,c,set());self.assertFalse(any(x['campaign']==2 for x in a))
 def test_last_campaign_member_not_removed(self):
  st,v,c,d,own=fixture();c[2]['nm_settings']=[n for n in c[2]['nm_settings']if n['nm_id']==102];next(r for r in own if r['nm_id']==102).update(orders_count=1,orders_sum=1000);a,cov=review(st,v,c,set());self.assertNotIn(102,[x['nm']for x in a]);self.assertTrue(any(x['status']=='last_sku_or_membership_change_not_allowed'for x in cov['restriction_audit']))
 def test_change_day_is_not_a_full_day_and_gap_is_explicit(self):
  st,v,c,d,own=fixture();a,cov=review(st,v,c,set(),sku_changes={102:DAY});self.assertNotIn(102,[x['nm']for x in a]);self.assertTrue(any(x['nm']==102 and x['status']=='latest_sku_row_missing_after_verified_change'for x in cov['restriction_audit']))
 def test_combined_exclusions_do_not_empty_a_campaign(self):
  st,v,c,d,own=fixture();c[2]['nm_settings']=[n for n in c[2]['nm_settings']if n['nm_id']in(102,104)]
  for n in c[2]['nm_settings']:n['bids_kopecks']['search']=281
  for r in own:
   if r['nm_id']in(102,104):r.update(orders_count=1,orders_sum=1000)
  candidates,cov=review(st,v,c,set());contract=dict(actions=[a for a in candidates if a['campaign']==2],review_coverage=cov)
  self.assertEqual(len(contract['actions']),2)
  actions,audit=screen(contract,v,dict(period=DAY,own=own,finance={},models={},gaps=[]))
  self.assertEqual(len(actions),1);self.assertTrue(any('empty campaign'in r['reason']for r in audit['rejected']))
if __name__=='__main__':unittest.main()
