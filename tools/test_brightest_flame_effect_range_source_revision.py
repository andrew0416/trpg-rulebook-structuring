"""S-p2c4-5: native Brightest Flame uses the existing live Effect Range owner."""
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_type_ace_acquisition as FIX
from engine import Engine,Rules
import class_passive_combat as PASSIVE
import combat_precision_features as PRECISION
import fast_combat as FAST
import native_scenario_fixture as NATIVE
import pokemon_move_edges as MOVES
import state_codec as CODEC
import state_grants as GRANTS
import taskmaster as TASK
import trainer_feature_acquisition as ACQUIRE
import training_features as TRAIN
import type_ace as TA
import world_entities as WORLD

FEATURE='feat/빛나는-화염'
FIRE='move/오버히트'
EMBER='move/불꽃세례'
WATER='move/물대포'


class BrightestFlameEffectRangeSourceRevisionTests(unittest.TestCase):
    def world(self,*,training=False,hardened=False,receipted=True,feature=True):
        fixture=FIX.TypeAceAcquisitionTests();fixture.rules=Rules(ROOT,ruleset='core');fixture.setup()
        self.e,self.t,self.p,self.q,self.b=fixture.e,fixture.t,fixture.p,fixture.q,fixture.b
        self.fixture=fixture
        self.t.spec['feats'].append(TRAIN.BRUTAL)
        fixture.acquire()
        if feature:
            if receipted:fixture.acquire(FEATURE)
            else:self.t.spec['feats'].append(FEATURE)
        for move in (FIRE,EMBER,WATER):
            self.e.gm.set_move(self.p,move,reason='actual learned native attack for the Effect Range boundary')
        self.e.register_abilities(self.p)
        if hardened:
            ACQUIRE.acquire_static(self.e,self.t,TASK.CLASS,acquisition_request_id='brightest/actual-taskmaster')
            self.e.rulings.add_answer('taskmaster',1,reason='actual Taskmaster grants one injury after Brutal Training')
        if training or hardened:
            self.training=self.e.train_pokemon(self.t,[(self.p,[TRAIN.BRUTAL])],minutes=30,
                request_id='brightest/actual-brutal-training',safe=True,
                reason='actual completed native Brutal Training for Effect Range')
            self.assertEqual(TRAIN.bonus(self.p,'effect'),1)
        if hardened:
            self.assertEqual(TASK.bonus(self.p,'effect'),1)
            self.assertEqual(self.p.injuries,1)

    def combat(self):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)

    def attack(self,*,move=FIRE,face=17):
        with patch.object(FAST,'roll',return_value=face):
            return self.e.use_move(self.p,self.b,move,set_damage=True)

    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])

    def restore(self):
        ids=[actor.entity_id for actor in (self.t,self.p,self.q,self.b)]
        state=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),state)
        index=WORLD.actor_index(self.e);self.t,self.p,self.q,self.b=[index[uid] for uid in ids]

    def sync(self,move,branch):
        fixture=self.fixture
        if branch!='불꽃':fixture.acquire(branch=branch)
        fixture.acquire(TA.REFRESH,branch)
        fixture.acquire(TA.SYNC,branch)
        TA.sync(self.e,self.t,self.p,branch,seconds=60,application_id='brightest/native-type-sync',
            move_id=move,new_name='실제 타입 변경 기술',
            effect_decision={'mode':'preserve','reason':'Preserve all native effects while changing only the reviewed type.','effects_exec':None},
            feasibility_review='Printed range, accuracy, class, frequency and target count remain unchanged.',
            power_review='Printed damage base and every native executable effect remain unchanged.',
            reason='actual completed native Move Sync before combat')
        self.assertEqual(MOVES.prepare(self.e,self.p,self.e.r.move(move))['type'],branch)

    def test_actual_training_and_hardened_attack_thresholds_use_effect_range_without_changing_raw_roll(self):
        cases=((False,False,17,False),(False,False,18,True),
               (True,False,16,False),(True,False,17,True),
               (True,True,15,False),(True,True,16,True))
        for training,hardened,face,burns in cases:
            for receipted in (False,True):
                with self.subTest(training=training,hardened=hardened,face=face,receipted=receipted):
                    self.world(training=training,hardened=hardened,receipted=receipted)
                    self.combat();owner_history=list(self.t._action_history)
                    hit,natural,critical=self.e.accuracy_check(self.p,self.b,self.e.r.move(FIRE),fixed_roll=face)
                    self.assertEqual((hit,natural,critical),(True,face,False))
                    self.assertGreater(self.attack(face=face),0)
                    self.assertEqual('화상' in self.b.conditions,burns)
                    self.assertEqual(self.p.move_uses[FIRE],1)
                    self.assertEqual(self.p._action_history,['standard'])
                    self.assertEqual(self.t._action_history,owner_history)
                    self.valid()

    def test_intrinsic_burn_plus_three_is_native_and_never_gets_a_second_passive_burn(self):
        for training,face,burns in ((False,15,False),(False,16,True),(True,14,False),(True,15,True)):
            with self.subTest(training=training,face=face):
                self.world(training=training);self.combat()
                with patch.object(self.e,'apply_status',wraps=self.e.apply_status) as statuses:
                    self.assertGreater(self.attack(move=EMBER,face=face),0)
                burns_applied=[call for call in statuses.call_args_list if call.args[1]=='화상']
                self.assertEqual(len(burns_applied),int(burns))
                if burns:self.assertEqual(burns_applied[0].kwargs['source'],EMBER)
                self.assertEqual('화상' in self.b.conditions,burns);self.valid()

    def test_existing_type_link_rank_damage_against_burned_target_is_unchanged(self):
        for receipted in (False,True):
            damage=[]
            for burned in (False,True):
                self.world(receipted=receipted)
                if burned:self.e.gm.add_condition(self.b,'화상',reason='actual target was already Burned before this attack')
                self.combat();damage.append(self.attack(face=10));self.valid()
            self.assertEqual(damage[1]-damage[0],6)

    def test_actual_move_sync_uses_current_damage_type_in_both_directions(self):
        for move,branch,burns in ((WATER,'불꽃',True),(FIRE,'물',False)):
            with self.subTest(move=move,branch=branch):
                self.world(training=True);self.sync(move,branch);self.combat()
                self.assertGreater(self.attack(move=move),0)
                self.assertEqual('화상' in self.b.conditions,burns);self.valid()

    def test_feature_absence_removal_and_actual_withdrawal_do_not_leave_a_burn_grant(self):
        self.world(training=True,feature=False);self.combat();self.attack()
        self.assertNotIn('화상',self.b.conditions);self.valid()
        self.world(training=True,receipted=False)
        self.t.spec['feats'].remove(FEATURE);self.e.register_abilities(self.p)
        self.combat();self.attack();self.assertNotIn('화상',self.b.conditions);self.valid()
        self.world(training=True)
        source=next(sid for sid,row,active in ACQUIRE._static_records(self.t)
            if active and row['static_acquisition']['feature_id']==FEATURE)
        GRANTS.revoke(self.t,source,engine=self.e);self.e.register_abilities(self.p)
        self.combat();self.attack();self.assertNotIn('화상',self.b.conditions);self.valid()

    def test_wrong_selected_source_rejects_before_native_cost_damage_or_rng(self):
        self.world(training=True);self.combat();before=CODEC.dump_engine(self.e)
        selected=self.e.r._selected_rule
        def other_source(uid):return FEATURE+'/unreviewed' if uid==FEATURE else selected(uid)
        with patch.object(self.e.r,'_selected_rule',side_effect=other_source):
            with self.assertRaisesRegex(ValueError,'selected feature variant'):
                self.attack()
        self.assertEqual(CODEC.dump_engine(self.e),before)
        self.assertNotIn('화상',self.b.conditions);self.valid()

    def test_natural_one_miss_and_nonfire_attack_keep_native_face_rules(self):
        for move,face in ((FIRE,1),(WATER,20)):
            with self.subTest(move=move,face=face):
                self.world(training=True,hardened=True);self.combat()
                damage=self.attack(move=move,face=face)
                if face==1:self.assertEqual(damage,0)
                else:self.assertGreater(damage,0)
                self.assertNotIn('화상',self.b.conditions)
                self.assertEqual(self.p.move_uses[move],1);self.valid()

    def test_gm_and_fresh_rules_json_restore_retain_actual_bonus_source_and_no_replay(self):
        self.world(training=True,hardened=True);self.combat()
        ids=[actor.entity_id for actor in (self.t,self.p,self.q,self.b)]
        self.e.gm.snapshot('brightest-before');self.e.gm.restore('brightest-before');self.restore()
        self.assertEqual([actor.entity_id for actor in (self.t,self.p,self.q,self.b)],ids)
        self.assertEqual((TRAIN.bonus(self.p,'effect'),TASK.bonus(self.p,'effect')),(1,1))
        self.assertGreater(self.attack(face=16),0);self.assertIn('화상',self.b.conditions)
        history=list(self.p._action_history);hp=self.b.hp
        self.e.gm.snapshot('brightest-after');self.e.gm.restore('brightest-after');self.restore()
        self.assertIn('화상',self.b.conditions);self.assertEqual(self.b.hp,hp)
        self.assertEqual(self.p._action_history,history);self.assertEqual(self.p.move_uses[FIRE],1)
        self.assertIs(PASSIVE._declaration(self.e,self.p,FEATURE)[0],self.t)
        self.valid()

    def test_late_passive_burn_failure_uses_existing_native_transaction_rollback(self):
        self.world(training=True,hardened=True);self.combat()
        apply_status=Engine.apply_status
        def fail(e,target,status,*args,**kwargs):
            if kwargs.get('source')==FEATURE:raise ValueError('actual Brightest Flame receiver failed')
            return apply_status(e,target,status,*args,**kwargs)
        with patch.object(Engine,'apply_status',new=fail):
            NATIVE.assert_rejected_unchanged(self.e,lambda:self.attack(face=16),
                reason_pattern='actual Brightest Flame receiver failed')
        self.assertNotIn('화상',self.b.conditions);self.assertEqual(self.p.move_uses.get(FIRE,0),0)
        self.assertEqual(self.p._action_history,[]);self.valid()


if __name__=='__main__':unittest.main()
