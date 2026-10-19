-- Complete retained text history; no rolling deletion or summary replaces originals.
create table public.owner_agent_messages (
 id bigint generated always as identity primary key,
 chat_id bigint not null, message_id bigint not null, revision bigint not null default 0,
 sender_id bigint not null, role text not null check(role in ('user','assistant')),
 thread_id bigint, reply_to_message_id bigint, content text not null check(length(content) between 1 and 20000),
 message_at timestamptz not null, recorded_at timestamptz not null default now(),
 correction boolean not null default false,
 search_vector tsvector generated always as (to_tsvector('russian',content)) stored,
 unique(chat_id,message_id,revision)
);
create index owner_agent_messages_chat on public.owner_agent_messages(chat_id,message_at desc,id desc);
create index owner_agent_messages_search on public.owner_agent_messages using gin(search_vector);
alter table public.owner_agent_messages enable row level security;
revoke all on public.owner_agent_messages from public,anon,authenticated;
grant select,insert on public.owner_agent_messages to service_role;
grant usage,select on sequence public.owner_agent_messages_id_seq to service_role;

create function public.owner_agent_archive_job() returns trigger language plpgsql security invoker
set search_path=pg_catalog,public as $$
begin
 insert into public.owner_agent_messages(chat_id,message_id,sender_id,role,thread_id,content,message_at,correction)
 values(new.chat_id,new.message_id,new.sender_id,'user',new.thread_id,new.request_text,new.created_at,
 new.request_text ~* '(исправ|поправ|уточн|запомни|договор|на самом деле|ошиб|неверн|впредь|всегда|теперь счита|имей в виду)')
 on conflict(chat_id,message_id,revision) do nothing;
 if new.answer is not null then
  -- Only confirmed Telegram deliveries become assistant history.
  insert into public.owner_agent_messages(chat_id,message_id,sender_id,role,thread_id,reply_to_message_id,content,message_at)
  select new.chat_id,(r->>'message_id')::bigint,c.bot_id,'assistant',new.thread_id,new.message_id,
   substring(new.answer from ((r->>'part')::integer*3500+1) for 3500),coalesce(new.completed_at,now())
  from public.owner_agent_config c,
   jsonb_array_elements(coalesce(new.delivery->'receipts','[]'::jsonb)) r
  where c.id=1
  on conflict(chat_id,message_id,revision) do nothing;
 end if;
 return new;
end $$;
revoke all on function public.owner_agent_archive_job() from public,anon,authenticated;
grant execute on function public.owner_agent_archive_job() to service_role;
create trigger owner_agent_job_archive after insert or update on public.owner_agent_jobs
for each row execute function public.owner_agent_archive_job();

-- Backfill existing requests and confirmed answers without rewriting any jobs.
insert into public.owner_agent_messages(chat_id,message_id,sender_id,role,thread_id,content,message_at,correction)
select chat_id,message_id,sender_id,'user',thread_id,request_text,created_at,
 request_text ~* '(исправ|поправ|уточн|запомни|договор|на самом деле|ошиб|неверн|впредь|всегда|теперь счита|имей в виду)'
from public.owner_agent_jobs on conflict do nothing;
insert into public.owner_agent_messages(chat_id,message_id,sender_id,role,thread_id,reply_to_message_id,content,message_at)
select j.chat_id,(r->>'message_id')::bigint,c.bot_id,'assistant',j.thread_id,j.message_id,substring(j.answer from ((r->>'part')::integer*3500+1) for 3500),j.completed_at
from public.owner_agent_jobs j cross join public.owner_agent_config c,
 jsonb_array_elements(coalesce(j.delivery->'receipts','[]'::jsonb)) r
where j.status='done' and j.answer is not null and c.id=1 on conflict do nothing;

create function public.owner_agent_history(args jsonb default '{}') returns jsonb
language plpgsql stable security invoker set search_path=pg_catalog,public set statement_timeout='8s' as $$
declare result jsonb; q text:=left(coalesce(args->>'query',''),300);
 page_offset integer:=greatest(0,coalesce((args->>'offset')::integer,0));
 page_limit integer:=least(30,greatest(1,coalesce((args->>'limit')::integer,20)));
begin
 -- Exact configured group only. No caller/model-provided chat ID is accepted.
 with latest as (
  select distinct on(m.message_id) m.*
  from public.owner_agent_messages m join public.owner_agent_config c on c.chat_id=m.chat_id and c.id=1 and c.active
  where m.recorded_at<=coalesce((args->>'as_of')::timestamptz,now())
  order by m.message_id,m.revision desc,m.id desc
 ), matches as (
  select l.id,l.message_id,l.revision,l.sender_id,l.role,l.thread_id,l.reply_to_message_id,
   l.content,l.message_at,greatest(l.message_at,to_timestamp(l.revision)) as effective_at,l.correction,
   coalesce(mem.role,case when l.role='assistant' then 'assistant' else 'former_member' end) as author_role
  from latest l left join public.owner_agent_members mem on mem.user_id=l.sender_id
  where (not coalesce((args->>'corrections_only')::boolean,false) or (l.role='user' and l.correction))
   and (q='' or l.search_vector @@ websearch_to_tsquery('russian',q) or position(lower(q) in lower(l.content))>0)
   and (not(args ? 'message_id') or l.message_id=(args->>'message_id')::bigint or l.reply_to_message_id=(args->>'message_id')::bigint)
 ), page as (select * from matches order by effective_at desc,id desc limit page_limit offset page_offset)
 select jsonb_build_object('rows',coalesce((select jsonb_agg(to_jsonb(p) order by effective_at desc,id desc) from page p),'[]'::jsonb),
  'total',(select count(*) from matches),'offset',page_offset,'returned',(select count(*) from page),
  'has_more',(select count(*) from matches)>page_offset+page_limit,
  'next_offset',page_offset+page_limit,'source','group_history',
  'note','Latest message revisions. Human statements are attributed claims; assistant answers may be wrong. Later applicable human corrections supersede earlier claims. Fetch current metrics from business tools.') into result;
 return result;
end $$;
revoke all on function public.owner_agent_history(jsonb) from public,anon,authenticated;
grant execute on function public.owner_agent_history(jsonb) to service_role;
