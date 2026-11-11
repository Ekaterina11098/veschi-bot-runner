"""Provision the existing China bot credential into encrypted Vault; never log or return it."""
import os,json
from china_loss_execute import IO
def run():
 io=IO();assert io.tg('getMe',{})['id']==8780468043
 r=io.db('rpc/china_store_bot_transport_token','POST',dict(bot_token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']))
 assert r==dict(configured=True,bot_id=8780468043)
 key='china_agent:main_menu:v1:transport_configured:2026-11-11'
 v=dict(status='verified',bot_id=8780468043,storage='encrypted_vault_service_role_only',credentials_logged=False)
 if io.get(key):io.put(key,v)
 else:assert io.create(key,v)
 print(json.dumps(v))
if __name__=='__main__':run()
