"""China review collection only; WB writes stay in the approved publisher."""
import contextlib,io,json,time
def run(collect,sleep=time.sleep,clock=time.monotonic):
    deadline=clock()+35*60
    result={'status':'not_started'}
    while clock()<deadline:
        result=collect(kind='feedbacks',china_two_hour=True)
        if result.get('status') in ('complete','already_complete'):return result
        sleep(60)
    return result

def run_all(collect,sleep=time.sleep,clock=time.monotonic):
    """Independent durable receipts for both kinds; never repeat completed scope."""
    deadline=clock()+35*60
    results={}
    while clock()<deadline:
        for kind in ('feedbacks','questions'):
            if results.get(kind,{}).get('status') in ('complete','already_complete'):continue
            results[kind]=collect(kind=kind,china_two_hour=True)
        if all(results.get(k,{}).get('status') in ('complete','already_complete') for k in ('feedbacks','questions')):
            return dict(status='complete',scopes=results)
        sleep(60)
    return dict(status='incomplete',scopes=results)

if __name__=='__main__':
    from review_morning import main
    output=io.StringIO()
    try:
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
            result=run_all(main)
        print(json.dumps(result))
        if result.get('status') not in ('complete','already_complete'):
            raise RuntimeError('China collection remains incomplete; durable checkpoints retained')
    except Exception as exc:
        from stock_deploy_support import seal,error
        seal('reviews-china-two-hour-error',dict(error=error(exc),private_log=output.getvalue()))
        print('China review collection incomplete; protected diagnostics saved.')
        raise SystemExit(1)
