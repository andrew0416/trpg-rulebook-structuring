"""U-011 uses completed native hits and the preceding actual owner-turn start."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_trainer
from engine import Rules,Engine,Combatant
import attack_damage_history as HISTORY
import move_completion as COMPLETE
import temporary_hp as TEMP
import world_entities as WORLD
import test_category2_move_defense_reactions as DEFENSE_TESTS
import test_category2_delayed_attacks as DELAYED_TESTS
import test_category2_ability_interrupt_choices as INTERRUPT_TESTS
import passive_events as PASSIVE
import test_book_taskmaster_hardened as HARDENED_TESTS
import test_foundation_maneuvers_grapple as GRAPPLE_TESTS
import test_category2_optional_weapon_framework as WEAPON_TESTS
import optional_weapon_framework as WEAPONS
import turn as TURN
import test_manual_equipment as EQUIPMENT_TESTS


class FickleNativeHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.rules,seed=401)
        self.user=self.actor('history user','party',['물'])
        self.foe=self.actor('historical attacker','enemy',['전기'],['move/전기쇼크'])
        self.other=self.actor('other attacker','enemy',['전기'],['move/전기쇼크'])
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.user,initiative_count=30)

    def actor(self,name,side,types,moves=()):
        actor=Combatant(self.rules,build_trainer(self.rules,name,30,
            {'hp':120,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},
            moves=list(moves),side=side,abilities=[],extra={'types':types}))
        self.e.gm.add_combatant(actor,reason='actual history participants')
        return actor

    def query(self,target=None):
        return HISTORY.target_hit_user_super_effectively_since_previous_own_turn(self.e,self.user,target or self.foe)

    def foe_hit_between_turns(self,*,face=12,attacker=None):
        attacker=attacker or self.foe
        self.e.end_of_turn(self.user)
        self.e.start_of_turn(attacker,initiative_count=20)
        with patch.object(Engine,'d20',return_value=face):
            self.e.use_move(attacker,self.user,'move/전기쇼크',set_damage=True)
        self.e.end_of_turn(attacker)
        self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.user,initiative_count=30)

    def advance_user(self):
        self.e.end_of_turn(self.user)
        self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.user,initiative_count=30)

    def test_native_hit_between_turns_survives_current_start_and_expires_next_start(self):
        self.assertIsNone(self.query())
        self.foe_hit_between_turns()
        row=HISTORY.records(self.user)[-1]
        self.assertGreater(HISTORY.amount(row),0)
        self.assertGreater(row['native_hit_facts']['multiplier'],1)
        self.assertEqual(row['attacker_id'],self.foe.entity_id)
        self.assertIs(self.query(),True)
        self.assertEqual(self.foe.move_uses['move/전기쇼크'],1)
        self.assertEqual(self.foe._action_history,['standard'])
        self.e.gm.set_types(self.user,['땅'],reason='later immunity must not rewrite historical effectiveness')
        self.assertIs(self.query(),True)
        self.advance_user()
        self.assertIs(self.query(),False)

    def test_scene_change_does_not_replace_the_user_selected_own_turn_boundary(self):
        self.foe_hit_between_turns()
        self.assertIs(self.query(),True)
        self.e.end_of_turn(self.user)
        self.e.end_scene(self.e.everyone)
        self.assertIs(self.query(),True)
    def test_native_temp_hp_loss_counts_but_zero_damage_and_miss_do_not(self):
        for mode in ('temporary','zero','miss','neutral'):
            with self.subTest(mode=mode):
                self.setUp()
                hp=self.user.hp
                if mode=='temporary':TEMP.grant(self.e,self.user,1000)
                if mode=='zero':self.user.damage_cap={'value':0}
                if mode=='neutral':self.e.gm.set_types(self.user,['노말'],reason='actual neutral historical recipient')
                self.foe_hit_between_turns(face=1 if mode=='miss' else 12)
                self.assertIs(self.query(),mode=='temporary')
                if mode in ('temporary','zero','miss'):self.assertEqual(self.user.hp,hp)
                if mode=='temporary':self.assertLess(self.user.temp_hp,1000)
                if mode=='neutral':
                    self.e.gm.set_types(self.user,['물'],reason='later weakness cannot change old neutral hit')
                    self.assertIs(self.query(),False)

    def test_attacker_identity_readonly_reader_and_json_restore(self):
        self.foe_hit_between_turns(attacker=self.other)
        self.assertIs(self.query(),False)
        self.assertIs(self.query(self.other),True)
        before=self.e.export_state();rng=self.e.rng.getstate()
        self.assertIs(self.query(self.other),True)
        with self.assertRaisesRegex(ValueError,'actual world participants'):
            HISTORY.target_hit_user_super_effectively_since_previous_own_turn(self.e,deepcopy(self.user),self.other)
        self.assertEqual(self.e.export_state(),before);self.assertEqual(self.e.rng.getstate(),rng)
        restored=Engine.import_state(self.rules,json.loads(json.dumps(before,ensure_ascii=False)))
        index=WORLD.actor_index(restored)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(
            restored,index[self.user.entity_id],index[self.other.entity_id]),True)
        self.assertTrue(restored.validate_state()['valid'])

    def test_legacy_window_unknown_and_record_or_boundary_tampering_rejected(self):
        self.foe_hit_between_turns()
        window=deepcopy(self.user.spec[HISTORY.TURN_WINDOW])
        self.user.spec.pop(HISTORY.TURN_WINDOW)
        self.assertIsNone(self.query())
        restored=Engine.import_state(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(restored)
        self.assertIsNone(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(
            restored,index[self.user.entity_id],index[self.foe.entity_id]))
        self.user.spec[HISTORY.TURN_WINDOW]=window
        rows=deepcopy(HISTORY.records(self.user))
        self.user.spec[HISTORY.KEY].pop()
        with self.assertRaisesRegex(ValueError,'truncated or changed'):self.query()
        self.user.spec[HISTORY.KEY]=deepcopy(rows)
        self.user.spec[HISTORY.KEY][0]['native_hit_facts']['multiplier']=1
        with self.assertRaisesRegex(ValueError,'observation changed'):self.query()
        self.user.spec[HISTORY.KEY]=rows
        self.user.spec[HISTORY.TURN_WINDOW]['starts'][0]['history_sequence']=1
        with self.assertRaisesRegex(ValueError,'boundary changed'):self.query()

    def test_missing_observation_is_unknown_and_older_completed_hits_do_not_reopen(self):
        # Simulate an older producer with no then-effective observation. The
        # actual native attack and its paid completed result still occur.
        with patch.object(HISTORY,'_hit_facts',return_value=None):
            self.foe_hit_between_turns()
        self.assertGreater(HISTORY.amount(HISTORY.records(self.user)[-1]),0)
        self.assertIsNone(self.query())
        self.advance_user()
        self.assertIs(self.query(),False)
        current=COMPLETE.history_watermark(self.e)
        self.assertEqual(current['sequence'],1)
        self.assertEqual(current['pending'],[])
        self.assertEqual(COMPLETE.after_history_watermark(self.e,current),[])

    def test_native_intercept_records_actual_recipient_not_original_target(self):
        f=DEFENSE_TESTS.MoveDefenseReactionsTests('runTest');f.rules=self.rules;f.setUp()
        self.e=f.e
        self.e.end_of_turn(f.a)
        for actor in (f.r,f.t):
            self.e.gm.set_types(actor,['불꽃'],reason='actual Water weakness')
            self.e.start_of_turn(actor,initiative_count=20);self.e.end_of_turn(actor)
        self.e.end_round();self.e.start_round(self.e.everyone)
        for actor in (f.r,f.t):
            self.e.start_of_turn(actor,initiative_count=20);self.e.end_of_turn(actor)
        self.e.start_of_turn(f.a,initiative_count=20)
        self.e.gm.set_position(f.t,(6,2),reason='native ranged intercept target')
        self.e.gm.set_position(f.r,(4,4),reason='native ranged intercept path')
        f.watch('maneuver/원거리-가로채기')
        with patch.object(Engine,'d20',return_value=12):event=f.waiting('move/물대포')
        f.choose(event,options=f.ranged())
        row=HISTORY.records(f.r)[-1]
        self.assertGreater(row['native_hit_facts']['multiplier'],1)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(self.e,f.r,f.a),True)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(self.e,f.t,f.a),False)
        self.assertEqual(HISTORY.records(f.t),[])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_first_area_recipient_is_known_while_later_recipient_is_pending(self):
        f=INTERRUPT_TESTS.AbilityInterruptChoiceTests('runTest');f.rules=self.rules;f.setUp()
        e=f.e
        e.end_of_turn(f.a)
        e.start_of_turn(f.t,initiative_count=20);e.end_of_turn(f.t)
        e.end_round();e.start_round(e.everyone)
        e.start_of_turn(f.t,initiative_count=20);e.end_of_turn(f.t)
        e.gm.set_types(f.t,['독'],reason='actual Ground-weak first recipient')
        e.start_of_turn(f.a,initiative_count=20)
        f.watch(f.r)
        with patch.object(Engine,'d20',return_value=12):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                e.use_move_on(f.a,f.t,'move/지진',e.everyone)
        event=e._passive_pending;completion=e._move_completions[e._passive_events[event]['completion_id']]
        self.assertNotEqual(completion['phase'],'complete')
        self.assertTrue(COMPLETE.recipient_result(completion,f.t)['hit'])
        self.assertGreater(HISTORY.records(f.t)[-1]['native_hit_facts']['multiplier'],1)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,f.t,f.a),True)
        before=f.t.hp
        f.choose(event,owner=f.r,use=False)
        self.assertEqual(f.t.hp,before)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,f.t,f.a),True)
    def test_actual_heavy_pending_interceptor_without_history_is_unknown_not_false(self):
        import heavy_injury_adapter as HEAVY
        f=DEFENSE_TESTS.MoveDefenseReactionsTests('runTest');f.rules=self.rules;f.setUp()
        e=f.e;e.end_of_turn(f.a)
        e.start_of_turn(f.r,initiative_count=20);e.end_of_turn(f.r)
        e.end_round();e.start_round(e.everyone)
        e.start_of_turn(f.r,initiative_count=20);e.end_of_turn(f.r)
        e.gm.set_injuries(f.r,value=5,reason='actual non-Hardened interceptor with heavy injury')
        e.gm.set_types(f.r,['불꽃'],reason='actual Water weakness at interrupted recipient')
        e.gm.set_position(f.t,(6,2),reason='native ranged target')
        e.gm.set_position(f.r,(4,4),reason='native ranged intercept path')
        e.start_of_turn(f.a,initiative_count=20);f.watch('maneuver/원거리-가로채기')
        with patch.object(Engine,'d20',return_value=12):event=f.waiting('move/물대포')
        with self.assertRaises(HEAVY.HeavyPending):f.choose(event,options=f.ranged())
        packet=e._heavy_events[e._heavy_pending]
        self.assertIs(packet['target'],f.r)
        self.assertGreater(packet['before']['hp']-packet['attack_after']['hp'],0)
        self.assertEqual(HISTORY.records(f.r),[])
        row=e._move_completions[e._passive_events[event]['completion_id']]
        self.assertNotIn(f.r,row['targets']);self.assertIsNone(COMPLETE.recipient_result(row,f.r))
        self.assertIsNone(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,f.r,f.a))
    def test_known_heavy_equipment_action_is_not_a_missing_attack_event(self):
        EQUIPMENT_TESTS.Tests.setUpClass()
        f=EQUIPMENT_TESTS.Tests('runTest');e,a,user,uid=f.fixture()
        e.end_of_turn(a);e.start_of_turn(user,initiative_count=19);e.end_of_turn(user)
        e.end_round();e.start_round(e.everyone)
        e.start_of_turn(user,initiative_count=20);e.end_of_turn(user)
        e.start_of_turn(a,initiative_count=20)
        e.gm.set_injuries(a,value=5,reason='actual heavy manual equipment actor')
        result=e.equip_equipment(a,uid)
        event=e._heavy_events[result['heavy_event']]
        self.assertEqual(event['kind'],'action_taken')
        self.assertEqual(event['producer'],'manual_equipment.actual_standard')
        self.assertTrue(event['event_id'].startswith('heavy-equipment-'))
        self.assertGreater(e._heavy_sequence,0)
        self.assertEqual(HISTORY.records(user),[])
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,user,a),False)
        del e._heavy_events[result['heavy_event']]
        self.assertIsNone(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,user,a))
    def test_hardened_additional_loss_never_turns_zero_attack_into_qualifying_damage(self):
        for mode in ('zero','positive','temporary'):
            with self.subTest(mode=mode):
                f=HARDENED_TESTS.TaskmasterTests('runTest');f.rules=self.rules
                f.setup();f.train();f.injury(f.p,5)
                e=f.e;e.gm.set_types(f.p,['불꽃'],reason='actual Water-weak Hardened recipient')
                if mode=='zero':f.p.damage_cap={'value':0,'applies_to':'damage'}
                if mode=='temporary':TEMP.grant(e,f.p,1000)
                f.combat(f.p);e.end_of_turn(f.p);e.start_of_turn(f.b,initiative_count=10)
                before=f.p.hp,f.p.temp_hp
                damage=f.attack(f.b,f.p)
                self.assertGreater(damage,0)
                row=HISTORY.records(f.p)[-1];facts=row['native_hit_facts'];leaf=facts['attack_application']
                total=HISTORY.amount(row)
                attack_loss=max(0,leaf['net_hp_loss'])+max(0,leaf['net_temporary_hp_loss'])
                event=e._heavy_events[facts['damage_event_id']]
                extra=event['heavy_consequence']['amount']
                self.assertGreaterEqual(extra,5);self.assertEqual(total,attack_loss+extra)
                self.assertEqual(event['attack_after'],leaf['after'])
                self.assertGreater(facts['multiplier'],1)
                self.assertEqual(attack_loss==0,mode=='zero')
                if mode=='zero':self.assertEqual((f.p.hp,f.p.temp_hp),(before[0]-5,before[1]))
                if mode=='temporary':self.assertEqual(f.p.hp,before[0]);self.assertLess(f.p.temp_hp,before[1])
                e.end_of_turn(f.b);e.end_round();e.start_round(e.everyone);e.start_of_turn(f.p,initiative_count=20)
                self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,f.p,f.b),mode!='zero')
                f.restore()
                self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(f.e,f.p,f.b),mode!='zero')
                f.valid()

    def test_delayed_hardened_retains_leaf_separately_from_additional_loss(self):
        for capped in (True,False):
            with self.subTest(capped=capped):
                f=HARDENED_TESTS.TaskmasterTests('runTest');f.rules=self.rules
                f.setup();f.train();f.injury(f.p,5);e=f.e
                e.gm.set_types(f.p,['격투'],reason='actual Psychic-weak Hardened recipient')
                e.gm.set_move(f.b,'move/미래예지',add=True,reason='observed learned delayed attack')
                if capped:f.p.damage_cap={'value':0,'applies_to':'damage'}
                f.combat(f.p);e.end_of_turn(f.p)
                e.start_of_turn(f.b,initiative_count=10)
                e.use_move(f.b,f.p,'move/미래예지',set_damage=True)
                e.end_of_turn(f.b);e.end_round();e.start_round(e.everyone)
                e.start_of_turn(f.p,initiative_count=20);e.end_of_turn(f.p)
                row=HISTORY.records(f.p)[-1];leaf=row['native_hit_facts']['attack_application']
                attack_loss=max(0,leaf['net_hp_loss'])+max(0,leaf['net_temporary_hp_loss'])
                extra=e._heavy_events[row['native_hit_facts']['damage_event_id']]['heavy_consequence']['amount']
                self.assertGreaterEqual(extra,5);self.assertEqual(HISTORY.amount(row),attack_loss+extra)
                self.assertEqual(attack_loss==0,capped)
                self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,f.p,f.b),not capped)
                f.valid()

    def test_actual_grapple_attack_uses_paid_relation_without_move_completion(self):
        f=GRAPPLE_TESTS.GrappleTests('runTest');f.r=self.rules;f.setUp();e=f.e
        e.end_of_turn(f.a);e.start_of_turn(f.b,initiative_count=10);e.end_of_turn(f.b)
        e.end_round();e.start_round(e.everyone);e.start_of_turn(f.a,initiative_count=20)
        f.enter();e.end_of_turn(f.a);e.start_of_turn(f.b,initiative_count=10);e.end_of_turn(f.b)
        e.end_round();e.start_round(e.everyone);e.start_of_turn(f.a,initiative_count=20)
        result=e.grapple_action(f.a,'attack',request_id='actual-fickle-history-grapple')
        self.assertGreater(result['damage'],0)
        row=HISTORY.records(f.b)[-1];facts=row['native_hit_facts']
        self.assertIsNone(facts['completion_id']);self.assertIn('grapple_origin',facts)
        self.assertGreater(facts['attack_application']['net_hp_loss'],0)
        self.assertEqual(f.a._action_history,['full'])
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,f.b,f.a),False)
        before=e.export_state()
        self.assertEqual(e.grapple_action(f.a,'attack',request_id='actual-fickle-history-grapple'),result)
        self.assertEqual(e.export_state(),before)
        restored=Engine.import_state(self.rules,json.loads(json.dumps(before,ensure_ascii=False)))
        index=WORLD.actor_index(restored)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(restored,index[f.b.entity_id],index[f.a.entity_id]),False)

    def test_actual_elemental_weapon_hit_survives_unequip_and_later_type_change(self):
        f=WEAPON_TESTS.OptionalWeaponFrameworkTests('runTest');f.r=Rules(ROOT,ruleset='all')
        e,a,user,_=f.fixture(element='물')
        uid=f.weapon(e,a,'fickle-history/actual-arcane-weapon',moves=['move/렌딩-스펠'])
        WEAPONS.bond(e,a,uid,family='arcane');key=WEAPONS.equip(e,a,uid)
        e.gm.set_types(user,['불꽃'],reason='actual Water-weak weapon recipient')
        e.start_round(e.everyone);e.start_of_turn(user,initiative_count=20);e.end_of_turn(user)
        e.start_of_turn(a,initiative_count=20)
        with patch.object(Engine,'d20',return_value=12):
            e.use_move(a,user,key,weapon_id=uid,set_damage=True)
        row=HISTORY.records(user)[-1]
        self.assertEqual(row['move_type'],'물');self.assertGreater(row['native_hit_facts']['multiplier'],1)
        e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.start_of_turn(user,initiative_count=20)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,user,a),True)
        TURN.unequip_weapon(e,a,key)
        self.assertNotIn(key,a.moves)
        e.gm.set_types(user,['물'],reason='later resistance cannot rewrite old hit')
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,user,a),True)
        restored=Engine.import_state(f.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(restored)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(restored,index[user.entity_id],index[a.entity_id]),True)
    def test_delayed_native_application_retains_actual_then_effective_facts(self):
        f=DELAYED_TESTS.DelayedAttackTests('runTest');f.rules=self.rules
        e,a,t=f.world('move/미래예지')
        e.gm.set_types(t,['격투'],reason='actual Psychic-weak delayed recipient')
        e.end_of_turn(a);e.start_of_turn(t,initiative_count=20);e.end_of_turn(t)
        e.end_round();e.start_round(e.everyone)
        e.start_of_turn(a,initiative_count=30)
        e.use_move(a,t,'move/미래예지',set_damage=True)
        e.end_of_turn(a);e.start_of_turn(t,initiative_count=20)
        self.assertIsNone(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,t,a))
        e.end_of_turn(t)
        rows=HISTORY.records(t)
        self.assertEqual(len(rows),1);self.assertGreater(rows[0]['native_hit_facts']['multiplier'],1)
        self.assertIs(HISTORY.target_hit_user_super_effectively_since_previous_own_turn(e,t,a),True)
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()






