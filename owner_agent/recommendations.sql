-- Read-only, complete-catalog SKU signals; not an own-profit ranking or execution queue.
create function public.owner_agent_product_candidates(args jsonb) returns jsonb
language plpgsql stable security invoker set search_path=pg_catalog,public set statement_timeout='12s' as $$
declare result jsonb; a date:=(args->>'from')::date; b date:=(args->>'to')::date;
 pa date:=(args->>'previous_from')::date; pb date:=(args->>'previous_to')::date;
begin
 if a is null or b is null or pa is null or pb is null or b-a not between 0 and 30 or pb-pa<>b-a then raise exception 'Equal exact windows required'; end if;
 if args ? 'cabinet' and args->>'cabinet' not in ('token_1','token_2','token_3') then raise exception 'Unknown cabinet'; end if;
 with windows as (select 'current' as slot,a as first,b as last union all select 'previous',pa,pb),
 latest as (
  select distinct on(s.cabinet,w.slot) s.id,s.cabinet,s.period_from,s.period_to,s.collected_at,w.slot,s.payload->0->'products' as products
  from public.analytics_snapshots s join windows w on s.period_from=w.first and s.period_to=w.last
  where s.source in('mpstats_products_validated','owner_mpstats_products') and s.status='complete'
   and s.cabinet in('token_1','token_2','token_3') and (not(args ? 'cabinet') or s.cabinet=args->>'cabinet')
   and s.payload->0->'complete'='true'::jsonb and jsonb_typeof(s.payload->0->'products')='array'
  order by s.cabinet,w.slot,s.collected_at desc,s.id desc
 ), expanded as (
  select l.id,l.cabinet,l.slot,p from latest l cross join lateral jsonb_array_elements(l.products) p
  where p->>'nm_id' ~ '^\d+$' and length(coalesce(p->>'article',''))>0
 ), sums as (
  select id,cabinet,slot,p->>'nm_id' as nm_id,p->>'article' as article,f.field,
   case when bool_and(jsonb_typeof(p->f.field) is not distinct from 'number') then sum(case when jsonb_typeof(p->f.field)='number' then (p->>f.field)::numeric end) else null end as amount
  from expanded cross join unnest(array['sales_count','orders_count','orders','returns_count','views','advertisement']) f(field)
  group by id,cabinet,slot,p->>'nm_id',p->>'article',f.field
 ), sku as (
  select id,cabinet,slot,nm_id,article,jsonb_object_agg(field,amount) as metrics from sums group by id,cabinet,slot,nm_id,article
 ), joined as (
  select c.cabinet,c.nm_id,c.article,c.id as current_id,p.id as previous_id,c.metrics as current_metrics,p.metrics as previous_metrics,
   (c.metrics->>'orders_count')::numeric-(p.metrics->>'orders_count')::numeric as orders_delta,
   (c.metrics->>'sales_count')::numeric-(p.metrics->>'sales_count')::numeric as sales_delta,
   array_remove(array[
    case when (c.metrics->>'orders_count')::numeric<(p.metrics->>'orders_count')::numeric then 'orders_down' end,
    case when (c.metrics->>'sales_count')::numeric<(p.metrics->>'sales_count')::numeric then 'sales_down' end,
    case when (c.metrics->>'returns_count')::numeric>0 then 'returns' end,
    case when (c.metrics->>'orders_count')::numeric>(p.metrics->>'orders_count')::numeric then 'orders_up' end,
    case when (c.metrics->>'advertisement')::numeric>0 and (c.metrics->>'sales_count')::numeric=0 then 'spend_no_sales' end
   ],null) as signals
  from sku c left join sku p on p.slot='previous' and c.cabinet=p.cabinet and c.nm_id=p.nm_id and c.article=p.article
  where c.slot='current'
 ), ranked as (
  select *,row_number() over(partition by cabinet order by greatest(coalesce(-orders_delta,0),coalesce(-sales_delta,0)) desc,
   (current_metrics->>'returns_count')::numeric desc nulls last,abs(orders_delta) desc nulls last,nm_id,article) as position
  from joined where cardinality(signals)>0
 )
 select jsonb_build_object('period_from',a,'period_to',b,'previous_from',pa,'previous_to',pb,
  'coverage',coalesce((select jsonb_agg(jsonb_build_object('id',id,'cabinet',cabinet,'slot',slot,'from',period_from,'to',period_to,'collected_at',collected_at,'records',jsonb_array_length(products))) from latest),'[]'::jsonb),
  'scanned_records',(select count(*) from expanded),'matched_skus',(select count(*) from joined where previous_id is not null),
  'candidates',coalesce((select jsonb_agg(to_jsonb(r)-'position' order by cabinet,position) from ranked r where position<=8),'[]'::jsonb),
  'note','Scans ALL rows, groups size variants by exact nm_id+article, never fills missing baseline SKU with zero. Signals are investigation priorities, not causal proof or own profit. Returns are calendar events, not a cohort rate. Spend is not budget, for_pay is not profitability. No automatic changes.') into result;
 return result;
end $$;
revoke all on function public.owner_agent_product_candidates(jsonb) from public,anon,authenticated;
grant execute on function public.owner_agent_product_candidates(jsonb) to service_role;

