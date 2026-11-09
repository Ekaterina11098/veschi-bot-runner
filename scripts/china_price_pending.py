"""Retire only owner-cancelled pending price notices; never replay or mark sent."""
import copy
from pathlib import Path

def reconcile(state, read, now):
    pending=state.get('pending_notice')
    if not pending:return state
    job_id=pending.get('job_id')
    if type(job_id) is not int:return state
    rows=read('business_agent_jobs',dict(id='eq.'+str(job_id),agent_id='eq.china',select='id,status,error,lease_until',limit=1)) or []
    if len(rows)!=1:return state
    job=rows[0]
    if (job.get('id')!=job_id or job.get('status')!='failed' or job.get('lease_until')
            or not str(job.get('error') or '').startswith('cancelled_by_owner')):return state
    result=copy.deepcopy(state)
    result.pop('pending_notice')
    result.setdefault('retired_cancelled_notices',{})[str(job_id)]=dict(
        status='cancelled_by_owner',reason=job['error'],retired_at=now.isoformat(),
        delivered=False,replay_allowed=False)
    return result

def install(root):
    import shutil
    target=Path(root)/'china_agent'
    shutil.copyfile(__file__,target/'price_pending.py')
    path=target/'demand.py';text=path.read_text(encoding='utf-8')
    marker='    # retire_terminal_owner_cancelled_notice_v1\n'
    if marker in text:return
    needle="    pending = state.get('pending_notice')\n"
    if text.count(needle)!=1:raise RuntimeError('Price pending hook changed')
    text=text.replace(needle,marker+"    from .price_pending import reconcile\n    state = reconcile(state, read, now)\n"+needle)
    path.write_text(text,encoding='utf-8')

