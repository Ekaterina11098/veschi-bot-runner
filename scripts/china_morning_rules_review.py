"""Morning-only full-check report review with no paid model transport."""
import copy
POLICY='china_agent:advertising_morning_review_policy:v1'
def enabled(io):
 p=io.get(POLICY)or{}
 return p.get('enabled')is True and p.get('mode')=='full_checks_no_model' and p.get('cabinet')=='token_3' and p.get('chat_id')==-1004342917488 and p.get('owner_id')==5122667182 and p.get('paid_api_allowed')is False
def review(io,bundle,source):
 if not enabled(io):raise ValueError('Morning no-model review not authorized')
 from china_midday_rules_review import review as full_checks
 out=full_checks(bundle,source)
 out['morning_review']=out.pop('midday_review')
 out['morning_review']['scope']='morning'
 out['morning_review']['policy_key']=POLICY
 return out
