"""Independent morning question cards; never publishes unapproved answers."""
import contextlib,io,json
from review_morning import main
if __name__=='__main__':
    hidden=io.StringIO()
    try:
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):result=main(kind='questions')
        print(json.dumps(result))
    except Exception as exc:
        from stock_deploy_support import seal,error
        seal('questions-morning-error',{'error':error(exc),'private_log':hidden.getvalue()})
        print('Morning questions failed; protected diagnostic saved.');raise SystemExit(1)
