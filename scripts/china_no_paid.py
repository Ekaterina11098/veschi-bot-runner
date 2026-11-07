"""Deterministic China bot replies; paid model transport is deliberately blocked."""
import re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

POLICY='china_agent:no_paid_ai:v1'
CHAT=-1004342917488
BOT=8780468043

def require_paid_api(policy=None):
    # Only explicitly restored group dialogue. Legacy scheduled analysis stays blocked.
    p=policy or {}
    if (p.get('enabled') is True and p.get('paid_api_allowed') is True
        and p.get('chat_id')==CHAT and p.get('bot_id')==BOT
        and p.get('model')=='gpt-6.1-sol' and p.get('wb_action_permission') is False):return
    raise PermissionError('Paid model API disabled by owner; no request was sent')

def enabled(w):
    p=w.get(POLICY) or {}
    return p.get('enabled') is True and p.get('chat_id')==CHAT and p.get('bot_id')==BOT and p.get('paid_api_allowed') is False

HELP=('������� ��������� � �� ���������. �������� ������� � ������ ��� ������:\n'
      '� ���������� ������� �� ��������� � �������;\n'
      '� ���������� ������� �� ��������� 7 ����;\n'
      '� ������� ���������� ��� ��������;\n'
      '� ������ �� �������, �������� �ʻ, ����������� ���������;\n'
      '� ����� ������˻, ���� ��������.\n'
      '��������� ��-������ � Telegram ������ ����������. ����� ������� ������ ����� ��������� � ���� ���� ��� ������� �������� API.')

def cells(value):
    return str(value).replace('|','/').replace('\n',' ')

def answer(w,job,history=()):
    text=re.sub(r'^/codex(?:@\w+)?\s*','',job.get('request_text',''),flags=re.I).strip()
    scoped=dict(job,request_text=text)
    if re.search(r'^(?:/start|/help|������|��� ������)|�������|�����|�������',text,re.I):
        return HELP
    from conversion_watches import intent,report
    command=intent(text)
    if command:
        if not w.authorized(job):return '��������� ��������� ����� ������ ����������� ��������� ���� ������.'
        return w.command(scoped)
    from china_conversion_context import handle as conversion
    reply=conversion(w,scoped,history)
    if reply is not None:return reply[0]
    if re.search(r'�������',text,re.I) and re.search(r'\d+-[A-Za-z]',text):
        nm,article=w.resolve(text)
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
        m=re.search(r'(?:��|��������\w*)\s+(\d+)\s+��',text,re.I)
        days=int(m[1]) if m else 7
        if not 1<=days<=14:return '��� ������� ������ ������ ������� �� 1 �� 14 ������ ����.'
        value=w.conversion_history(article,date_from=dates[0] if len(dates)==2 else None,date_to=dates[1] if len(dates)==2 else None,days=days,saved_only=True)
        rows=value.get('daily',[])
        lines=[f'����� � {article} � {value["date_from"]}�{value["date_to"]} � ������ ���',
               '| ���� | ��������� | ������ | ��������� |','|---|---:|---:|---:|']
        for r in rows:
            v,n=r.get('views'),r.get('orders')
            cr=f'{100*n/v:.2f}%' if isinstance(v,(int,float)) and v>0 and isinstance(n,(int,float)) else '��� ������'
            lines.append(f'| {r["date"]} | {v if v is not None else "��� ������"} | {n if n is not None else "��� ������"} | {cr} |')
        lines.append('��������: ����������� ������� ������� MPStats; �������� �� ����. '+('������ ������.' if value.get('complete') else '������ ������� ��������.'))
        return '\n'.join(lines)
    if re.search(r'��������|����.*������|��������.*������|�������.*����',text,re.I):
        from china_growth_candidates import collect
        scan=collect(w,days=3)
        rows=scan.get('rows',[])
        lines=[f'��������� � {scan.get("period_from","?")}�{scan.get("period_to","?")} � ���� {scan.get("observed_at","�� ������")}',
               '| ������� | �� | ����������� | ��������� |','|---|---|---|---|']
        for r in rows[:30]:
            action='����������' if r.get('kind')=='ad_add_sku' else '�������� ���������'
            lines.append('| '+' | '.join(cells(x) for x in [r.get('article'),r.get('campaign_id'),action,r.get('reason','��� �������������')])+' |')
        if not rows:return '�� ������������ ������� �� ��� ������ ��� ������� ��������� �� ��������. ��� �� ���������� ���������� ������ ������������; ��������� ���.'
        lines.append(f'�������� {min(len(rows),30)} �� {len(rows)}. ������ �� ��������, ��� ��; ����� ����������� ����� ���������� ��������. ������ �� �����������.')
        return '\n'.join(lines)
    if re.search(r'���������|���������.*���',text,re.I):
        from china_break_even import answer as break_even
        reply=break_even(w,scoped,history)
        if reply is not None:return reply[0]
    if re.search(r'���[�]�|������|���������.*��������',text,re.I):
        from china_agent_reports import make,catalog
        kind=('outcomes' if re.search(r'���������.*��������',text,re.I) else
              'budgets' if re.search(r'������',text,re.I) else
              'advertising' if re.search(r'������|���|������',text,re.I) else None)
        if kind:
            value=make(w,scoped,kind,days=3)
            return value['marker']
        return '��������� ������:\n'+'\n'.join('� '+v['title'] for v in catalog()['reports'].values())
    if re.search(r'���',text,re.I) and re.search(r'\d+-[A-Za-z]',text):
        nm,article=w.resolve(text)
        source=w.get('china_agent:prices:v1') or {}
        if source.get('cabinet')!='token_3':return '������������ ����� ��� ����� ���.'
        rows=[r for r in source.get('rows',[]) if str(r.get('nmID'))==str(nm)]
        if len(rows)!=1:return '����������� ����������� ���� ����� �������� �� �������.'
        r=rows[0]
        return f'{article} � nmID {nm}\n����: {r.get("price","��� ������")} {r.get("currencyIsoCode4217","")}; ������ ��������: {r.get("discount","��� ������")}%.\n����: {source.get("observed_at","�� ������")}. ��� ����������� ������, �� ����� �������� WB. ���� �� ��������.'
    return HELP

def safe_answer(w,job,history=()):
    try:
        result=answer(w,job,history)
        if not isinstance(result,str) or not 0<len(result)<=12000:raise ValueError('Reply outside bounds')
        return result
    except Exception as exc:
        return ('�� ������� �������� ������ ������������� ������ ��� �� ('+type(exc).__name__+'). '
                '������� API �� �������������, ��������� �� �����������. ��������� �������: ��������.')

