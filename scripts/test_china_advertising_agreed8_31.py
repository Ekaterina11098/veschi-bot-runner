import unittest,copy
from datetime import datetime,timezone
from china_morning_agreed8_31_replace import agreed_bundle
class AgreedEight(unittest.TestCase):
 def test_exact_eight_replace_old_actions_and_preserve_financials(self):
  actions=[];campaigns=[]
  for cid in [12,13]:
   members=[]
   for i in range(4):
    nm=cid*10+i;members.append({'nm':nm});kind='ad_exclude_sku' if len(actions)<5 else 'ad_set_bid'
    a=dict(id=str(cid)+':'+str(nm),campaign_id=cid,nm_id=nm,article='sku'+str(nm),kind=kind,old_minor=38,placement='recommendations',minimum_minor=28)
    if kind=='ad_set_bid':a['target_minor']=28
    actions.append(a)
   campaigns.append(dict(id=cid,current_articles=members,attention=[dict(action={'old':True})],period={'spend':12,'amount':100},last={'spend':4,'amount':20}))
  b=dict(day='2026-10-31',campaigns=campaigns);original=copy.deepcopy(b)
  review=dict(status='ready_for_owner_review',actions=actions,condition_observed_at=datetime.now(timezone.utc).isoformat())
  class IO:
   def get(self,k):return {'bundle':b} if 'advertising_artifacts' in k else review
  result=agreed_bundle(IO());new=[r['action']for c in result['campaigns']for r in c['attention']]
  self.assertEqual(len(new),8);self.assertEqual(len({x['id']for x in new}),8);self.assertEqual(sum(x['kind']=='ad_exclude_sku'for x in new),5)
  self.assertEqual(b,original)
  for n,o in zip(result['campaigns'],original['campaigns']):self.assertEqual(n['period'],o['period']);self.assertEqual(n['last'],o['last'])
if __name__=='__main__':unittest.main()
