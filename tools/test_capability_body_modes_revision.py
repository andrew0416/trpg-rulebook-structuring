"""Actual gift and species capability holders reach their existing native owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', 'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from builder import build_pokemon
from grid import Grid
import test_category2_body_modes as FIXTURE
import test_category2_cleanse_barrier as BARRIER
import native_scenario_fixture as NATIVE
import items
import body_modes as MODES
import body_state as BODY
import state_grants as G
import struggle_capabilities as STRUGGLE
import ranged_struggle as RANGED
import telekinetic_combat as TK
import cleanse_tags as TAG
import common_checks as C
import world_entities as WORLD


class CapabilityBodyModesRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='all')

    def world(self):
        case = FIXTURE.Tests('runTest')
        case.r = self.r
        case.setUp()
        return case

    def gift(self, case, uid):
        case.a.spec.setdefault('feats', []).append(uid)
        items.register_feats(case.e, case.a)
        return 'feature:' + case.a.entity_id + ':' + uid

    def withdraw(self, case, uid, source):
        case.a.spec['feats'].remove(uid)
        G.revoke(case.a, source, engine=case.e)

    def test_actual_gift_trainers_use_both_elemental_struggle_classes_and_final_withdrawal(self):
        gifts = [('feat/가이오가의-메이저-기프트-웨이브크래셔', '물줄기', '물'),
                 ('feat/레쿠쟈의-메이저-기프트-공기-적응', '세찬바람', '비행')]
        for uid, capability, element in gifts:
            for special in (False, True):
                with self.subTest(gift=uid, special=special):
                    f = self.world()
                    f.a.pos = (2, 3)
                    source = self.gift(f, uid)
                    choice = {'capability': capability, 'special': special}
                    raw = deepcopy(f.r.move('struggle'))
                    prepared = STRUGGLE.prepare(f.e, f.a, raw, choice)
                    self.assertEqual(prepared['range'], raw['range'])
                    self.assertNotIn('_struggle_range', prepared)
                    f.begin(f.a)
                    with patch.object(f.e, 'damage_base', wraps=f.e.damage_base) as damage:
                        with patch.object(f.e.rng, 'randint', return_value=20):
                            f.e.use_move_on(f.a, f.p, 'struggle', f.e.everyone, struggle_choice=choice)
                    self.assertTrue(any(call.args[1]['type'] == element and
                        call.args[1]['class'] == ('특수' if special else '물리') for call in damage.call_args_list))
                    self.assertEqual(f.a.budget['standard'], 0)
                    self.assertEqual(f.r.move('struggle'), raw)
                    self.withdraw(f, uid, source)
                    NATIVE.assert_rejected_unchanged(f.e,
                        lambda: STRUGGLE.prepare(f.e, f.a, prepared), reason_pattern='actual Struggle capability')

    def test_trainer_kind_cannot_supply_capability_weapon_ranged_or_telekinetic_authority(self):
        f = self.world()
        choice = {'capability': '물줄기', 'special': False}
        NATIVE.assert_rejected_unchanged(f.e,
            lambda: STRUGGLE.prepare(f.e, f.a, f.r.move('struggle'), choice),
            reason_pattern='actual Struggle capability')
        self.gift(f, 'feat/가이오가의-메이저-기프트-웨이브크래셔')
        weapon = dict(f.r.move('struggle'), _weapon_attack=True)
        NATIVE.assert_rejected_unchanged(f.e,
            lambda: STRUGGLE.prepare(f.e, f.a, weapon, choice), reason_pattern='ordinary unarmed')
        with patch.object(TK, 'prepare_struggle', wraps=TK.prepare_struggle) as telekinetic:
            with self.assertRaisesRegex(ValueError, 'Telekinetic|염력'):
                STRUGGLE.prepare(f.e, f.a, f.r.move('struggle'), {'capability': 'Telekinetic', 'special': False})
        self.assertEqual(telekinetic.call_count, 1)
        # A gift is not a Pokemon Tutor Point investment or ranged source.
        self.assertIsNone(RANGED.range_for(f.a, '물줄기'))

    def test_gift_trainer_amorphous_uses_measured_native_passage_and_same_body_restore(self):
        f = self.world()
        uid = 'feat/메이저-기프트-부정형'
        source = self.gift(f, uid)
        f.e.grid = Grid(7, 5, walls=[((2, y), (3, y)) for y in range(5)])
        f.a.pos = (2, 2); f.p.pos = (0, 0); f.t.pos = (5, 2)
        f.e.gm.set_movement_capabilities(f.a, {'land': 4}, basis='base', reason='actual Trainer Overland')
        f.begin(f.a)
        before = deepcopy(f.a.budget)
        identity = f.a.entity_id
        f.e.change_body_mode(f.a, 'amorphous', offsets=[(0, 0)], form='flatten', height_m=.03,
            cross_section={'axis': 'x', 'width_m': .4}, reason='actual gifted Trainer flattens the same body')
        self.assertEqual(f.a.budget, before)
        f.e.approach(f.a, f.t, movement_mode='land')
        self.assertEqual(f.a.pos, (2, 2))
        f.begin(f.a)
        WORLD.register_object(f.e, 'gift-door', location={'kind': 'grid', 'cell': (2, 2)}, reason='actual door')
        f.e.gm.observe_body_passage('gift-door', [(2, 2), (3, 2)], passage_id='gift-gap',
            height_m=.04, width_m=.5, reason='measured gap under the actual closed door')
        f.e.approach(f.a, f.t, movement_mode='land')
        self.assertEqual((f.a.pos, f.a.budget['shift']), ((4, 2), 0))
        self.assertTrue(f.e.grid.blocked((2, 2), (3, 2)))
        loaded = f.restored(); actual = WORLD.actor_index(loaded)[identity]
        self.assertEqual(actual.spec[MODES.KEY], f.a.spec[MODES.KEY])
        self.withdraw(f, uid, source)
        f.e.change_body_mode(f.a, 'normal', reason='same Trainer reforms after actual gift withdrawal')
        NATIVE.assert_rejected_unchanged(f.e, lambda: f.e.change_body_mode(f.a, 'amorphous',
            offsets=[(0, 0)], form='flatten', reason='no remaining actual capability'),
            reason_pattern='actual body capability')

    def test_gift_trainer_phasing_reaches_body_tick_and_existing_cleanse_pending_focus_owner(self):
        case = BARRIER.BarrierTests('runTest')
        case.rules = self.r
        case.setUp()
        G.set_baseline(case.a, 'capabilities', [])
        uid = 'feat/메이저-기프트-페이징'
        self.gift(case, uid)
        case.a.pos = (2, 1); case.p.pos = (1, 2)
        case.e.start_round(case.e.everyone); case.e.start_of_turn(case.a, initiative_count=20)
        hp = case.a.hp; loss = case.e.tick_loss(case.a)
        case.e.change_body_mode(case.a, 'phasing', reason='actual gifted Trainer becomes intangible')
        self.assertEqual(case.a.budget['standard'], 0)
        self.assertIsInstance(TAG.phasing_passage(case.e, case.a, (4, 1)), C.PendingDecision)
        self.assertTrue(case.gate(actor=case.a, attempt='gifted-trainer-focus', faces=[3] * 4))
        self.assertEqual(case.e._physical_objects['tag:one']['destroyed']['by_actor_id'], case.a.entity_id)
        case.e.end_of_turn(case.a); case.e.end_round()
        self.assertEqual(case.a.hp, hp - loss)

    def test_phasing_tick_uses_true_max_hp_and_round_marker_survives_native_codec(self):
        f = self.world()
        G.grant(f.p, 'capabilities', 'Phasing', 'fixture:phasing', 'fixture')
        f.e.gm.set_injuries(f.p, value=3, reason='actual injuries before becoming intangible')
        f.e.gm.set_hp(f.p, value=f.p.max_hp, reason='actual current injured HP')
        self.assertNotEqual(f.p.base_max_hp // 10, f.p.max_hp // 10)
        f.begin(f.p)
        f.e.change_body_mode(f.p, 'phasing', reason='source-defined one Tick at each round end')
        hp = f.p.hp; expected = f.p.base_max_hp // 10
        with patch.object(f.e, 'lose_tick_hp', wraps=f.e.lose_tick_hp) as ticks:
            f.e.end_of_turn(f.p); f.e.end_round()
        self.assertEqual(ticks.call_count, 1)
        self.assertEqual(f.p.hp, hp - expected)
        loaded = f.restored(); actual = WORLD.actor_index(loaded)[f.p.entity_id]
        hp = actual.hp; MODES.finish_round(loaded)
        self.assertEqual(actual.hp, hp)
        loaded.start_round(loaded.everyone); loaded.end_round()
        self.assertEqual(actual.hp, hp - expected)

    def test_marshadow_csv_holder_uses_shadow_with_standard_cost_host_motion_and_shift_return(self):
        f = self.world()
        c = f.add(build_pokemon(f.r, '마샤도', 20, moves=[], abilities=[],
            extra={'trainer_id': f.a.entity_id}))
        self.assertIn('그림자숨기', G.effective_capabilities(c))
        f.e.gm.observe_loyalty(c, 6, reason='actual trusted species capability holder')
        c.pos = f.t.pos
        f.begin(c)
        f.e.change_body_mode(c, 'shadow', shadow_host=f.t, reason='actual Marshadow enters this creature shadow')
        self.assertEqual(c.budget['standard'], 0)
        self.assertTrue(MODES.flat(c))
        f.e.gm.set_position(f.t, (8, 3), reason='actual host moves with its shadow')
        self.assertEqual(c.pos, f.t.pos)
        loaded = f.restored(); actual = WORLD.actor_index(loaded)[c.entity_id]
        self.assertEqual(actual.spec[MODES.KEY], c.spec[MODES.KEY])
        f.begin(c)
        f.e.change_body_mode(c, 'normal', reason='actual Marshadow reforms using Shift')
        self.assertEqual(c.budget['shift'], 0)
        self.assertNotIn(MODES.KEY, c.spec)
        # Species identity does not manufacture possession for a non-holder.
        f.begin(f.p)
        NATIVE.assert_rejected_unchanged(f.e,
            lambda: f.e.change_body_mode(f.p, 'shadow', reason='no acquired Shadow Meld capability'),
            reason_pattern='actual body capability')


if __name__ == '__main__':
    unittest.main()
