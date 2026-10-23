"""Private read-only acceptance check, no model or Telegram sends."""
import os,json
from datetime import timedelta
from china_wb_evidence import Reports,daily,settlement,own_costs,ROOT
from china_analytic_dialog import Analyst,reading
from conversion_watches import runtime

def main():
 w=runtime();today=w.now.astimezone(__import__('china_wb_evidence').timezone(timedelta(hours=3))).date();last=today-timedelta(days=1);first=last-timedelta(days=1)
 collection=daily(w)
 with reading():
  reports=Reports(w);finance=reports.finance(str(last-timedelta(days=29)),str(last));stock=Analyst(w,{},[]).live('stock',[],str(first),str(last))
 with reading():costs,cost_evidence=own_costs(w,stock,finance.get('rows',[]),str(first),str(last))
 result=dict(collection=collection,costs_source={k:stock.get(k) for k in ['source','source_key','observed_at']},finance_complete=finance.get('complete'),finance_rows=len(finance.get('rows',[])),
  cabinet=settlement(finance,str(first),str(last),None,costs),daily=[settlement(finance,str(d),str(d),None,costs) for d in [first,last]],cost_evidence=cost_evidence,costs_matched=sum(v is not None for v in costs.values()),catalogue=len(costs),wb_writes=0,telegram_sends=0)
 w.save(ROOT+'verification',result)
 print(json.dumps({k:result[k] for k in ['finance_complete','finance_rows','costs_matched','catalogue','wb_writes','telegram_sends']}))
 if not finance.get('complete'):raise SystemExit('Finance pagination not complete; inspect private receipt')

if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 main()

