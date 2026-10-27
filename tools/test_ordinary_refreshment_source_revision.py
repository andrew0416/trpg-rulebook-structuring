"""Actual Extended refreshment source choices, completion clocks and stock."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import clock_invocations as CLOCK
import common_checks as CHECKS
import food_effects as FOOD
import state_codec as CODEC
import world_entities as WORLD
import test_clock_native_consumers as FIXTURE


class OrdinaryRefreshmentSourceRevisionTests(unittest.TestCase):
    def world(self, profile='core'):
        fixture = FIXTURE.TimedConsumerTests()
        fixture.rules = Rules(ROOT, ruleset=profile)
        fixture.setUp()
        fixture.a.spec['items']['맛있는물'] = 6
        fixture.p.hp = 1
        return fixture

    def state(self, fixture):
        return deepcopy((CODEC.dump_engine(fixture.e), fixture.e.rng.getstate()))

    def choice(self, fixture, variant, *, target=None):
        query = FOOD.refreshment_source_choices(fixture.e, fixture.a, target or fixture.p, 'item/맛있는물')
        self.assertEqual(query['status'], 'PolicyInputsRequired')
        return {'value': variant, 'reason': 'GM selected this actual printed refreshment definition',
                'scope': query['decision_scope']}

    def drink(self, fixture, choice=None, **options):
        return fixture.e.use_item(fixture.a, '맛있는물', fixture.p, food_policy=choice,
            duration_minutes=1, duration_reason='observed complete one-minute drink', **options)

    def restore(self, fixture, *, annotation=False):
        if annotation:
            # Table notes are mutable campaign state, not a silent rule-profile edit.
            fixture.e.rulings.add_answer('refreshment_campaign_note','unrelated current table annotation',
                reason='actual campaign note retained through restoration',scope='campaign')
        snapshot = fixture.e.gm.snapshot()
        fixture.e.gm.restore(snapshot)
        rules = Rules(ROOT, ruleset=fixture.e.r.ruleset.name)
        ids = fixture.a.entity_id, fixture.p.entity_id
        fixture.e = Engine.import_state(rules, json.loads(json.dumps(fixture.e.export_state())))
        fixture.a, fixture.p = (WORLD.actor_index(fixture.e)[uid] for uid in ids)

    def test_complete_kr_default_and_both_scoped_definitions_use_exact_completion_boundaries(self):
        for variant, seconds in ((None, 3600), ('korean_hour', 3600), ('english_half_hour', 1800)):
            with self.subTest(variant=variant):
                fixture = self.world()
                choice = self.choice(fixture, variant) if variant else None
                first = self.drink(fixture, choice)
                self.assertEqual((first['healed'], fixture.e.elapsed_seconds, fixture.a.spec['items']['맛있는물']), (20, 60, 5))
                receipt = fixture.p.spec['drink_history'][0]['refreshment_policy']
                self.assertEqual((receipt['ordinary']['variant'], receipt['effective']),
                    (variant or 'korean_hour', {'seconds': seconds, 'limit': 1, 'source': FOOD.DRINK_SOURCE}))
                self.assertEqual(receipt['ordinary']['definition']['action'], 'extended')
                self.assertTrue(receipt['ordinary']['definition']['outside_combat'])
                fixture.e.advance_time(seconds - 61, [fixture.a, fixture.p])
                before = self.state(fixture)
                with self.assertRaisesRegex(ValueError, 'drink intake limit'):
                    self.drink(fixture, choice)
                self.assertEqual(self.state(fixture), before)
                fixture.e.advance_time(1, [fixture.a, fixture.p])
                self.drink(fixture, choice)
                self.assertEqual((fixture.e.elapsed_seconds, fixture.a.spec['items']['맛있는물'], len(fixture.p.spec['drink_history'])), (seconds + 60, 4, 2))

    def test_invalid_or_wrong_actual_scope_choices_never_pay_advance_or_roll(self):
        fixture = self.world()
        choice = self.choice(fixture, 'english_half_hour')
        wrong_target = self.choice(fixture, 'english_half_hour', target=fixture.a)
        invalid = deepcopy(choice)
        invalid['value'] = 'arbitrary_120_seconds'
        no_reason = deepcopy(choice)
        no_reason['reason'] = ''
        for supplied in ('english_half_hour', invalid, no_reason, wrong_target):
            with self.subTest(choice=supplied):
                before = self.state(fixture)
                with self.assertRaises((ValueError, TypeError)):
                    self.drink(fixture, supplied)
                self.assertEqual(self.state(fixture), before)
        before = self.state(fixture)
        with self.assertRaises(ValueError):
            fixture.e.use_item(fixture.a, '초코바', fixture.p, food_policy=choice,
                duration_minutes=1, duration_reason='wrong food source choice')
        self.assertEqual(self.state(fixture), before)
        shell = FIXTURE.TimedPhysicalIntakeTests()
        shell.r = Rules(ROOT, ruleset='core')
        shell.setUp()
        shell.e.advance_time(1295970)
        shell.install()
        self.assertEqual(shell.row()['stage'], 'juice')
        query = FOOD.refreshment_source_choices(shell.e, shell.p, shell.p, 'item/나무열매쥬스')
        ordinary_choice = {'value': 'english_half_hour',
            'reason': 'valid ordinary refreshment choice cannot authorize a shell Snack',
            'scope': query['decision_scope']}
        for supplied in (ordinary_choice, 'arbitrary_policy'):
            before = self.state(shell)
            reason='exact food source policy' if isinstance(supplied,dict) else 'exact reviewed CSV food clause selection required'
            with self.assertRaisesRegex(ValueError, reason):
                shell.use(food_policy=supplied)
            self.assertEqual(self.state(shell), before)
            self.assertEqual(shell.row()['stage'], 'juice')
            self.assertNotIn('shell', getattr(shell.e, '_clock_invocations', {}))
        # Actual shell Snack with no unrelated policy retains its old request
        # and real start-payment/conditional pause/completion path.
        self.assertEqual(shell.use()['status'], 'waiting')
        self.assertEqual((shell.row()['stage'], shell.row()['removal']['at'], shell.e.elapsed_seconds),
                         ('consumed', 1295970, 1295975))
        self.assertNotIn('refreshment_policy', shell.e._clock_invocations['shell']['activity']['plan'])
        shell.answer()
        self.assertEqual(shell.use()['status'], 'digestion_buff_gained')
        self.assertEqual(shell.p.buffs[-1]['effect'], {'kind': 'heal', 'amount': 30})
        self.assertFalse(shell.p.spec.get('drink_history'))
        fixture.e.unresolved_time_intervals.append({'round': 0, 'reason': 'actual unknown elapsed interval'})
        self.drink(fixture, choice)
        fixture.e.unresolved_time_intervals.append({'round': 0, 'reason': 'another unknown interval'})
        before = self.state(fixture)
        self.assertIsInstance(self.drink(fixture, choice), CHECKS.PendingDecision)
        self.assertEqual(self.state(fixture), before)

    def test_both_actual_gluttony_sources_override_each_ordinary_definition(self):
        for profile, ability in (('core', FOOD.CORE_GLUTTONY), ('playtest', FOOD.GLUTTONY)):
            for variant in ('korean_hour', 'english_half_hour'):
                with self.subTest(profile=profile, variant=variant):
                    fixture = self.world(profile)
                    fixture.e.gm.set_ability(fixture.p, ability, reason='actual current acquired Gluttony source')
                    choice = self.choice(fixture, variant)
                    self.drink(fixture, choice)
                    self.drink(fixture, choice)
                    self.restore(fixture)
                    for record in fixture.p.spec['drink_history']:
                        self.assertEqual(record['refreshment_policy']['effective'], {'seconds': 1800, 'limit': 2, 'source': ability})
                    before = self.state(fixture)
                    with self.assertRaisesRegex(ValueError, 'drink intake limit'):
                        self.drink(fixture, choice)
                    self.assertEqual(self.state(fixture), before)
                    fixture.e.advance_time(1679, [fixture.a, fixture.p])
                    before = self.state(fixture)
                    with self.assertRaisesRegex(ValueError, 'drink intake limit'):
                        self.drink(fixture, choice)
                    self.assertEqual(self.state(fixture), before)
                    fixture.e.advance_time(1, [fixture.a, fixture.p])
                    self.drink(fixture, choice)
                    self.assertEqual((fixture.a.spec['items']['맛있는물'], len(fixture.p.spec['drink_history'])), (3, 3))
                    fixture.p.abilities_suppressed = True
                    before = self.state(fixture)
                    with self.assertRaisesRegex(ValueError, 'drink intake limit'):
                        self.drink(fixture, choice)
                    self.assertEqual(self.state(fixture), before)

    def test_real_pending_en_work_pins_producing_choice_across_restore_and_late_failure(self):
        fixture = self.world()
        choice = self.choice(fixture, 'english_half_hour')
        fixture.install()
        out = self.drink(fixture, choice, resumable=True, request_id='english-drink')
        self.assertEqual((out['status'], fixture.e.elapsed_seconds, fixture.a.spec['items']['맛있는물'], fixture.p.hp), ('waiting', 5, 6, 1))
        plan = deepcopy(fixture.e._clock_invocations['english-drink']['activity']['plan'])
        self.restore(fixture, annotation=True)
        fixture.answer('english-drink')
        before = self.state(fixture)
        with self.assertRaises(ValueError):
            self.drink(fixture, self.choice(fixture, 'korean_hour'), resumable=True, request_id='english-drink')
        self.assertEqual(self.state(fixture), before)
        heal = type(fixture.e).heal
        def fail(engine, *args, **kwargs):
            heal(engine, *args, **kwargs)
            raise ValueError('actual late refreshment healing failure')
        with patch.object(type(fixture.e), 'heal', fail):
            with self.assertRaisesRegex(ValueError, 'late refreshment'):
                self.drink(fixture, choice, resumable=True, request_id='english-drink')
        self.assertEqual((fixture.e.elapsed_seconds, fixture.a.spec['items']['맛있는물'], fixture.p.hp), (60, 6, 1))
        self.assertFalse(fixture.p.spec.get('drink_history'))
        self.restore(fixture, annotation=True)
        result = self.drink(fixture, choice, resumable=True, request_id='english-drink')
        record = fixture.p.spec['drink_history'][0]
        clock = fixture.e._clock_invocations['english-drink']['activity']
        self.assertEqual(record['refreshment_policy'], plan['refreshment_policy'])
        self.assertEqual(record['refreshment_policy']['ordinary']['choice'], choice)
        self.assertIs(clock['native'], record)
        self.assertIs(clock['payment'], record['item_stock'])
        self.assertEqual((result['healed'], fixture.a.spec['items']['맛있는물']), (20, 5))
        self.restore(fixture, annotation=True)
        before = self.state(fixture)
        self.assertEqual(self.drink(fixture, choice, resumable=True, request_id='english-drink'), result)
        self.assertEqual(self.state(fixture), before)

    def test_authenticated_58_plan_shape_and_completed_old_history_gain_no_retroactive_choice(self):
        fixture = self.world()
        fixture.install()
        native = CLOCK.run_activity
        def prior_optional_plan(engine, actor, actors, *, prepare, **options):
            # Source-accurate 58 fixture: the actual prior drink plan had no
            # refreshment_policy. Remove only that additive field BEFORE the
            # real clock owner authenticates admission, not from a saved hash.
            def prepare_58(*args):
                plan, payment = prepare(*args)
                plan.pop('refreshment_policy')
                return plan, payment
            return native(engine, actor, actors, prepare=prepare_58, **options)
        with patch.object(CLOCK, 'run_activity', prior_optional_plan):
            self.assertEqual(self.drink(fixture, resumable=True, request_id='prior-drink')['status'], 'waiting')
        self.assertNotIn('refreshment_policy', fixture.e._clock_invocations['prior-drink']['activity']['plan'])
        self.restore(fixture)
        fixture.answer('prior-drink')
        self.drink(fixture, resumable=True, request_id='prior-drink')
        old = deepcopy(fixture.p.spec['drink_history'][0])
        self.assertNotIn('refreshment_policy', old)
        self.restore(fixture)
        before = self.state(fixture)
        with self.assertRaisesRegex(ValueError, 'drink intake limit'):
            self.drink(fixture)
        self.assertEqual(self.state(fixture), before)
        fixture.e.advance_time(1740, [fixture.a, fixture.p])
        choice = self.choice(fixture, 'english_half_hour')
        self.drink(fixture, choice)
        self.assertEqual(fixture.p.spec['drink_history'][0], old)
        self.assertEqual(fixture.p.spec['drink_history'][1]['refreshment_policy']['ordinary']['variant'], 'english_half_hour')
        self.restore(fixture)
        self.assertEqual(fixture.p.spec['drink_history'][0], old)


if __name__ == '__main__':
    unittest.main()
