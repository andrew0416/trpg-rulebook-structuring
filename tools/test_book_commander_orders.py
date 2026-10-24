"""Actual Mobilize and single-activation Commander transformations."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from commander_fixture import CommanderFixture
import commander as C,commander_orders as O,class_passive_combat as P
import action_points as AP,turn as TURN,training_features as TRAIN,priority_limited as PRIORITY
import cheerleader as CHEER,combat_precision_features as CPF


class CommanderOrderTests(CommanderFixture,unittest.TestCase):
    def test_mobilize_actual_opportunity_before_next_turn_during_and_after(self):
        self.scene();self.acquire(C.MOBILIZE);self.combat()
        self.e.gm.set_position(self.b,(3,2),reason='actual adjacent enemy')
        C.mobilize(self.e,self.a,self.p)
        self.assertFalse(C.no_opportunity(self.e,self.p));self.assertTrue(TURN.can_aoo(self.e,self.b))
        self.next_turn(self.p);hp=self.p.hp
        TURN.trigger_aoo(self.e,self.p,'인접 칸 밖으로 이동',enemies=[self.b])
        self.assertEqual(self.p.hp,hp);self.assertFalse(self.b.aoo_used)
        self.restore();self.assertTrue(C.no_opportunity(self.e,self.p));self.valid()
        self.e.end_of_turn(self.p);self.assertFalse(C.no_opportunity(self.e,self.p))
        self.next_round(self.p)
        TURN.trigger_aoo(self.e,self.p,'인접 칸 밖으로 이동',enemies=[self.b])
        self.assertTrue(self.b.aoo_used);self.assertFalse(C.no_opportunity(self.e,self.p))

    def test_mobilize_each_ally_once_encounter_not_scene_and_independent_csv84(self):
        self.scene();self.acquire(C.MOBILIZE);self.combat()
        first=C.mobilize(self.e,self.a,self.p,edition='local_csv')
        self.assertEqual(first['source']['record'],84)
        self.assertEqual(first['source']['cell_sha256'],'5aef5f0f947f504d2e59cc8b399d445c4cf14b81f27c77f4131ad26a0d002928')
        self.rejected(lambda:C.mobilize(self.e,self.a,self.p),'once per encounter')
        C.mobilize(self.e,self.a,self.q);self.valid();self.restore()
        self.rejected(lambda:C.mobilize(self.e,self.a,self.p),'once per encounter')
        self.e.end_encounter();self.combat();C.mobilize(self.e,self.a,self.p)
        self.assertEqual(len(C.uses(self.a)),3);self.valid()

    def test_mobilize_allied_trainer_wrong_side_unavailable_and_auditory_rejections(self):
        self.scene();self.acquire(C.MOBILIZE);self.combat()
        self.rejected(lambda:C.mobilize(self.e,self.a,self.b),'allied Trainer or Pokemon')
        self.rejected(lambda:C.mobilize(self.e,self.a,self.a),'allied Trainer or Pokemon')
        self.hears(self.q,False)
        self.rejected(lambda:C.mobilize(self.e,self.a,self.q),'communication.*delivered')
        self.hears(self.q);C.mobilize(self.e,self.a,self.q)
        self.e.gm.set_hp(self.s,value=0,reason='actual unavailable ally')
        self.rejected(lambda:C.mobilize(self.e,self.a,self.s),'conscious and available')

    def test_leadership_replaces_own_pokemon_with_actual_allied_trainer_for_existing_stratagem(self):
        self.scene(bundle='feat/명사수-지시');self.leaders();self.combat()
        initial=AP.available(self.a)
        self.e.issue_orders(self.a,P.TRICK_SHOT,self.q)
        self.assertIsNotNone(P._active(self.e,self.q,P.TRICK_SHOT));self.assertEqual(AP.available(self.a),initial-2)
        self.assertEqual(self.a.budget['standard'],0)
        self.restore();self.valid();self.assertIsNotNone(P._active(self.e,self.q,P.TRICK_SHOT))

    def test_leadership_retains_communication_slot_and_other_target_conditions(self):
        self.scene(bundle='feat/명사수-지시');self.leaders();self.combat()
        self.hears(self.q,False)
        self.rejected(lambda:self.e.issue_orders(self.a,P.TRICK_SHOT,self.q),'communication.*delivered')
        self.hears(self.q);self.e.issue_orders(self.a,P.TRICK_SHOT,self.q)
        self.next_round()
        self.rejected(lambda:self.e.issue_orders(self.a,P.TRICK_SHOT,self.q),'Stratagem|stratagem')

    def test_battle_three_recipients_one_original_standard_one_swift_and_each_ap(self):
        self.scene(bundle='feat/명사수-지시');self.leaders(battle=True);self.combat()
        initial=AP.available(self.a)
        with patch.object(CHEER,'complete_native_order',wraps=CHEER.complete_native_order) as completion:
            result=self.e.issue_orders(self.a,P.TRICK_SHOT,self.p,modifier=C.BATTLE,
                additional_targets=[self.q,self.s])
            self.assertEqual(completion.call_count,1)
        self.assertEqual(result['target_ids'],[self.p.entity_id,self.q.entity_id,self.s.entity_id])
        self.assertEqual(AP.available(self.a),initial-6)
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0))
        for recipient in (self.p,self.q,self.s):self.assertIsNotNone(P._active(self.e,recipient,P.TRICK_SHOT))
        self.restore();self.valid()

    def test_battle_invalid_extra_duplicate_nonatwill_and_late_failure_are_atomic(self):
        self.scene(bundle='feat/명사수-지시');self.leaders(battle=True);self.combat()
        self.rejected(lambda:self.e.issue_orders(self.a,P.TRICK_SHOT,self.p,modifier=C.BATTLE,
            additional_targets=[self.q,self.q]),'distinct actual')
        self.rejected(lambda:self.e.issue_orders(self.a,O.LONG,self.p,modifier=C.BATTLE),'At-Will Order')
        self.hears(self.s,False)
        self.rejected(lambda:self.e.issue_orders(self.a,P.TRICK_SHOT,self.p,modifier=C.BATTLE,
            additional_targets=[self.q,self.s]),'communication.*delivered')
        self.assertFalse(P._state(self.p));self.assertFalse(P._state(self.q))

    def test_battle_training_uses_one_real_priority_payment_and_survives_restore(self):
        self.scene();self.leaders(battle=True)
        self.acquire(TRAIN.FOCUSED);self.e.start_round(self.e.everyone)
        self.e.issue_orders(self.a,TRAIN.FOCUSED,self.p,modifier=C.BATTLE,additional_targets=[self.q,self.s],options={'edition':'local_csv'})
        self.assertEqual(len(PRIORITY.records(self.a)),1)
        for recipient in (self.p,self.q,self.s):self.assertEqual(TRAIN.bonus(recipient,'accuracy'),1)
        self.restore();self.valid()
        self.next_turn(self.a)
        for recipient in (self.p,self.q,self.s):self.assertEqual(TRAIN.bonus(recipient,'accuracy'),0)

    def test_core_four_training_orders_pay_actual_standard_without_priority_and_restore_expiry(self):
        for uid in TRAIN.RULES:
            with self.subTest(feature=uid):
                self.scene();self.acquire(uid);self.combat()
                result=self.e.manual_feat(self.a,uid,self.p,adjustment={'edition':'core'})
                self.assertEqual(self.a.budget['standard'],0);self.assertEqual(PRIORITY.records(self.a),[])
                payment=result['core_standard_payment']
                self.assertEqual((payment['action'],payment['source']['pages']),('standard',[60,60]))
                self.assertEqual(payment['source']['sha256'],C.CORE_SHA)
                self.assertNotIn('priority_receipt',result)
                self.rejected(lambda:self.e.manual_feat(self.a,uid,self.p,adjustment={'edition':'core'}),'Standard action unavailable')
                self.restore();self.valid();self.assertEqual(len(TRAIN.active(self.p)),1)
                self.next_round();self.assertEqual(TRAIN.active(self.p),[])

    def test_core_commander_training_three_allies_one_standard_and_swift_has_no_priority_loan(self):
        self.scene();self.acquire(TRAIN.FOCUSED);self.leaders(battle=True);self.combat()
        self.e.issue_orders(self.a,TRAIN.FOCUSED,self.p,modifier=C.BATTLE,additional_targets=[self.q,self.s])
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0))
        self.assertEqual(PRIORITY.records(self.a),[]);self.assertEqual(len(TRAIN.core_payments(self.a)),1)
        for target in (self.p,self.q,self.s):self.assertEqual(TRAIN.bonus(target,'accuracy'),1)
        self.restore();self.valid()
        import json,state_codec as CODEC
        payload=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        # Change only the actual Core payment source, retaining every other source and receipt.
        changed=0
        for node in payload['nodes'].values():
            if node['kind']!='dict':continue
            values={k:v for k,v in node['items'] if isinstance(k,str)}
            if values.get('id')==TRAIN.core_payments(self.a)[0]['id'] and 'action' in values:
                for pair in node['items']:
                    if pair[0]=='action':pair[1]='priority_limited_standard';changed+=1
        self.assertGreater(changed,0)
        with self.assertRaisesRegex(ValueError,'Core Training Order|timed_type_contract'):
            CODEC.load_engine(self.r,payload)
        self.next_round()
        for target in (self.p,self.q,self.s):self.assertEqual(TRAIN.bonus(target,'accuracy'),0)

    def test_core_commander_training_late_delivery_failure_is_atomic_and_csv_keeps_priority(self):
        self.scene();self.acquire(TRAIN.FOCUSED);self.leaders(battle=True);self.combat()
        self.hears(self.s,False)
        self.rejected(lambda:self.e.issue_orders(self.a,TRAIN.FOCUSED,self.p,modifier=C.BATTLE,
            additional_targets=[self.q,self.s]),'communication.*delivered')
        self.assertEqual(TRAIN.core_payments(self.a),[]);self.assertEqual(TRAIN.records(self.p),[])
        self.hears(self.s)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.issue_orders(self.a,TRAIN.FOCUSED,self.p,modifier=C.BATTLE,
            additional_targets=[self.q,self.s],options={'edition':'local_csv'})
        self.assertEqual(len(PRIORITY.records(self.a)),1);self.assertEqual(TRAIN.core_payments(self.a),[])
        for target in (self.p,self.q,self.s):self.assertEqual(TRAIN.bonus(target,'accuracy'),1)
        self.restore();self.valid()

    def test_core_training_completion_uses_actual_cheerleader_source_and_restores_after_expiry(self):
        self.scene();self.acquire(TRAIN.FOCUSED)
        import moment_of_action as MOMENT
        for uid in (MOMENT.TRAINING,MOMENT.CLASS):self.acquire(uid)
        self.choice('cheerleader','Cheered');self.combat();initial=AP.available(self.a)
        self.e.manual_feat(self.a,TRAIN.FOCUSED,self.p,adjustment={'edition':'core'})
        self.assertEqual(len(CHEER._uses(self.a)),1)
        self.assertEqual(CHEER._uses(self.a)[0]['origin']['kind'],'training_core_order')
        self.assertEqual(PRIORITY.records(self.a),[]);self.assertEqual(AP.available(self.a),initial)
        self.assertEqual(CHEER._uses(self.a)[0]['cost'],0)
        self.restore();self.valid();self.next_round();self.restore();self.valid()

    def test_complex_two_distinct_core_training_orders_share_original_action_and_keep_each_source(self):
        self.scene();self.acquire(TRAIN.FOCUSED);self.acquire(TRAIN.INSPIRED)
        self.leaders(battle=True,complex_orders=True);self.combat()
        self.e.issue_orders(self.a,TRAIN.FOCUSED,self.p,modifier=C.BATTLE,additional_targets=[self.q],
            assignments=[{'target_id':self.p.entity_id,'feature':TRAIN.FOCUSED,'options':{'edition':'core'}},
                         {'target_id':self.q.entity_id,'feature':TRAIN.INSPIRED,'options':{'edition':'core'}}])
        self.assertEqual((self.a.budget['standard'],self.a.budget['shift'],self.a.budget['swift']),(0,0,0))
        self.assertEqual([p['action'] for p in TRAIN.core_payments(self.a)],['standard','free'])
        self.assertEqual(PRIORITY.records(self.a),[])
        self.assertEqual(TRAIN.bonus(self.p,'accuracy'),1);self.assertEqual(TRAIN.bonus(self.q,'save'),2)
        self.restore();self.valid()

    def test_tip_all_actual_allies_ten_meter_boundary_pays_two_ap_and_base_order(self):
        self.scene();self.leaders(tip=True);self.acquire(C.MOBILIZE)
        self.e.gm.set_position(self.q,(11,1),reason='exact ten meter boundary')
        self.e.gm.set_position(self.s,(12,1),reason='outside ten meter boundary')
        for actor in (self.p,self.q,self.s):self.hears(actor)
        self.combat()
        initial=AP.available(self.a)
        result=self.e.issue_orders(self.a,C.MOBILIZE,self.p,modifier=C.TIP)
        self.assertEqual(set(result['target_ids']),{self.p.entity_id,self.q.entity_id})
        self.assertEqual(AP.available(self.a),initial-2);self.assertEqual(self.a.budget['swift'],0)
        self.assertEqual(len(C.uses(self.a)),2);self.restore();self.valid()

    def test_complex_actual_different_orders_cost_shift_and_original_action(self):
        self.scene();self.leaders(battle=True,complex_orders=True);self.acquire(C.MOBILIZE);self.combat()
        initial=AP.available(self.a)
        choices=[{'target_id':self.p.entity_id,'feature':P.RECKLESS,'options':{}},
                 {'target_id':self.q.entity_id,'feature':C.MOBILIZE,'options':{}}]
        result=self.e.issue_orders(self.a,P.RECKLESS,self.p,modifier=C.BATTLE,
            additional_targets=[self.q],assignments=choices)
        self.assertTrue(result['complex_orders']);self.assertEqual(AP.available(self.a),initial-2)
        self.assertEqual((self.a.budget['standard'],self.a.budget['shift'],self.a.budget['swift']),(0,0,0))
        self.assertEqual(C.uses(self.a)[0]['target_id'],self.q.entity_id);self.restore();self.valid()

    def test_complex_repeated_unknown_and_mixed_frequency_choices_reject_atomically(self):
        self.scene();self.leaders(battle=True,complex_orders=True);self.combat()
        def call(second):
            return self.e.issue_orders(self.a,P.RECKLESS,self.p,modifier=C.BATTLE,additional_targets=[self.q],
                assignments=[{'target_id':self.p.entity_id,'feature':P.RECKLESS,'options':{}},
                             {'target_id':self.q.entity_id,'feature':second,'options':{}}])
        self.rejected(lambda:call(P.RECKLESS),'different Order')
        self.rejected(lambda:call(O.PERFECT),'actually known')
        self.rejected(lambda:call(O.STRIKE),'mixed-frequency')

    def test_scheme_scene_two_activations_share_original_scene_use_across_targets(self):
        self.scene(bundle='feat/명사수-지시');self.leaders(scheme=True);self.combat()
        for attempt in range(2):
            if attempt:self.next_round()
            self.e.issue_orders(self.a,O.LONG,self.p,modifier=C.SCHEME,additional_targets=[self.q,self.s])
        self.next_round()
        self.rejected(lambda:self.e.issue_orders(self.a,O.LONG,self.p,modifier=C.SCHEME,
            additional_targets=[self.q]),'Scene frequency|Scene.*exhausted')
        self.assertEqual(len(self.a.spec[C.ACTIVATIONS]),2);self.restore();self.valid()

    def test_targetless_or_unacquired_order_cannot_become_targeted_and_modifier_not_inferred(self):
        self.scene();self.combat()
        self.rejected(lambda:self.e.issue_orders(self.a,'feat/집중된-지시',self.p),'known targeted')
        self.rejected(lambda:self.e.issue_orders(self.a,P.RECKLESS,self.p,modifier=C.BATTLE),'acquired Commander modifier')
        self.rejected(lambda:self.e.issue_orders(self.a,P.RECKLESS,self.p,additional_targets=[self.q]),'printed Commander modifier')

    def test_pinpoint_gift_expert_waiver_allied_target_actual_bound_ap_owner(self):
        self.scene(bundle='feat/정밀-지시',command=3);self.leaders();self.combat()
        initial=AP.available(self.a)
        self.e.issue_orders(self.a,CPF.PINPOINT,self.q)
        self.assertEqual(CPF.binding(self.e,self.q)['owner'],self.a)
        self.assertEqual(AP.available(self.a),initial-2);self.restore();self.valid()

    def test_actual_cheerleader_single_completion_three_instances_and_bound_ap_after_battle(self):
        self.scene(bundle='feat/명사수-지시');self.leaders(battle=True)
        import moment_of_action as MOMENT
        for uid in (MOMENT.TRAINING,MOMENT.CLASS):self.acquire(uid)
        self.choice('cheerleader','Cheered');self.combat();initial=AP.available(self.a)
        self.e.issue_orders(self.a,P.TRICK_SHOT,self.p,modifier=C.BATTLE,additional_targets=[self.q,self.s])
        self.assertEqual(len(CHEER._uses(self.a)),1)
        self.assertEqual(set(CHEER._uses(self.a)[0]['targets']),{self.p.entity_id,self.q.entity_id,self.s.entity_id})
        self.assertEqual(AP.available(self.a),initial-7)
        self.assertEqual(self.a.custom_conditions['duelist_order_sequence'],1)
        self.restore();self.valid()

    def test_battle_late_third_actual_ap_reservation_failure_rolls_back_all_native_bindings(self):
        self.scene(bundle='feat/명사수-지시');self.leaders(battle=True);self.combat()
        AP.charge(self.a,AP.available(self.a)-4)
        self.rejected(lambda:self.e.issue_orders(self.a,P.TRICK_SHOT,self.p,
            modifier=C.BATTLE,additional_targets=[self.q,self.s]),'AP|액션|포인트')
        self.assertEqual(AP.available(self.a),4)
        for actor in (self.p,self.q,self.s):self.assertIsNone(P._active(self.e,actor,P.TRICK_SHOT))

    def test_mobilize_actual_ranged_attack_does_not_spend_enemy_opportunity_for_unrelated_actor(self):
        self.scene();self.acquire(C.MOBILIZE)
        self.e.gm.set_position(self.b,(3,2),reason='actual adjacent ranged provocation')
        self.combat();C.mobilize(self.e,self.a,self.p);self.next_turn(self.p)
        self.attack();self.assertFalse(self.b.aoo_used)
        self.next_turn(self.q)
        TURN.trigger_aoo(self.e,self.q,'인접 칸 밖으로 이동',enemies=[self.b])
        self.assertTrue(self.b.aoo_used)


if __name__=='__main__':unittest.main()
