"""Selected CSV optional DB replacements through actual native Move producers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import native_scenario_fixture as NATIVE
import optional_move_modes as MODES
import passive_events as PASSIVE

BITTER = 'move/천추지한'
MOULD = 'move/곰팡이독소'
HEX = 'move/병상첨병'
CASES = ((BITTER, 6, 12), (MOULD, 7, 13))


class OptionalMoveChoiceRevisionTests(unittest.TestCase):
    def make_world(self):
        stats = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30)
        actors = []
        for key, side, pos, moves in (
                ('user', 'party', (2, 2), [BITTER, MOULD, HEX]),
                ('first', 'enemy', (6, 2), []),
                ('later', 'enemy', (6, 3), []),
                ('reactor', 'enemy', (4, 4), [])):
            actors.append(dict(key=key, kind='trainer', sheet=dict(
                name=key, level=30, stats=stats, abilities=[], moves=moves,
                pos=pos, side=side, skills={'육상': 3},
                extra={'movement': {'land': 8}, 'movement_basis': 'current'}),
                body=dict(size='중형', offsets=[(0, 0)], reason='observed actual combatant')))
        self.e, index = NATIVE.prepare_scene(str(ROOT), ruleset='all', seed=530,
            grid={'width': 20, 'height': 20}, actors=actors)
        self.a, self.b, self.c, self.reactor = (index[k] for k in ('user', 'first', 'later', 'reactor'))
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=30)

    def setUp(self):
        self.make_world()

    def next_turn(self):
        self.e.end_of_turn(self.a)
        self.e.end_round()
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=30)

    def afflict(self, *targets):
        for target in targets:
            self.e.apply_status(target, '화상', source='move/도깨비불', applied_by=self.a)

    def choose(self, move_id):
        return self.e.gm.choose_optional_move_effect(self.a, move_id, reason='explicit DB replacement')

    def native_db(self, move_id, target, *, face=10, area_entry=False):
        seen = []
        original = Engine.damage_base
        def observe(engine, actor, move, *args, **kwargs):
            result = original(engine, actor, move, *args, **kwargs)
            if actor.entity_id == self.a.entity_id and move['id'] == move_id:
                seen.append(result)
            return result
        with patch.object(Engine, 'damage_base', observe), patch.object(Engine, 'd20', return_value=face):
            if area_entry:
                dealt = self.e.use_move_on(self.a, target, move_id, self.e.everyone, set_damage=True)
            else:
                dealt = self.e.use_move(self.a, target, move_id, set_damage=True)
        return dealt, seen

    def restore(self):
        identities = [actor.entity_id for actor in (self.a, self.b, self.c, self.reactor)]
        blob = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        self.e = Engine.import_state(self.e.r, blob)
        index = {actor.entity_id: actor for actor in self.e.everyone}
        self.a, self.b, self.c, self.reactor = (index[uid] for uid in identities)

    def test_decline_first_afflicted_target_then_accept_later_without_legacy_counter(self):
        for move_id, normal, boosted in CASES:
            with self.subTest(move=move_id):
                self.make_world()
                self.afflict(self.b, self.c)
                self.assertEqual(self.native_db(move_id, self.b, face=19 if move_id == BITTER else 10)[1], [normal])
                if move_id == BITTER:
                    self.assertTrue({'구속', '수렁'} <= self.b.conditions)
                self.assertEqual(MODES.history(self.a), [])
                self.assertNotIn('lim:conditional-db:' + move_id + ':scene', self.a.counters)
                self.next_turn()
                self.choose(move_id)
                self.assertEqual(self.native_db(move_id, self.c, area_entry=True)[1], [boosted])
                record = MODES.history(self.a)[0]
                self.assertEqual(record['use']['target_ids'], [self.c.entity_id])
                self.assertEqual(record['use']['boundary'], 'activation')
                self.assertNotIn('lim:conditional-db:' + move_id + ':scene', self.a.counters)
                self.next_turn()
                self.assertEqual(self.native_db(move_id, self.b)[1], [normal])

    def test_ineligible_selected_activation_rejects_unchanged_then_can_use_real_affliction(self):
        for move_id, _, boosted in CASES:
            with self.subTest(move=move_id):
                self.make_world()
                self.choose(move_id)
                NATIVE.assert_rejected_unchanged(self.e,
                    lambda: self.e.use_move(self.a, self.b, move_id, set_damage=True),
                    reason_pattern='previously afflicted')
                self.assertIsNone(MODES.history(self.a)[0]['use'])
                self.afflict(self.b)
                self.assertEqual(self.native_db(move_id, self.b)[1], [boosted])

    def test_selected_miss_spends_only_that_explicit_activation_and_scene_refreshes(self):
        for move_id, normal, boosted in CASES:
            with self.subTest(move=move_id):
                self.make_world()
                self.afflict(self.b)
                self.choose(move_id)
                hp = self.b.hp
                self.assertEqual(self.native_db(move_id, self.b, face=1), (0, []))
                self.assertEqual(self.b.hp, hp)
                self.assertIsNotNone(MODES.history(self.a)[0]['use'])
                NATIVE.assert_rejected_unchanged(self.e, lambda: self.choose(move_id),
                    reason_pattern='already selected')
                self.next_turn()
                self.assertEqual(self.native_db(move_id, self.b)[1], [normal])
                self.e.end_of_turn(self.a)
                self.e.end_scene(self.e.everyone)
                self.e.start_round(self.e.everyone)
                self.e.start_of_turn(self.a, initiative_count=30)
                self.choose(move_id)
                self.assertEqual(self.native_db(move_id, self.b)[1], [boosted])
                self.assertEqual([row['scene'] for row in MODES.history(self.a)], [0, 1])

    def test_native_seed_alone_cannot_qualify_either_selected_replacement(self):
        for move_id, _, boosted in CASES:
            with self.subTest(move=move_id):
                self.make_world()
                self.e.gm.set_move(self.a, 'move/씨뿌리기', reason='actual learned Leech Seed')
                with patch.object(Engine, 'd20', return_value=10):
                    self.e.use_move(self.a, self.b, 'move/씨뿌리기')
                self.assertIn('씨뿌리기', self.b.conditions)
                self.next_turn()
                self.choose(move_id)
                NATIVE.assert_rejected_unchanged(self.e,
                    lambda: self.e.use_move(self.a, self.b, move_id, set_damage=True),
                    reason_pattern='previously afflicted')
                self.assertIsNone(MODES.history(self.a)[0]['use'])
                self.afflict(self.b)
                self.assertEqual(self.native_db(move_id, self.b)[1], [boosted])

    def test_pending_and_used_choices_restore_with_independent_mandatory_hex(self):
        self.afflict(self.b, self.c)
        self.choose(BITTER)
        self.choose(MOULD)
        self.restore()
        self.assertEqual(self.native_db(BITTER, self.b)[1], [12])
        self.next_turn()
        self.assertEqual(self.native_db(HEX, self.b)[1], [13])
        self.assertIsNone(next(row for row in MODES.history(self.a) if row['move_id'] == MOULD)['use'])
        self.next_turn()
        self.restore()
        self.assertEqual(self.native_db(MOULD, self.c)[1], [13])
        self.next_turn()
        self.assertEqual(self.native_db(HEX, self.b)[1], [7])
        self.restore()
        self.assertTrue(all(row['use'] is not None for row in MODES.history(self.a)))

    def test_defense_wait_cold_restore_keeps_choice_db_and_single_native_payment(self):
        for move_id, _, boosted in CASES:
            with self.subTest(move=move_id):
                self.make_world()
                self.afflict(self.b)
                self.choose(move_id)
                self.e.watch_move_defense(self.b, [{'actor_id': self.reactor.entity_id,
                    'source': 'maneuver/원거리-가로채기'}], reason='actual ally defense declaration')
                hp = self.b.hp
                with patch.object(Engine, 'd20', return_value=10):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        self.e.use_move_on(self.a, self.b, move_id, self.e.everyone, set_damage=True)
                event = self.e._passive_pending
                self.assertEqual(self.b.hp, hp)
                self.assertEqual(self.a.move_uses[move_id], 1)
                self.assertEqual(self.a._action_history, ['standard'])
                choice = deepcopy(MODES.history(self.a)[0])
                self.assertEqual(choice['use']['boundary'], 'activation')
                rng = self.e.rng.getstate()
                self.restore()
                completion = next(iter(self.e._move_completions.values()))
                self.assertEqual(completion['move']['damage_base'], boosted)
                NATIVE.assert_rejected_unchanged(self.e, lambda: self.e.choose_move_defense(
                    event, self.reactor, use=True, options={'path': [(4, 4), (4, 2)],
                    'skill': '육상', 'mode': 'land', 'roll_options': {'fixed': [6, 6, 6]}},
                    reason='invalid noncontiguous path'), reason_pattern='continuous Intercept route')
                seen = []
                original = Engine.damage_base
                def observe(engine, actor, move, *args, **kwargs):
                    value = original(engine, actor, move, *args, **kwargs)
                    seen.append(value)
                    return value
                with patch.object(Engine, 'damage_base', observe):
                    self.e.choose_move_defense(event, self.reactor, use=False,
                        reason='decline actual intercept and continue the paid attack')
                self.assertEqual(seen, [boosted])
                self.assertLess(self.b.hp, hp)
                self.assertEqual(self.e.rng.getstate(), rng)
                self.assertEqual(self.a.move_uses[move_id], 1)
                self.assertEqual(self.a._action_history, ['standard'])
                self.assertEqual(MODES.history(self.a)[0], choice)
                self.restore()


if __name__ == '__main__':
    unittest.main()
