"""A borrowed live frame keeps producer authority and caller-specific absence."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import attack_damage_history as HISTORY
import native_area_hit_effects as AREA


class NativeRecipientOwnerTests(unittest.TestCase):
    def setUp(self):
        self.actor = object(); self.target = object(); self.move = {'id': 'actual', 'class': '물리'}
        self.frame = (self.actor, self.target, self.move, 'completion')
        self.context = dict(source_id='actual', move_completion='completion', hit=True)
        self.engine = SimpleNamespace(_attack_loss_effect_scopes=[self.frame])

    def test_returns_borrowed_current_frame_without_replacing_or_mutating_stack(self):
        stack = self.engine._attack_loss_effect_scopes
        self.assertIs(HISTORY.native_recipient(self.engine, self.actor, self.target, self.context), self.frame)
        self.assertIs(self.engine._attack_loss_effect_scopes, stack)
        stack.append((self.actor, object(), self.move, 'inner'))
        with self.assertRaises(ValueError):HISTORY.native_recipient(self.engine, self.actor, self.target, self.context)
        stack.pop()
        self.assertIs(HISTORY.native_recipient(self.engine, self.actor, self.target, self.context), self.frame)

    def test_all_five_native_bindings_reject_before_consequence(self):
        for field, value in [('source_id', 'other'), ('move_completion', 'other'), ('hit', False), ('hit', 1)]:
            context = dict(self.context, **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                HISTORY.native_recipient(self.engine, self.actor, self.target, context)
        for actor, target in [(object(), self.target), (self.actor, object())]:
            with self.assertRaises(ValueError):HISTORY.native_recipient(self.engine, actor, target, self.context)
        with self.assertRaisesRegex(ValueError, 'caller detail'):
            HISTORY.native_recipient(self.engine, object(), self.target, self.context, error='caller detail')

    def test_absent_frame_remains_false_neutral_loss_or_area_error_at_each_caller(self):
        engine = SimpleNamespace()
        calls = []
        engine.lose_hp = lambda recipient, amount, **options: calls.append((recipient, amount, options))
        self.assertIsNone(HISTORY.native_recipient(engine, self.actor, self.target, self.context))
        self.assertFalse(HISTORY.wake_effect_loss(engine, self.actor, self.target, self.context, {}))
        HISTORY.effect_loss(engine, self.actor, self.target, self.target, {}, {'source_id': 'passive'}, 3)
        self.assertEqual(calls, [(self.target, 3, {'source': 'passive', 'unpreventable': False})])
        with self.assertRaisesRegex(ValueError, 'continuation'):
            HISTORY.effect_loss(engine, self.actor, self.target, self.target, {}, self.context, 3)
        with patch.object(AREA, 'preflight', return_value=(self.target,)):
            with self.assertRaisesRegex(ValueError, 'live native hit recipient'):
                AREA.recipients(engine, self.actor, self.target, {}, self.context)
        self.assertEqual(len(calls), 1)

    def test_valid_frame_does_not_bypass_domain_effect_receipt(self):
        import effect_contracts
        effect = {'type': 'hp_loss', 'value': 3}
        with patch.object(effect_contracts, 'validate_receipt', side_effect=ValueError('actual receipt required')) as validator:
            with self.assertRaisesRegex(ValueError, 'actual receipt required'):
                HISTORY.effect_loss(self.engine, self.actor, self.target, self.target, effect, self.context, 3)
            self.assertEqual(validator.call_count, 1)
            with patch.object(AREA, 'preflight', return_value=(self.target,)):
                with self.assertRaisesRegex(ValueError, 'actual receipt required'):
                    AREA.recipients(self.engine, self.actor, self.target, effect, self.context)
            self.assertEqual(validator.call_count, 2)
