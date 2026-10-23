"""Independent lifecycle, rollback, replay and restore checks for native events."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_category2_reactive_ability_events as CONSUMER
import reactive_ability_events as REACTIVE
import state_grants as GRANTS
import combat_timing as TIME
import world_entities as WORLD
from engine import Engine, Rules
from state_codec import StateCodecError, rules_fingerprint

ROOT = Path(__file__).resolve().parents[1]


class ReactiveAbilityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.case = CONSUMER.ReactiveAbilityEventsTests()
        self.case.r = self.rules
        self.case.setUp()

    def test_owned_type_removal_preserves_independent_added_type(self):
        c = self.case
        c.give(c.t, ['변색']); c.choose(c.t, REACTIVE.COLOR)
        c.e.use_move(c.a, c.t, 'move/물대포', set_damage=True)
        GRANTS._source(c.t, 'independent-fairy', 'effect')
        GRANTS.type_operation(c.t, 'add', ['페어리'], 'independent-fairy')
        self.assertEqual(c.t.types, ['물', '페어리'])
        c.give(c.t, [])
        self.assertEqual(c.t.types, list(dict.fromkeys(c.t.spec['types'] + ['페어리'])))
        self.assertTrue(REACTIVE.validate_world(c.e, WORLD.actor_index(c.e)))
        _, _, target = c.fresh()
        self.assertEqual(target.types, c.t.types)

    def test_completed_hit_replay_cannot_spend_or_change_state_again(self):
        c = self.case
        c.give(c.t, ['가시지않는향기']); c.give(c.a, ['인분'])
        c.choose(c.t, REACTIVE.AROMA)
        c.e.use_move(c.a, c.t, 'move/몸통박치기')
        row = list(c.e._move_completions.values())[-1]
        before = deepcopy((c.a.spec, c.t.spec, c.e.rng.getstate(), c.t._action_history))
        REACTIVE.resolved_hit(c.e, c.a, c.t, row['move'], row['id'])
        self.assertEqual((c.a.spec, c.t.spec, c.e.rng.getstate(), c.t._action_history), before)

    def test_forged_matching_lifetime_records_still_fail_source_policy_validation(self):
        c = self.case
        c.give(c.t, ['가시지않는향기']); c.give(c.a, ['인분'])
        c.choose(c.t, REACTIVE.AROMA)
        c.e.use_move(c.a, c.t, 'move/몸통박치기')
        row = list(c.e._move_completions.values())[-1]
        grant = row[REACTIVE.TAG]['applications'][0]['grants'][0]
        timed = next(record for record in TIME.records(c.a) if REACTIVE.TAG in record)
        grant['timing']['ends'].append('recall')
        timed['ends'].append('recall')
        with self.assertRaisesRegex(ValueError, 'source policy'):
            REACTIVE.validate_world(c.e, WORLD.actor_index(c.e))
        with self.assertRaises((ValueError, StateCodecError)):
            c.e.export_state()

    def test_late_recipient_failure_rolls_back_hit_rng_action_and_frequency(self):
        c = self.case
        c.give(c.t, ['가시지않는향기']); c.give(c.a, ['인분'])
        c.choose(c.t, REACTIVE.AROMA)
        before = deepcopy((c.a.spec, c.t.spec, c.a.hp, c.t.hp,
                           c.a.budget, c.e.rng.getstate(), c.a.move_uses))
        original = GRANTS.reconcile
        def fail_after_grant(engine, actor, **kwargs):
            if actor.entity_id == c.a.entity_id and '가시지않는향기' in actor.abilities:
                raise ValueError('recipient registration failed')
            return original(engine, actor, **kwargs)
        with patch.object(GRANTS, 'reconcile', side_effect=fail_after_grant):
            with self.assertRaisesRegex(ValueError, 'recipient registration failed'):
                c.e.use_move(c.a, c.t, 'move/몸통박치기')
        self.assertEqual((c.a.spec, c.t.spec, c.a.hp, c.t.hp,
                          c.a.budget, c.e.rng.getstate(), c.a.move_uses), before)

    def test_swap_recall_restores_only_recalled_participant(self):
        c = self.case
        c.give(c.t, ['떠도는영혼']); c.give(c.a, ['인분'])
        c.choose(c.t, REACTIVE.SPIRIT)
        c.e.use_move(c.a, c.t, 'move/몸통박치기')
        c.e.gm.recall(c.t, reason='actual participant recall')
        self.assertEqual(c.t.abilities, ['떠도는영혼'])
        self.assertEqual(c.a.abilities, ['떠도는영혼'])
        _, attacker, target = c.fresh()
        self.assertEqual(attacker.abilities, ['떠도는영혼'])
        self.assertEqual(target.abilities, ['떠도는영혼'])

    def test_empty_area_actual_use_spends_swift_and_projects_type(self):
        c = self.case
        c.a.pos = (1, 5); c.t.pos = (15, 15)
        GRANTS.replace_baseline(c.e, c.a, 'moves', ['move/날려버리기'])
        c.give(c.a, ['변환자재']); c.choose(c.a, REACTIVE.PROTEAN)
        c.e.use_move_on(c.a, c.a, 'move/날려버리기', c.e.everyone, aim=(5, 5))
        self.assertEqual(c.a.types, [c.r.move('move/날려버리기')['type']])
        self.assertEqual((c.a.budget['standard'], c.a.budget['swift']), (0, 0))
        row = list(c.e._move_completions.values())[-1]
        self.assertEqual(row['activation'], 'empty_area_field')
        self.assertEqual(row['results'], {})
        self.assertTrue(REACTIVE.validate_world(c.e, WORLD.actor_index(c.e)))

    def test_cold_warm_policy_cache_normalization_retains_mutation_detection(self):
        import ability_native_actions as NATIVE
        cold = Rules(ROOT, ruleset='core')
        before = rules_fingerprint(cold)
        NATIVE.policy(cold)
        self.assertEqual(rules_fingerprint(cold), before)
        cold._ability_native_actions_policy['schema_version'] = 99
        self.assertNotEqual(rules_fingerprint(cold), before)

    def test_unresolved_entrainment_is_not_admitted_as_a_reactive_source(self):
        c = self.case
        before = deepcopy((c.a.spec, c.a.budget, c.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'reviewed reactive source'):
            c.e.choose_reactive_ability(c.a, 'move/동료만들기', ability='인분', reason='unresolved source')
        self.assertEqual((c.a.spec, c.a.budget, c.e.rng.getstate()), before)


if __name__ == '__main__':
    unittest.main()
