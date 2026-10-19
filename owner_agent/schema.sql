-- Additive, isolated owner agent. Existing agents, functions and grants unchanged.
begin;
create table public.owner_agent_setup (
 id smallint primary key check(id=1), payload jsonb not null, observed_at timestamptz not null default now()
);
alter table public.owner_agent_setup enable row level security;
revoke all on public.owner_agent_setup from public,anon,authenticated;
grant select,insert,update,delete on public.owner_agent_setup to service_role;
create table public.owner_agent_config (
 id smallint primary key check(id=1), chat_id bigint not null check(chat_id<0),
 bot_id bigint not null check(bot_id>0), bot_username text not null check(bot_username='veschi_owner_ai_bot'),
 active boolean not null default false, secret_digest text check(secret_digest is null or secret_digest ~ '^[a-f0-9]{64}$'), created_at timestamptz not null default now()
);
create table public.owner_agent_members (
 user_id bigint primary key check(user_id>0), role text not null check(role in ('owner','observer')),
 active boolean not null default true
);
create table public.owner_agent_jobs (
 id bigint generated always as identity primary key,
 update_id bigint not null unique, chat_id bigint not null, sender_id bigint not null,
 message_id bigint not null, thread_id bigint, request_text text not null check(length(request_text) between 1 and 4000),
 status text not null default 'pending' check(status in ('pending','running','done','failed','uncertain')),
 answer text, evidence jsonb not null default '[]', delivery jsonb not null default '{}',
 lease_token uuid, created_at timestamptz not null default now(), completed_at timestamptz, error text
);
create index owner_agent_jobs_history on public.owner_agent_jobs(chat_id,id desc);
alter table public.owner_agent_config enable row level security;
alter table public.owner_agent_members enable row level security;
alter table public.owner_agent_jobs enable row level security;
revoke all on public.owner_agent_config,public.owner_agent_members,public.owner_agent_jobs from public,anon,authenticated;
grant select,insert,update,delete on public.owner_agent_config,public.owner_agent_members,public.owner_agent_jobs to service_role;
revoke all on sequence public.owner_agent_jobs_id_seq from public,anon,authenticated;
grant usage,select on sequence public.owner_agent_jobs_id_seq to service_role;

-- Fixed operations only; caller privileges apply. No dynamic SQL or source writes.
create function public.owner_agent_read(operation text,args jsonb default '{}') returns jsonb
language plpgsql stable security invoker set search_path=pg_catalog,public set statement_timeout='8s'
as $$
declare
 result jsonb; snap public.analytics_snapshots%rowtype; value jsonb; rows_value jsonb;
 path text[]; off integer:=greatest(0,least(coalesce((args->>'offset')::integer,0),100000));
 lim integer:=greatest(1,least(coalesce((args->>'limit')::integer,30),100));
 fields text[]; group_field text:=coalesce(args->>'group_by',''); n integer; missing integer; meta jsonb; cab text; cancelled integer; not_cancelled integer;
