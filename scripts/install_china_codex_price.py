"""Keep pricing acquisition and delivery; replace final analysis before answer freeze."""
import argparse
from pathlib import Path
def install(root):
 from china_price_pending import install as install_pending
 install_pending(root)
 from china_price_period import install as install_period
 install_period(root)
 path=Path(root)/'china_agent/daily_report_worker.py';text=path.read_text(encoding='utf-8')
 marker='# cloud_codex_final_price_review_v1'
 if marker in text:
  from china_price_delivery import install as install_delivery
  install_delivery(root)
  return
 preview="            answer, trace = self.prepare(preview=True)\n"
 live="                answer, trace = self.prepare()\n"
 if text.count(preview)!=1 or text.count(live)!=1:raise RuntimeError('Price worker analysis hook changed; review source')
 guarded_preview=preview # Owner11Nov: no diagnostic report substitution; source failures stop delivery.
 text=text.replace(preview,guarded_preview+"            "+marker+"\n            from china_codex_reports import review_price\n            answer, trace = review_price(self, answer, trace)\n")
 guarded_live=live
 text=text.replace(live,guarded_live+"                from china_codex_reports import review_price\n                answer, trace = review_price(self, answer, trace)\n")
 # An old prepared answer may be reused only if delivery already started; never regenerate uncertain parts.
 needle="            import business_agents.conversation as conv\n"
 if text.count(needle)!=1:raise RuntimeError('Price delivery hook changed')
 patch="""            from china_codex_analysis import POLICY
            existing_trace=self.job.get('tool_trace') or []
            started=any(e.get('name')=='china_report_delivery' and e.get('sent_parts') for e in existing_trace)
            if (self.get(POLICY)or{}).get('status')=='active' and not started and not any(e.get('name') in ('china_codex_analysis','china_price_rules_review','china_control_canonical_report') for e in existing_trace):
                from china_codex_reports import review_price
                answer,trace=review_price(self,self.job['answer'],existing_trace)
                saved=self.patch(dict(answer=answer,tool_trace=trace))
                if len(saved)!=1:raise RuntimeError('Cloud price answer freeze lost lease')
                self.job=saved[0]
"""
 text=text.replace(needle,patch+needle)
 rejected="                    source, normalized = normalize(observation, cabinet)\n"
 if text.count(rejected)!=1:raise RuntimeError('Price source validation hook changed')
 text=text.replace(rejected,"                    try:\n                        source, normalized = normalize(observation, cabinet)\n                    except ValueError as exc:\n                        self.audit['errors'].append(dict(stage='mpstats_validation',status='rejected',reason=str(exc)[:200],raw_snapshot_id=raw[0]['id'] if raw else None))\n                        return\n")
 path.write_text(text,encoding='utf-8')
 from china_price_delivery import install as install_delivery
 install_delivery(root)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',default='source');args=parser.parse_args();install(args.root);print('Pricing acquisition/delivery retained; cloud final-analysis hooks installed')
