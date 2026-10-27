"""Native legal setup/strict refusal regressions; run only in Actions."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import combat_precision_features as CPF
import confusion_attacks as CONFUSION
import effects as FX
import skill_modifiers as SKILLS
import turn as TURN
from native_scenario_fixture import prepare_scene,assert_rejected_unchanged
import test_category3_combat_precision as PRECISION_FIX
import test_attack_loss_provenance as CONFUSION_FIX


class ActionBoundaryFixtureRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')

    def test_order_stale_route_stays_rejected_until_actual_current_observation(self):
        fixture=PRECISION_FIX.CombatPrecisionTests();fixture.r=self.rules;fixture.setUp()
        e,a,p=fixture.e,fixture.a,fixture.p
        e.gm.set_position(a,(1,1),reason='actual new sender position')
        e.gm.set_position(p,(2,1),reason='actual new recipient position')
        fixture.begin()
        assert_rejected_unchanged(e,lambda:e.manual_feat(a,CPF.PINPOINT,p),
                                 reason_pattern='contemporaneous order communication')
        e.gm.observe_sensory_environment(a,p,paths={'auditory':True},present=True,
                                        reason='actual order route at the current positions')
        self.assertEqual(e.manual_feat(a,CPF.PINPOINT,p),(1,0))
        self.assertIs(CPF.binding(e,p)['owner'],a)
        self.assertTrue(e.validate_state()['valid'])

    def test_core_and_february_confusion_keep_distinct_opportunity_contracts(self):
        for profile,core,allowed in (('core',True,True),('core-confusion-feb2016',False,False)):
            with self.subTest(profile=profile):
                fixture=CONFUSION_FIX.AttackLossTests()
                fixture.r=Rules(str(ROOT),ruleset=profile);fixture.setUp()
                fixture.e.apply_status(fixture.b,'혼란')
                self.assertEqual(CONFUSION.core(fixture.e),core)
                self.assertEqual(TURN.can_aoo(fixture.e,fixture.b),allowed)

    def test_reviewed_free_trip_component_uses_real_turn_hit_and_opposed_choices(self):
        rows=[dict(key=key,kind='trainer',sheet=dict(name=key,level=20,
            stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
            skills={'전투':4},moves=['move/돌진'],abilities=[],pos=pos,side=side),
            body=dict(size='중형',offsets=[(0,0)],reason='actual adjacent maneuver participant'))
            for key,pos,side in (('a',(1,1),'party'),('b',(2,1),'foe'))]
        e,actors=prepare_scene(ROOT,ruleset='core',seed=5,grid={'width':8,'height':8},actors=rows)
        a,b=actors['a'],actors['b']
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        effect=next(x for x in e.r.move_mech('move/돌진')[0]['effects_exec'] if x['type']=='free_maneuver')
        options={'accept':True,'challenger_skill':'전투','defender_skill':'전투','fixed_accuracy':20,
                 'challenger_options':{'fixed':[6]*SKILLS.rank(e.r,a,'전투')[2]},
                 'defender_options':{'fixed':[1]*SKILLS.rank(e.r,b,'전투')[2]}}
        budget=dict(a.budget)
        batch=FX.run_effects(e,a,b,[effect],{'hit':True,'maneuver_options':options},'move/돌진')
        self.assertEqual(batch,(1,0));self.assertFalse(batch.pending)
        self.assertIn('넘어짐',b.conditions)
        self.assertEqual(a.budget,budget)
        self.assertEqual(a._action_history,['free'])


if __name__=='__main__':unittest.main()
