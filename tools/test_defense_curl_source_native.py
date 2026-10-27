"""Native Core and September Defense Curl costs, sources, consumers and endings."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from engine import Engine,Rules
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import defense_curl as CURL
import blessing_effects as CONDITIONS
import world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]
TACKLE='move/몸통박치기'
ICE='move/아이스볼'
ROLL='move/구르기'


class DefenseCurlSourceTests(unittest.TestCase):
    def world(self,*,variant='core',rolling=False):
        moves=[CURL.MOVE,TACKLE]+([ICE,ROLL] if rolling else [])
        def declaration(key,pos,side):
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':40,
                'stats':{'hp':100,'atk':60,'def':5,'spa':30,'spd':5,'spe':10},
                'moves':moves,'abilities':[],'pos':pos,'side':side,
                'extra':{'movement':{'land':6,'power':3},'movement_basis':'current'}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual native Curl combatant'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='core',seed=7517,grid={'width':20,'height':12},
            actors=[declaration('curl',(2,2),'party'),declaration('foe',(3,2),'foe')])
        self.a,self.foe=actors['curl'],actors['foe']
        if variant!='core':self.e.choose_defense_curl_source(self.a,variant,reason='actual complete September source choice')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def cast(self):
        before=self.a.budget['standard'];uses=self.a.move_uses.get(CURL.MOVE,0)
        self.e.use_move(self.a,self.a,CURL.MOVE)
        self.assertEqual(self.a.budget['standard'],before-1)
        self.assertEqual(self.a.move_uses[CURL.MOVE],uses+1)
        self.assertIn(CURL.NAME,self.a.conditions)
        return CURL.live(self.a)

    def next_turn(self):
        self.e.end_of_turn(self.e._active_turn_actor);self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20)

    def restore(self):
        ids=(self.a.entity_id,self.foe.entity_id)
        saved=self.e.gm.snapshot();self.e.gm.restore(saved)
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=WORLD.actor_index(self.e);self.a,self.foe=[index[uid] for uid in ids]
        self.assertTrue(self.e.validate_state()['valid'])

    def test_core_native_cost_slowness_accuracy_and_swift_end_preserve_independent_slow(self):
        self.world();self.cast()
        self.assertIn('둔화',CONDITIONS.effective_conditions(self.a));self.assertEqual(self.e.move_profile(self.a)[0],3)
        self.assertFalse(self.e.accuracy_check(self.a,self.foe,self.e.r.move(TACKLE),fixed_roll=5)[0])
        self.next_turn();hp=self.foe.hp
        with patch.object(Engine,'d20',return_value=5):self.e.use_move(self.a,self.foe,TACKLE,set_damage=True)
        self.assertEqual(self.foe.hp,hp);self.assertEqual(self.a.budget['standard'],0)
        self.e.apply_status(self.a,'둔화',source='condition/둔화')
        self.assertTrue(self.e.stop_defense_curl(self.a));self.assertEqual(self.a.budget['swift'],0)
        self.assertNotIn(CURL.NAME,self.a.conditions);self.assertIn('둔화',self.a.conditions)
        self.assertEqual(self.e.move_profile(self.a)[0],3)
        self.e.cure_status(self.a,'둔화');self.assertEqual(self.e.move_profile(self.a)[0],6)
        self.assertEqual(self.a.spec['effect_instance_history'][-1]['effect_instance']['end_event'],
                         {'kind':'defense_curl_end','boundary':'swift'})

    def test_core_actual_hit_immunity_and_ten_dr_use_native_damage_and_restore(self):
        self.world();move=self.e.r.move(TACKLE)
        baseline=self.e.roll_damage(self.foe,self.a,move,set_damage=True)
        self.cast();self.restore()
        protected=self.e.roll_damage(self.foe,self.a,move,set_damage=True)
        self.assertEqual(baseline-protected,10)
        self.assertEqual(self.e.roll_damage(self.foe,self.a,move,crit=True,set_damage=True),protected)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.foe,initiative_count=10)
        hp=self.a.hp
        with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.foe,self.a,TACKLE,set_damage=True)
        self.assertEqual(hp-self.a.hp,protected);self.assertTrue(CURL.live(self.a))

    def test_both_rolling_moves_have_no_core_penalty_and_gain_exact_ten_native_damage(self):
        for variant in ('core','september_playtest'):
            with self.subTest(variant=variant):
                self.world(variant=variant,rolling=True)
                baseline={mid:self.e.roll_damage(self.a,self.foe,self.e.r.move(mid),set_damage=True) for mid in (ICE,ROLL)}
                self.cast();self.assertNotIn('둔화',CONDITIONS.effective_conditions(self.a))
                self.assertEqual(self.e.move_profile(self.a)[0],6)
                for mid in (ICE,ROLL):
                    move=self.e.r.move(mid)
                    threshold=move['ac']+self.foe.evasion(move['class'],attacker=self.a,engine=self.e)
                    self.assertTrue(self.e.accuracy_check(self.a,self.foe,move,fixed_roll=threshold)[0])
                    self.assertFalse(self.e.accuracy_check(self.a,self.foe,move,fixed_roll=threshold-1)[0])
                    self.assertEqual(self.e.roll_damage(self.a,self.foe,self.e.r.move(mid),set_damage=True)-baseline[mid],10)
                self.next_turn();hp=self.foe.hp
                with patch.object(Engine,'d20',return_value=10):self.e.use_move(self.a,self.foe,ICE,set_damage=True)
                self.assertEqual(hp-self.foe.hp,baseline[ICE]+10)
                self.assertEqual(self.a.move_uses[ICE],1);self.assertEqual(self.a.budget['standard'],0)

    def test_choice_changes_only_future_cast_and_september_has_its_own_stage_and_lifetime(self):
        self.world();self.cast();original=CURL.live(self.a)['id']
        self.e.choose_defense_curl_source(self.a,'september_playtest',reason='actual later table source choice')
        self.assertEqual(CURL.live(self.a)['id'],original);self.assertTrue(CURL.critical_immune(self.a))
        self.restore();self.assertTrue(CURL.critical_immune(self.a));self.assertEqual(self.a.stages['def'],0)
        self.next_turn();self.cast();self.assertEqual(self.a.stages['def'],1)
        self.assertFalse(CURL.critical_immune(self.a));self.assertNotIn('둔화',CONDITIONS.effective_conditions(self.a))
        self.assertTrue(self.e.accuracy_check(self.a,self.foe,self.e.r.move(TACKLE),fixed_roll=5)[0])
        self.assertTrue(self.e.accuracy_check(self.foe,self.a,self.e.r.move(TACKLE),fixed_roll=20)[2])
        before=CODEC.dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'active Core'):self.e.stop_defense_curl(self.a)
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.e.end_of_turn(self.a);self.e.end_scene([self.a,self.foe],round_elapsed_seconds=10)
        self.assertFalse(CURL.live(self.a));self.assertEqual(self.a.stages['def'],0)
        self.restore()

    def test_source_specific_recall_and_breather_endings_and_core_scene_persistence(self):
        for variant in ('core','september_playtest'):
            for ending in ('recall','breather','scene'):
                with self.subTest(variant=variant,ending=ending):
                    self.world(variant=variant);self.cast();self.next_turn()
                    if ending=='recall':self.e.gm.recall(self.a,reason='actual source-ending recall')
                    elif ending=='scene':
                        self.e.end_of_turn(self.a);self.e.end_scene([self.a,self.foe],round_elapsed_seconds=10)
                    else:
                        self.e.gm.set_position(self.foe,(15,2),reason='actual foe outside retreat route')
                        length=self.e.move_profile(self.a)[0]
                        path=[(2,2+i) for i in range(length+1)]
                        result=self.e.take_breather(self.a,request_id='curl-rest',path=path,
                            retreat_reason='actual maximal observed retreat',save_dc=1,save_reason='explicit GM permission DC',
                            save_cost='full',fixed_save=20)
                        self.assertIsInstance(result,dict)
                        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
                    self.assertEqual(bool(CURL.live(self.a)),variant=='core')
                    self.assertTrue(self.e.validate_state()['valid'])

    def test_rollout_actual_pass_uses_same_source_bonus_and_one_paid_activation(self):
        observed={}
        for variant in ('uncurled','core','september_playtest'):
            self.world(variant='core' if variant=='uncurled' else variant,rolling=True)
            if variant!='uncurled':self.cast()
            self.next_turn();hp=self.foe.hp
            with patch.object(Engine,'d20',return_value=10):
                self.e.use_pass_move(self.a,ROLL,(4,2),event_id='curl-pass',object_adjudications={},
                    source='gm/observed-object-hits',reason='actual complete Rollout route')
            observed[variant]=hp-self.foe.hp
            self.assertEqual(self.a.pos,(4,2));self.assertEqual(self.a.move_uses[ROLL],1)
            self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0))
            self.assertTrue(self.e.validate_state()['valid'])
        self.assertGreater(observed['uncurled'],0)
        self.assertEqual(observed['core'],observed['uncurled']+10)
        self.assertEqual(observed['september_playtest'],observed['uncurled']+10)

    def test_late_september_stage_failure_rolls_back_cost_state_history_and_rng(self):
        self.world(variant='september_playtest');before=CODEC.dump_engine(self.e)
        with patch.object(Engine,'change_stage',side_effect=ValueError('actual Curl stage receiver failed')):
            with self.assertRaisesRegex(ValueError,'actual Curl stage receiver failed'):
                self.e.use_move(self.a,self.a,CURL.MOVE)
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.assertFalse(CURL.live(self.a))

    def test_invalid_choice_or_tampered_producing_variant_rejects_before_native_payment(self):
        self.world();before=CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.choose_defense_curl_source(self.a,'not-a-source',reason='invalid selection')
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.cast();self.next_turn();row=CURL.live(self.a);row['effect']['variant']='september_playtest'
        budget=deepcopy(self.a.budget);uses=deepcopy(self.a.move_uses);rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.e.use_move(self.a,self.a,CURL.MOVE)
        self.assertEqual((self.a.budget,self.a.move_uses,self.e.rng.getstate()),(budget,uses,rng))
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)


if __name__=='__main__':unittest.main()
