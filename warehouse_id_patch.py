"""Apply only owner-approved warehouse ID binding to the pinned stock source."""
from pathlib import Path
import shutil,sys
def patch_source(root):
 path=Path(root)/'tg_agent_new.py'
 source=path.read_text(encoding='utf-8')
 old='matches = [s for s in stores if norm(s.get("name")) == norm(MS_STORE_NAME)]'
 new='matches = [select_store(stores)]'
 if old not in source and new not in source:raise ValueError('Stock source selection changed; review required')
 if old in source:
  source=source.replace(old,new,1)
  start=source.index('    expected_id =',source.index('def is_exact_ms_store_entry'))
  end=source.index('\n\ndef load_ms_stocks_dict',start)
  source=source[:start]+'    return exact_store_entry(entry, store)\n'+source[end:]
  source=source.replace('MS_STORE_NAME = os.getenv("MOYSKLAD_STORE_NAME", "МСК")','from moysklad_warehouses import select_store, exact_store_entry\nMS_STORE_NAME = "МСК"  # display label only')
  compile(source,str(path),'exec')
  path.write_text(source,encoding='utf-8')
 shutil.copyfile(Path(__file__).parent/'scripts'/'moysklad_warehouses.py',Path(root)/'moysklad_warehouses.py')
if __name__=='__main__':patch_source(sys.argv[1])
