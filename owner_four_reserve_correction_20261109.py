"""Owner-approved correction; only shared service may prepare or dispatch stock."""
import json
import stock_regular_service as service
import stock_performance as performance
from stock_owner_four_correction import install,SLOT
from stock_regular_job import send
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store
with runtime_db() as db:
    row=Store(db,postgres=True).sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-09:0700',)).fetchone()
    if not row:raise RuntimeError('Reference catalogue missing')
    sales=json.loads(row[0])['source']['sales']
# Demand weights are not used for a reduction to free capacity; never call Statistics orders.
original_preflight=performance.preflight
performance.preflight=lambda g,shared,orders=True:original_preflight(g,shared,orders=False)
install(service,sales)
result=service.run(runtime_db,send,SLOT)
seal('owner-four-reserve-correction',result)
print(json.dumps(result))
