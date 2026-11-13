import ast,copy,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
import china_addition_minimum as q
import china_advertising_directions as directions
import china_midday_rules_review as rules

def campaign(cid=10,subject=61):
 return dict(id=cid,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=True,recommendations=False)),nm_settings=[dict(nm_id=100,subject=dict(id=subject))])

class ReadyCandidates(unittest.TestCase):
 def test_same_category_quote_keeps_representative_provenance_and_reuses_read(self):
  calls=[]
  def http(io,path,method,body):
   calls.append(body)
   return dict(bids=[dict(nm_id=100,bids=[dict(type='search',value=27,currency='CNY')])])
  stub=types.SimpleNamespace(http=http)
  inputs=dict(campaigns=[campaign()]);item=dict(nm_id=200,campaign_id=10,subject_id=61,placement='search')
  with patch.dict(sys.modules,{'china_advertising_v2':stub}):
   a=q.read_quote(None,inputs,item);b=q.read_quote(None,inputs,dict(item,nm_id=201))
  self.assertEqual(1,len(calls));self.assertEqual([100],calls[0]['nm_ids'])
  self.assertEqual(200,a['bids'][0]['nm_id']);self.assertEqual(201,b['bids'][0]['nm_id'])
  self.assertEqual(100,a['quote_nm_id']);self.assertEqual(q.CATEGORY_BASIS,a['quote_basis'])
 def test_other_subject_or_placement_never_supplies_minimum(self):
  with self.assertRaises(q.MinimumMembershipUnavailable):q.category_context(dict(campaigns=[campaign(subject=50)]),dict(nm_id=200,campaign_id=10,subject_id=61,placement='search'))
  with self.assertRaises(q.MinimumMembershipUnavailable):q.category_context(dict(campaigns=[campaign()]),dict(nm_id=200,campaign_id=10,subject_id=61,placement='recommendations'))
 def test_midday_preserves_full_growth_quotes(self):
  tree=ast.parse(Path(__file__).with_name('china_midday_completed_review.py').read_text(encoding='utf-8'))
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='attach')
  gate=next(n for n in fn.body if isinstance(n,ast.If)and ast.unparse(n.test)=="not source.get('full_growth_inputs')")
  source=dict(full_growth_inputs={'status':'complete'},addition_bid_quotes={'10:200:search':{'target_minor':27}})
  before=copy.deepcopy(source)
  exec(compile(ast.Module(body=[gate],type_ignores=[]),'legacy-quote-gate','exec'),{'source':source})
  self.assertEqual(before,source)
 def test_alternative_campaigns_do_not_duplicate_unready_sku(self):
  source=dict(period_to='2026-11-12',catalogue=dict(rows=[dict(nmID=200,vendorCode='SKU')]),addition_scan=dict(status='complete',period_from='2026-10-14',period_to='2026-11-12',candidate_ids=[200]*9),economics=dict(rows={'200':dict(expected_margin_before_ads_cny=20,stock_free=6,buyout_fallback=False,sample_size=8)}))
  r=directions.attach(dict(campaigns=[]),source)
  self.assertEqual(1,r['recommendation_directions']['add']['count'])
  self.assertEqual(1,r['recommendation_directions']['add']['unready_count'])
 def test_unfinished_addition_prevents_claim_of_full_ready_review(self):
  b=dict(economic_review_complete=True,recommendation_directions={k:dict(rows=[])for k in ('raise','add','reduce','exclude')},campaigns=[])
  b['recommendation_directions']['add']['rows']=[dict(nm_id=200,ready=False)]
  with self.assertRaisesRegex(ValueError,'Addition validation unfinished'):rules.review(b,dict(day_quality=dict(usable=True),full_growth_review=dict(status='complete')))
 def test_ready_revision_is_required_for_review_reuse(self):
  content=Path(__file__).with_name('china_advertising_midday.py').read_text(encoding='utf-8')
  ast.parse(content)
  self.assertIn("get('validation_revision')=='ready_candidates_v2'",content)
 def test_composition_additions_do_not_reset_unchanged_member_test_days(self):
  content=Path(__file__).with_name('china_midday_completed_review.py').read_text(encoding='utf-8')
  tree=ast.parse(content)
  assignment=next(n for n in ast.walk(tree)if isinstance(n,ast.AugAssign)and ast.unparse(n.target)=="source['verified_composition_changes']")
  source={'verified_composition_changes':[]}
  exec(compile(ast.Module(body=[assignment],type_ignores=[]),'composition','exec'),dict(source=source,cid='10',key='verified-receipt',at='2026-11-13T10:00:00Z',old={100},new={100,200}))
  self.assertEqual([200],[e['nm']for e in source['verified_composition_changes']])
if __name__=='__main__':unittest.main()

