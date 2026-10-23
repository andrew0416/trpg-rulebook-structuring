"""Complete ready original state clauses through the existing native consumers."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from state_codec import dump_engine,load_engine
import test_reuse_partial_payments as PAY
import test_reuse_partial_party as PARTY
import test_reuse_partial_terrain as TERRAIN_FIX
import map_terrain as MAP
import movement_actions as MOVE
import state_grants as GRANTS


class ReopenedCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def restore(self):return load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))

    def test_retraining_spends_only_bank_and_retains_earned_level_entitlements(self):
        PAY.TrainerXPPaymentTests.setUp(self)
        amount=self.r.mech('trainer/experience')['exp_per_level']+3
        self.e.award_trainer_progression(self.c,kind='experience',amount=amount,
            request_id='earned-level',reason='actual earned experience')
        self.assertEqual(self.c.level,6)
        earned=deepcopy({key:self.c.spec[key] for key in
            ('trainer_progression_events','trainer_entitlements')})
        bank=self.c.spec['exp_bank']
        paid=self.e.pay_trainer_retraining(self.c,'feature',request_id='actual-retrain',
            reason='retrain from bank',refund_policy='none')
        self.assertEqual((self.c.level,self.c.spec['exp_bank']),(6,bank-paid['amount']))
        self.e.commit_trainer_xp_payment(self.c,'actual-retrain',event_id='actual-consumption')
        e=self.restore();c=e.everyone[0]
        self.assertEqual({key:c.spec[key] for key in earned},earned)
        before=dump_engine(e)
        self.assertEqual(e.pay_trainer_retraining(c,'feature',request_id='actual-retrain',
            reason='retrain from bank',refund_policy='none'),paid)
        self.assertEqual(dump_engine(e),before)

    def test_separate_party_actions_combine_after_restore_and_expire_next_round(self):
        PARTY.Tests.setup_world(self,'league')
        self.e.act_on_party(self.a,recall=[self.p],request_id='first-recall',reason='actual recall')
        self.e=self.restore();self.a,self.p,self.q,self.z=self.e.everyone
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'same Pokemon'):
            self.e.act_on_party(self.a,send=[(self.p,(2,0))],request_id='blocked',reason='same round return')
        self.assertEqual(dump_engine(self.e),before)
        row=self.e.act_on_party(self.a,send=[(self.q,(2,0))],request_id='second-send',reason='actual send')
        self.assertTrue(row['counts_as_switch'])
        self.assertEqual((self.a.budget['shift'],self.a.budget['standard']),(0,0))
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20)
        row=self.e.act_on_party(self.a,recall=[self.q],send=[(self.p,(2,0))],
            request_id='next-round',reason='return on next round')
        self.assertEqual((self.p.on_field,self.q.on_field),(True,False))
        self.assertEqual(row['payment']['funded'],{'standard':1})

    def test_two_recalls_share_one_standard_and_keep_individual_source_history(self):
        PARTY.Tests.setup_world(self)
        self.e.gm.send_out(self.q,(3,0),reason='actual second field Pokemon')
        row=self.e.act_on_party(self.a,recall=[self.p,self.q],request_id='pair',reason='actual paired recall')
        self.assertEqual((self.p.on_field,self.q.on_field,self.a.budget['shift']),(False,False,1))
        self.assertEqual(row['payment']['funded'],{'standard':1})
        self.assertEqual(set(row['recalled']),{self.p.entity_id,self.q.entity_id})
        e=self.restore();a,p,q=e.everyone[:3];before=dump_engine(e)
        self.assertEqual(e.act_on_party(a,recall=[p,q],request_id='pair',reason='actual paired recall'),row)
        self.assertEqual(dump_engine(e),before)

    def test_body_base_and_naturewalk_overlays_remain_independent_after_restore(self):
        TERRAIN_FIX.Tests.setUp(self)
        self.e.gm.set_footprint(self.a,[(0,0),(1,0)],reason='actual two-cell body')
        self.b.pos=(6,0)
        self.e.observe_map_terrain([(x,0) for x in range(1,6)],base='underwater',
            slow=True,rough=True,reason='actual underwater forest corridor')
        MOVE.observe_cell_terrain(self.e,[(x,0) for x in range(1,6)],['forest'],'actual forest tags')
        GRANTS.grant(self.a,'capabilities','Naturewalk(forest)','observed/forest-walk','actual capability')
        e=self.restore();a,b,c=e.everyone
        self.assertFalse(MAP.can_travel(e,a,(1,0),'육상'))
        move=self.r.move('move/불꽃세례');face=move['ac']+b.evasion('특수')
        self.assertTrue(e.accuracy_check(a,b,move,fixed_roll=face)[0])
        c.on_field=True;c.pos=(3,0)
        self.assertFalse(e.accuracy_check(a,b,move,fixed_roll=face)[0])
        c.on_field=False
        result=e.approach(a,b,movement_mode='swim')
        self.assertEqual((a.pos,result['distance']),((4,0),4))
        self.assertEqual((MAP.base_at(e.grid,(5,0)),e.grid.slow),('underwater',{(x,0) for x in range(1,6)}))
        GRANTS.revoke(a,'observed/forest-walk')
        self.assertEqual(MAP.slow_multiplier(e,a,a.pos,'수중'),2)
        # Its front cell is now adjacent to b: that clear body ray crosses no rough cell.
        self.assertTrue(e.accuracy_check(a,b,move,fixed_roll=face)[0])


if __name__=='__main__':unittest.main()
