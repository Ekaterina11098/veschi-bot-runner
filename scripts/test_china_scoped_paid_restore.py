import unittest
from unittest.mock import patch
import china_no_paid as n
import china_codex_cloud as c

class ScopedPaidRestore(unittest.TestCase):
    def policy(self):
        return dict(enabled=True,paid_api_allowed=True,chat_id=n.CHAT,bot_id=n.BOT,model='gpt-6.1-sol',transport='responses_bounded_v1',wb_action_permission=False)
    def test_exact_scoped_policy_permits_bounded_dialogue(self):
        n.require_paid_api(self.policy())
    def test_missing_foreign_unbounded_and_write_enabled_policies_block(self):
        for field,value in [('enabled',False),('paid_api_allowed',False),('chat_id',1),('bot_id',1),('model','other'),('transport','legacy'),('wb_action_permission',True)]:
            p=self.policy();p[field]=value
            with self.subTest(field=field),self.assertRaises(PermissionError):n.require_paid_api(p)
        with self.assertRaises(PermissionError):n.require_paid_api()
    def test_generation_checks_mutable_policy_before_network(self):
        class DB:
            def get(self,key):return dict(enabled=False)
        with patch('bounded_sol_dialog.BoundedSol.answer',side_effect=AssertionError('No network')):
            with self.assertRaises(PermissionError):c.Worker(DB()).generate('responses-stateless','message','test')
    def test_maintenance_instruction_does_not_authorize_wb(self):
        self.assertIn('НЕ prepare_advertising',c.INSTRUCTIONS)
        self.assertIn('тоже требует подтверждения',c.INSTRUCTIONS)

if __name__=='__main__':unittest.main()

