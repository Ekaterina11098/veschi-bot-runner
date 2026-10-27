"""Dated manual funding context; no network, marketplace writes or sends."""
import math,re
from datetime import datetime,timezone
KEY='china_agent:manual_budget_recommendations:v1'
RULES=('Бюджет и эффективность разделять. Сегодняшний ДРР или отсутствие заказов в неполный день '
'не являются самостоятельным основанием отказать в резерве согласованного теста. '
'Оценка эффективности — только полные дни после последнего verified изменения; исторический расход сохранять. '
'Не гарантировать ДРР5%. Недостаточная экономика — конкретный пробел, не достаточный остаток. '
'Действующие согласованные суммы из manual_budget_context учитывать с датой и сроком; '
'после ручного пополнения не предлагать старую сумму повторно. '
'Пополняет владелец вручную. Ничего не переводить, не просить сумму заново, если она уже есть в действующей рекомендации. '
'О поступлении денег утверждать только по датированному WB срезу; автор ручного пополнения — по заявлению владельца.')

def read_context(get,now):
 p=get(KEY) or {}
 try:
  start=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'))
  end=datetime.fromisoformat(p['valid_until'].replace('Z','+00:00'))
  if p.get('status')!='active' or p.get('mode')!='manual_only' or not start<=now<end:return {}
 except (KeyError,TypeError,ValueError):return {}
 return dict(p,execution_authorized=False,automatic_funding=False)

def dialog_context(w,job,reply_text=''):
 text=job.get('request_text','')+' '+reply_text
 if job.get('agent_id','china')!='china' or job.get('chat_id')!=-1004342917488 or not re.search(r'бюджет|пополн|денег|деньги',text,re.I):return {}
 return read_context(w.get,w.now) or dict(available=False,reason='Нет действующей датированной суммы; использовать рабочую память и назвать пробел',wb_reads=0,automatic_funding=False)

def decision(cid,assessment,economics,context,balance):
 r=context.get('campaigns',{}).get(str(cid),{})
 try:
  reviewed=float(r['balance_at_review'])
  amount=float(r['remaining_manual_cny'])
  valid=math.isfinite(amount) and amount>0 and math.isfinite(reviewed) and balance<=reviewed+1 and r.get('status')=='pending_manual'
 except (KeyError,TypeError,ValueError):valid=False
 if valid:
  return (f"Согласованная рекомендация: пополнить вручную на {amount:.0f} CNY. "
          f"Срез рекомендации {context.get('observed_at')}; срок {context.get('valid_until')}. "
          "Резерв для продолжения согласованного теста; эффективность ещё не подтверждена. "
          "ДРР неполного дня не отменяет эту рекомендацию.")
 if r.get('status')=='manual_funded' or r and balance>r.get('balance_at_review',balance)+1:
  return "После рекомендации баланс изменился. Старую сумму повторно не вносить; новый резерв рассчитать по свежему остатку и расходу."
 rate=assessment.get('drr_3days')
 if economics.get('all_costs_confirmed') is True and economics.get('expected_total_profit_cny',-1)>0 and rate is not None and rate<=5:
  return f"Предварительный резерв: {assessment['proposed']:.0f} CNY до следующего среза; ручное пополнение. Подтверждённость периода после последнего изменения проверить отдельно."
 return ("Есть риск окончания бюджета. Сегодня неполный день: его ДРР не доказывает провал теста. "
         "Точная новая сумма не согласована: нужны полные дни после последнего verified изменения и актуальная экономика оставшихся SKU. "
         "Недостаток этих данных не означает, что денег хватает.")
