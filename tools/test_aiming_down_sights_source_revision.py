"""FAN104: one actual long-range weapon activation owns every aiming bonus."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Engine
import fast_combat as FAST
import native_scenario_fixture as NATIVE
import optional_state_effect_contracts as OPTIONAL
import passive_events as PASSIVE
import state_codec as CODEC
import state_grants as G
import turn as TURN
import weapon_actions as WEAPONS

ROOT=Path(__file__).resolve().parents[1]
FEATURE='feat/시야-아래-조준'
TRIPLE='move/3중공격'
SALVO='move/일제사격'
DOUBLE='move/두번-베기'


class AimingDownSightsSourceRevisionTests(unittest.TestCase):
    def world(self,*,kind='장거리 사격무기',moves=(TRIPLE,SALVO),near=False):
        def declaration(key,pos,side,owned=False):
            extra={'skills':{'전투':6,'육상':3,'곡예':3},
                   'movement':{'land':6,'power':3},'movement_basis':'current'}
            if owned:extra['feats']=[FEATURE]
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':40,
                'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),
                'moves':['move/몸통박치기','move/스피드스타'],'abilities':[],
                'pos':pos,'side':side,'extra':extra},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual weapon user and observed targets'}}
        positions=((5,2),(6,2),(5,3)) if near else ((8,2),(9,2),(8,3))
        if kind=='소형 근접무기':positions=((3,2),(6,2),(5,3))
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=104,
            grid={'width':24,'height':12},actors=[declaration('marksman',(2,2),'party',True)]+
            [declaration('foe'+str(n),pos,'foe') for n,pos in enumerate(positions,1)])
        self.a=actors['marksman'];self.targets=[actors['foe'+str(n)] for n in (1,2,3)]
        self.weapon=TURN.equip_weapon(self.e,self.a,{'name':'actual aiming weapon','kind':kind,
            'grade':'좋음','slot':'주요손','moves':list(moves)})
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.e.activate_optional_state_effect(self.a,'FAN-104')
        self.seen=[]

    def observe_modifiers(self):
        original=OPTIONAL.attack_modifiers
        def observe(actor,move,**options):
            result=original(actor,move,**options)
            if options.get('engine') is not None:self.seen.append(result)
            return result
        return patch.object(OPTIONAL,'attack_modifiers',side_effect=observe)

    def attack(self,move,*,area=False):
        options={'weapon_id':self.weapon,'set_damage':True}
        if area:options['aim']=self.targets[0].pos
        return self.e.use_move_on(self.a,self.targets[0],move,self.e.everyone,**options)

    def completion(self):return list(self.e._move_completions.values())[-1]

    def assert_consumed(self):
        self.assertFalse(OPTIONAL.records(self.a,FEATURE))
        self.assertEqual(len(self.completion()['optional_aiming']),1)
        self.assertEqual(self.a.budget['shift'],0)
        self.assertEqual(self.a.budget['standard'],0)

    def restore(self):
        identities=[actor.entity_id for actor in [self.a,*self.targets]]
        self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index={actor.entity_id:actor for actor in self.e.everyone}
        self.a,*self.targets=[index[uid] for uid in identities]

    def test_actual_three_recipient_weapon_activation_gives_every_target_accuracy_and_critical(self):
        self.world();rng=self.e.rng.getstate()
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18) as rolls:
            self.attack(TRIPLE)
        self.assertEqual(rolls.call_count,3);self.assertEqual(self.seen,[(2,2)]*3)
        self.assert_consumed();self.assertEqual(self.a.move_uses[TRIPLE],1)
        self.assertEqual(self.e.rng.getstate(),rng)
        events=[event for event in self.e._passive_events.values() if event['actor'] is self.a]
        self.assertEqual(len(events),3)
        for event in events:
            accuracy=next(row['facts'] for row in PASSIVE.observations(self.e,event['id']) if row['stage']=='accuracy')
            self.assertTrue(accuracy['hit']);self.assertTrue(accuracy['critical'])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_area_weapon_activation_keeps_one_shared_roll_and_all_target_bonuses(self):
        self.world()
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18) as rolls:
            self.attack(SALVO,area=True)
        self.assertEqual(rolls.call_count,1);self.assertEqual(self.seen,[(2,2)]*3)
        self.assert_consumed();self.assertEqual(self.a.move_uses[SALVO],1)
        self.assertEqual(len(self.completion()['results']),3)
        self.assertTrue(self.e.validate_state()['valid'])

        import ice_lake as ICE_LAKE
        self.world()
        ICE_LAKE.adopt(self.e,shallow_cells=[(12,8)],breaking_moves=[SALVO],
            water_air_available=True,gm_id='actual-gm',reason='explicit Salvo ice-breaking adoption')
        rng=self.e.rng.getstate()
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18) as rolls:
            self.e.use_move_on(self.a,self.targets[0],SALVO,self.e.everyone,
                weapon_id=self.weapon,set_damage=True,aim=(12,8))
        self.assertEqual(rolls.call_count,0);self.assertEqual(self.seen,[])
        self.assert_consumed();self.assertEqual(self.a.move_uses[SALVO],1)
        self.assertEqual(self.e.rng.getstate(),rng)
        row=self.completion()
        self.assertEqual(row['activation'],'empty_area_field');self.assertEqual(row['phase'],'complete')
        self.assertEqual(row['targets'],[]);self.assertEqual(row['started'],[]);self.assertEqual(row['results'],{})
        self.assertIn((12,8),row['field_cells']);self.assertEqual(row[ICE_LAKE.KEY]['phase'],'resolved')
        self.assertEqual(row['optional_aiming'][0]['payload'],{'accuracy':2,'critical_range':2})
        self.e.gm.snapshot('empty-aim-used');self.e.gm.restore('empty-aim-used');self.restore()
        self.assert_consumed();self.assertEqual(self.a.move_uses[SALVO],1)
        self.assertEqual(len(self.e._move_completions),1)
        self.assertEqual(self.completion()['activation'],'empty_area_field')
        self.assertEqual(self.completion()['optional_aiming'][0]['payload'],{'accuracy':2,'critical_range':2})
        self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_double_strike_accuracy_rolls_share_one_consumed_weapon_activation(self):
        self.world(moves=(DOUBLE,))
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18) as rolls:
            self.e.use_move(self.a,self.targets[0],DOUBLE,weapon_id=self.weapon,set_damage=True)
        self.assertEqual(rolls.call_count,2);self.assertEqual(self.seen,[(2,2)]*2)
        self.assert_consumed();self.assertEqual(self.a.move_uses[DOUBLE],1)
        history=self.a.spec['multi_strike_history'][-1]
        self.assertEqual(history['rolls'],[[True,18,True],[True,18,True]])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_unarmed_short_and_melee_attacks_cannot_consume_the_long_range_weapon_bonus(self):
        for kind,ordinary in (('단거리 사격무기',False),('소형 근접무기',False),('장거리 사격무기',True)):
            with self.subTest(kind=kind,ordinary=ordinary):
                self.world(kind=kind,moves=(),near=True)
                move='move/스피드스타' if ordinary else self.weapon
                options={} if ordinary else {'weapon_id':self.weapon}
                with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18):
                    self.e.use_move(self.a,self.targets[0],move,set_damage=True,**options)
                self.assertTrue(self.seen);self.assertEqual(set(self.seen),{(0,0)})
                self.assertTrue(OPTIONAL.records(self.a,FEATURE))
                self.assertEqual(self.completion()['optional_aiming'],[])
        self.world(kind='단거리 사격무기',moves=())
        prepared=WEAPONS.prepare(self.e,self.a,self.e.r.move(self.weapon),self.weapon)
        prepared=deepcopy(prepared);prepared['_weapon_attack']['range']['origin']=12
        self.assertEqual(OPTIONAL.attack_modifiers(self.a,prepared),(0,0))
        self.assertTrue(OPTIONAL.records(self.a,FEATURE))

    def test_pre_activation_rejection_and_atomic_rollback_keep_pending_aim_and_resources(self):
        self.world(near=True,moves=())
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:self.e.use_move(self.a,self.targets[0],self.weapon,weapon_id=self.weapon,set_damage=True),
            reason_pattern='within four metres')
        self.assertTrue(OPTIONAL.records(self.a,FEATURE));self.assertEqual(self.a.budget['standard'],1)
        self.world(moves=())
        def staged(e,a,t):return e.use_move(a,t,self.weapon,weapon_id=self.weapon,set_damage=True)
        with patch.object(Engine,'_accuracy_check_native',side_effect=ValueError('actual accuracy receiver failed')):
            NATIVE.assert_rejected_unchanged(self.e,
                lambda:G.transition(self.e,self.a,staged,participants=(self.targets[0],),include_grid=True),
                reason_pattern='actual accuracy receiver failed')
        self.assertTrue(OPTIONAL.records(self.a,FEATURE));self.assertEqual(self.a.budget['standard'],1)

    def test_started_prefix_consumes_once_and_later_move_does_not_reuse_the_saved_bonus(self):
        self.world(moves=())
        with patch.object(Engine,'_accuracy_check_native',side_effect=ValueError('actual started receiver failed')):
            with self.assertRaisesRegex(ValueError,'actual started receiver failed'):
                self.e.use_move(self.a,self.targets[0],self.weapon,weapon_id=self.weapon,set_damage=True)
        self.assert_consumed();self.assertEqual(self.a.move_uses[self.weapon],1)
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.seen=[]
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18):
            self.e.use_move(self.a,self.targets[0],self.weapon,weapon_id=self.weapon,set_damage=True)
        self.assertEqual(self.seen,[(0,0)])
        self.assertEqual(self.completion()['optional_aiming'],[])

    def test_actual_pending_defense_and_cold_restore_resume_all_remaining_targets_without_reconsume(self):
        self.world()
        self.e.watch_move_defense(self.targets[0],[{'actor_id':self.targets[2].entity_id,
            'source':'maneuver/원거리-가로채기'}],reason='actual defender may intercept the first weapon hit')
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18) as before_rolls:
            with self.assertRaises(PASSIVE.PassiveEventPending):self.attack(TRIPLE)
        self.assertEqual(before_rolls.call_count,1);self.assertEqual(self.seen,[(2,2)])
        event=self.e._passive_pending;self.assert_consumed();rng=self.e.rng.getstate()
        self.e.gm.snapshot('aim-pending');self.e.gm.restore('aim-pending');self.restore();self.seen=[]
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18) as after_rolls:
            self.e.choose_move_defense(event,self.targets[2],use=False,reason='actual defender declines intercept')
        self.assertEqual(after_rolls.call_count,2);self.assertEqual(self.seen,[(2,2)]*2)
        self.assert_consumed();self.assertEqual(self.a.move_uses[TRIPLE],1)
        self.assertEqual(len(self.completion()['results']),3);self.assertEqual(self.e.rng.getstate(),rng)
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:self.e.choose_move_defense(event,self.targets[2],use=False,reason='attempted replay'),
            reason_pattern='pending|already|resolved')
        self.assertTrue(self.e.validate_state()['valid'])

    def test_unused_pending_effect_expires_at_owner_next_turn_and_saved_receipt_is_source_checked(self):
        self.world();self.e.gm.snapshot('unused-aim');self.e.gm.restore('unused-aim');self.restore()
        self.assertTrue(OPTIONAL.records(self.a,FEATURE))
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.assertFalse(OPTIONAL.records(self.a,FEATURE));self.seen=[]
        with self.observe_modifiers(),patch.object(FAST,'roll',return_value=18):self.attack(TRIPLE)
        self.assertEqual(self.seen,[(0,0)]*3)
        self.world()
        with patch.object(FAST,'roll',return_value=18):self.attack(TRIPLE)
        self.completion()['optional_aiming'][0]['payload']['accuracy']=3
        with self.assertRaisesRegex(ValueError,'consumed aiming Move receipt'):
            OPTIONAL.validate_world(self.e)


if __name__=='__main__':unittest.main(verbosity=2)
