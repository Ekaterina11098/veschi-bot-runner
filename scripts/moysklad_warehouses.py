"""Owner-bound MoySklad stores. Names are display labels, never identity."""
BASE='https://api.moysklad.ru/api/remap/1.2'
STORE_IDS={'msk':'3c67619d-f25d-11ee-0a80-0c6f000a027a','guangzhou':'2233c6a7-d906-11f1-0a80-197e004df0d2'}
STORE_LABELS={'msk':'МСК','guangzhou':'Гуанджоу'}
def select_store(rows,role='msk'):
 if role not in STORE_IDS:raise ValueError('Unknown warehouse role')
 identity=STORE_IDS[role]
 found=[r for r in rows if r.get('id')==identity]
 if len(found)!=1:raise ValueError('Bound MoySklad warehouse missing or duplicated: '+role)
 store=found[0]
 if store.get('archived') or store.get('meta',{}).get('href')!=BASE+'/entity/store/'+identity:
  raise ValueError('Bound MoySklad warehouse archived or identity mismatch: '+role)
 return store
def exact_store_entry(entry,store):
 identity=store.get('id')
 return bool(identity and entry.get('meta',{}).get('href')==BASE+'/entity/store/'+identity)
