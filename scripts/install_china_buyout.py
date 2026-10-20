"""Install shared actual-buyout rules without changing source pins or schedules."""
import argparse,shutil
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--root',default='.')
args=parser.parse_args()
root=Path(args.root);scripts=Path(__file__).resolve().parent
for source,target in [('china_expected_order_profit.py','expected_order_profit.py'),('china_core_buyout.py','core.py'),('china_forecast_policy.py','forecast_policy.py')]:
 shutil.copyfile(scripts/source,root/'china_agent'/target)
path=root/'business_agents/conversation.py'
text=path.read_text(encoding='utf-8')
before="{'cost_rub': {'type': 'number'}, 'delivery_rub_per_order': {'type': 'number'}}"
after="{'cost_rub': {'type': 'number'}, 'delivery_rub_per_order': {'type': 'number'}, 'article': {'type': 'string'}}"
if before in text:text=text.replace(before,after)
elif after not in text:raise RuntimeError('Unexpected forecast tool schema')
before="        from china_agent.core import forecast_price\n        return forecast_price(**arguments)"
after="        from china_agent.forecast_policy import forecast_for_product\n        return forecast_for_product(data,arguments)"
if before in text:text=text.replace(before,after)
elif after not in text:raise RuntimeError('Unexpected forecast dispatch')
path.write_text(text,encoding='utf-8')

# Advertise actual-first semantics to all model/context consumers, not a fixed 50%.
import json
profile_path=root/'china_agent/profile.json'
profile=json.loads(profile_path.read_text(encoding='utf-8'))
profile['economics']['parameters']['buyout_rate']=dict(value=None,fallback_value=0.5,
 source='current_article_settled_orders',rule='Use actual kept buyouts / finished orders, including small samples and true zero; 50% only when own settled sample is absent')
profile_path.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
