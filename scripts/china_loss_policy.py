"""China loss decisions: explicit economics, no inferred expense zeroes."""
from decimal import Decimal
from datetime import datetime,timedelta,timezone
def number(v):
 if v is None or isinstance(v,bool):raise ValueError('Не хватает подтверждённой суммы')
 d=Decimal(str(v))
 if not d.is_finite():raise ValueError('Некорректная сумма')
 return d
def evaluate(r):
 """All monetary inputs RUB; fee is a fraction, tax per kept sale explicitly supplied.
 Unit result is only an intermediate. Objective is total expected profit for N orders.
 Logistics include direct and expected nonbuyout costs exactly once upstream.
 """
 if r.get('cabinet')!='token_3' or r.get('currency')!='RUB':raise ValueError('Кабинет/валюта не подтверждены')
 if not r.get('source_ids') or not r.get('period_from') or not r.get('period_to'):raise ValueError('Нет источника/периода')
 n=number(r.get('orders'));done=number(r.get('finished'));kept=number(r.get('kept'))
 if n<0 or done<0 or kept<0 or kept>done or any(x!=int(x) for x in [n,done,kept]):raise ValueError('Некорректные счётчики')
 p=kept/done if done else Decimal('.5')
 price=number(r.get('seller_revenue_rub'));fee=number(r.get('commission_fraction'))
 if not 0<=fee<=1 or price<=0:raise ValueError('Цена/комиссия')
 expense_ids=r['expense_ids']
 if len(expense_ids)!=len(set(expense_ids)):raise ValueError('Повторный расход')
 ad=number(r.get('advertising_rub'));order_sum=number(r.get('orders_sum_rub'))
 if ad<0 or order_sum<0:raise ValueError('Расход/заказы отрицательны')
 drr=ad/order_sum if order_sum else None
 retained=price*(1-fee)-number(r.get('own_cogs_rub'))-number(r.get('tax_per_kept_rub'))-number(r.get('other_per_kept_rub'))
 pre=p*retained-number(r.get('logistics_per_order_rub'))-number(r.get('other_per_order_rub'))
 scenario_ad=drr*price*n if r.get('ad_model')=='constant_drr' and drr is not None else ad
 total=pre*n-scenario_ad-number(r.get('shared_confirmed_rub'))
 return dict(buyout_percent=float(p*100),buyout_source='own_completed' if done else 'fallback50_no_completed',sample_size=int(done),
  actual_drr_percent=float(drr*100) if drr is not None else None,
  expected_total_profit_rub=float(total),max_drr_percent=float(pre/price*100),
  expected_total_at5_rub=float((pre-price*Decimal('.05'))*n-number(r.get('shared_confirmed_rub'))),
  preliminary=not r.get('all_expenses_confirmed',False),method='expected_total_not_closed_cohort_profit')

POLICY='''Алгоритм Китай, решение владельца 22.10.2026.
1. Полный каталог token_3, точные article/nmID; последние30 полных дней МСК, свежесть/все страницы/охват/пропуски. Не выдавать 10 найденных за проверку всех без аудита охвата.
2. Текущая цена после скидки продавца из WB; цена покупателя без кошелька и СПП отдельно. История купленных цен не текущая цена.
3. Выкуп только собственный по завершённым заказам, незавершённые исключить. Источник/когорта/дата/count обязательны. 50% только нет своей завершённой статистики, с пометкой. Малый N и0% не доказанный устойчивый убыток.
4. ДРР=полный рекламный расход / сумма заказов до скидокWB одной валюты/периода. При0 суммы не определена; расход остаётся. Рекламная атрибуция и заказыWB отдельны, точный источник конкретного ID не выдумывать.
5. СобственнаяCOGS, фактическая комиссия, налог с проверенной базой, логистика отправки/отказа/возвратаРФ, приёмка/эквайринг/удержания. Расходы в netpayout повторно не вычитать. MPStats returns_sum отрицателен: net_sales=sales_sum+returns_sum. ВозвратРФ включён в тариф — не начислять повторно. Unknown не0; общий резерв19329.76 не постоянный расход и возможен дубльWBPromotion.
6. Разделять фактическую прибыль реализации (проверенный for_pay минус собственнаяCOGSнетто и свой налог без повторной рекламы) и ожидаемую при текущихценах/выкупе. Курс12 только согласованная ценовая модель; не для конвертации фактического bidder. Налог5%/комиссия20% старой таблицы — сценарий, не подтверждённый универсальный тариф; историческое правило Китай0% не менять молча.
7. Ожидаемая общая прибыль=sum[p*вкладвыкупа+(1-p)*вкладневыкупа]−реклама−подтверждённыеобщиерасходы. Прибыль на заказ только промежуточная арифметика, НЕ критерий отбора. Сравнивать общую прибыль, заказы, конверсию за равные полные периоды; после изменения4 полных дня, деньизмененияисключить. Не менять одновременноцену/рекламу/контент без отдельного плана.
8. Причина кратко: выкуп ниже исходных50%, ДРР выше5%; первопричину поведения не выдумывать. Диагностировать карточку, вопросы/отзывы точногоSKU, цены/конкурентов, запросы ипозицииWB/MPStats. Не предлагать управлять одинаковой неуправляемой доставкойКитая.
9. Рассчитать запас на рекламу после всех подтверждённых расходов. ДРР5% не всегда выводитвноль; дажеДРР0можетоставлятьминус. Для119 цельраспродаживноль иожидание23Octсохранены. Неполнаяэкономика→предварительныйрезультат,небезопасныйлимит.
10. Каждыйпунктплана:точныеSKU/РК,источник/время,старое→новое,ограничения/риски,готовиликонкретнонехватает. ДРРцель не являетсянастройкойWB; сначала самостоятельно получить запросы/кампании/минимумы, потом точнаяставка/исключениеSKU. ОбщуюРКрадиодногоSKUнеостанавливать.
11. Публиковать PNG:Артикул|Что влияет|Рекомендации. Не добавлять «Показатели», «При50%» или «Безубыток» без запроса. Прибыль можноиспользоватьврасчётебезвыдуманнойточности.
12. «Сделайвсё» владельца через ответнапоследнийплан запускаетвсеготовыепунктыэтогоплана. Неизвестные/неполныепункты не блокируют независимыеготовые. Точныенедостающиезамеры/фото/материалыспроситьвТГ;доступныеAPIданныеполучитьсамостоятельно. Фото/текстотчёта не самостоятельное разрешение. Цены сейчасзаморожены;119неизменятьдо23Oct. Каждаяоперацияимеетидентичность/CAS/квитанцию/проверкуWB;uncertainнеповторятьвслепую.
13. ИтогвТГ:выполнено(провереноWB),принятоWBожидаетпроверки,неудалось/нужныданныепоартикулу. Непроверенноенеобъявлятьвыполненным. Неисполнятьстарыеочереди/чужиекабинеты;обычныйвопрос неавторизация. Послеуточнения продолжатьтолькосогласованныйпункт,существенноеизменениеплана требуетновогоподтверждения.
'''
