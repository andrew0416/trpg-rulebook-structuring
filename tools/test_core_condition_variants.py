"""C11-083: actual adopted inflictor -> native Poison, turns, stages and cure."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
import test_category2_persistent_conditions as fixture
from engine import Engine, Rules
import condition_variants as V
import condition_instances as CI
import combat_timing as TIME
import combat_stage_sources as STAGES
import effects as FX
import persistent_conditions as P
import boss_transitions as BOSS


class ConditionVariantTests(unittest.TestCase):
    setUpClass = classmethod(fixture.PersistentConditionsTests.setUpClass.__func__)
    setUp = fixture.PersistentConditionsTests.setUp
    add = fixture.PersistentConditionsTests.add
    known = fixture.PersistentConditionsTests.known
    begin = fixture.PersistentConditionsTests.begin
    cast = fixture.PersistentConditionsTests.cast
    valid = fixture.PersistentConditionsTests.valid
    restored = fixture.PersistentConditionsTests.restored

    def snap(self):
        # The native codec retains opaque producer-token aliases and all RNG,
        # action, cost and turn fields; ordinary deepcopy invents token objects.
        return self.e.export_state()

    def adopt(self):
        return V.adopt(self.e, self.other, reason='GM adopts the alternate venom example on this actual Pokemon')

    def venom(self, move='독가스', target=None):
        self.adopt()
        self.cast(move, target)
        return V.active(target or self.p)

    def holder_turn(self, stat='atk'):
        self.begin(self.p)
        with patch.object(type(self.e.rng), 'choice', return_value=stat) as draw:
            self.e.end_of_turn(self.p)
        return draw

    def test_explicit_actual_adoption_reaches_native_source_target_poison_and_slowed_movement(self):
        ordinary_move = deepcopy(self.r.move_mech('move/독가스')[0])
        baseline = self.e.move_profile(self.p)[0]
        row = self.venom()
        self.assertTrue({'독', '둔화'} <= self.p.conditions)
        self.assertEqual(self.p.stages['spd'], 0)
        self.assertEqual(self.e.move_profile(self.p)[0], max(1, baseline//2))
        self.assertEqual(row['source'], 'move/독가스')
        self.assertEqual(row['effect'], V.PAYLOAD)
        self.assertEqual(row['effect_instance']['applied_by_actor_id'], self.other.entity_id)
        child = self.e._effect_dispatch_receipts[row['slowed_receipt']]
        self.assertIs(child['actor'], self.other)
        self.assertIs(child['target'], self.p)
        self.assertNotIn('독', self.a.conditions)
        self.assertNotIn('독', self.other.conditions)
        self.assertEqual(self.r.move_mech('move/독가스')[0], ordinary_move)
        self.valid()

    def test_all_five_native_random_stages_apply_once_each_actual_holder_turn_without_standard_action(self):
        for stat in STAGES.STATS:
            with self.subTest(stat=stat):
                self.setUp()
                row = self.venom()
                before = dict(self.p.stages)
                hp = self.p.hp
                draw = self.holder_turn(stat)
                self.assertEqual(draw.call_args_list, [((STAGES.STATS,), {})])
                expected = dict(before)
                expected[stat] -= 1
                self.assertEqual(self.p.stages, expected)
                self.assertEqual(self.p.hp, hp)
                self.assertEqual(len(row['applications']), 1)
                self.assertEqual(row['applications'][0]['stat'], stat)
                self.assertEqual(P.loss(self.e, self.p, '독', 1), 0)
                self.valid()

    def test_native_stage_floor_immunity_and_boss_turn_gate_remain_authoritative(self):
        self.venom()
        self.e.change_stage(self.p, 'atk', -6)
        self.holder_turn('atk')
        self.assertEqual(self.p.stages['atk'], -6)
        self.e.gm.set_ability(self.p, '클리어바디', reason='native stage-loss immunity')
        self.holder_turn('def')
        self.assertEqual(self.p.stages['def'], 0)
        self.begin(self.p)
        count = len(V.active(self.p)['applications'])
        original = BOSS.condition_applies_this_turn
        with patch.object(BOSS, 'condition_applies_this_turn', side_effect=lambda actor, condition:
                          False if actor.entity_id == self.p.entity_id and condition == '독'
                          else original(actor, condition)), \
                patch.object(type(self.e.rng), 'choice') as draw:
            self.e.end_of_turn(self.p)
        draw.assert_not_called()
        self.assertEqual(len(V.active(self.p)['applications']), count)
        self.valid()

    def test_native_toxic_from_adopted_actor_replaces_both_ordinary_poison_effects_and_escalating_counter(self):
        row = self.venom('맹독')
        self.assertEqual(row['source'], 'move/맹독')
        self.assertEqual(CI.records(self.p, '독'), [row])
        self.assertNotIn('completed_rounds', row)
        self.assertEqual(self.p.stages['spd'], 0)
        hp = self.p.hp
        self.holder_turn('spa')
        self.e.end_round()
        self.assertEqual(self.p.hp, hp)
        self.assertEqual(self.p.stages['spa'], -1)
        self.assertEqual(len(row['applications']), 1)
        self.valid()

    def test_native_poison_immunity_and_missed_infliction_create_no_variant_or_slowed(self):
        for types in (['독'], ['강철']):
            with self.subTest(types=types):
                self.setUp()
                self.e.gm.set_types(self.p, types, reason='actual Poison immunity')
                self.venom()
                self.assertNotIn('독', self.p.conditions)
                self.assertNotIn('둔화', self.p.conditions)
                self.assertIsNone(V.active(self.p))
                self.valid()
        self.setUp()
        self.adopt()
        self.cast('독가스', face=1)
        self.assertIsNone(V.active(self.p))
        self.assertNotIn('둔화', self.p.conditions)
        self.valid()

    def test_same_species_ordinary_source_and_existing_poison_are_never_rewritten(self):
        self.cast('독가스')
        self.assertEqual(self.p.stages['spd'], -2)
        self.assertIsNone(V.active(self.p))
        self.adopt()
        self.cast('맹독')
        self.assertIsNone(V.active(self.p))
        self.assertNotIn('둔화', self.p.conditions)
        self.e.cure_status(self.p, '독')
        self.begin(self.other)  # Native Scene x2 also forbids consecutive owner turns.
        self.cast('맹독')
        row = V.active(self.p)
        self.assertIsNotNone(row)
        self.assertFalse(self.e.apply_status(self.p, '독', source='move/독가스', applied_by=self.other))
        self.assertIs(V.active(self.p), row)
        self.assertEqual(len(CI.records(self.p, '독')), 1)
        self.assertEqual(self.p.stages['spd'], 0)
        self.valid()

    def test_while_poison_child_cure_and_overlapping_slowed_sources_preserve_actual_ownership(self):
        self.venom()
        result = FX.run_effects(self.e, self.a, self.p,
                               [{'type': 'apply_status', 'status': '둔화', 'until': 'encounter_end'}],
                               {'hit': True}, 'gm/independent-slowed')
        self.assertEqual(result, (1, 0))
        self.assertFalse(self.e.cure_status(self.p, '둔화'))
        self.e.cure_status(self.p, '독')
        self.assertNotIn('독', self.p.conditions)
        self.assertIn('둔화', self.p.conditions)
        self.assertEqual(self.p.stages['spd'], 0)
        self.e.end_encounter()
        self.assertNotIn('둔화', self.p.conditions)
        self.valid()

    def test_native_recall_encounter_reset_snapshot_and_fresh_restore_keep_poison_without_standard_stage(self):
        row = self.venom()
        self.holder_turn('atk')
        self.e.gm.recall(self.p, reason='actual recall with persistent venom')
        self.assertTrue({'독', '둔화'} <= self.p.conditions)
        self.assertEqual(self.p.stages, dict.fromkeys(STAGES.STATS, 0))
        self.e.end_encounter()
        self.assertTrue({'독', '둔화'} <= self.p.conditions)
        self.e.gm.snapshot('venom')
        self.e.cure_status(self.p, '독')
        self.assertNotIn('둔화', self.p.conditions)
        self.e.gm.restore('venom')
        self.assertEqual(V.active(self.p)['id'], row['id'])
        fresh = Engine.import_state(Rules(ROOT, ruleset='core'), json.loads(json.dumps(self.e.export_state())))
        holder = next(actor for actor in fresh.gm.everyone if actor.entity_id == self.p.entity_id)
        self.assertTrue({'독', '둔화'} <= holder.conditions)
        fresh.cure_status(holder, '맹독')
        self.assertNotIn('독', holder.conditions)
        self.assertNotIn('둔화', holder.conditions)
        self.assertEqual(holder.stages['spd'], 0)
        self.assertTrue(fresh.validate_state()['valid'])
        self.valid()

    def test_native_antidote_cures_parent_and_only_its_child_without_reversing_earned_stage_losses(self):
        self.venom()
        self.holder_turn('atk')
        self.begin(self.a)
        self.a.spec['items']['해독제'] = 1
        self.e.use_item(self.a, '해독제', self.p)
        self.assertNotIn('독', self.p.conditions)
        self.assertNotIn('둔화', self.p.conditions)
        self.assertFalse(CI.records(self.p, '독'))
        self.assertEqual(self.p.stages['atk'], -1)
        self.assertEqual(self.p.stages['spd'], 0)
        self.valid()

    def test_withdrawal_changes_future_infliction_and_preserves_actual_inflicted_source(self):
        row = self.venom()
        V.withdraw(self.e, self.other, reason='future normal venom')
        self.assertFalse(V.adoption(self.other)['active'])
        self.holder_turn('def')
        self.assertEqual(V.active(self.p)['id'], row['id'])
        self.assertEqual(self.p.stages['def'], -1)
        self.cast('맹독', self.a)
        self.assertIn('독', self.a.conditions)
        self.assertEqual(self.a.stages['spd'], -2)
        self.assertIsNone(V.active(self.a))
        self.valid()

    def test_invalid_source_and_late_stage_failure_leave_rng_costs_turn_and_instance_unchanged(self):
        self.venom()
        self.begin(self.p)
        before = self.snap()
        with patch.object(type(self.e), 'change_stage', side_effect=ValueError('injected actual stage failure')):
            with self.assertRaisesRegex(ValueError, 'stage contribution did not complete'):
                self.e.end_of_turn(self.p)
        self.assertEqual(before, self.snap())
        self.assertFalse(V.active(self.p)['applications'])
        self.valid()
        self.e.cure_status(self.p, '독')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'Poison-inflicting Move'):
            self.e.apply_status(self.p, '독', source='move/물대포', applied_by=self.other)
        self.assertEqual(before, self.snap())
        with patch('source_context.verified_source', side_effect=ValueError('alternate Poison source changed')):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.e.apply_status(self.p, '독', source='move/독가스', applied_by=self.other)
        self.assertEqual(before, self.snap())

    def test_restoration_rejects_forged_adoption_source_and_stage_receipts(self):
        self.venom()
        self.holder_turn('atk')
        state = self.e.export_state()
        saved = V.active(self.p)
        saved['source_fingerprint'] = 'forged'
        self.assertFalse(self.e.validate_state()['valid'])
        saved['source_fingerprint'] = V._source(self.r, saved['source'])
        saved['applications'][0]['stage_receipt'] = saved['slowed_receipt']
        self.assertFalse(self.e.validate_state()['valid'])
        restored = Engine.import_state(Rules(ROOT, ruleset='core'), json.loads(json.dumps(state)))
        self.assertTrue(restored.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
