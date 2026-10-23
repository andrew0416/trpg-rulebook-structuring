"""Actual R0636 partial producer and local/global native consumer boundary."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
import field_effects as FIELD
import state_codec as CODEC

ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')

class LocalGrassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,seed=636)
        self.e.grid=Grid(12,12,blocking={(5,4)})
        self.a=self.add('이상해씨','곰팡이군주',(4,4))
        self.t=self.add('피카츄','정전기',(3,4))
        self.o=self.add('피카츄','정전기',(9,9))
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20)

    def add(self,species,ability,pos):
        spec=build_pokemon(self.r,species,30,moves=['move/덩굴채찍','move/용의분노','move/전기쇼크','move/전광석화'],abilities=[ability])
        spec['footprint']={'kind':'observed_cells','offsets':[[0,0]],'reason':'actual mapped single square body'}
        a=Combatant(self.r,spec);self.e.gm.add_combatant(a,pos=pos,side='party',reason='actual field participant');return a

    def activate(self,request='grass/1'):
        return self.e.activate_ability(self.a,FIELD.LOCAL_SOURCE,self.a,request_id=request)

    def global_field(self,name):
        mid='move/'+name+'필드';fx=self.r.move_mech(mid)[0]['effects_exec'][0]
        FIELD.install(self.e,self.a,fx,mid)

    def test_native_activation_cost_replay_geometry_and_scene_lifetime(self):
        budget=deepcopy(self.a.budget);row=self.activate()
        self.assertEqual(self.a.budget['shift'],budget['shift']-1)
        self.assertNotIn([4,4],row['cells']);self.assertNotIn([6,4],row['cells'])
        before=CODEC.dump_engine(self.e)
        self.assertEqual(self.activate(),row);self.assertEqual(CODEC.dump_engine(self.e),before)
        with self.assertRaises(ValueError):self.activate('grass/2')
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.e.gm.set_position(self.a,(8,8),reason='creator leaves fixed field')
        self.assertEqual(FIELD.terrain_for(self.e,self.t)['name'],'그래스')
        self.assertIsNone(FIELD.terrain_for(self.e,self.a))
        self.e.end_encounter(round_elapsed_seconds=0)
        self.assertEqual(FIELD.terrain_for(self.e,self.t)['name'],'그래스')
        self.e.end_scene()
        self.assertIsNone(FIELD.terrain_for(self.e,self.t))

    def test_native_grass_heal_damage_and_target_specific_global_shadow(self):
        self.activate();self.global_field('일렉트릭')
        self.assertTrue(self.e.apply_status(self.t,'잠듦',source='test/sleep',applied_by=self.a))
        self.assertFalse(self.e.apply_status(self.o,'잠듦',source='test/sleep',applied_by=self.a))
        self.e.cure_status(self.t,'잠듦')
        self.t.hp-=20;hp=self.t.hp
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        self.assertEqual(self.t.hp,hp+self.t.max_hp//10)
        self.global_field('미스트')
        self.assertTrue(self.e.apply_status(self.t,'화상',source='test/burn',applied_by=self.a))
        self.assertFalse(self.e.apply_status(self.o,'화상',source='test/burn',applied_by=self.a))
        move=self.r.move('move/용의분노')
        # One local recipient does not erase the other grounded endpoint's Mist.
        self.assertEqual(FIELD.damage_roll_modifier(self.e,self.t,self.o,move,'드래곤'),-10)
        self.assertEqual(FIELD.damage_roll_modifier(self.e,self.o,self.t,move,'드래곤'),-10)
        self.e.gm.set_position(self.o,(3,3),reason='second endpoint enters Grass')
        self.assertEqual(FIELD.damage_roll_modifier(self.e,self.t,self.o,move,'드래곤'),0)
        self.global_field('사이코')
        priority=self.r.move('move/전광석화');mech=self.r.move_mech(priority['id'])[0]
        self.assertIsNone(FIELD.move_block_reason(self.e,self.a,self.t,priority,mech))
        self.e.gm.set_position(self.o,(9,9),reason='endpoint exits Grass')
        self.assertIsNotNone(FIELD.move_block_reason(self.e,self.a,self.o,priority,mech))
        self.e.gm.set_position(self.a,(3,2),reason='attacker enters Grass')
        grass=self.r.move('move/덩굴채찍')
        inside=self.e.roll_damage(self.a,self.o,grass,set_damage=True)
        self.e.gm.set_position(self.a,(9,8),reason='attacker exits Grass')
        outside=self.e.roll_damage(self.a,self.o,grass,set_damage=True)
        self.assertEqual(inside-outside,10)

    def test_bad_ownership_and_unknown_geometry_are_atomic_before_payment(self):
        self.a.abilities_suppressed=True
        before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.activate()
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.a.abilities_suppressed=False;self.e.grid=None
        before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.activate()
        self.assertEqual(CODEC.dump_engine(self.e),before)

    def test_both_restores_and_original_receipt_tamper_are_atomic(self):
        row=self.activate();self.e.gm.snapshot('grass')
        payload=self.e.export_state()
        loaded=Engine.import_state(Rules(str(ROOT),ruleset='core'),json.loads(json.dumps(payload)))
        self.assertEqual(FIELD.validate_local(loaded)[0],row)
        self.e.gm.restore('grass')
        snapshot=self.e.gm.snapshots['grass']['engine'][FIELD.LOCAL_KEY]
        original=deepcopy(snapshot);before=CODEC.dump_engine(self.e)
        for key,value in [('source_row_sha256','wrong'),('cells',[]),('until','encounter_end'),('creator_id','missing')]:
            snapshot.clear();snapshot.update(deepcopy(original))
            snapshot['receipts']['grass/1'][key]=value
            with self.assertRaises(ValueError):self.e.gm.restore('grass')
            self.assertEqual(CODEC.dump_engine(self.e),before)
            saved=deepcopy(getattr(self.e,FIELD.LOCAL_KEY))
            getattr(self.e,FIELD.LOCAL_KEY)['receipts']['grass/1'][key]=value
            encoder=CODEC._Encoder(self.e);bad=deepcopy(payload)
            bad['root']=encoder.value(self.e);bad['nodes']=encoder.nodes
            setattr(self.e,FIELD.LOCAL_KEY,saved)
            with self.assertRaises(ValueError):Engine.import_state(Rules(str(ROOT),ruleset='core'),bad)
        snapshot.clear();snapshot.update(original)

if __name__=='__main__':unittest.main()
