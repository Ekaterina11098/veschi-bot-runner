"""Published report approvals live until replacement or explicit revocation."""
from datetime import datetime,timezone
CURRENT='china_agent:daily_ad_current_report:v1:'
def generation(p):
 return p.get('report_generation') or p.get('parent_plan_id') or p['plan_id']
def publish(io,p):
 if p.get('validity_mode')=='until_replaced':
  io.put(CURRENT+p['family'],dict(report_generation=generation(p),plan_id=p['plan_id'],published_at=datetime.now(timezone.utc).isoformat()))
def valid(io,p,now=None):
 if p.get('invalidated_at') or p.get('status') in ('revoked','invalidated'):return False
 if p.get('validity_mode')!='until_replaced':
  return (now or datetime.now(timezone.utc))<=datetime.fromisoformat(p['expires_at'])
 current=io.get(CURRENT+p['family']) or {}
 return current.get('report_generation')==generation(p)
def require(io,p):
 if not valid(io,p):raise ValueError('Report replaced or explicitly revoked')
