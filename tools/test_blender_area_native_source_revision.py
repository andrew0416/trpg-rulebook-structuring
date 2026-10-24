"""Q6: actual catalog Blender holder, executed area ranges and native conversions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon
from engine import Combatant,Engine,Rules
from grid import Grid
import blender_state as B
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import state_grants as G
import weapon_actions as WEAPONS
import world_entities as WORLD
import test_book_duelist_momentum as DUELIST_FIXTURE
import test_book_type_ace_acquisition as TYPE_FIXTURE
import type_ace as TA


def catalog_blender(engine,pos):
    actor=Combatant(engine.r,build_pokemon(engine.r,'켈리몬',30,moves=[],abilities=[],wild=True))
    engine.gm.add_combatant(actor,pos=pos,side='foe',reason='actual catalog Blender capability holder')
    NATIVE.prepare_body(engine,actor,size=actor.spec['size'],offsets=[(0,0)],reason='complete observed catalog body')
    return actor


class BlenderAreaNativeSourceRevisionTests(unittest.TestCase):
    def add(self,species,pos,*,moves=(),side='party'):
        actor=Combatant(self.e.r,build_pokemon(self.e.r,species,30,moves=list(moves),abilities=[],wild=True))
        self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native area participant')
        NATIVE.prepare_body(self.e,actor,size=actor.spec['size'],offsets=[(0,0)],reason='complete observed participant body')
        return actor

    def world(self,move):
        self.e=Engine(Rules(ROOT,ruleset='core'),seed=10012);self.e.grid=Grid(16,12)
        self.a=self.add('리자드',(2,3),moves=[move])
        self.t=catalog_blender(self.e,(4,3))
        self.u=self.add('이브이',(4,4),side='foe')
        self.assertIn('녹아들기',G.effective_capabilities(self.t))
        self.assertIn('녹아들기',self.e.r.species['pokemon/켈리몬']['capabilities'])
        self.assertFalse(G.state(self.t)['sources'].get('fixture:blender'))

    def start(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        if self.e.round_start_seconds is None:self.e.start_round(self.e.everyone)
        if self.e._ordinary_turn_rounds.get(actor)==self.e.round_no:
            self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=20)

    def minimum(self,move):
        return next(face for face in range(2,20)
            if self.e.accuracy_check(self.a,self.t,move,fixed_roll=face)[0])

    def execute(self,move):
        self.start(self.a)
        with patch.object(Engine,'d20',return_value=19):
            self.e.use_move_on(self.a,self.t,move,self.e.everyone,set_damage=True)
        if move=='move/솔라빔':
            self.start(self.a)
            with patch.object(Engine,'d20',return_value=19):
                self.e.use_move_on(self.a,self.t,move,self.e.everyone,set_damage=True)
        rows=[r for r in self.e._move_completions.values() if r['actor'] is self.a and r['move_id']==move and r['phase']=='complete']
        self.assertEqual(len(rows),1)
        self.assertIn(self.t.entity_id,rows[0]['results'])
        self.assertTrue(rows[0]['results'][self.t.entity_id]['hit'])
        self.assertEqual(self.a.budget['standard'],0)
        return rows[0]

    def test_actual_five_area_shapes_apply_adopted_bonus_and_complete_native_attacks(self):
        for move,shape,bonus in (
                ('move/지진','burst',2),('move/째려보기','cone',2),
                ('move/하이퍼보이스','close_blast',2),('move/솔라빔','line',4),
                ('move/일렉트릭네트','blast',4)):
            with self.subTest(move=move):
                self.world(move);native=self.e.r.move(move)
                self.assertEqual(WEAPONS.range_spec(self.e,native,self.a)['shape'],shape)
                base=self.minimum(native);evasion=self.t.evasion(native['class'],attacker=self.a,engine=self.e)
                self.start(self.t);self.e.activate_blender(self.t,reason='actual catalog camouflage choice')
                self.assertEqual(self.t.budget['shift'],0)
                self.assertEqual(B.evasion(self.e,self.t,native,self.a),bonus)
                threshold=base+min(9,evasion+bonus)-evasion
                self.assertEqual(self.minimum(native),threshold)
                self.assertFalse(self.e.accuracy_check(self.a,self.t,native,fixed_roll=threshold-1)[0])
                self.assertTrue(self.e.accuracy_check(self.a,self.t,native,fixed_roll=threshold)[0])
                row=self.execute(move)
                if shape!='line':self.assertIn(self.u.entity_id,row['results'])

    def test_real_melee_pass_executes_paid_path_against_catalog_blender(self):
        self.world('move/할퀴기');native=self.e.r.move('move/할퀴기')
        self.start(self.t);self.e.activate_blender(self.t,reason='actual camouflage before Pass')
        self.assertEqual(WEAPONS.range_spec(self.e,native,self.a)['origin'],'melee')
        self.assertEqual(B.evasion(self.e,self.t,native,self.a),2)
        self.start(self.a)
        with patch.object(Engine,'d20',return_value=19):
            self.e.use_pass_move(self.a,'move/할퀴기',(6,3),event_id='blender/actual-pass',
                object_adjudications={},source='gm/observed-clear-pass',reason='actual clear Pass path with creature recipients')
        rows=[r for r in self.e._move_completions.values() if r['actor'] is self.a and r['move_id']=='move/할퀴기' and r['phase']=='complete']
        self.assertEqual(len(rows),1);self.assertIn(self.t.entity_id,rows[0]['results'])
        self.assertEqual(self.a.pos,(6,3));self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.a.budget['shift'],0)

    def test_real_type_ace_range_conversion_uses_attacker_at_native_preflight_and_accuracy(self):
        helper=TYPE_FIXTURE.TypeAceAcquisitionTests('runTest')
        helper.rules=Rules(ROOT,ruleset='core');helper.setup()
        helper.acquire(branch='불꽃');helper.acquire('Brightest Flame');helper.acquire('Fan The Flames')
        target=catalog_blender(helper.e,(3,2))
        helper.e.gm.set_move(helper.p,'move/화염방사',reason='actual learned Fire Move for conversion')
        helper.e.start_round(helper.e.everyone);helper.e.start_of_turn(target,initiative_count=20)
        helper.e.activate_blender(target,reason='actual camouflage against converted attack')
        helper.e.end_of_turn(target);helper.e.start_of_turn(helper.p,initiative_count=20)
        move=helper.e.r.move('move/화염방사')
        ranged=next(face for face in range(2,20) if helper.e.accuracy_check(helper.p,target,move,fixed_roll=face)[0])
        base=target.evasion(move['class'],attacker=helper.p,engine=helper.e)
        difference=min(9,base+4)-min(9,base+2)
        self.assertGreater(difference,0);face=ranged-difference
        self.assertFalse(helper.e.accuracy_check(helper.p,target,move,fixed_roll=face)[0])
        with patch.object(Engine,'d20',return_value=face):
            TA.use_move(helper.e,helper.t,helper.p,target,'move/화염방사',
                feature=TA.uid('Fan The Flames'),set_damage=True)
        rows=[r for r in helper.e._move_completions.values() if r['actor'] is helper.p and r['move_id']=='move/화염방사' and r['phase']=='complete']
        self.assertEqual(len(rows),1);self.assertTrue(rows[0]['results'][target.entity_id]['hit'])
        helper.valid()

    def test_real_duelist_conversion_and_catalog_state_survive_native_json_and_gm_restore(self):
        helper=DUELIST_FIXTURE.DuelistMomentumTests('runTest');helper.rules=Rules(ROOT,ruleset='all')
        helper.setup();helper.rounds(3)
        target=catalog_blender(helper.e,(helper.p.pos[0]+1,helper.p.pos[1]))
        helper.start(target);helper.e.activate_blender(target,reason='actual camouflage before Duelist conversion')
        helper.manual(2)
        move=helper.e.r.move('move/불태우기');effective=WEAPONS.range_spec(helper.e,move,helper.p)
        self.assertEqual(effective['origin'],'melee');self.assertNotIn('shape',effective)
        self.assertEqual(B.evasion(helper.e,target,move,helper.p),2)
        helper.start(helper.p);helper.attack(move='move/불태우기',target=target,area=True,natural=19)
        rows=[r for r in helper.e._move_completions.values() if r['actor'] is helper.p and r['move_id']=='move/불태우기' and r['phase']=='complete']
        self.assertEqual(set(rows[-1]['results']),{target.entity_id})
        self.assertTrue(rows[-1]['results'][target.entity_id]['hit'])
        self.world('move/일렉트릭네트');self.start(self.t)
        self.e.activate_blender(self.t,reason='actual catalog state for restoration')
        view=deepcopy(B.projection(self.t));identity=self.t.entity_id
        self.e.gm.snapshot('actual catalog Blender')
        payload=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
        restored=CODEC.load_engine(Rules(ROOT,ruleset='core'),payload)
        actor=WORLD.actor_index(restored)[identity]
        self.assertEqual(B.projection(actor),view);self.assertIs(B.validate(actor)['turn_owner'],actor)
        self.e.end_of_turn(self.t);self.start(self.t);self.e.end_of_turn(self.t)
        self.assertFalse(B.projection(self.t)['active'])
        self.e.gm.restore('actual catalog Blender',reason='restore actual camouflage source and owner clock')
        self.t=WORLD.actor_index(self.e)[identity]
        self.assertEqual(B.projection(self.t),view);self.assertIs(B.validate(self.t)['turn_owner'],self.t)


if __name__=='__main__':unittest.main(verbosity=2)
