"""Source-only class joins to reviewed native Astonish/Sand Attack owners."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_natural_fighter_native as BASE
from engine import Engine, Rules, Combatant
import action_points as AP
import book_survivalist_fixture as FIX
import combat_timing as TIME
import frequency as F
import natural_fighter as NF
import natural_fighter_moves as MOVES
import passive_events as PASSIVE
import state_grants as G
import survivalist_class as SC


class NaturalFighterClassRouteTests(unittest.TestCase):
    scene = BASE.NaturalFighterTests.scene
    cast = BASE.NaturalFighterTests.cast
    next_round = BASE.NaturalFighterTests.next_round
    snap = BASE.NaturalFighterTests.snap
    reject_unchanged = BASE.NaturalFighterTests.reject_unchanged

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.t, self.p, self.foe, self.actor = [index[a.entity_id] for a in
                                              (self.t, self.p, self.foe, self.actor)]

    def observe(self, unaware, *, target=None):
        key = MOVES.awareness_key(self.e, self.actor, target or self.foe)
        FIX.ruling(self.e, key, {'observation_key': key, 'unaware': unaware},
                   reason='GM observed this actual recipient before the class-granted attack')
        return key

    def cave_target(self):
        self.e.gm.set_types(self.foe, ['물'], reason='actual recipient without Ghost immunity')

    def test_new_routes_use_actual_trainer_or_owned_pokemon_and_pay_once(self):
        for role in ('trainer', 'partner'):
            for terrain in ('cave', 'desert'):
                with self.subTest(role=role, terrain=terrain):
                    self.scene(role, terrain)
                    if terrain == 'cave':
                        self.cave_target()
                        self.observe(True)
                    ap = AP.available(self.t)
                    owner_budget = deepcopy(getattr(self.t, 'budget', None))
                    learned = deepcopy(self.actor.spec.get('moves', []))
                    with patch.object(Engine, 'd20', return_value=14):
                        result = self.cast(terrain, target=self.foe)
                    mid = NF.MOVES[terrain]
                    self.assertEqual(result['move_id'], mid)
                    self.assertEqual(AP.available(self.t), ap - 1)
                    self.assertEqual(self.actor.budget['standard'], 0)
                    if role == 'partner':
                        self.assertEqual(getattr(self.t, 'budget', None), owner_budget)
                        self.assertNotIn(mid, self.t.move_uses)
                    self.assertEqual(self.actor.move_uses[mid], 1)
                    self.assertEqual(self.actor.spec.get('moves', []), learned)
                    self.assertNotIn(mid, self.actor.moves)
                    self.assertIsNone(NF.current(self.actor))
                    self.assertNotIn(result['activation_id'], self.actor.spec[G.KEY]['sources'])
                    self.assertEqual(self.e._move_completions[result['completion_id']]['phase'], 'complete')
                    self.assertIn('풀죽음' if terrain == 'cave' else '실명', self.foe.conditions)
                    self.restore()

    def test_class_sand_blindness_outlives_permission_until_target_next_turn_end(self):
        self.scene('partner', 'desert')
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=18):
            result = self.cast('desert', target=self.foe)
        self.assertNotIn(result['activation_id'], self.p.spec[G.KEY]['sources'])
        self.assertIn('실명', self.foe.conditions)
        self.restore()
        self.e.end_of_turn(self.p)
        self.assertIn('실명', self.foe.conditions)
        self.e.start_of_turn(self.foe, initiative_count=19)
        self.assertIn('실명', self.foe.conditions)
        self.e.end_of_turn(self.foe)
        self.assertNotIn('실명', self.foe.conditions)
        self.assertFalse([row for row in TIME.records(self.foe) if row['source'] == MOVES.SAND])
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.p.move_uses[MOVES.SAND], 1)

    def test_class_astonish_requires_typed_current_actual_target_observation_atomically(self):
        for kind in ('absent', 'wrong_target', 'stale', 'untyped'):
            with self.subTest(kind=kind):
                self.scene('partner', 'cave')
                self.cave_target()
                key = MOVES.awareness_key(self.e, self.actor, self.foe)
                self.e.rulings.answers = [row for row in self.e.rulings.answers if row['key'] != key]
                if kind == 'wrong_target':
                    self.observe(True, target=self.t)
                elif kind == 'stale':
                    FIX.ruling(self.e, key, {'observation_key': 'old-occurrence', 'unaware': True})
                elif kind == 'untyped':
                    FIX.ruling(self.e, key, True)
                self.reject_unchanged('presence-awareness', lambda: self.cast('cave', target=self.foe))
                self.assertNotIn(MOVES.ASTONISH, self.p.moves)
                self.assertIsNone(NF.current(self.p))

    def test_new_routes_still_require_acquired_feature_and_actual_pokemon_owner(self):
        for terrain in ('cave', 'desert'):
            with self.subTest(terrain=terrain):
                self.scene(terrain=terrain, feats=(SC.CLASS,))
                self.reject_unchanged('acquired source', lambda: self.cast(terrain, target=self.foe))
                self.scene(terrain=terrain)
                self.reject_unchanged('trainer-owned Pokemon',
                    lambda: self.cast(terrain, subject=self.foe, target=self.p))

    def test_class_sand_regrant_keeps_native_eot_cooldown_and_does_not_spend_ap(self):
        self.scene(terrain='desert')
        with patch.object(Engine, 'd20', return_value=18):
            self.cast('desert', target=self.foe)
        self.next_round()
        ap = AP.available(self.t)
        self.reject_unchanged('.', lambda: self.cast('desert', target=self.foe))
        self.assertEqual(AP.available(self.t), ap)
        self.assertEqual(self.t.move_uses[MOVES.SAND], 1)
        self.assertEqual(self.t.budget['standard'], 1)

    def test_class_astonish_uses_shared_auto_quota_but_pays_for_each_at_will_move(self):
        self.scene(terrain='cave')
        self.cave_target()
        self.observe(True)
        ap = AP.available(self.t)
        with patch.object(Engine, 'd20', return_value=14):
            self.cast('cave', target=self.foe)
        self.assertIn('풀죽음', self.foe.conditions)
        self.e.cure_status(self.foe, '풀죽음')
        self.restore()
        self.next_round()
        with patch.object(Engine, 'd20', return_value=14):
            self.cast('cave', target=self.foe)
        self.assertNotIn('풀죽음', self.foe.conditions)
        self.assertFalse(F.activation_allowed(self.t, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
        self.assertEqual(AP.available(self.t), ap - 2)
        self.assertEqual(self.t.move_uses[MOVES.ASTONISH], 2)
        self.assertEqual(len(self.t.spec[NF.KEY]), 2)
        self.assertIsNone(NF.current(self.t))

    def test_new_routes_restore_actual_defense_wait_without_repaying_owner_ap(self):
        for terrain in ('cave', 'desert'):
            with self.subTest(terrain=terrain):
                self.scene('partner', terrain)
                if terrain == 'cave':
                    self.cave_target()
                    self.observe(True)
                if terrain == 'cave':   # Astonish is Physical: Dodge applies
                    self.e.gm.set_ability(self.foe, '회피', reason='actual optional native Dodge')
                    source = 'ability/회피'
                else:                   # Sand Attack is a Status Move: only Detect watches it (move_defense_reactions.watch_interested)
                    self.e.gm.set_move(self.foe, 'move/판별', reason='actual optional Detect before this status Move')
                    source = 'move/판별'
                self.e.watch_move_defense(self.foe,
                    [{'actor_id': self.foe.entity_id, 'source': source}],
                    reason='actual defense of this class-granted Move')
                ap = AP.available(self.t)
                with patch.object(Engine, 'd20', return_value=14):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        self.cast(terrain, target=self.foe)
                event = self.e._passive_pending
                self.assertEqual(AP.available(self.t), ap - 1)
                identity = NF.current(self.p)['id']
                self.restore()
                costs = deepcopy((self.p.budget, self.p.move_uses))
                self.e.choose_move_defense(event, self.foe, use=False,
                                          reason='decline this actual pending native defense')
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual((self.p.budget, self.p.move_uses), costs)
                self.assertIn('풀죽음' if terrain == 'cave' else '실명', self.foe.conditions)
                self.assertNotIn(identity, self.p.spec[G.KEY]['sources'])
                self.assertIsNone(NF.current(self.p))
                self.restore()


    def test_redirected_low_roll_waits_before_damage_without_borrowing_original_awareness(self):
        self.scene(terrain='cave')
        self.cave_target()
        defender = Combatant(self.rules, FIX.trainer_spec(self.rules, 'actual defending trainer'))
        self.e.gm.add_combatant(defender, pos=(4, 3), side=self.foe.side,
                               reason='actual ally of the original target')
        self.e.gm.set_types(defender, ['물'], reason='actual interceptor without Ghost immunity')
        self.next_round()
        self.observe(True)
        self.e.watch_move_defense(self.foe,
            [{'actor_id': defender.entity_id, 'source': 'maneuver/근접-가로채기'}],
            reason='actual optional Intercept of Astonish')
        ap, hp = AP.available(self.t), defender.hp
        with patch.object(Engine, 'd20', return_value=14):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                self.cast('cave', target=self.foe)
        event = self.e._passive_pending
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.choose_move_defense(event, defender, use=True,
                options={'path': [(4, 3), (3, 3)], 'skill': '육상', 'mode': 'land',
                         'shove_destination': [3, 4], 'roll_options': {'fixed': [6] * 4}},
                reason='actual successful Intercept to a different recipient')
        self.assertEqual(self.e._passive_pending, event)
        self.assertEqual(self.e._passive_events[event]['reason'], MOVES.AWARENESS_WAIT)
        self.assertEqual(defender.hp, hp)
        self.assertNotIn('풀죽음', defender.conditions)
        self.assertTrue(F.activation_allowed(self.t, MOVES.QUOTA, MOVES.ONCE, engine=self.e))
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.move_uses[MOVES.ASTONISH], 1)
        self.assertEqual(NF.current(self.t)['phase'], 'waiting')
        self.restore()
        self.assertEqual(NF.current(self.t)['phase'], 'waiting')

if __name__ == '__main__':
    unittest.main()


