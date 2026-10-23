"""C03-017 Athletics inputs through existing movement, throw and Grapple paths.

Native Intercept evidence is reused from the separate defense direct suite.
Fishing reuses two existing tests rather than copying its execution procedure.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
import capability_actions as CAP
import grapple_state as GRAPPLE
import test_category3_physics_maneuvers as MANEUVERS
import test_category3_pokemon_activities as FISHING


class AthleticsConsumersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')

    def fixture(self,athletics):
        engine=Engine(self.rules,seed=374)
        # A single mapped corridor isolates distance from route selection.
        engine.grid=Grid(14,4,blocking=[(x,y) for x in range(14) for y in range(4) if y!=2])
        stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)
        actor=Combatant(self.rules,build_trainer(self.rules,'native athlete',20,stats,
            skills={'육상':athletics,'곡예':3},items={'돌':2},pos=(1,2)))
        target=Combatant(self.rules,build_trainer(self.rules,'far marker',20,stats,
            skills={'육상':3,'곡예':3},pos=(12,2),side='opponent'))
        engine.gm.add_combatant(actor);engine.gm.add_combatant(target)
        engine.start_round(engine.everyone);engine.start_of_turn(actor)
        return engine,actor,target

    def test_athletics_rank_changes_actual_derived_land_shift_at_rounding_boundary(self):
        # ch02:135-137: land = 3 + floor((Athletics + Acrobatics)/2).
        observed=[]
        for rank,distance in ((3,6),(4,6),(5,7)):
            with self.subTest(athletics=rank):
                engine,actor,target=self.fixture(rank)
                self.assertEqual(actor.spec['movement_basis'],'trainer_base')
                self.assertEqual(engine.move_profile(actor,movement_mode='land')[0],distance)
                rng=engine.rng.getstate()
                engine.approach(actor,target,movement_mode='land')
                observed.append(actor.pos[0]-1)
                self.assertEqual(actor.pos,(1+distance,2))
                self.assertEqual(actor.budget,{'standard':1,'shift':0,'swift':1})
                self.assertEqual(engine.rng.getstate(),rng)
        self.assertEqual(observed,[6,6,7])

    def test_baseline_athletics_throw_limit_controls_real_inventory_action_and_refusal(self):
        # ch02:143: baseline throwing range = 4 + Athletics; no mastery owned.
        for rank,limit in ((3,7),(5,9)):
            with self.subTest(athletics=rank):
                engine,actor,_=self.fixture(rank)
                self.assertFalse(actor.spec.get('edges'))
                self.assertEqual(CAP.throwing_range(engine,actor),limit)
                before=deepcopy((actor.spec,actor.budget,engine.rng.getstate(),
                    engine.elapsed_seconds,engine.log_lines))
                options={'item':'돌','small_object':True,'action_cost':'standard',
                         'reason':'GM identifies this actual owned small stone'}
                with self.assertRaises(ValueError):
                    engine.throw_small_object(actor,destination=(2+limit,2),**options)
                self.assertEqual((actor.spec,actor.budget,engine.rng.getstate(),
                    engine.elapsed_seconds,engine.log_lines),before)
                result=engine.throw_small_object(actor,destination=(1+limit,2),**options)
                self.assertEqual(result['distance'],limit);self.assertIsNone(result['hit'])
                self.assertEqual(actor.spec['items']['돌'],1)
                self.assertEqual(actor.budget,{'standard':0,'shift':1,'swift':1})
                self.assertEqual(actor.spec['thrown_objects'][0]['destination'],[1+limit,2])
                self.assertEqual(engine.rng.getstate(),before[2])

    def test_grapple_explicit_athletics_for_both_sides_resolves_win_and_defended_tie(self):
        for attack,defense,won in (([3]*4,[2]*4,True),([2]*4,[2]*4,False)):
            with self.subTest(challenger=attack,defender=defense):
                fixture=MANEUVERS.Tests('runTest');fixture.r=self.rules;fixture.setUp()
                engine,actor,target=fixture.e,fixture.a,fixture.b
                # Combat cannot accept these four fixed dice. Both actual
                # selected Athletics pools can, so aliases cannot mask routing.
                actor.spec['skills']['전투']=1;target.spec['skills']['전투']=1
                rng=engine.rng.getstate()
                result=engine.grapple(actor,target,challenger_skill='육상',
                    defender_skill='육상',fixed_accuracy=4,
                    challenger_options={'fixed':attack},defender_options={'fixed':defense})
                self.assertEqual(actor.budget,{'standard':0,'shift':1,'swift':1})
                self.assertEqual(engine.rng.getstate(),rng)
                if won:
                    self.assertEqual(result['dominant'],actor.entity_id)
                    self.assertEqual(GRAPPLE.relation(engine,target)['id'],result['id'])
                    self.assertIn('취약',target.conditions)
                else:
                    self.assertFalse(result)
                    self.assertIsNone(GRAPPLE.relation(engine,actor))
                    self.assertIsNone(GRAPPLE.relation(engine,target))
                    self.assertNotIn('취약',target.conditions)





if __name__=='__main__':unittest.main()
