import os,sys,json,uuid,time
import psycopg
from psycopg import sql
from stock_deploy_support import *
def main():
    report=dict(success=False,wb_writes=0,telegram_calls=0,role=ROLE,source_commit='b1f54e3770fba9aabbe7773c2106fc6d56c92911')
    admin=None;db=None
    try:
        admin=psycopg.connect(host=HOST,port=5432,dbname='postgres',user='postgres.'+PROJECT,password=os.environ['SUPABASE_DB_PASSWORD'],sslmode='require',connect_timeout=15,application_name='owner_stock_role_provision_20261015')
        with admin.transaction():
            with admin.cursor() as cur:
                cur.execute('SET LOCAL statement_timeout=30000')
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(ROLE,))
                exists=cur.fetchone() is not None
                if not exists:
                    cur.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 3 PASSWORD {}').format(sql.Identifier(ROLE),sql.Literal(password())))
                # No role memberships; do not grant postgres/service_role.
                cur.execute('SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s',(ROLE,));assert cur.fetchone()[0]==0
                cur.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s',(ROLE,));assert cur.fetchone()==(False,)*6
                cur.execute(sql.SQL('GRANT CONNECT ON DATABASE postgres TO {}').format(sql.Identifier(ROLE)))
                cur.execute(sql.SQL('GRANT USAGE ON SCHEMA stock_execution TO {}').format(sql.Identifier(ROLE)))
                grants={'stock_runs':['SELECT','INSERT','UPDATE'],'stock_operations':['SELECT','INSERT','UPDATE'],'stock_events':['SELECT','INSERT'],'stock_sku_locks':['SELECT','INSERT','DELETE']}
                for table,privileges in grants.items():
                    cur.execute('SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass',('stock_execution.'+table,));assert cur.fetchone()==(True,)
                    cur.execute(sql.SQL('GRANT {} ON stock_execution.{} TO {}').format(sql.SQL(','.join(privileges)),sql.Identifier(table),sql.Identifier(ROLE)))
                    for privilege in privileges:
                        policy='stock_executor_'+privilege.lower()
                        cur.execute('SELECT 1 FROM pg_policies WHERE schemaname=%s AND tablename=%s AND policyname=%s',('stock_execution',table,policy))
                        if not cur.fetchone():
                            tail='USING (true) WITH CHECK (true)' if privilege=='UPDATE' else 'WITH CHECK (true)' if privilege=='INSERT' else 'USING (true)'
                            cur.execute(sql.SQL('CREATE POLICY {} ON stock_execution.{} FOR {} TO {} '+tail).format(sql.Identifier(policy),sql.Identifier(table),sql.SQL(privilege),sql.Identifier(ROLE)))
                for role in ('anon','authenticated','service_role'):
                    cur.execute("SELECT has_schema_privilege(%s,'stock_execution','USAGE')",(role,));assert cur.fetchone()==(False,)
        admin.close();admin=None
        db=runtime_db()
        with db.cursor() as cur:
            cur.execute('SELECT current_user');assert cur.fetchone()==(ROLE,)
            for table in ('stock_runs','stock_operations','stock_events','stock_sku_locks'):
                cur.execute('SELECT count(*) FROM stock_execution.'+table)
                report.setdefault('journal_counts',{})[table]=cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM stock_execution.stock_operations WHERE state='uncertain'");assert cur.fetchone()[0]>=1
            cur.execute("SELECT count(*) FROM stock_execution.stock_sku_locks WHERE article='20-furbigscarf-khaki'");assert cur.fetchone()[0]==1
            # Negative privilege checks; no arbitrary public/Auth/Storage writes or ownership/DDL.
            for schema in ('auth','storage'):
                cur.execute('SELECT has_schema_privilege(current_user,%s,\'USAGE\')',(schema,));assert cur.fetchone()==(False,)
            for table in ('stock_runs','stock_operations','stock_events'):
                cur.execute('SELECT has_table_privilege(current_user,%s,\'DELETE\')',('stock_execution.'+table,));assert cur.fetchone()==(False,)
            cur.execute("SELECT has_schema_privilege(current_user,'stock_execution','CREATE')");assert cur.fetchone()==(False,)
        db.commit()
        ident='technical:deployment-proof:'+os.environ['GITHUB_RUN_ID']
        value=json.dumps({'technical':True,'queued':False,'nonce':str(uuid.uuid4())},sort_keys=True)
        with db.transaction():
            with db.cursor() as cur:cur.execute('INSERT INTO stock_execution.stock_runs VALUES(%s,%s,%s,%s,%s,%s)',(ident,value,'{}',hashlib.sha256(b'{}').hexdigest(),'technical-no-executor',time.time()))
        with db.cursor() as cur:
            cur.execute('SELECT snapshot,origin FROM stock_execution.stock_runs WHERE id=%s',(ident,));assert cur.fetchone()==(value,'technical-no-executor')
            cur.execute('SELECT count(*) FROM stock_execution.stock_operations WHERE run=%s',(ident,));assert cur.fetchone()[0]==0
        db.commit()
        report.update(success=True,limited_login_verified=True,committed_write_readback_verified=True,negative_privileges_verified=True,uncertain_lock_retained=True,technical_run_id=ident,role_password_logged=False,dsn_persisted_in_public=False)
    except BaseException as exc:report['error']=error(exc)
    finally:
        if admin:admin.close()
        if db:db.close()
        seal('deployment',report)
    public={k:v for k,v in report.items() if k in ('success','wb_writes','telegram_calls','limited_login_verified','committed_write_readback_verified','negative_privileges_verified','uncertain_lock_retained')}
    if 'error' in report:public['error_type']=report['error']['type']
    print(json.dumps(public))
    (OUT/'deployment-summary.json').write_text(json.dumps(public))
    return 0 if report['success'] else 1
if __name__=='__main__':sys.exit(main())
