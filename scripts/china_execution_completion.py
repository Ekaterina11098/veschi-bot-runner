"""Complete registered owner-authorized recoveries through the normal result sender."""
def complete(io,contract_key):
 contract=io.get(contract_key) or {}
 if not contract:raise ValueError('Completion contract absent')
 key=contract['execution_key'];p=contract['plan'];states=[]
 for item in p['items']:
  state=io.get(contract['state_keys'][item['id']]) or {}
  if state.get('status')!='verified':raise ValueError('Recovery not fully WB verified')
  states.append(dict(state,id=item['id']))
 e=dict(io.get(key) or {},status='verified',items=states,completion_notice=dict(
  authorization_key=contract['authorization_key'],plan=p,approval=contract['approval']))
 # AdvertisingIO saves/readbacks first, then runs the registered completion hook.
 if io.get(key):io.put(key,e)
 elif not io.create(key,e):raise ValueError('Completion execution claimed')
 from china_execution_notice import PREFIX
 result=io.get(PREFIX+p['plan_id']) or {}
 if result.get('status')!='sent' or not result.get('message_id'):
  raise RuntimeError('Completion delivery not confirmed; marketplace actions must not replay')
 return result
