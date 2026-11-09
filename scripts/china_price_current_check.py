"""Current exact price and positive MSK/WB availability before a proposal is shown."""
import re
from decimal import Decimal

def check(worker,answer):
    from china_price_delivery import rows
    from china_morning_readiness import current_prices,published_stock
    from china_advertising_state import AdvertisingIO
    from china_moysklad_read import read_stock
    offers=rows(answer)
    if not offers:return answer
    catalogue=worker.get('china_agent:prices:v1') or {}
    mapping={r['vendorCode']:str(r['nmID']) for r in catalogue.get('rows',[])}
    ids=[int(mapping[r[1]]) for r in offers]
    if len(set(ids))!=len(ids):raise RuntimeError('Duplicate price proposal')
    io=AdvertisingIO();prices=current_prices(io,ids);stock=read_stock([r[1] for r in offers]);wb=published_stock(io,prices,ids)
    retained=[];blocked=[]
    for action,article,change,buyer in offers:
        nm=mapping[article];old=Decimal(change.split('→')[0].strip().replace(',','.'))
        p=[r for r in prices['rows'] if str(r['nm_id'])==nm];s=[r for r in stock['rows'] if r['article'].casefold()==article.casefold()]
        reason=None
        if nm in ('1473245494','1473245510'):reason='owner_hold'
        elif len(p)!=1 or Decimal(str(p[0]['seller_price']))!=old:reason='price_changed'
        elif len(s)!=1 or not all(type(s[0].get(k)) in (int,float) for k in ('stock','reserve')) or s[0]['stock']-s[0]['reserve']<=0:reason='MSK_stock_unknown_or_zero'
        elif type(wb['amounts'].get(nm))is not int or wb['amounts'][nm]<=0:reason='WB_stock_unknown_or_zero'
        if not reason and action=='Снижение':
            review=getattr(worker,'price_control_review',None) or worker.get('china_agent:daily_expected_candidates:'+str(worker.day)) or {}
            models=[r for r in review.get('products',[]) if str(r.get('nm_id'))==nm]
            own_cost=s[0].get('price')
            if len(models)!=1 or own_cost is None or models[0].get('own_cogs_rub') is None or abs(float(own_cost)/100-float(models[0]['own_cogs_rub']))>.02:reason='current_COGS_changed_or_unknown'
        if reason:blocked.append(dict(article=article,reason=reason));continue
        retained.append(action+' · '+article+' Продавец: '+change+'\nПокупатель: '+buyer)
    worker.audit['proposal_current_check']=dict(prices=prices,stock=stock,published_stock=wb,blocked=blocked,retained=len(retained))
    if retained:
        statuses=[block for block in answer.split('\n\n') if block.startswith(('Повышение:','Снижение:'))]
        return '\n\n'.join(retained+statuses)
    return 'Повышение: нет готовых рекомендаций\n\nСнижение: нет готовых рекомендаций'

