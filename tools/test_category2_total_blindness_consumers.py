"""C07-166 consumers: actual darkness, sensory exclusion and action gates.

The relative Shift cases are connected only to the shared source-bound API.
Existing C07-165 accuracy precedence is reused without transferring its credit.
"""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import effects_ext as EXT
import survivalist_features as SURVIVALIST
import vision_impairment as VISION
import test_category2_move_defense_reactions as DEFENSE_FIXTURE
import test_category2_vision_impairment as VISION_CHECKS
import state_grants as G


class TotalBlindnessConsumersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')

    def fixture(self,*,capabilities=()):
        engine=Engine(self.rules,seed=166)
        engine.grid=Grid(10,4)
        actor=VISION_CHECKS.combatant(self.rules,'total-actor',pos=(1,1),capabilities=capabilities)
        target=VISION_CHECKS.combatant(self.rules,'total-target',pos=(2,1))
        actor.side='players';target.side='enemies'
        for participant in (actor,target):engine.gm.add_combatant(participant)
        G.replace_baseline(engine,actor,'moves',['move/할퀴기','move/전광석화'])
        engine.start_round(engine.everyone);engine.start_of_turn(actor)
        return engine,actor,target

    def observe(self,engine,actor,*,terrain='cave',light='complete_darkness'):
        return SURVIVALIST.observe_environment(engine,actor,terrains=[terrain],light=light,
            reason='GM observes actual illumination of this cave or building')

    def penalty(self,engine,actor,target):
        move=engine.r.move('move/할퀴기');mechanics,_=engine.r.move_mech(move['id'])
        return EXT.accuracy_hook(engine,actor,target,move,mechanics,
            {'attacker':actor,'target':target,'hit':True,'nat':10,'engine':engine,'move':move})[2]

    def test_complete_dark_cave_and_building_block_visual_position_and_absolute_approach(self):
        for terrain in ('cave','urban'):
            with self.subTest(terrain=terrain):
                engine,actor,target=self.fixture()
                self.observe(engine,actor,terrain=terrain)
                self.assertEqual(VISION.accuracy_level(engine,actor),'total')
                self.assertEqual(self.penalty(engine,actor,target),-10)
                self.assertNotIn('완전-실명',actor.conditions)
                # Actual observed visual path cannot grant map coordinates in total darkness.
                engine.gm.observe_sensory_environment(actor,target,paths={'visual':True},
                    present=True,reason='GM confirms geometric line of sight, without granting light')
                declaration={'id':'ordinary-map-view','source':'condition/완전-실명',
                    'capabilities':[],'mode':'visual','range':None,'path':'visual','medium':[],
                    'vision':'usable','provider':'entity','information':['position'],'check':None}
                result=engine.observe_target(actor,target,declaration)
                self.assertEqual((result['status'],result['reason']),('not_observable','vision_blocked'))
                self.assertEqual(result['values'],{})
                target.pos=(8,1);before=engine.export_state()
                with self.assertRaises(ValueError):engine.approach(actor,target)
                self.assertEqual(engine.export_state(),before)

    def test_explicit_total_blindness_remains_total_in_normal_light(self):
        engine,actor,target=self.fixture()
        self.observe(engine,actor,light='normal')
        self.assertTrue(engine.apply_status(actor,'완전 실명',parameters={'cause':'external'}))
        self.assertEqual(VISION.accuracy_level(engine,actor),'total')
        self.assertEqual(self.penalty(engine,actor,target),-10)

    def test_blindsense_excludes_explicit_and_environmental_total_blindness(self):
        engine,actor,target=self.fixture(capabilities=['Blindsense'])
        self.observe(engine,actor)
        self.assertFalse(engine.apply_status(actor,'완전 실명',parameters={'cause':'external'}))
        self.assertEqual(VISION.accuracy_level(engine,actor),'none')
        self.assertEqual(self.penalty(engine,actor,target),0)
        target.pos=(8,1);rng=engine.rng.getstate()
        engine.approach(actor,target)
        self.assertEqual(actor.pos[0],7)
        self.assertEqual(actor.budget,{'standard':1,'shift':0,'swift':1})
        self.assertEqual(engine.rng.getstate(),rng)

    def defense_fixture(self):
        fixture=DEFENSE_FIXTURE.MoveDefenseReactionsTests('runTest')
        fixture.rules=self.rules;fixture.setUp()
        return fixture

    def test_total_blindness_refuses_actual_intercept_before_roll_cost_or_movement(self):
        for cause in ('external','darkness'):
            with self.subTest(cause=cause):
                fixture=self.defense_fixture()
                if cause=='external':
                    fixture.e.apply_status(fixture.r,'완전 실명',parameters={'cause':'external'})
                else:self.observe(fixture.e,fixture.r)
                fixture.watch();event=fixture.waiting();before=fixture.e.export_state()
                with self.assertRaisesRegex(ValueError,'condition prohibits Intercept'):
                    fixture.choose(event,options=fixture.melee())
                self.assertEqual(fixture.e.export_state(),before)
                fixture.choose(event,use=False)
                self.assertIsNone(fixture.e._passive_pending)

    def test_blindsense_permits_actual_intercept_in_complete_darkness(self):
        fixture=self.defense_fixture()
        G.replace_baseline(fixture.e,fixture.r,'capabilities',['Blindsense'])
        self.observe(fixture.e,fixture.r)
        self.assertEqual(VISION.accuracy_level(fixture.e,fixture.r),'none')
        fixture.watch();event=fixture.waiting();hp=fixture.t.hp
        fixture.choose(event,options=fixture.melee())
        self.assertEqual(fixture.t.hp,hp)
        self.assertEqual(fixture.r.pos,(3,2))

    def test_total_blindness_refuses_native_priority_before_budget_frequency_or_rng(self):
        for cause in ('external','darkness'):
            with self.subTest(cause=cause):
                engine,actor,target=self.fixture()
                if cause=='external':engine.apply_status(actor,'완전 실명',parameters={'cause':'external'})
                else:self.observe(engine,actor)
                before=engine.export_state()
                with self.assertRaises(ValueError):
                    engine.use_move(actor,target,'move/전광석화',set_damage=True)
                self.assertEqual(engine.export_state(),before)

    def test_actual_priority_control_is_available_normally_and_with_blindsense_in_darkness(self):
        for capabilities,dark in (([],False),(['Blindsense'],True)):
            with self.subTest(capabilities=capabilities):
                engine,actor,target=self.fixture(capabilities=capabilities)
                if dark:self.observe(engine,actor)
                move=engine.r.move('move/전광석화')
                self.assertIn('우선',' '.join(move.get('keywords',()))+' '+str(move.get('range','')))
                engine.use_move(actor,target,move['id'],set_damage=True)
                self.assertEqual(actor.move_uses[move['id']],1)
                self.assertEqual(actor._action_history,['standard'])
                self.assertEqual(actor.budget,{'standard':0,'shift':1,'swift':1})


CERTIFIED_METHODS=(
    'test_complete_dark_cave_and_building_block_visual_position_and_absolute_approach',
    'test_explicit_total_blindness_remains_total_in_normal_light',
    'test_blindsense_excludes_explicit_and_environmental_total_blindness',
    'test_total_blindness_refuses_actual_intercept_before_roll_cost_or_movement',
    'test_blindsense_permits_actual_intercept_in_complete_darkness',
)


def load_tests(loader,tests,pattern):
    # Priority admission and relative movement are separate pending contracts.
    # The prepared Priority refusal case remains addressable by exact test ID.
    return unittest.TestSuite(TotalBlindnessConsumersTests(name) for name in CERTIFIED_METHODS)


if __name__=='__main__':unittest.main()
