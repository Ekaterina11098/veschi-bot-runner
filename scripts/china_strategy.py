"""Owner-approved China strategy31Oct. Recommendations only, never WB permission."""
import math
KEY='china_agent:strategy:v1'
TARGET_DRR_PCT=5
RULES=('Принятая стратегия владельца: единый целевой потолок ДРР5% для всех товаров; собственная экономика может требовать меньшего значения. '
'ДРР=sumрасход/sumатрибутированная сумма заказов; ноль заказов означает неопределённую ДРР. '
'Если расходы есть, а заказов нет, обязательно оцени накопленный расход, клики, завершённые дни после verified изменения, собственную экономику и согласованный предел теста. '
'Рассмотри снижение ставки до проверенного допустимого уровня или исключение SKU из конкретной РК; не оправдывай бесконечный расход малой выборкой. '
'Продолжение расходного теста без заказов обоснуй положительной предварительной экономикой и действующим явно согласованным остатком риска; предложенный моделью лимит не согласованный бюджет. '
'Превышение5% не разрешает обычное расширение/пополнение только потому, что экономика положительная. Исключение — отдельно согласованный ограниченный тест; цель5% сохраняется. '
'Для рекомендаций используй завершённые дни после изменения, исключая день изменения; сегодняшний неполный день только сигнал диагностики. '
'Проверяй текущие состав/ставку/минимум/шаг/цену/COGS/stock-reserve, память экспериментов и исполнений. '
'Позиция — диагностика, цель — ожидаемая прибыль при ограниченном риске. Не менять карточку без конкретного подтверждения проблемы; доставка внешнее условие. '
'Резерв бюджета —3 завершённых дня, учитывать фактический остаток и уже выполненные пополнения. '
'Если РК сначала требует снижения ставок/исключения SKU, в столбце рекомендованной суммы добавь «после исполнения рекомендаций РК». Сумму владелец может согласовать сейчас; для фактического пополнения одного согласия с мерами недостаточно: сверить WBverified исполнение, оставшийся состав, свежий баланс и экономику; пересчитать сумму. После нового изменения — полный следующий день либо отдельно согласованный ограниченный резерв теста. '
'Снижение/исключение только рекомендация до отдельного подтверждённого плана; никаких автоматических WB действий, пополнений или пауз.')

def number(x):return type(x) in (int,float) and math.isfinite(x) and x>=0

def review(traffic,economics,campaign,eligible_dates,inputs_verified=False,approved_risk_remaining_cny=None,approved_exception=False):
 out=dict(target_drr_pct=TARGET_DRR_PCT,execution_authorized=False,wb_writes=0,action=None,requires_review=False)
 spend,orders,amount=(traffic.get(k) for k in ['spend','orders','amount'])
 if not number(spend) or not number(orders):return dict(out,status='unknown_counters',reason='Расход/заказы неполны; неизвестное не0')
 zero=spend>0 and orders==0
 rate=100*spend/amount if orders>0 and number(amount) and amount>0 else None
 out.update(drr_pct=rate,zero_orders_with_spend=zero)
 high=rate is not None and rate>TARGET_DRR_PCT
 if not zero and not high:return dict(out,status='within_target_or_no_spend')
 out['requires_review']=True
 if not eligible_dates:return dict(out,status='await_completed_day',reason='Сегодняшний неполный день/день изменения не основание для снижения или исключения')
 if not inputs_verified:return dict(out,status='verify_inputs',reason='Обязательная проверка текущих условий/истории перед снижением или исключением')
 pre=economics.get('pre_ad_per_order_cny')
 if not economics.get('available') or type(pre) not in (int,float) or not math.isfinite(pre):return dict(out,status='verify_economics',reason='Проверить собственную экономику; рассмотреть снижение ставки или исключение, продолжение не подтверждено')
 approved=number(approved_risk_remaining_cny) and approved_risk_remaining_cny>0
 if pre>0 and approved and (zero or approved_exception):
  return dict(out,status='approved_bounded_test',remaining_risk_cny=approved_risk_remaining_cny,reason='Продолжение только в пределах явно согласованного остатка теста; это не доказанная эффективность и не отмена цели5%')
 if pre<=0:return dict(out,status='exclude_proposal',action='exclude_sku_recommendation',reason='Предварительная экономика не оставляет запаса на рекламу; предложить исключение из этой РК')
 old,minimum,step=(campaign.get(k) for k in ['bid_minor','minimum_minor','step_minor'])
 if campaign.get('payment_type')!='cpc' or campaign.get('currency')!='CNY' or any(type(v)is not int or v<=0 for v in [old,minimum,step]) or old<minimum:
  return dict(out,status='verify_bid_limits',reason='Проверить ставку/минимум/шаг; рассмотреть снижение или исключение без выдуманной ставки')
 if old>minimum:return dict(out,status='lower_proposal',action='lower_bid_recommendation',old_minor=old,target_minor=minimum,reason='Расход без заказов' if zero else 'ДРР завершённого периода выше общего потолка5%')
 return dict(out,status='exclude_proposal',action='exclude_sku_recommendation',reason='Ставка уже на минимуме; предложить исключение SKU из этой РК, чтобы ограничить дальнейшие расходы. Это не доказательство отсутствия спроса')