begin
 if jsonb_typeof(args)<>'object' or octet_length(args::text)>12000 then raise exception 'Invalid arguments'; end if;
 if args ? 'cabinet' and args->>'cabinet' not in ('','token_1','token_2','token_3','shared') then raise exception 'Unknown cabinet'; end if;
 if operation='sources' then
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
   select source,cabinet,count(*) as snapshots,min(period_from) as earliest_period,max(period_to) as latest_period,
    max(collected_at) as latest_collection,array_agg(distinct status) as statuses
   from public.analytics_snapshots
   where (coalesce(args->>'search','')='' or position(lower(args->>'search') in lower(source))>0)
    and (coalesce(args->>'search','')<>'' or source !~ '^replay_')
    and (coalesce(args->>'cabinet','')='' or cabinet=args->>'cabinet')
   group by source,cabinet order by source,cabinet limit 1000
  ) x;
  return jsonb_build_object('rows',result,'note','Periods and collection differ; statuses do not prove payload completeness. Default excludes replay_*; search replay explicitly for archived test results. Limited to 1000 source/cabinet pairs.');
 elsif operation='order_snapshot_counts' then
  if coalesce(args->>'from','')='' or coalesce(args->>'to','')='' then raise exception 'Exact period required'; end if;
  result:='[]'::jsonb;
  foreach cab in array array['token_1','token_2','token_3'] loop
   if coalesce(args->>'cabinet','')<>'' and cab<>args->>'cabinet' then continue; end if;
   select * into snap from public.analytics_snapshots where source='orders' and cabinet=cab and status='complete'
    and period_from=(args->>'from')::date and period_to=(args->>'to')::date and jsonb_typeof(payload)='array'
    order by collected_at desc,id desc limit 1;
   if not found then
    result:=result||jsonb_build_array(jsonb_build_object('cabinet',cab,'available',false,'rows_all',null,'cancelled',null,'not_cancelled',null,'note','No completed exact-period orders snapshot. Unknown, not zero.'));
    continue;
   end if;
   select count(*) filter(where v->'isCancel'='true'::jsonb),count(*) filter(where v->'isCancel'='false'::jsonb),
    count(*) filter(where v->'isCancel' is null or jsonb_typeof(v->'isCancel')<>'boolean')
    into cancelled,not_cancelled,missing from jsonb_array_elements(snap.payload) a(v);
   result:=result||jsonb_build_array(jsonb_build_object('id',snap.id,'source','orders','cabinet',cab,'available',true,'period_from',snap.period_from,'period_to',snap.period_to,'collected_at',snap.collected_at,
    'rows_all',jsonb_array_length(snap.payload),'cancelled',case when missing=0 then cancelled else null end,'not_cancelled',case when missing=0 then not_cancelled else null end,'missing_cancel_status',missing));
  end loop;
  return jsonb_build_object('source','orders','period_from',args->>'from','period_to',args->>'to','rows',result,'note','One latest completed exact-period snapshot per cabinet, never summed revisions. Record counts, not revenue, buyouts or deduplicated business events.');
 elsif operation='snapshots' then
  if coalesce(args->>'source','')='' then raise exception 'Exact source required'; end if;
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
   select id,source,cabinet,period_from,period_to,collected_at,status,run_id,
    jsonb_typeof(payload) as payload_type,octet_length(payload::text) as payload_bytes,
    case when jsonb_typeof(payload)='object' then payload->>'batch_id' end as batch_id
   from public.analytics_snapshots where source=args->>'source'
    and (coalesce(args->>'cabinet','')='' or cabinet=args->>'cabinet')
    and (coalesce(args->>'from','')='' or period_to>=(args->>'from')::date)
    and (coalesce(args->>'to','')='' or period_from<=(args->>'to')::date)
   order by collected_at desc,id desc limit 101 offset off
  ) x;
  return jsonb_build_object('rows',coalesce((select jsonb_agg(v) from jsonb_array_elements(result) with ordinality a(v,i) where i<=100),'[]'),
   'has_more',jsonb_array_length(result)>100,'next_offset',off+100,'note','Overlapping snapshots are revisions, not additive. Inspect all batch pages.');
 elsif operation in ('read_snapshot','aggregate_snapshot','count_snapshot') then
  select * into snap from public.analytics_snapshots where id=(args->>'id')::bigint;
  if not found then raise exception 'Snapshot not found'; end if;
  select coalesce(array_agg(t),'{}') into path from jsonb_array_elements_text(coalesce(args->'path','[]')) t;
  if cardinality(path)>12 then raise exception 'Path too deep'; end if;
  value:=case when cardinality(path)=0 then snap.payload else snap.payload#>path end;
  meta:=jsonb_build_object('id',snap.id,'source',snap.source,'cabinet',snap.cabinet,'period_from',snap.period_from,'period_to',snap.period_to,
   'collected_at',snap.collected_at,'status',snap.status,'run_id',snap.run_id,'path',path,'value_type',jsonb_typeof(value));
  if value is null or jsonb_typeof(value)='null' then
   return meta||jsonb_build_object('error','JSON path has no value. Not zero.','root_type',jsonb_typeof(snap.payload),'hint','If root_type=array, use path=[]; never invent a source-named key.');
  end if;
  if operation='count_snapshot' then
   if jsonb_typeof(value) is distinct from 'array' then raise exception 'Array path required'; end if;
   if jsonb_typeof(coalesce(args->'filters','{}'))<>'object' then raise exception 'Filters must be object'; end if;
   select count(*) into n from jsonb_array_elements(value) a(v)
    where not exists(select 1 from jsonb_each_text(coalesce(args->'filters','{}')) f where v#>>string_to_array(f.key,'.') is distinct from f.value);
   select count(*) into missing from jsonb_array_elements(value) a(v)
    where exists(select 1 from jsonb_each_text(coalesce(args->'filters','{}')) f where v#>>string_to_array(f.key,'.') is null);
   return meta||jsonb_build_object('count',case when missing=0 then n else null end,'observed_matches',n,'missing_filter_rows',missing,'source_array_rows',jsonb_array_length(value),'filters',coalesce(args->'filters','{}'),
    'note','Exact count inside this snapshot, not proof of business scope or batch completeness.');
  end if;
  if operation='read_snapshot' then
   if jsonb_typeof(value)='array' then
    n:=jsonb_array_length(value);
    select coalesce(jsonb_agg(v order by i),'[]') into rows_value from jsonb_array_elements(value) with ordinality a(v,i) where i>off and i<=off+lim;
    result:=meta||jsonb_build_object('rows',rows_value,'total',n,'offset',off,'returned',jsonb_array_length(rows_value),'has_more',off+lim<n);
   else result:=meta||jsonb_build_object('value',value); end if;
   if octet_length(result::text)>50000 then
    return meta||jsonb_build_object('too_large',true,'hint','Narrow path or read with limit=1; no rows returned.',
     'keys',case when jsonb_typeof(value)='object' then (select jsonb_agg(k) from jsonb_object_keys(value) k) else null end);
   end if;
   return result;
  end if;
  if jsonb_typeof(value) is distinct from 'array' then raise exception 'Array path required'; end if;
  if jsonb_array_length(value)>200000 then raise exception 'Array too large; narrow scope'; end if;
  select array_agg(t) into fields from jsonb_array_elements_text(args->'fields') t;
  if fields is null or cardinality(fields) not between 1 and 12 then raise exception '1 to 12 fields required'; end if;
  if jsonb_typeof(coalesce(args->'filters','{}'))<>'object' then raise exception 'Filters must be object'; end if;
  with filtered as (
   select v from jsonb_array_elements(value) a(v)
   where not exists(select 1 from jsonb_each_text(coalesce(args->'filters','{}')) f where v#>>string_to_array(f.key,'.') is distinct from f.value)
  ), cells as (
   select case when group_field='' then 'all' else coalesce(v#>>string_to_array(group_field,'.'),'<missing>') end as group_value,
    f as field,case when jsonb_typeof(v#>string_to_array(f,'.'))='number' then (v#>>string_to_array(f,'.'))::numeric end as number
   from filtered cross join unnest(fields) f
  ), totals as (
   select group_value,field,count(*) as rows,count(number) as known,count(*)-count(number) as missing,sum(number) as sum
   from cells group by group_value,field
  ) select coalesce(jsonb_agg(to_jsonb(t)),'[]') into result from (select * from totals order by group_value,field limit 1001) t;
  if jsonb_array_length(result)>1000 then raise exception 'Too many groups; narrow filters'; end if;
  return meta||jsonb_build_object('aggregates',result,'source_array_rows',jsonb_array_length(value),'filters',coalesce(args->'filters','{}'),
   'note','One exact snapshot only. Missing retained. Does not certify period, currency, pagination, identity or business completeness.');
 elsif operation='economics' then
  if coalesce(args->>'from','')='' or coalesce(args->>'to','')='' then raise exception 'Exact period required'; end if;
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
   select distinct on(cabinet,nm_id,period_from,period_to) cabinet,nm_id,article,period_from,period_to,as_of_date,
    net_units,seller_for_pay,cost_per_unit,cogs,tax_reserve,advertising_spend,net_profit,net_margin_pct,economics_status,
    finance_complete,advertising_complete,source_run_id,updated_at
   from public.advertising_sku_economics_daily
   where period_from=(args->>'from')::date and period_to=(args->>'to')::date
    and (coalesce(args->>'cabinet','')='' or cabinet=args->>'cabinet')
    and (coalesce(args->>'article','')='' or article=args->>'article')
   order by cabinet,nm_id,period_from,period_to,updated_at desc,id desc limit 101 offset off
  ) x;
 elsif operation='costs' then
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
   select article,cost,observed_at,source from public.analytics_costs
   where coalesce(args->>'article','')='' or position(lower(args->>'article') in lower(article))>0
   order by article limit 101 offset off
  ) x;
 elsif operation='ozon' then
  if coalesce(args->>'from','')='' or coalesce(args->>'to','')='' then raise exception 'Period required'; end if;
  select coalesce(jsonb_agg(to_jsonb(x)),'[]') into result from (
   select account,report_date,source,sku,query_text,offer_id,name,metrics,missing_fields,run_id,updated_at
   from public.ozon_analytics_daily where report_date between (args->>'from')::date and (args->>'to')::date
    and (coalesce(args->>'source','')='' or source=args->>'source') and (coalesce(args->>'sku','')='' or sku=args->>'sku')
   order by report_date,source,sku,query_text,run_id limit 101 offset off
  ) x;
 else raise exception 'Operation forbidden';
 end if;
 return jsonb_build_object('rows',coalesce((select jsonb_agg(v) from jsonb_array_elements(result) with ordinality a(v,i) where i<=100),'[]'),
  'has_more',jsonb_array_length(result)>100,'next_offset',off+100,'note','Partial page; preserve source and quality flags.');
end $$;
revoke execute on function public.owner_agent_read(text,jsonb) from public,anon,authenticated;
grant execute on function public.owner_agent_read(text,jsonb) to service_role;
commit;
