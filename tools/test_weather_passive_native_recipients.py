"""Native Dry Skin recipient regressions; authored source, not executed locally."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import state_grants as GRANTS
import weather_passive_benefits as WEATHER
import test_category2_move_defense_reactions as FIXTURE


class WeatherPassiveNativeRecipientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def fixture(self, *, dry=True):
        fixture = FIXTURE.MoveDefenseReactionsTests('runTest')
        fixture.rules = self.rules
        fixture.setUp()
        if dry:
            GRANTS.replace_baseline(fixture.e, fixture.r, 'abilities', ['건조피부'])
        fixture.e.gm.set_hp(fixture.r, value=fixture.r.base_max_hp // 2,
                            reason='injured actual native recipient')
        fixture.t.pos = (6, 2)
        fixture.r.pos = (4, 4)
        return fixture

    def test_water_interceptor_is_authenticated_and_cold_resume_heals_once(self):
        fixture = self.fixture()
        fixture.watch('maneuver/원거리-가로채기')
        with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
            event = fixture.waiting('move/물대포')
        original_hp, interceptor_hp = fixture.t.hp, fixture.r.hp
        completion = fixture.completion()
        self.assertNotIn(fixture.r, completion['targets'])
        before = fixture.e.export_state()
        with self.assertRaisesRegex(ValueError, 'active native hit producer'):
            WEATHER.water_hit(fixture.e, fixture.a, fixture.r, self.rules.move('move/물대포'), {},
                completion['id'], substitute=None, natural=12, critical=False,
                defense_token=(event, fixture.t.entity_id, fixture.r.entity_id))
        self.assertEqual(fixture.e.export_state(), before)
        fixture.fresh()
        fixture.choose(event, options=fixture.ranged())
        completion = fixture.completion()
        self.assertEqual(fixture.t.hp, original_hp)
        self.assertEqual(fixture.r.hp, interceptor_hp + fixture.e.tick(fixture.r))
        self.assertEqual(completion['targets'], [fixture.t])
        self.assertEqual(completion['dry_skin_hits'][fixture.r.entity_id]['healed'], fixture.e.tick(fixture.r))
        self.assertTrue(completion['received'][fixture.r.entity_id]['hit_prevented'])
        self.assertEqual(fixture.a.move_uses['move/물대포'], 1)
        self.assertIsNone(fixture.e._passive_pending)
        before = fixture.e.export_state()
        with self.assertRaises(ValueError):
            fixture.choose(event, options=fixture.ranged())
        self.assertEqual(fixture.e.export_state(), before)
        fixture.fresh()
        self.assertEqual(fixture.r.hp, interceptor_hp + fixture.e.tick(fixture.r))

    def test_omitted_token_cannot_heal_declared_target_during_pending_defense(self):
        fixture = self.fixture(dry=False)
        GRANTS.replace_baseline(fixture.e, fixture.t, 'abilities', ['건조피부'])
        fixture.e.gm.set_hp(fixture.t, value=fixture.t.base_max_hp // 2,
                            reason='injured original declared Dry Skin target')
        fixture.watch('maneuver/원거리-가로채기')
        with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
            event = fixture.waiting('move/물대포')
        completion = fixture.completion()
        before = fixture.e.export_state()
        target_hp = fixture.t.hp
        with self.assertRaisesRegex(ValueError, 'active native hit producer'):
            WEATHER.water_hit(fixture.e, fixture.a, fixture.t, self.rules.move('move/물대포'), {},
                completion['id'], substitute=None, natural=12, critical=False)
        self.assertEqual(fixture.e.export_state(), before)
        with self.assertRaisesRegex(ValueError, 'active native hit producer'):
            WEATHER.fire_hit(fixture.e, fixture.a, fixture.t, self.rules.move('move/물대포'),
                completion['id'], 'Fire')
        self.assertEqual(fixture.e.export_state(), before)
        fixture.choose(event, use=False)
        self.assertEqual(fixture.t.hp, target_hp + fixture.e.tick(fixture.t))
        self.assertEqual(fixture.a.move_uses['move/물대포'], 1)
        self.assertIsNone(fixture.e._passive_pending)
        fixture.fresh()

    def test_intercepted_water_keeps_self_cost_receipts_on_completion_through_cold_restore(self):
        fixture = self.fixture()
        fixture.e.rule_effect('move/물대포', 'add',
            effect={'type': 'hp_loss', 'target': 'self', 'value': 1},
            reason='selected campaign self cost independent of recipient immunity')
        attacker_hp, original_hp, interceptor_hp = fixture.a.hp, fixture.t.hp, fixture.r.hp
        fixture.watch('maneuver/원거리-가로채기')
        with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
            event = fixture.waiting('move/물대포')
        fixture.choose(event, options=fixture.ranged())
        completion = fixture.completion()
        received = completion['received'][fixture.r.entity_id]
        self.assertTrue(received['hit_prevented'])
        self.assertEqual((received['dealt'], received['held'], received['effects']), (0, 0, []))
        self.assertEqual(fixture.a.hp, attacker_hp - 1)
        self.assertEqual(fixture.t.hp, original_hp)
        self.assertEqual(fixture.r.hp, interceptor_hp + fixture.e.tick(fixture.r))
        own = completion['dry_skin_hits'][fixture.r.entity_id]['attacker_effects']
        self.assertTrue(own)
        self.assertTrue(all(token in completion['effects'] for token in own))
        self.assertTrue(any(fixture.e._effect_dispatch_receipts[token]['effect'] ==
            {'type': 'hp_loss', 'target': 'self', 'value': 1} for token in own))
        self.assertTrue(fixture.e.validate_state()['valid'])
        fixture.fresh()
        completion = fixture.completion()
        own = completion['dry_skin_hits'][fixture.r.entity_id]['attacker_effects']
        self.assertTrue(own)
        self.assertTrue(all(token in completion['effects'] and token in fixture.e._effect_dispatch_receipts
                            for token in own))
        self.assertEqual(fixture.a.hp, attacker_hp - 1)
        self.assertEqual(fixture.r.hp, interceptor_hp + fixture.e.tick(fixture.r))
        self.assertTrue(fixture.e.validate_state()['valid'])

    def test_fire_interceptor_takes_one_additional_tick_without_changing_declared_target(self):
        fixture = self.fixture()
        fixture.e.gm.set_hp(fixture.r, value=fixture.r.base_max_hp, reason='living Fire recipient control')
        fixture.e.gm.set_move(fixture.a, 'move/파도타기', add=False,
                              reason='forget the actual fixture Move before replacement')
        fixture.e.gm.set_move(fixture.a, 'move/불꽃세례',
                              reason='actual Fire Move for the native recipient test')
        self.assertNotIn('move/파도타기', fixture.a.moves)
        self.assertIn('move/불꽃세례', fixture.a.moves)
        fixture.watch('maneuver/원거리-가로채기')
        with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
            event = fixture.waiting('move/불꽃세례')
        original_hp = fixture.t.hp
        fixture.choose(event, options=fixture.ranged())
        completion = fixture.completion()
        observed = completion['dry_skin_hits'][fixture.r.entity_id]
        self.assertEqual(observed['hp_before'] - observed['hp_after'], fixture.e.tick_loss(fixture.r))
        self.assertEqual(fixture.t.hp, original_hp)
        self.assertEqual(completion['targets'], [fixture.t])
        self.assertEqual(fixture.a.move_uses['move/불꽃세례'], 1)
        self.assertIsNone(fixture.e._passive_pending)
        fixture.fresh()

    def test_water_immunity_precedes_target_only_hit_hooks_with_unowned_positive_control(self):
        import illusion_state as ILLUSION
        import ninja as NINJA
        import endure as ENDURE
        import type_ace as TYPE_ACE
        for dry in (True, False):
            with self.subTest(dry=dry):
                fixture = self.fixture(dry=dry)
                before = fixture.r.hp
                with patch.object(ILLUSION, 'end_ability_illusion', wraps=ILLUSION.end_ability_illusion) as illusion, \
                     patch.object(NINJA, 'poison_hit', wraps=NINJA.poison_hit) as poison, \
                     patch.object(ENDURE, 'offer', wraps=ENDURE.offer) as endure, \
                     patch.object(TYPE_ACE, 'observe_close_quarters_hit', wraps=TYPE_ACE.observe_close_quarters_hit) as close, \
                     patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
                    fixture.e.use_move(fixture.a, fixture.r, 'move/물대포', set_damage=True)
                self.assertEqual([hook.call_count for hook in (illusion, poison, endure, close)], [0 if dry else 1] * 4)
                if dry:
                    self.assertEqual(fixture.r.hp, before + fixture.e.tick(fixture.r))
                else:
                    self.assertLess(fixture.r.hp, before)
                self.assertEqual(fixture.a.move_uses['move/물대포'], 1)


if __name__ == '__main__':
    unittest.main()
