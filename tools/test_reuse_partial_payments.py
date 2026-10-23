from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine,StateCodecError
import trainer_xp_payments as XP
import composition_reconcile as COMPOSITION


class TrainerXPPaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,seed=7)
        self.c=Combatant(self.r,build_trainer(self.r,'Trainer',5,
            {'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},extra={'exp_bank':5}))
        self.e.everyone=self.e.gm.everyone=[self.c]

    def pay(self,kind='edge',request='retrain',policy='before_use'):
        return self.e.pay_trainer_retraining(self.c,kind,request_id=request,
            reason='explicit retraining',refund_policy=policy)

    def test_actual_bank_debit_preserves_level_and_replays_after_json(self):
        result=self.pay('feature')
        self.assertEqual((self.c.spec['exp_bank'],self.c.level),(3,5))
        self.assertEqual((result['bank_before'],result['bank_after']),(5,3))
        e=load_engine(self.r,dump_engine(self.e));c=e.everyone[0]
        before=dump_engine(e)
        self.assertEqual(e.pay_trainer_retraining(c,'feature',request_id='retrain',
            reason='explicit retraining',refund_policy='before_use'),result)
        self.assertEqual(dump_engine(e),before)

    def test_insufficient_bank_never_borrows_a_level_or_rng(self):
        self.c.spec['exp_bank']=0
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'levels cannot'):
            self.pay()
        self.assertEqual(dump_engine(self.e),before)

    def test_same_request_cannot_change_amount_or_refund_policy(self):
        self.pay();before=dump_engine(self.e)
        with self.assertRaises(ValueError):self.pay('feature')
        with self.assertRaises(ValueError):self.pay(policy='none')
        self.assertEqual(dump_engine(self.e),before)

    def test_cancel_refunds_actual_amount_once_without_leveling(self):
        self.pay('feature')
        result=self.e.refund_trainer_xp_payment(self.c,'retrain',reason='cancel before use')
        self.assertEqual((self.c.spec['exp_bank'],self.c.level),(5,5))
        before=dump_engine(self.e)
        self.assertEqual(self.e.refund_trainer_xp_payment(self.c,'retrain',reason='cancel before use'),result)
        self.assertEqual(dump_engine(self.e),before)
        with self.assertRaises(ValueError):self.e.refund_trainer_xp_payment(self.c,'retrain',reason='changed')

    def test_used_and_explicit_no_refund_payments_cannot_refund(self):
        self.pay();self.e.commit_trainer_xp_payment(self.c,'retrain',event_id='actual retraining')
        self.pay(request='second',policy='none');before=dump_engine(self.e)
        for identity in ('retrain','second'):
            with self.assertRaises(ValueError):self.e.refund_trainer_xp_payment(self.c,identity,reason='cancel')
        self.assertEqual(dump_engine(self.e),before)

    def test_late_failure_rolls_back_debit_receipt_and_rng(self):
        before=dump_engine(self.e)
        with patch.object(COMPOSITION,'reconcile',side_effect=ValueError('late failure')):
            with self.assertRaisesRegex(ValueError,'late failure'):self.pay()
        self.assertEqual(dump_engine(self.e),before)

    def test_corrupt_saved_bank_receipt_is_rejected(self):
        self.pay();self.c.spec[XP.KEY]['retrain']['result']['bank_after']=5
        with self.assertRaises(StateCodecError):dump_engine(self.e)

    def test_unknown_source_cannot_debit(self):
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):
            XP.spend(self.e,self.c,1,source='missing/source',reason='retrain',
                     request_id='missing',refund_policy='none')
        self.assertEqual(dump_engine(self.e),before)

    def test_cost_comes_from_selected_progression_policy(self):
        self.assertEqual(self.pay('feature')['amount'],self.r.mech('trainer/experience')['retrain_cost']['feat'])
        self.assertEqual(self.pay('stat_point',request='stat')['amount'],self.r.mech('trainer/experience')['retrain_cost']['stat_point'])


if __name__=='__main__':unittest.main()
