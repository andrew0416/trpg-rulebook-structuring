"""Native Heavy certificates validate, rather than discard, target references."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from engine import Combatant, Engine, Rules
import heavy_injury_adapter as H
import heavy_standard_adapter as S


class HeavyTargetBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def pair(self, *, seed=0, actor_injuries=0, target_injuries=5):
        engine = Engine(self.rules, seed=seed)
        def actor(name):
            return Combatant(engine.r, dict(name=name, kind='trainer', level=10,
                stats={key: 30 for key in ('hp', 'atk', 'def', 'spa', 'spd', 'spe')},
                types=[], abilities=[], moves=['struggle']))
        a, b = actor('attacker'), actor('target')
        a.hp, a.injuries = 50, actor_injuries
        b.hp, b.injuries = (110 if actor_injuries else 50), target_injuries
        engine.everyone = engine.gm.everyone = [a, b]
        engine.start_round([a, b])
        engine.start_of_turn(a)
        return engine, a, b

    def test_source_and_exact_target_binding_have_same_diagnostic(self):
        e, a, b = self.pair()
        source = e.r.move('struggle')
        bound = dict(source, _actual_targets=(b,))
        raw = H.certify_native_context(e, a, b, source, {}, ordinary_single=True)
        actual = H.certify_native_context(e, a, b, bound, {}, ordinary_single=True)
        self.assertEqual(raw.failures, ())
        self.assertEqual(actual.failures, raw.failures)
        self.assertEqual(actual.checked, raw.checked)
        self.assertIs(bound['_actual_targets'][0], b)
        self.assertNotIn('_actual_targets', source)

    def test_binding_requires_exact_tuple_and_current_target_identity(self):
        e, a, b = self.pair()
        class Targets(tuple):
            pass
        for refs in ((), (a,), (a, b), (b, b), [b], Targets((b,)), None):
            with self.subTest(refs=type(refs).__name__, length=len(refs) if refs is not None else None):
                move = dict(e.r.move('struggle'), _actual_targets=refs)
                self.assertIsNone(H.single_target_move_data(move, b))
                result = H.certify_native_context(e, a, b, move, {}, ordinary_single=True)
                self.assertIn('not_empty_mech_native_struggle', result.failures)

    def test_unknown_move_metadata_and_real_semantic_changes_are_not_erased(self):
        e, a, b = self.pair()
        source = dict(e.r.move('struggle'), _actual_targets=(b,))
        for change in ({'_unknown_receipt': {'state': 'ended'}},
                       {'_actual_rule_effect': True}, {'damage_base': 99},
                       {'type': '불꽃'}, {'range': '자신'}):
            with self.subTest(change=change):
                result = H.certify_native_context(e, a, b, dict(source, **change), {}, ordinary_single=True)
                self.assertIn('not_empty_mech_native_struggle', result.failures)

    def test_exact_binding_does_not_admit_live_actor_effects(self):
        e, a, b = self.pair()
        b.modifiers.append({'type': 'damage_roll_mod', 'value': 1})
        result = H.certify_native_context(e, a, b,
            dict(e.r.move('struggle'), _actual_targets=(b,)), {}, ordinary_single=True)
        self.assertIn('target:modifiers', result.failures)

    def test_standard_public_data_checks_the_source_and_binding_separately(self):
        e, a, b = self.pair(actor_injuries=5, target_injuries=0)
        inputs = dict(situational=0, set_damage=True, count_use=True, free_action=False)
        move = dict(e.r.move('struggle'), _actual_targets=(b,))
        self.assertEqual(S._public_data_failures(a, b, move, {}, inputs), [])
        self.assertIn('nonplain_move_data', S._public_data_failures(
            a, b, dict(move, _actual_targets=(a,)), {}, inputs))
        self.assertIn('nonplain_move_data', S._public_data_failures(
            a, b, dict(move, _unknown=object()), {}, inputs))

    def test_native_standard_hit_and_miss_keep_one_real_loss(self):
        for seed, dealt in ((0, 11), (31, 0)):
            with self.subTest(seed=seed):
                e, a, b = self.pair(seed=seed, actor_injuries=5, target_injuries=0)
                self.assertEqual(e.use_move(a, b, 'struggle', set_damage=True), dealt)
                self.assertEqual((a.hp, b.hp), (45, 110-dealt))
                self.assertEqual(a.move_uses['struggle'], 1)
                self.assertEqual(a.budget['standard'], 0)
                self.assertIsNone(e._heavy_pending)
                self.assertFalse(e._heavy_standard_receipts)

    def test_native_target_attack_keeps_one_loss_and_consumes_receipt(self):
        e, a, b = self.pair()
        self.assertEqual(e.use_move(a, b, 'struggle', set_damage=True), 11)
        self.assertEqual((a.hp, b.hp, b.injuries), (50, 34, 5))
        self.assertIsNone(e._heavy_pending)
        self.assertFalse(e._heavy_native_receipts)

    def test_valid_binding_diagnostic_is_not_an_activation_receipt(self):
        e, a, b = self.pair()
        move = dict(e.r.move('struggle'), _actual_targets=(b,))
        diagnostic = H.certify_native_context(e, a, b, move, {}, ordinary_single=True)
        self.assertEqual(diagnostic.failures, ())
        before = (a.hp, b.hp, dict(a.move_uses), dict(a.budget), e.rng.getstate())
        with self.assertRaises(ValueError):
            e.resolve_attack_damage(a, b, move, set_damage=True, _heavy_context=diagnostic)
        self.assertEqual((a.hp, b.hp, a.move_uses, a.budget, e.rng.getstate()), before)
        self.assertFalse(e._heavy_events)


if __name__ == '__main__':
    unittest.main()
