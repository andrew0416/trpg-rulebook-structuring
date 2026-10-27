"""Actual path cleanup and source-bound area state through native actions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from engine import Engine,Rules
from ruleset import ExcludedRuleSelection
import native_scenario_fixture as NATIVE
import native_path_area_moves as SOURCE
import field_effects as FIELD
import combat_timing as TIME
import state_codec as CODEC
import world_entities as WORLD
import status_sets as STATUS
import condition_instances as INSTANCES
import weapon_actions as WEAPONS
import effects as FX

ROOT=Path(__file__).resolve().parents[1]
GRASS='move/그래스필드';MAGIC='move/매직룸';SEED='move/씨뿌리기';SPIN='move/고속스핀'


class NativePathAreaSourceTests(unittest.TestCase):
    def world(self,*,mould=False):
        moves=[SOURCE.FAIRY,SOURCE.ROLLER,GRASS,MAGIC,SEED,SPIN,'move/몸통박치기']
        if mould:moves.append('move/곰팡이독소')
        def row(key,pos,side):
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':30,
                'stats':{'hp':100,'atk':30,'def':5,'spa':30,'spd':5,'spe':10},
                'moves':moves,'abilities':[],'pos':pos,'side':side,
                'extra':{'movement':{'land':6,'power':3},'movement_basis':'current'}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual source-owned path/area body'}}
        self.e,self.actors=NATIVE.prepare_scene(ROOT,ruleset='homebrew' if mould else 'core',seed=7566,grid={'width':16,'height':12},
            actors=[row('a',(2,2),'party'),row('b',(3,2),'foe'),row('c',(4,2),'foe'),
                    row('ally',(2,3),'party'),row('far',(12,10),'foe')])
        self.a,self.b,self.c,self.ally,self.far=[self.actors[key] for key in ('a','b','c','ally','far')]

    def turn(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor,initiative_count=20)

    def restore(self):
        ids={name:actor.entity_id for name,actor in self.actors.items()}
        self.e.gm.restore(self.e.gm.snapshot())
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=WORLD.actor_index(self.e);self.actors={name:index[uid] for name,uid in ids.items()}
        self.a,self.b,self.c,self.ally,self.far=[self.actors[key] for key in ('a','b','c','ally','far')]

    def test_fairy_all_actual_foes_once_and_each_source_end_preserves_independent_slow(self):
        for ending in ('faint','recall','encounter'):
            with self.subTest(ending=ending):
                self.world();self.e.apply_status(self.c,'둔화',source='condition/둔화')
                self.turn(self.a);self.e.use_move_on(self.a,self.b,SOURCE.FAIRY,self.e.everyone)
                for target in (self.b,self.c):
                    self.assertTrue({'수렁','둔화'}<=target.conditions)
                    self.assertEqual(len([r for r in TIME.records(target) if SOURCE.FAIRY_SOURCE in r]),2)
                self.assertFalse({'수렁','둔화'}&self.ally.conditions)
                self.assertFalse({'수렁','둔화'}&self.far.conditions)
                self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.move_uses[SOURCE.FAIRY],1)
                self.restore()
                if ending=='faint':self.e.gm.set_hp(self.a,value=0,reason='actual Fairy Lock source knockout')
                elif ending=='recall':self.e.gm.recall(self.a,reason='actual Fairy Lock source leaves')
                else:
                    self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=10)
                self.assertFalse({'수렁','둔화'}&self.b.conditions)
                self.assertNotIn('수렁',self.c.conditions);self.assertIn('둔화',self.c.conditions)
                self.assertFalse(any(SOURCE.FAIRY_SOURCE in r for actor in self.e.everyone for r in TIME.records(actor)))
                self.assertTrue(self.e.validate_state()['valid'])

    def test_fairy_wrong_source_reference_is_rejected_and_unrelated_recall_does_not_end_it(self):
        self.world();self.turn(self.a);self.e.use_move_on(self.a,self.b,SOURCE.FAIRY,self.e.everyone)
        self.e.gm.recall(self.far,reason='unrelated actor leaves')
        self.assertIn('수렁',self.b.conditions)
        row=next(r for r in TIME.records(self.b) if SOURCE.FAIRY_SOURCE in r)
        row[SOURCE.FAIRY_SOURCE]=self.ally
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        row[SOURCE.FAIRY_SOURCE]=self.a
        row['owned_statuses'].add('독')
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        row['owned_statuses'].discard('독');row['installing']=True
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

    def prepare_roller(self):
        self.world();self.turn(self.ally);self.e.use_move(self.ally,self.ally,MAGIC)
        self.turn(self.ally);self.e.use_move(self.ally,self.ally,GRASS)
        for cell in ((1,2),(3,2),(3,3),(9,8)):
            self.e.gm.place_hazard(cell,'actual observed damaging trap',effects=[{'type':'hp_loss','value':7}],
                reason='actual mapped hazard before Steel Roller')
        self.turn(self.a)

    def test_roller_clears_actual_path_and_adjacent_hazards_before_entry_and_only_terrain(self):
        for face in (14,16):
            with self.subTest(face=face):
                self.prepare_roller();hp=self.a.hp
                with patch.object(Engine,'d20',return_value=face):
                    result=self.e.use_pass_move(self.a,SOURCE.ROLLER,(6,2),event_id='roller/native',
                        object_adjudications={},source='gm/observed-clear-pass',reason='actual four metre Steel Roller path')
                self.assertEqual(self.a.pos,(6,2));self.assertEqual(self.a.hp,hp)
                self.assertFalse(set(self.e.hazards)&{(1,2),(3,2),(3,3)})
                self.assertIn((9,8),self.e.hazards)
                self.assertIsNone(self.e.field)
                self.assertEqual({r['source_id'] for r in FIELD.active_fields(self.e)},{MAGIC})
                self.assertEqual((self.a.budget['standard'],self.a.budget['shift'],self.a.move_uses[SOURCE.ROLLER]),(0,0,1))
                for target in (self.b,self.c):self.assertEqual('넘어짐' in target.conditions,face>=15)
                self.assertEqual([r['position'] for r in result[SOURCE.STEPS]],[[2,2],[3,2],[4,2],[5,2],[6,2]])
                self.restore();self.assertTrue(self.e.validate_state()['valid'])

    def test_roller_blocked_path_and_late_entry_failure_are_atomic(self):
        self.prepare_roller();self.e.grid.blocking.add((6,2));before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.use_pass_move(self.a,SOURCE.ROLLER,(6,2),event_id='blocked',object_adjudications={},source='gm/path',reason='actual blocked endpoint')
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.e.grid.blocking.remove((6,2));before=CODEC.dump_engine(self.e);native=FIELD.clear_terrain_at
        def fail(*args,**kwargs):
            native(*args,**kwargs);raise ValueError('late actual Terrain receiver failure')
        with patch.object(FIELD,'clear_terrain_at',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late actual Terrain receiver failure'):
                self.e.use_pass_move(self.a,SOURCE.ROLLER,(6,2),event_id='late',object_adjudications={},source='gm/path',reason='actual admitted endpoint')
        self.assertEqual(CODEC.dump_engine(self.e),before)

    def test_missing_mechanics_header_keeps_moulds_actual_six_metre_source_range(self):
        with self.assertRaisesRegex(ExcludedRuleSelection,'variant:홈브류'):
            Rules(ROOT,ruleset='core').move('move/곰팡이독소')
        self.world(mould=True);move=self.e.r.move('move/곰팡이독소')
        self.assertEqual(move['range'],'6, 대상 1')
        selected=WEAPONS.range_spec(self.e,move,self.a)
        self.assertEqual((selected['origin'],selected['targets']),(6,1))
        self.assertNotIn('shape',selected)

    def test_ordinary_status_cure_keeps_seed_but_actual_rapid_spin_removes_named_effect(self):
        self.world();self.turn(self.a)
        with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.b,SEED)
        self.assertIn('씨뿌리기',self.b.conditions);self.assertTrue(INSTANCES.records(self.b,'씨뿌리기'))
        self.e.apply_status(self.b,'독',source='condition/독')
        STATUS.cure_group(self.e,self.b)
        self.assertNotIn('독',self.b.conditions);self.assertIn('씨뿌리기',self.b.conditions)
        before=deepcopy(self.b.conditions)
        response=FX.h_cure_status(self.e,self.a,self.b,{'type':'cure_status','status':'invented undeclared effect'},
            {'engine':self.e,'source_id':SPIN})
        self.assertIsInstance(response,str);self.assertEqual(self.b.conditions,before)
        self.turn(self.b)
        with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.b,self.a,SPIN,self.e.everyone)
        self.assertNotIn('씨뿌리기',self.b.conditions);self.assertFalse(INSTANCES.records(self.b,'씨뿌리기'))
        self.assertEqual(self.b.move_uses[SPIN],1);self.assertEqual(self.b.budget['standard'],0)
        self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
