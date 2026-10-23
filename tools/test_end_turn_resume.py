"""Accepted native turn-end conditions keep their original producer boundary."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import action_lifecycle as ACTION
import combat_timing as TIME
import effect_contracts as CONTRACTS
import effect_lifetimes as LIFE
import frequency as FREQ
from state_codec import dump_engine, load_engine, StateCodecError
import test_historical_effect_source_closure as FIXTURE

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'data').is_dir() or not (ROOT / 'output').is_dir():ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')


class EndTurnResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.AcceptedTriggerSources.setUpClass()

    def setUp(self):
        self.f = FIXTURE.AcceptedTriggerSources()
        self.f.base = FIXTURE.AcceptedTriggerSources.base
        self.f.setUp()
        self.e, self.a = self.f.e, self.f.a

    def stage(self, stat, *, conditional=False):
        row = dict(type='stage_change', stat=stat, delta=1, target='self')
        if conditional:row['if'] = 'target was asleep'
        return row

    def suspend(self, effects=None):
        self.f.register(effects=effects or [self.stage('atk'), self.stage('def', conditional=True), self.stage('spe')])
        result = self.e.end_of_turn(self.a)
        rows = self.e._effect_dispatch_receipts
        self.assertTrue(any(row['status'] == 'condition_unknown' for row in rows.values()),
                        [(row['status'], str(row.get('result'))) for row in rows.values()])
        token = next(token for token, row in rows.items() if row['status'] == 'condition_unknown')
        return token, result

    def resolve(self, token, truth=True):
        return self.e.resolve_effect_condition(self.a, token, target_was_asleep=truth,
                                               reason='actual historical sleep observation')

    def assert_closed_once(self):
        self.assertIsNone(self.e._active_turn_actor)
        self.assertEqual(len(self.e._turn_closures), 1)
        self.assertEqual(FREQ.state(self.a)['activations'][FIXTURE.SOURCE_A]['used'], 1)

    def test_native_producer_preserves_boundary_then_suffix_and_close_once(self):
        token, returned = self.suspend()
        row = self.e._effect_dispatch_receipts[token]
        self.assertEqual(row['condition_request']['boundary'], CONTRACTS.boundary(self.e, self.a, self.a))
        self.assertIs(self.e._active_turn_actor, self.a)
        self.assertEqual(len(self.e._turn_closures), 0)
        self.assertEqual(returned['status'], 'awaiting_input')
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 0, 0))
        self.resolve(token)
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 1, 1))
        self.assert_closed_once()
        before = dump_engine(self.e)
        self.resolve(token)
        self.assertEqual(dump_engine(self.e), before)
        self.e.advance_time(1, [self.a])

    def test_false_observation_skips_only_the_condition_and_finishes_suffix(self):
        token, _ = self.suspend()
        self.resolve(token, False)
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 0, 1))
        self.assert_closed_once()

    def test_final_condition_without_suffix_blocks_boundaries_and_then_closes(self):
        token, _ = self.suspend([self.stage('atk'), self.stage('def', conditional=True)])
        for attempt in (lambda: self.e.advance_time(1, [self.a]),
                        lambda: self.e.end_of_turn(self.a),
                        lambda: ACTION.ordinary_permission(self.e, self.a)):
            before = dump_engine(self.e)
            with self.assertRaisesRegex(ValueError, 'turn.end|turn end|turn-end'):
                attempt()
            self.assertEqual(dump_engine(self.e), before)
        self.resolve(token)
        self.assert_closed_once()

    def test_native_condition_damage_is_never_replayed(self):
        for condition in ('화상', '독'):
            self.e.apply_status(self.a, condition, source='gm/end-turn-native-prefix')
        self.a.took_standard = True
        before_hp = self.a.hp
        token, _ = self.suspend()
        after_hp = self.a.hp
        self.assertLess(after_hp, before_hp)
        self.resolve(token)
        self.assertEqual(self.a.hp, after_hp)
        self.assertFalse(self.a.took_standard)
        self.assert_closed_once()

    def test_due_owner_turn_lifetime_waits_for_the_original_close(self):
        def temporary(value):
            return dict(type='damage_reduction', value=value, target='self',
                        until={'event':'turn_end', 'owner':'user'})
        self.e.apply_effect(self.a, self.a, temporary(2), None, True, 0, 'gm/due-owner-turn')
        self.e.end_of_turn(self.a)
        self.e.end_round(); self.e.start_round([self.a])
        self.e.start_of_turn(self.a, initiative_count=20)
        token, _ = self.suspend([self.stage('def', conditional=True), temporary(3)])
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 2)
        self.resolve(token)
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 3)
        self.assertEqual(self.a.stages['def'], 1)
        self.assertEqual(len(self.e._turn_closures), 2)
        self.assertEqual(len(self.a.custom_conditions['effect_lifetime_history']), 1)
        self.e.end_round(); self.e.start_round([self.a])
        self.e.start_of_turn(self.a, initiative_count=20)
        self.e.end_of_turn(self.a)
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 0)
        self.assertEqual(len(self.a.custom_conditions['effect_lifetime_history']), 2)
        self.assertEqual(len(self.e._turn_closures), 3)

    def test_late_close_fault_rolls_back_observation_suffix_and_can_retry(self):
        token, _ = self.suspend()
        before = dump_engine(self.e)
        actual = TIME.end_turn
        def fail_after_native_close(engine, actor):
            actual(engine, actor)
            raise ValueError('late turn-end close fault')
        with patch.object(TIME, 'end_turn', side_effect=fail_after_native_close):
            with self.assertRaisesRegex(ValueError, 'late turn-end close fault'):
                self.resolve(token)
        self.assertEqual(dump_engine(self.e), before)
        self.resolve(token)
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 1, 1))
        self.assert_closed_once()

    def test_pending_json_roundtrip_resolves_the_original_occurrence(self):
        self.suspend()
        saved = json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False))
        self.e = load_engine(self.f.r, saved)
        self.a = self.e.everyone[0]
        token = next(t for t, row in self.e._effect_dispatch_receipts.items() if row['status'] == 'condition_unknown')
        self.resolve(token)
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 1, 1))
        self.assert_closed_once()
        self.e = load_engine(self.f.r, json.loads(json.dumps(dump_engine(self.e))))
        self.a = self.e.everyone[0]
        token = next(t for t, row in self.e._effect_dispatch_receipts.items() if 'condition_reply' in row)
        before = dump_engine(self.e)
        self.resolve(token)
        self.assertEqual(dump_engine(self.e), before)

    def test_gm_snapshot_restores_pending_close_phase_and_original_prefix(self):
        self.suspend()
        self.e.gm.snapshot('pending-native-turn-end')
        token = next(t for t, row in self.e._effect_dispatch_receipts.items() if row['status'] == 'condition_unknown')
        self.resolve(token)
        self.assert_closed_once()
        self.e.gm.restore('pending-native-turn-end', reason='restore accepted native pending event')
        token = next(t for t, row in self.e._effect_dispatch_receipts.items() if row['status'] == 'condition_unknown')
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 0, 0))
        self.assertIs(self.e._active_turn_actor, self.a)
        self.resolve(token)
        self.assert_closed_once()

    def test_changed_source_rejects_without_mutation_and_original_source_can_retry(self):
        token, _ = self.suspend()
        before = dump_engine(self.e)
        with self.f.changed_source():
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.resolve(token)
        self.assertEqual(dump_engine(self.e), before)
        self.resolve(token)
        self.assert_closed_once()

    def test_second_condition_in_suffix_keeps_native_close_pending(self):
        token, _ = self.suspend([self.stage('atk'), self.stage('def', conditional=True),
                                 self.stage('spe', conditional=True), self.stage('spd')])
        self.resolve(token)
        self.assertIs(self.e._active_turn_actor, self.a)
        self.assertEqual(len(self.e._turn_closures), 0)
        token2 = next(t for t, row in self.e._effect_dispatch_receipts.items() if row['status'] == 'condition_unknown')
        self.assertIsNot(token, token2)
        self.resolve(token2, False)
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe'], self.a.stages['spd']), (1, 1, 0, 1))
        self.assert_closed_once()

    def test_wrong_actor_and_boundary_cannot_answer_the_pending_producer(self):
        token, _ = self.suspend()
        before = dump_engine(self.e)
        with self.assertRaisesRegex(ValueError, 'owner'):
            self.e.resolve_effect_condition(deepcopy(self.a), token, target_was_asleep=True,
                                            reason='wrong observation owner')
        self.assertEqual(dump_engine(self.e), before)
        self.e.elapsed_seconds += 1
        with self.assertRaisesRegex(ValueError, 'boundary'):
            self.resolve(token)
        self.e.elapsed_seconds -= 1
        self.assertEqual(dump_engine(self.e), before)
        self.resolve(token)
        self.assert_closed_once()

    def test_close_phase_metadata_tamper_is_rejected_by_persistence_and_resume(self):
        token, _ = self.suspend()
        rows = self.e._effect_dispatch_receipts
        anchor, root = next((t,r) for t,r in rows.items() if 'turn_end_close' in r)
        meta = root['turn_end_close']
        changes = [('actor', None), ('boundary', (99, *meta['boundary'][1:])),
                   ('status', 'closed'), ('effects', meta['effects'][:-1]),
                   ('profiles', {})]
        for field, invalid in changes:
            with self.subTest(field=field):
                original = meta[field]
                meta[field] = invalid
                try:
                    with self.assertRaises((ValueError, StateCodecError)):
                        dump_engine(self.e)
                    with self.assertRaises(ValueError):
                        self.e.gm.snapshot('invalid-' + field)
                    with self.assertRaises(ValueError):
                        self.resolve(token)
                finally:
                    meta[field] = original
        missing = rows.pop(token)
        try:
            with self.assertRaises((ValueError, StateCodecError)):
                dump_engine(self.e)
        finally:
            rows[token] = missing
        condition=rows[token]
        suffix=rows[condition['continuation']]
        corruptions=[(condition,'condition_request',None), (condition,'turn_end_owner',[]),
                     (condition,'fingerprint','changed'), (suffix,'effects',[])]
        for row,field,invalid in corruptions:
            with self.subTest(receipt=field):
                original=row[field]
                row[field]=invalid
                try:
                    with self.assertRaises((ValueError,StateCodecError)):dump_engine(self.e)
                    with self.assertRaises(ValueError):self.e.gm.snapshot('invalid-receipt-'+field)
                    with self.assertRaises(ValueError):self.resolve(token)
                finally:row[field]=original
        self.resolve(token)
        self.assert_closed_once()

    def test_json_restore_rejects_pending_phase_forged_as_closed(self):
        self.suspend()
        payload = json.loads(json.dumps(dump_engine(self.e)))
        pointer = next(value for node in payload['nodes'].values()
                       if node.get('kind') == 'dict' for key,value in node['items']
                       if key == 'turn_end_close')
        meta = payload['nodes'][pointer['$ref']]
        next(pair for pair in meta['items'] if pair[0] == 'status')[1] = 'closed'
        with self.assertRaises(StateCodecError):
            load_engine(self.f.r, payload)

    def costed_head(self, *, unsupported=False):
        frequency=dict(raw='장면 2AP - 기본 행동', kind='scene', uses=1, action='standard', ap=2)
        effects=[self.stage('def', conditional=True), self.stage('spe')]
        if unsupported:effects[0]['repeat']='forever'
        value=dict(name='Explicit authored head-unknown cost probe', spec={'event':'turn_end'},
                   frequency=frequency, effects=effects, usage_key=FIXTURE.SOURCE_A, _feat=True,
                   activation_header={'id':FIXTURE.SOURCE_A,'frequency':frequency})
        self.a.active_effects.register_definition_row(self.e, 'external-row:head-cost', 'ability_triggers', value)
        returned=self.e.end_of_turn(self.a)
        print('ACTUAL_HEADUNKNOWN_COST', json.dumps(dict(source_id=FIXTURE.SOURCE_A,
              explicit_source=self.f.reference, selected_profile=CONTRACTS.source_profile(self.e,FIXTURE.SOURCE_A),
              header=value['activation_header'], effect_condition=effects[0]['if'], unsupported=unsupported,
              returned_status=returned.get('status') if isinstance(returned,dict) else returned,
              ap_spent=self.a.spec.get('ap_spent',0), action_history=self.a._action_history, budget=self.a.budget,
              frequency_used=FREQ.state(self.a)['activations'].get(FIXTURE.SOURCE_A,{}).get('used',0)), ensure_ascii=False))
        if unsupported:return None
        token=next(t for t,row in self.e._effect_dispatch_receipts.items() if row['status']=='condition_unknown')
        self.assertEqual(returned['status'], 'awaiting_input')
        self.assertEqual(self.a.spec.get('ap_spent',0), 2)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertEqual(self.a._action_history, ['standard'])
        self.assertEqual(FREQ.state(self.a)['activations'][FIXTURE.SOURCE_A]['used'],1)
        return token

    def assert_cost_once(self):
        self.assertEqual(self.a.spec['ap_spent'],2)
        self.assertEqual(self.a._action_history,['standard'])
        self.assertEqual(self.a.budget['standard'],0)
        self.assert_closed_once()

    def test_head_unknown_true_pays_original_action_ap_and_frequency_once(self):
        token=self.costed_head()
        self.resolve(token)
        self.assertEqual((self.a.stages['def'],self.a.stages['spe']),(1,1))
        self.assert_cost_once()
        before=dump_engine(self.e)
        self.resolve(token)
        self.assertEqual(dump_engine(self.e),before)

    def test_head_unknown_false_retains_the_single_accepted_activation_cost(self):
        token=self.costed_head()
        self.resolve(token,False)
        self.assertEqual((self.a.stages['def'],self.a.stages['spe']),(0,1))
        self.assert_cost_once()

    def test_head_unknown_late_fault_and_retry_never_charge_again(self):
        token=self.costed_head()
        before=dump_engine(self.e)
        with patch.object(TIME,'end_turn',side_effect=ValueError('late head-unknown close fault')):
            with self.assertRaisesRegex(ValueError,'late head-unknown close fault'):
                self.resolve(token)
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(self.a.spec['ap_spent'],2)
        self.resolve(token)
        self.assert_cost_once()

    def test_unsupported_head_is_still_rejected_without_activation_payment(self):
        budget=dict(self.a.budget)
        self.costed_head(unsupported=True)
        self.assertEqual(self.a.spec.get('ap_spent',0),0)
        self.assertEqual(self.a._action_history,[])
        self.assertEqual(self.a.budget,budget)
        self.assertFalse(FREQ.state(self.a)['activations'])
        self.assertFalse(getattr(self.e,'_effect_dispatch_receipts',{}))
        self.assertEqual((self.a.stages['def'],self.a.stages['spe']),(0,0))

    def test_new_trigger_blocked_by_pending_suffix_rejects_the_native_producer_atomically(self):
        self.f.register(FIXTURE.SOURCE_B, [self.stage('spd',conditional=True), self.stage('spa')])
        self.f.register(effects=[self.stage('atk'), self.stage('def',conditional=True), self.stage('spe')])
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'unfinished required effect suffix'):
            self.e.end_of_turn(self.a)
        self.assertEqual(dump_engine(self.e),before)
        self.assertIs(self.e._active_turn_actor,self.a)
        self.assertEqual(len(self.e._turn_closures),0)

    def test_removed_or_reselected_source_cannot_finish_the_pending_turn(self):
        token,_=self.suspend()
        before=dump_engine(self.e)
        selected=self.f.r._selected_rule
        with patch.object(self.f.r,'_selected_rule',side_effect=lambda uid,*a,**k:
                          uid+'/changed' if uid==FIXTURE.SOURCE_A else selected(uid,*a,**k)):
            with self.assertRaisesRegex(ValueError,'source changed'):
                self.resolve(token)
        definition=self.f.r.selection.units.pop(FIXTURE.SOURCE_A)
        try:
            with self.assertRaisesRegex(ValueError,'source changed'):
                self.resolve(token)
        finally:
            self.f.r.selection.units[FIXTURE.SOURCE_A]=definition
        self.assertEqual(dump_engine(self.e),before)
        self.resolve(token)
        self.assert_closed_once()

    def native_status_child(self,nested_effects,outer_effects):
        b=FIXTURE.Combatant(self.f.r,FIXTURE.build_trainer(
            self.f.r,'Actual prior native attacker',20,
            dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),abilities=[]))
        self.e.end_of_turn(self.a);self.e.end_round()
        self.e.gm.add_combatant(b,pos=(0,1),side='wild',reason='actual nested receipt owner')
        self.e.start_round([b,self.a]);self.e.start_of_turn(b,initiative_count=20)
        with patch.object(self.e,'d20',return_value=20):
            self.e.use_move(b,self.a,'struggle')
        self.assertIs(self.e._inflictor,b)
        self.e.end_of_turn(b);self.e.start_of_turn(self.a,initiative_count=10)
        nested=dict(name='Explicit authored native status child',usage_key=FIXTURE.SOURCE_B,
                    spec={'event':'on_inflict_status'},frequency=dict(kind='scene',uses=1),
                    effects=nested_effects)
        b.active_effects.register_definition_row(self.e,'external-row:native-child','ability_triggers',nested)
        self.f.register(effects=outer_effects)
        returned=self.e.end_of_turn(self.a)
        print('ACTUAL_NATIVE_STATUS_CHILD',json.dumps(dict(returned=returned.get('status') if isinstance(returned,dict) else returned,
              original_prefix=self.a.stages['spe'],native_closures=len(self.e._turn_closures),
              receipt_actors=[row['actor'].entity_id for row in self.e._effect_dispatch_receipts.values()]),ensure_ascii=False))
        self.assertIsInstance(returned,dict)
        return b,returned

    def test_native_status_child_keeps_its_distinct_actor_and_original_turn_owner(self):
        b,returned=self.native_status_child([self.stage('spa')],
            [dict(type='apply_status',status='독',target='self'),
             self.stage('def',conditional=True),self.stage('spe')])
        token=returned['receipt']
        child=next(row for row in self.e._effect_dispatch_receipts.values() if row['source_id']==FIXTURE.SOURCE_B)
        self.assertIs(child['actor'],b)
        self.assertIs(child['target'],self.a)
        self.assertEqual(b.stages['spa'],1)
        self.assertIs(self.e._active_turn_actor,self.a)
        self.assertEqual(len(self.e._turn_closures),2)
        print('ACTUAL_DISTINCT_ACTOR_CHILD',json.dumps(dict(producer=self.a.entity_id,
              native_attacker=b.entity_id,child_source=child['source_id'],
              child_actor=child['actor'].entity_id,child_target=child['target'].entity_id,
              initial_receipts=len(next(row['turn_end_close']['effects'] for row in self.e._effect_dispatch_receipts.values() if 'turn_end_close' in row))),ensure_ascii=False))
        self.resolve(token)
        self.assertEqual((self.a.stages['def'],self.a.stages['spe'],b.stages['spa']),(1,1,1))
        self.assertIsNone(self.e._active_turn_actor)
        self.assertEqual(len(self.e._turn_closures),3)

    def test_pending_distinct_actor_child_restores_and_closes_only_the_original_turn(self):
        self.native_status_child([self.stage('spa',conditional=True),self.stage('spd')],
            [dict(type='apply_status',status='독',target='self'),self.stage('spe')])
        self.e=load_engine(self.f.r,json.loads(json.dumps(dump_engine(self.e))))
        self.a=next(c for c in self.e.everyone if c.name=='Authored declaration owner')
        b=next(c for c in self.e.everyone if c.name=='Actual prior native attacker')
        token=next(t for t,row in self.e._effect_dispatch_receipts.items() if row['status']=='condition_unknown')
        row=self.e._effect_dispatch_receipts[token]
        self.assertIs(row['actor'],b)
        self.assertEqual(row['condition_request']['boundary'],CONTRACTS.boundary(self.e,b,self.a))
        self.assertEqual(self.a.stages['spe'],1)
        self.e.resolve_effect_condition(b,token,target_was_asleep=True,reason='actual nested historical observation')
        self.assertEqual((b.stages['spa'],b.stages['spd'],self.a.stages['spe']),(1,1,1))
        self.assertIsNone(self.e._active_turn_actor)
        self.assertEqual(len(self.e._turn_closures),3)
        before=dump_engine(self.e)
        self.e.resolve_effect_condition(b,token,target_was_asleep=True,reason='actual nested historical observation')
        self.assertEqual(dump_engine(self.e),before)

    def test_removing_the_trigger_preserves_its_already_accepted_occurrence(self):
        token,_=self.suspend()
        self.assertTrue(self.a.active_effects.remove(self.e,'external-row:'+FIXTURE.SOURCE_A))
        self.assertEqual(self.a.ability_triggers,[])
        self.resolve(token)
        self.assertEqual((self.a.stages['atk'],self.a.stages['def'],self.a.stages['spe']),(1,1,1))
        self.assert_closed_once()


if __name__ == '__main__':
    unittest.main()
