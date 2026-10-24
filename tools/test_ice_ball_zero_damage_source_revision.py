"""S-move1-6: a real zero-damage Ice Ball hit continues the successful-use chain."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import conditional_damage_base as CONDITIONAL
import fast_combat as FAST
import forced_move_lock as FORCED
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import world_entities as WORLD

ICE='move/아이스볼'
TACKLE='move/몸통박치기'


class IceBallZeroDamageSourceRevisionTests(unittest.TestCase):
    def world(self):
        def actor(key,pos,side,moves):
            stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),30)
            stats['hp']=1000
            if key=='user':stats['atk']=1
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':30,'stats':stats,
                'moves':moves,'abilities':[],'skills':{},'pos':pos,'side':side,
                'extra':{'id':'ice-ball-'+key,'types':['노말'],
                    'movement':{'land':6,'power':3},'movement_basis':'current','power_basis':'current'}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual complete native trainer body'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='core',seed=421,
            grid={'width':10,'height':8},actors=[actor('user',(2,2),'party',[ICE,TACKLE]),
                actor('first',(3,2),'foe',[]),actor('second',(3,3),'foe',[])])
        self.a,self.b,self.c=[actors[key] for key in ('user','first','second')]
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=30)

    def next_turn(self):
        self.e.end_of_turn(self.a);self.e.end_round()
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=30)

    def target_state(self,target,*,zero):
        self.e.gm.set_stat(target,'def',value=1000 if zero else 30,
            reason='actual observed Defense makes resisted minimum damage zero' if zero else 'actual ordinary Defense')
        self.e.gm.set_types(target,['강철'] if zero else ['노말'],
            reason='actual Steel resistance after the native minimum-one defense step' if zero else 'actual neutral typing')

    def base(self,target=None):
        return self.e.damage_base(self.a,self.e.r.move(ICE),target=self.b if target is None else target)

    def successes(self):
        return CONDITIONAL._streak(self.a,self.e.r.move(ICE)).get('successes',0)

    def use(self,target=None,*,move=ICE,face=15):
        with patch.object(FAST,'roll',return_value=face):
            return self.e.use_move(self.a,self.b if target is None else target,move,set_damage=True)

    def hit(self,target,*,zero):
        self.target_state(target,zero=zero)
        hp,temp=target.hp,target.temp_hp;before=set(getattr(self.e,'_move_completions',{}))
        dealt=self.use(target)
        completion=next(row for key,row in self.e._move_completions.items() if key not in before)
        self.assertEqual((completion['actor'],completion['move_id'],completion['phase'],completion['sealed']),
            (self.a,ICE,'complete',True))
        result=completion['results'][target.entity_id]
        self.assertTrue(result['hit']);self.assertFalse(result['cancelled'])
        if zero:
            self.assertEqual((dealt,result['dealt']),(0,0))
            self.assertEqual((target.hp,target.temp_hp),(hp,temp))
        else:self.assertGreater(dealt,0)
        self.assertEqual(self.a._action_history,['standard'])
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(FORCED.current(self.e,self.a),ICE)

    def resources(self):
        return deepcopy((self.a.budget,self.a.move_uses,self.a._action_history,
            self.a.custom_conditions,self.a.locked_move,self.e.rng.getstate()))

    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])

    def restore(self):
        ids=[actor.entity_id for actor in (self.a,self.b,self.c)]
        state=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),state)
        index=WORLD.actor_index(self.e);self.a,self.b,self.c=[index[uid] for uid in ids]

    def test_real_resisted_zero_on_first_or_third_hit_keeps_progression_cap_lock_and_changed_targets(self):
        for zero_index in (0,2):
            with self.subTest(zero_index=zero_index):
                self.world()
                for index,base in enumerate((3,6,9,12,15,15)):
                    target=self.b if index%2==0 else self.c
                    self.assertEqual(self.base(target),base)
                    self.hit(target,zero=index==zero_index)
                    self.assertEqual(self.successes(),index+1)
                    self.assertEqual(self.a.move_uses[ICE],index+1)
                    self.assertEqual(self.base(target),min(15,base+3))
                    if index<5:self.next_turn()
                self.valid()

    def test_actual_miss_and_no_target_reset_while_another_move_rejects_without_resource_or_rng_cost(self):
        self.world();self.hit(self.b,zero=True);self.next_turn()
        before=self.resources();self.assertEqual(self.use(move=TACKLE),0)
        self.assertEqual(self.resources(),before);self.assertEqual(self.successes(),1)
        self.assertEqual(self.use(face=1),0)
        self.assertIsNone(FORCED.current(self.e,self.a));self.assertEqual(self.successes(),0)
        self.next_turn();self.assertEqual(self.base(),3);self.hit(self.b,zero=True);self.next_turn()
        self.e.gm.recall(self.b,reason='actual first target leaves the encounter field')
        self.e.gm.recall(self.c,reason='actual last remaining target leaves the encounter field')
        budget=deepcopy(self.a.budget);uses=deepcopy(self.a.move_uses);rng=self.e.rng.getstate()
        self.assertEqual(self.e.use_move_on(self.a,self.a,ICE,self.e.everyone,set_damage=True),0)
        self.assertIsNone(FORCED.current(self.e,self.a));self.assertEqual(self.successes(),0)
        self.assertEqual((self.a.budget,self.a.move_uses,self.e.rng.getstate()),(budget,uses,rng))
        self.e.gm.send_out(self.b,pos=(3,2),reason='actual target returns after the chain ended')
        self.target_state(self.b,zero=False)
        self.assertGreater(self.use(move=TACKLE),0)
        self.next_turn();self.assertEqual(self.base(),3);self.valid()

    def test_gm_and_fresh_rules_json_restore_keep_paid_zero_hit_and_next_db_twelve_once(self):
        self.world();self.hit(self.b,zero=False);self.next_turn()
        self.hit(self.c,zero=False);self.next_turn();self.hit(self.b,zero=True)
        self.assertEqual((self.successes(),self.a.move_uses[ICE]),(3,3))
        self.e.gm.snapshot('actual-paid-zero-hit');self.e.gm.restore('actual-paid-zero-hit');self.restore()
        self.assertEqual((self.successes(),self.a.move_uses[ICE]),(3,3))
        self.assertEqual(self.a._action_history,['standard']);self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(FORCED.current(self.e,self.a),ICE)
        self.assertEqual(self.base(self.c),12);self.assertEqual(self.base(self.c),12)
        self.assertEqual(self.successes(),3)
        self.next_turn();self.hit(self.c,zero=False)
        self.assertEqual((self.successes(),self.a.move_uses[ICE],self.base(self.c)),(4,4,15))
        self.valid()


if __name__=='__main__':unittest.main()
