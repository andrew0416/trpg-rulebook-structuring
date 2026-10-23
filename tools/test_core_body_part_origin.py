"""C10-438: the actual observed part owns a ranged single Move's ray."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
import body_state as BODY,turn as TURN,weapon_actions as WEAPONS,state_codec as CODEC


class BodyPartOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,438);self.e.grid=Grid(30,20)
        moves=['물대포','몸통박치기','칼춤','방전']
        def actor(name):
            return Combatant(self.r,build_trainer(self.r,name,40,
                {'hp':100,'atk':20,'def':10,'spa':20,'spd':10,'spe':20},moves=moves,abilities=[]))
        self.a=actor('Observed irregular body');self.b=actor('Actual target')
        self.e.gm.add_combatant(self.a,pos=(2,2),side='party',reason='actual user')
        self.e.gm.add_combatant(self.b,pos=(10,2),side='foes',reason='actual target')
        self.shape=[(x,0) for x in range(5)]
        self.e.gm.set_footprint(self.a,self.shape,reason='GM observes five actual occupied cells')
        self.observe('head',(6,2));self.observe('tail',(2,2))
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def observe(self,part,cell):
        return self.e.gm.observe_body_part(self.a,part,cell,reason='GM observes the actual named body part')

    def snapshot(self):return deepcopy(CODEC.dump_engine(self.e))

    def fire(self,*,part='head',group=False,move='move/물대포',**options):
        with patch.object(self.e,'d20',return_value=12):
            if group:return self.e.use_move_on(self.a,self.b,move,self.e.everyone,origin_part=part,**options)
            return self.e.use_move(self.a,self.b,move,origin_part=part,set_damage=True,**options)

    def test_native_direct_and_group_use_exact_part_range_and_pay_once(self):
        for group in (False,True):
            with self.subTest(group=group):
                self.setUp();before=self.b.hp;pos=self.a.pos
                self.assertGreater(self.fire(group=group),0)
                self.assertLess(self.b.hp,before);self.assertEqual(self.a.pos,pos)
                self.assertEqual(self.a.budget['standard'],0)
                self.assertEqual(self.a.move_uses['move/물대포'],1)
        self.setUp();before_rng=self.e.rng.getstate()
        self.assertEqual(self.fire(part='tail'),0)
        self.assertEqual(self.a.budget['standard'],1);self.assertFalse(self.a.move_uses)
        self.assertEqual(self.b.hp,self.b.max_hp);self.assertEqual(self.e.rng.getstate(),before_rng)

    def test_selected_ray_blocking_cannot_borrow_a_clear_body_cell(self):
        shape=[(0,y) for y in range(4)]+[(x,3) for x in range(1,5)]
        self.e.gm.set_footprint(self.a,shape,reason='observed bent body')
        self.observe('head',(2,2));self.e.gm.set_position(self.b,(6,2),reason='target in head range')
        self.e.grid.blocking.add((4,2));hp=self.b.hp
        for group in (False,True):
            self.assertEqual(self.fire(group=group),0)
            self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.b.hp,hp)
        self.assertGreater(self.fire(part=None),0)
        self.assertEqual(self.a.budget['standard'],0)

    def test_unobserved_invalid_and_outside_choices_reject_atomically(self):
        for part in ('unobserved','',True,(6,2)):
            for group in (False,True):
                with self.subTest(part=part,group=group):
                    before=self.snapshot()
                    with self.assertRaises(ValueError):self.fire(part=part,group=group)
                    self.assertEqual(self.snapshot(),before)
        for cell in ((9,2),(99,2),(True,2)):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.observe('outside',cell)
            self.assertEqual(self.snapshot(),before)
        before=self.snapshot()
        with self.assertRaises(ValueError):self.e.gm.observe_body_part(self.b,'head',self.b.pos,reason='single cell')
        self.assertEqual(self.snapshot(),before)

    def test_native_movement_translates_part_and_changed_body_requires_observation(self):
        self.e.gm.set_position(self.b,(14,2),reason='beyond current body range')
        old=self.a.pos;self.e.approach(self.a,self.b,4)
        self.assertNotEqual(self.a.pos,old);self.assertEqual(self.a.budget['shift'],0)
        self.assertEqual(BODY.part_cell(self.e,self.a,'head'),(self.a.pos[0]+4,self.a.pos[1]))
        self.assertGreater(self.fire(),0)
        self.e.gm.set_footprint(self.a,[(0,0),(1,0),(2,0)],reason='actual current body changed')
        for group in (False,True):
            before=self.snapshot()
            with self.assertRaisesRegex(ValueError,'current body observation'):self.fire(group=group)
            self.assertEqual(self.snapshot(),before)
        self.observe('head',(self.a.pos[0]+2,self.a.pos[1]))
        self.assertEqual(BODY.part_cell(self.e,self.a,'head'),(self.a.pos[0]+2,self.a.pos[1]))

    def test_selected_origin_is_not_granted_to_square_area_melee_self_or_mapless(self):
        for move in ('move/몸통박치기','move/칼춤','move/방전'):
            for group in (False,True):
                before=self.snapshot()
                with self.assertRaises(ValueError):self.fire(move=move,group=group)
                self.assertEqual(self.snapshot(),before)
        self.e.gm.set_footprint(self.a,[(0,0),(1,0),(0,1),(1,1)],reason='actual square body')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'non-square'):self.observe('head',(2,2))
        self.assertEqual(self.snapshot(),before)
        self.setUp();self.e.grid=None;before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'actual grid'):self.fire()
        self.assertEqual(self.snapshot(),before)

    def test_weapon_minimum_maximum_and_blocking_use_the_selected_part(self):
        self.a.spec['skills']['전투']='달인'
        key=TURN.equip_weapon(self.e,self.a,{'name':'actual long bow','kind':'장거리 사격무기','grade':'좋음','moves':['불스아이']})
        # The fixture's generated Struggle source is admitted before measuring
        # rejection; lazy source admission is separate from gameplay changes.
        self.assertEqual(self.r._selected_rule(key),key)
        self.e.gm.set_position(self.b,(8,2),reason='within four of head and beyond four of tail')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'within four'):self.fire(move='move/불스아이',weapon_id=key)
        self.assertEqual(self.snapshot(),before)
        self.e.gm.set_position(self.b,(18,2),reason='head within selected weapon maximum')
        self.assertGreater(self.fire(move='move/불스아이',weapon_id=key),0)
        self.e.gm.set_position(self.b,(25,2),reason='outside selected weapon maximum');before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'outside selected weapon range'):self.fire(move='move/불스아이',weapon_id=key)
        self.assertEqual(self.snapshot(),before)
        self.e.gm.set_position(self.b,(18,2),reason='target restored');self.e.grid.blocking.add((9,2));before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'line of sight'):self.fire(move='move/불스아이',weapon_id=key)
        self.assertEqual(self.snapshot(),before)

    def test_observation_is_actor_bound_and_current_selected_source_is_verified(self):
        row=self.a.spec[BODY.PARTS]['head'];row['actor_id']=self.b.entity_id
        with self.assertRaises(ValueError):BODY.part_cell(self.e,self.a,'head')
        self.setUp()
        import source_context
        original=source_context.verified_source
        def changed(rules,reference,**options):
            if reference==BODY.PART_SOURCE:raise ValueError('changed body origin source')
            return original(rules,reference,**options)
        before=self.snapshot()
        with patch.object(source_context,'verified_source',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'changed body origin source'):self.fire()
        self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main(verbosity=2)
