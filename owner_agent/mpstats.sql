-- Isolated read API for validated MPStats product reports, including owner-only recovery snapshots.
create function public.owner_agent_mpstats_products(args jsonb default '{}') returns jsonb
language plpgsql stable security invoker set search_path=pg_catalog,public set statement_timeout='8s' as $$
declare cab text; s public.analytics_snapshots%rowtype; p jsonb; totals jsonb; result jsonb:='[]';
 a date:=(args->>'from')::date; b date:=(args->>'to')::date;
 off integer:=greatest(0,coalesce((args->>'offset')::integer,0));
 lim integer:=least(20,greatest(1,coalesce((args->>'limit')::integer,5))); latest_day date;
begin
 if a is null or b is null or b<a or b-a>30 then raise exception 'Exact period of up to 31 days required'; end if;
 if args ? 'cabinet' and args->>'cabinet' not in ('token_1','token_2','token_3') then raise exception 'Unknown cabinet'; end if;
 foreach cab in array array['token_1','token_2','token_3'] loop
  if coalesce(args->>'cabinet','')<>'' and args->>'cabinet'<>cab then continue; end if;
  select max(period_to) into latest_day from public.analytics_snapshots where cabinet=cab and source in('mpstats_products_validated','owner_mpstats_products') and status='complete';
  select * into s from public.analytics_snapshots where cabinet=cab and source in('mpstats_products_validated','owner_mpstats_products')
   and period_from=a and period_to=b and status='complete' and payload->0->'complete'='true'::jsonb
   and jsonb_typeof(payload->0->'products')='array' order by collected_at desc,id desc limit 1;
  if not found then
   result:=result||jsonb_build_array(jsonb_build_object('cabinet',cab,'available',false,'latest_saved_period_to',latest_day,'note','Exact requested MPStats report missing. Fetch this cabinet/period; do not substitute WB orders or another period.'));
   continue;
  end if;
  p:=s.payload->0->'products';
  select jsonb_object_agg(field,jsonb_build_object('value',case when absent=0 then amount else null end,'missing_rows',absent)) into totals from (
   select field,sum(case when jsonb_typeof(v->field)='number' then (v->>field)::numeric end) as amount,
    count(*) filter(where jsonb_typeof(v->field) is distinct from 'number') as absent
   from unnest(array['views','orders','orders_count','sales_count','returns_count','sales_sum','returns_sum','for_pay','advertisement']) f(field)
   left join lateral jsonb_array_elements(p) x(v) on true group by field
  ) t;
  result:=result||jsonb_build_array(jsonb_build_object('id',s.id,'source',s.source,'cabinet',cab,'available',true,
   'period_from',s.period_from,'period_to',s.period_to,'collected_at',s.collected_at,'product_records',jsonb_array_length(p),
   'totals',totals,'products',coalesce((select jsonb_agg(v order by i) from jsonb_array_elements(p) with ordinality x(v,i) where i>off and i<=off+lim),'[]'::jsonb),
   'offset',off,'returned',greatest(0,least(lim,jsonb_array_length(p)-off)),'has_more',jsonb_array_length(p)>off+lim,
   'currency_verified',false,'own_profit_verified',false));
 end loop;
 return jsonb_build_object('source','mpstats_products_validated','period_from',a,'period_to',b,'rows',result,
  'has_more',exists(select 1 from jsonb_array_elements(result) r where r->'has_more'='true'::jsonb),'next_offset',off+lim,
  'note','Counts are sums of reported product records, including size variants, not unique business events. orders=funnel order-date cohort; orders_count=statistics orders; sales_count=sale-date sales; returns separate. Scope is the returned product catalog; excluded products may be absent. Currency and own profit require separate evidence. for_pay is NOT own net profit. Missing metrics are null.');
end $$;
revoke all on function public.owner_agent_mpstats_products(jsonb) from public,anon,authenticated;
grant execute on function public.owner_agent_mpstats_products(jsonb) to service_role;
