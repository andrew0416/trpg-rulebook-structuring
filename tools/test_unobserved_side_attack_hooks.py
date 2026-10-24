"""C09-085 audit repair: an attack on/by a legal actor without an observed side reaches damage.

Combatant/state_fields do not require ``side``.  The shared attack hooks (Deadly Gambit
preparation, Gleeful Interference hit snapshot, Taskmaster after-attack and Hunter Pack Hunt
after-damage) read an absent side as the unobserved value None, like the other side
consumers (effect_contracts, manual_effects, hunter.teamwork_bonus).  Observed sides keep
their existing behavior (see the Taskmaster, Gleeful Interference and Hunter suites).
The historical downstream-only cases remain; native cases below retain real accuracy
and map geometry. Only outcome-relevant unobserved flanking relations remain pending.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon
from engine import Combatant,Engine,Rules
from grid import Grid
import attack_damage_history as HISTORY,state_codec as CODEC,world_entities as W
import gleeful_interference as GLEEFUL,taskmaster as TASK
import hunter as HUNTER,body_state as BODY


class UnobservedSideAttackHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.rules,seed=8501);self.e.grid=Grid(10,10)
        self.a=self.add('attacking carp',(2,2),'party');self.t=self.add('struck carp',(3,2),'enemy')
        self.o=self.add('observer carp',(6,6),'enemy')
        self.e.grid=None  # Existing unknown-side boundary has no flanking map.

    def add(self,name,pos,side):
        spec=build_pokemon(self.rules,'잉어킹',20,abilities=[],moves=['몸통박치기','튀어오르기'])
        spec['name']=name
        actor=Combatant(self.rules,spec)
        self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native participant')
        return actor

    def unobserve(self,actor):
        del actor.side;actor.spec.pop('side',None)
        self.assertFalse(hasattr(actor,'side'))

    def start(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor,initiative_count=20)

    def hit(self,attacker,target):
        self.start(attacker)
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
            return self.e.use_move(attacker,target,'move/몸통박치기',set_damage=True)

    def test_hooks_read_absent_side_as_unobserved_none(self):
        move=self.rules.move('move/몸통박치기')
        self.unobserve(self.t)
        self.assertIsNone(TASK._side(self.t));self.assertEqual(TASK._side(self.a),'party')
        self.assertIsNone(GLEEFUL.snapshot(self.e,self.a,self.t,move))
        self.assertIsNone(GLEEFUL.snapshot(self.e,self.t,self.a,move))
        self.assertIsNone(TASK.prepare_gambit(self.e,self.a,self.t,move))
        self.assertIsNone(TASK.after_attack(self.e,self.a,self.t,move,critical=False,damage=1))

    def test_attack_on_unobserved_side_target_damages_once(self):
        self.unobserve(self.t);hp=self.t.hp
        dealt=self.hit(self.a,self.t)
        self.assertGreater(dealt,0);self.assertEqual(hp-self.t.hp,dealt)
        rows=HISTORY.records(self.t)
        self.assertEqual(len(rows),1);self.assertEqual(HISTORY.amount(rows[-1]),dealt)
        self.assertFalse(hasattr(self.t,'side'))

    def test_attack_by_unobserved_side_attacker_damages_once(self):
        self.unobserve(self.a);hp=self.t.hp
        dealt=self.hit(self.a,self.t)
        self.assertGreater(dealt,0);self.assertEqual(hp-self.t.hp,dealt)
        self.assertEqual(len(HISTORY.records(self.t)),1)

    def test_invalid_attack_option_still_rejects_before_payment_without_side(self):
        self.unobserve(self.t);self.start(self.a)
        def snap():return (self.t.hp,dict(self.a.budget),json.dumps(self.a.move_uses,sort_keys=True),
                           len(HISTORY.records(self.t)),self.e.rng.getstate())
        before=snap()
        with patch.object(Engine,'accuracy_check',return_value=(True,12,False)):
            with self.assertRaises(ValueError):
                self.e.use_move(self.a,self.t,'move/몸통박치기',set_damage=True,appendage_id='unobserved:part')
        self.assertEqual(snap(),before)

    def test_observed_sides_still_separate_allies_from_foes(self):
        move=self.rules.move('move/몸통박치기')
        self.assertEqual(TASK._side(self.t),'enemy')
        self.o.side=self.a.side
        self.assertIsNone(GLEEFUL.snapshot(self.e,self.a,self.o,move))
        restored=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=W.actor_index(restored)
        self.assertEqual(index[self.t.entity_id].side,'enemy');self.assertEqual(index[self.a.entity_id].side,'party')


    def native_hit(self,attacker,target):
        self.start(attacker)
        # Only supply the die face. The complete native accuracy consumer runs.
        with patch.object(Engine,'d20',return_value=12) as die:
            dealt=self.e.use_move(attacker,target,'move/몸통박치기',set_damage=True)
        die.assert_called()
        return dealt

    def test_native_accuracy_and_move_cover_absent_none_actor_target_third_on_both_maps(self):
        for mapped in (False,True):
            for role in ('a','t','o'):
                for absence in (True,False):
                    with self.subTest(mapped=mapped,role=role,absence=absence):
                        self.setUp()
                        if mapped:self.e.grid=Grid(10,10)
                        actor=getattr(self,role)
                        if absence:self.unobserve(actor)
                        else:actor.side=None;actor.spec['side']=None
                        self.start(self.a)
                        hit,natural,_=self.e.accuracy_check(self.a,self.t,self.rules.move('move/몸통박치기'),fixed_roll=12)
                        self.assertTrue(hit);self.assertEqual(natural,12)
                        hp=self.t.hp;dealt=self.native_hit(self.a,self.t)
                        self.assertGreater(dealt,0);self.assertEqual(hp-self.t.hp,dealt)
                        self.assertEqual(len(HISTORY.records(self.t)),1)
                        self.assertEqual(HUNTER.teamwork_bonus(self.e,self.a,self.t,self.rules.move('move/몸통박치기')),0)
                        self.assertEqual(hasattr(actor,'side'),not absence)

    def test_only_geometry_that_can_change_flanking_requires_the_missing_relation(self):
        self.e.grid=Grid(10,10);self.o.pos=(4,2);self.unobserve(self.o)
        state=BODY.flanking(self.e,self.t)
        self.assertIsNone(state['flanked']);self.assertIsNone(state['evasion_penalty'])
        self.assertEqual(state['pending'],['foe relation: '+self.o.entity_id+' -> '+self.t.entity_id])
        self.start(self.a);before=(dict(self.a.budget),self.t.hp,self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'foe relation'):
            self.e.accuracy_check(self.a,self.t,self.rules.move('move/몸통박치기'),fixed_roll=12)
        self.assertEqual((self.a.budget,self.t.hp,self.e.rng.getstate()),before)
        self.o.pos=(2,3) # Both possible contributors touch: never a flanking witness.
        self.assertFalse(BODY.flanking(self.e,self.t)['flanked'])
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.rules.move('move/몸통박치기'),fixed_roll=12)[0])
        self.o.pos=(4,2);self.o.side='party'
        self.assertTrue(BODY.flanking(self.e,self.t)['flanked'])
        self.o.side='enemy'
        self.assertFalse(BODY.flanking(self.e,self.t)['flanked'])
        self.o.side=None;self.o.pos=(8,8);self.o.spec['_movement_altitude']=1
        state=BODY.flanking(self.e,self.t)
        self.assertFalse(state['flanked']);self.assertEqual(state['pending'],[])

    def test_one_unknown_large_foe_matters_only_with_sufficient_contact_weight(self):
        self.e.grid=Grid(10,10);self.t.spec['size']='Large';self.a.pos=(2,2)
        self.o.pos=(5,2);self.o.spec['size']='Large';self.unobserve(self.o)
        state=BODY.flanking(self.e,self.t)
        self.assertEqual(state['required'],3);self.assertIsNone(state['flanked'])
        self.assertEqual(state['pending'],['foe relation: '+self.o.entity_id+' -> '+self.t.entity_id])
        self.o.spec['size']='Medium'
        self.assertFalse(BODY.flanking(self.e,self.t)['flanked'])
        self.o.spec['size']='Large';self.o.side='party'
        self.assertTrue(BODY.flanking(self.e,self.t)['flanked'])

    def test_known_flanking_witness_does_not_need_unrelated_unknown_third_relation(self):
        self.e.grid=Grid(10,10);self.o.pos=(4,2);self.o.side='party'
        unknown=self.add('unknown bystander',(8,8),'party');self.unobserve(unknown)
        state=BODY.flanking(self.e,self.t)
        self.assertTrue(state['flanked']);self.assertEqual(state['evasion_penalty'],-2)
        self.assertEqual(state['pending'],[])

    def test_unknown_teamwork_holder_is_not_assumed_to_be_an_ally(self):
        self.o.pos=(3,3);self.o.abilities=['팀워크'];self.e.register_abilities(self.o)
        move=self.rules.move('move/몸통박치기')
        for absent in (False,True):
            if absent:self.unobserve(self.o)
            else:self.o.side=None
            self.assertEqual(HUNTER.teamwork_bonus(self.e,self.a,self.t,move),0)
        self.o.side='party'
        self.assertEqual(HUNTER.teamwork_bonus(self.e,self.a,self.t,move),2)
        self.o.side='enemy'
        self.assertEqual(HUNTER.teamwork_bonus(self.e,self.a,self.t,move),0)


import test_category2_cleanse_weapon as _tag_fixture

class NativeUnobservedTagAttackTests(unittest.TestCase):
    setUpClass=classmethod(_tag_fixture.WeaponTagTests.setUpClass.__func__)
    setUp=_tag_fixture.WeaponTagTests.setUp
    actor=_tag_fixture.WeaponTagTests.actor
    craft=_tag_fixture.WeaponTagTests.craft
    part=_tag_fixture.WeaponTagTests.part
    start=_tag_fixture.WeaponTagTests.start
    restore=_tag_fixture.WeaponTagTests.restore
    used=_tag_fixture.WeaponTagTests.used

    def test_native_tagged_appendage_accuracy_damages_and_consumes_once_without_side(self):
        for mapped in (False,True):
            with self.subTest(mapped=mapped):
                self.setUp();self.part();del self.p.side;self.p.spec.pop('side',None)
                self.q.pos=(9,9)
                if not mapped:self.e.grid=None
                self.start();hp=self.p.hp
                with patch.object(Engine,'d20',return_value=12) as die:
                    dealt=self.e.use_move(self.a,self.p,'struggle',appendage_id='actual:right-hand',set_damage=True)
                die.assert_called();self.assertGreater(dealt,0);self.assertEqual(hp-self.p.hp,dealt)
                self.assertTrue(self.used());used=deepcopy(self.used())
                self.restore();self.assertEqual(self.used(),used)

    def test_native_tagged_pending_damage_and_restore_do_not_repeat_consumption(self):
        import passive_events as PE
        self.part(self.q);self.q.moves=['struggle'];self.q.spec['moves']=['struggle']
        self.q.abilities=['자기과신'];self.e.register_abilities(self.q)
        self.q.side='party';self.p.hp=1;del self.p.side;self.p.spec.pop('side',None)
        self.start(self.q)
        with patch.object(Engine,'d20',return_value=12) as die:
            with self.assertRaises(PE.PassiveEventPending):
                self.e.use_move(self.q,self.p,'struggle',appendage_id='actual:right-hand',set_damage=True)
        die.assert_called();self.assertTrue(self.used());event=self.e._passive_pending;self.restore()
        before=(self.p.hp,dict(self.q.move_uses),deepcopy(self.used()),self.e.rng.getstate())
        self.p.side='enemy';self.assertEqual(self.e.deliver_passive_event(event),'applied')
        self.assertEqual(before,(self.p.hp,self.q.move_uses,self.used(),self.e.rng.getstate()))
        self.assertEqual(self.e.deliver_passive_event(event),'already_delivered')


if __name__=='__main__':unittest.main()
