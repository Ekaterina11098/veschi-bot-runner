import shutil,tempfile,unittest
from pathlib import Path
from datetime import datetime
from china_price_due import in_window
from install_china_codex_price import install

class Install(unittest.TestCase):
    def test_agreed_time_windows(self):
        for mode,h,m,expected in [('morning',10,29,False),('morning',10,30,True),('morning',11,15,True),('morning',11,16,False),('intraday',14,59,False),('intraday',15,0,True),('intraday',15,45,True),('intraday',15,46,False)]:
            self.assertEqual(in_window(datetime(2026,11,9,h,m),mode),expected)
    def test_install_idempotent_preserves_existing_guards(self):
        base=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root=Path(tmp);(root/'china_agent').mkdir()
            shutil.copyfile(base/'cloud_migration3/pinned/china_agent/daily_report_worker.py',root/'china_agent/daily_report_worker.py')
            shutil.copyfile(base/'five-percent/sandbox/china_agent/demand.py',root/'china_agent/demand.py')
            install(root);first=(root/'china_agent/daily_report_worker.py').read_text(encoding='utf8')
            compile(first,'worker','exec')
            self.assertIn('WB operation forbidden',first)
            self.assertIn('from china_price_delivery import deliver',first)
            self.assertIn('retire_terminal_owner_cancelled_notice_v1',(root/'china_agent/demand.py').read_text(encoding='utf8'))
            install(root);self.assertEqual(first,(root/'china_agent/daily_report_worker.py').read_text(encoding='utf8'))
if __name__=='__main__':unittest.main()

