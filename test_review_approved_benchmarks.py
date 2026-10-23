import sys,unittest,copy,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))
from review_telegram_approval import sha,Repository,identity
from review_approved_benchmarks import candidates,sync
class Tests(unittest.TestCase):
 def case(self,cab='token_1',kind='feedbacks'):
  ref=identity(cab,kind,'id')
  old=dict(ref=ref,version='v',texts=['original'])
  edit=dict(actor='owner',decision='revision_requested',token='old',version='v',instruction='edited')
  src=dict(rating=5 if kind=='feedbacks' else 0,text='review',pros='',cons='',article='sku')
  card=dict(ref=ref,cabinet=cab,kind=kind,item_id='id',version='v-edit-'+sha('edit:e')[:8],source=src,hashes=[sha('edited')])
  i=dict(card,id='i',card_token='new',owner_id='owner',status='confirmed',answer='edited',answer_sha256=sha('edited'),source_sha256=sha(src),created_at=1)
  return {'old':old,'new':card},{'edit:e':edit},{'i':i}
 def test_all_cabinets_and_questions(self):
  for cab in ('token_1','token_2','token_3'):
   for kind in ('feedbacks','questions'):
    c,e,i=self.case(cab,kind);out=candidates(c,e,i,'owner')
    self.assertEqual(len(out),1);self.assertEqual(out[0]['row']['edited_answer'],'edited')
    self.assertEqual(out[0]['kind'],kind)
 def test_unapproved_bad_hash_foreign_and_automatic_excluded(self):
  for change in ({'status':'blocked'},{'owner_id':'other'},{'authorization_channel':'automatic_policy'},{'answer_sha256':'wrong'},{'version':'different'}):
   c,e,i=self.case();i['i'].update(change);self.assertEqual(candidates(c,e,i,'owner'),[])
  c,e,i=self.case();e['edit:e']['actor']='other';self.assertEqual(candidates(c,e,i,'owner'),[])
  c,e,i=self.case();e['edit:e']['instruction']='unapproved';self.assertEqual(candidates(c,e,i,'owner'),[])
 def test_latest_approved_version_wins(self):
  c,e,i=self.case();c['old2']=dict(c['old'],version=c['new']['version'])
  e['edit:e2']=dict(e['edit:e'],token='old2',version=c['new']['version'],instruction='edited again')
  c['new2']=dict(c['new'],version=c['new']['version']+'-edit-'+sha('edit:e2')[:8],hashes=[sha('edited again')])
  i['i2']=dict(i['i'],id='i2',card_token='new2',version=c['new2']['version'],answer='edited again',answer_sha256=sha('edited again'),created_at=2)
  out=candidates(c,e,i,'owner');self.assertEqual(len(out),1);self.assertEqual(out[0]['intent_id'],'i2')
 def test_idempotence_readback_and_retry(self):
  repo=Repository(sqlite3.connect(':memory:'));repo.setup()
  c,e,i=self.case()
  for table,data in [('cards',c),('events',e),('intents',i)]:
   for k,v in data.items():repo.put(table,k,v)
  repo.conn.commit();before=copy.deepcopy(repo.get('intents','i'));saved={};calls=[]
  def write(row):calls.append(row);saved[row['feedback_id']]=row
  self.assertEqual(sync(repo,'owner',write,saved.get)['saved'],1)
  self.assertEqual(sync(repo,'owner',write,saved.get)['existing'],1)
  self.assertEqual(len(calls),1);self.assertEqual(repo.get('intents','i'),before)
  repo.put('events','approved-benchmark:i',{});repo.conn.commit()
  self.assertEqual(sync(repo,'owner',write,lambda _:None,clock=lambda:1)['errors'],1)
  self.assertEqual(repo.get('events','approved-benchmark:i')['status'],'retry')
if __name__=='__main__':unittest.main()
