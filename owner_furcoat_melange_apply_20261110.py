"""Owner authorized remaining two melange China targets after MS article fix; only shared journal executor writes."""
import json
import stock_regular_service as service
import stock_performance as performance
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store
from stock_regular_job import send
from stock_owner_fur_manual import install,SLOT
with runtime_db() as db:
 row=Store(db,postgres=True).sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-10:0700',)).fetchone()
 if not row:raise RuntimeError('Morning reference missing')
 reference=json.loads(row[0])['source']
original=performance.preflight
performance.preflight=lambda g,shared,orders=True:original(g,shared,orders=False)
install(service,reference)
result=service.run(runtime_db,send,SLOT)
seal('owner-furcoat-melange-approved',result)
print(json.dumps(result))
