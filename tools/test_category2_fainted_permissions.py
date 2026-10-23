"""Fainted actors through native actions, actual abilities/features and both restores."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
import items as ITEMS
import state_codec as CODEC
import turn as TURN

SHIELD = '불굴의방패'
GIFT = 'feat/이벨타르의-메이저-기프트-박피사의-접촉'


class FaintedPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')

    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        self.e = Engine(self.r, seed=163)
        self.e.grid = Grid(12, 12)
        self.a = self.add(build_trainer(
            self.r, 'trainer', 10, dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            extra={'moves': ['move/몸통박치기'], 'feats': [GIFT], 'side': 'party', 'pos': (2, 2)}))
        self.p = self.add(build_pokemon(
            self.r, '이브이', 10, moves=['move/몸통박치기'], abilities=[],
            extra={'trainer_id': self.a.entity_id, 'side': 'party', 'pos': (2, 3)}))
        self.t = self.add(build_pokemon(
            self.r, '잉어킹', 10, moves=[], abilities=[],
            extra={'side': 'opponent', 'pos': (3, 2)}))
        self.e.gm.observe_loyalty(self.p, 6, reason='actual current trainer relationship')
        ITEMS.register_feats(self.e, self.a)
        for actor in (self.a, self.p):
            self.e.gm.set_ability(actor, '트레이스', True, reason='observed actual ability')
        self.e.gm.set_ability(self.t, SHIELD, True, reason='actual copy donor')

    def begin(self, actor):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor, initiative_count=20)

    def knock(self, actor, hp=0):
        self.e.lose_hp(actor, actor.hp - hp, source='actual observed HP loss')
        self.assertEqual(actor.hp, hp)
        self.assertTrue(actor.fainted)
        self.assertIn('기절', actor.conditions)

    def state(self, engine, actor, target):
        return deepcopy((actor.hp, actor.budget, actor.spec, actor.conditions,
                         actor.move_uses, actor.counters, target.hp, target.injuries,
                         engine.rng.getstate()))

    def test_native_zero_and_negative_hp_block_actions_move_and_common_check(self):
        for role in ('a', 'p'):
            for hp in (0, -1):
                with self.subTest(role=role, hp=hp):
                    self.setUp()
                    actor = getattr(self, role)
                    self.begin(actor)
                    self.knock(actor, hp)
                    before = self.state(self.e, actor, self.t)
                    for action in ('standard', 'shift', 'swift', 'free', 'full'):
                        self.assertFalse(TURN.spend(self.e, actor, action, 'fainted actor cannot act'))
                    with patch.object(self.e, 'd20', return_value=20) as roller:
                        self.assertEqual(self.e.use_move(actor, self.t, 'move/몸통박치기'), 0)
                    self.assertEqual(roller.call_count, 0)
                    with self.assertRaises(ValueError):
                        self.e.skill_check(actor, '육상', 10)
                    self.assertEqual(self.state(self.e, actor, self.t), before)

    def test_actual_trace_refusal_and_revival_after_native_gm_and_json_state(self):
        for role in ('a', 'p'):
            for restoration in ('native', 'gm', 'json'):
                with self.subTest(role=role, restoration=restoration):
                    self.setUp()
                    actor = getattr(self, role)
                    self.begin(actor)
                    self.knock(actor)
                    if restoration == 'gm':
                        self.e.gm.snapshot('fainted')
                        self.e.gm.revive(actor, 10, reason='temporary observed change')
                        self.e.gm.restore('fainted')
                    engine = self.e
                    if restoration == 'json':
                        import json
                        engine = CODEC.load_engine(self.r, json.loads(json.dumps(
                            CODEC.dump_engine(self.e), ensure_ascii=False)))
                    by_id = {c.entity_id: c for c in engine.gm.everyone}
                    actual, target = by_id[actor.entity_id], by_id[self.t.entity_id]
                    before = self.state(engine, actual, target)
                    with self.assertRaisesRegex(ValueError, 'actual active copying ability'):
                        engine.activate_ability(actual, '트레이스', target)
                    self.assertEqual(self.state(engine, actual, target), before)
                    engine.gm.revive(actual, 10, reason='explicit actual revival')
                    engine.gm.choose_ability_transition(
                        actual, target, 'ability/트레이스', ability=SHIELD,
                        reason='actual target and ability selection')
                    engine.activate_ability(actual, '트레이스', target)
                    self.assertIn(SHIELD, actual.abilities)
                    self.assertFalse(actual.fainted)

    def test_actual_owned_feature_cannot_activate_until_revival(self):
        self.begin(self.a)
        self.assertTrue(any(row.get('type') == 'feat_manual' and row.get('name') == GIFT
                            for row in self.a.registry))
        self.knock(self.a)
        before = self.state(self.e, self.a, self.t)
        self.assertEqual(self.e.manual_feat(self.a, GIFT, self.t), (0, 1))
        self.assertEqual(self.state(self.e, self.a, self.t), before)
        self.e.gm.revive(self.a, 10, reason='explicit actual revival')
        injuries = self.t.injuries
        self.assertEqual(self.e.manual_feat(self.a, GIFT, self.t), (1, 0))
        self.assertEqual(self.t.injuries, injuries + 1)

    def test_new_encounter_preserves_faint_injuries_and_actual_daily_resources(self):
        import frequency as F
        import downtime as D
        daily = 'move/회복지령'
        self.begin(self.a)
        # The fixture's manual activation is GM-admitted; this does not certify
        # the gift's separate acquisition prerequisites or automatic trigger.
        feature = next(row for row in self.a.registry
                       if row.get('type') == 'feat_manual' and row.get('name') == GIFT)
        frequency = feature['frequency']
        key = feature.get('usage_key', GIFT)
        self.assertEqual(F.parse(frequency), ('daily', 3))
        self.assertEqual(self.e.manual_feat(self.a, GIFT, self.t), (1, 0))
        for actor in (self.a, self.p):
            self.e.gm.set_move(actor, daily, True, reason='observed learned daily move')
            self.begin(actor)
            self.e.lose_hp(actor, actor.hp // 2, source='actual encounter damage')
            self.e.use_move(actor, actor, daily)
            self.assertEqual(actor.move_uses[daily], 1)
            self.knock(actor)
            self.assertGreater(actor.injuries, 0)
        saved = {actor.entity_id: (actor.hp, actor.injuries, actor.fainted,
                                  actor.move_uses[daily]) for actor in (self.a, self.p)}
        activation = deepcopy(F.state(self.a)['activations'][key])
        self.assertEqual(activation['used'], 1)
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=10)
        self.e.begin_encounter(self.e.everyone)
        self.begin(self.t)
        for actor in (self.a, self.p):
            self.assertEqual((actor.hp, actor.injuries, actor.fainted,
                              actor.move_uses[daily]), saved[actor.entity_id])
            self.assertIn('기절', actor.conditions)
            self.assertFalse(TURN.can_act(self.e, actor))
        self.assertEqual(F.state(self.a)['activations'][key], activation)
        for actor in (self.a, self.p):
            self.e.gm.revive(actor, 10, reason='explicit recovery after encounter')
            self.assertFalse(actor.fainted)
            self.assertEqual(actor.injuries, saved[actor.entity_id][1])
            self.assertEqual(actor.move_uses[daily], 1)
        self.begin(self.a)
        for _ in range(2):
            self.assertEqual(self.e.manual_feat(self.a, GIFT, self.t), (1, 0))
        injuries = self.t.injuries
        self.assertEqual(self.e.manual_feat(self.a, GIFT, self.t), (0, 1))
        self.assertEqual(self.t.injuries, injuries)
        self.assertEqual(F.state(self.a)['activations'][key]['used'], 3)
        D.new_day(self.a)
        self.assertTrue(F.activation_allowed(self.a, key, frequency, engine=self.e))
        self.assertEqual(self.a.move_uses[daily], 1)
        self.assertEqual(self.e.manual_feat(self.a, GIFT, self.t), (1, 0))
        self.assertEqual(F.state(self.a)['activations'][key]['used'], 1)

    def test_actual_dark_hit_automatic_ability_stops_after_lethal_hit(self):
        for role in ('a', 'p'):
            with self.subTest(role=role):
                self.setUp()
                actor = getattr(self, role)
                self.e.gm.set_ability(actor, '정의의마음 [Playtest]', True,
                                      reason='actual native dark-hit ability owner')
                self.assertTrue(any(row['spec'].get('event') == 'on_hit_received'
                                    and row['spec'].get('move_type') == '악'
                                    for row in actor.ability_triggers))
                attacker = self.add(build_trainer(
                    self.r, 'native dark attacker', 1,
                    dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 1),
                    extra={'moves': ['move/물기'], 'side': 'opponent', 'pos': (3, 3)}))
                self.begin(attacker)
                stage = actor.stages['spa']
                with patch.object(self.e, 'd20', return_value=10):
                    self.assertGreater(self.e.use_move(attacker, actor, 'move/물기'), 0)
                self.assertFalse(actor.fainted)
                self.assertEqual(actor.stages['spa'], stage + 1)
                self.begin(attacker)
                self.e.lose_hp(actor, actor.hp - 1, source='actual pre-hit HP loss')
                self.assertFalse(actor.fainted)
                stage = actor.stages['spa']
                with patch.object(self.e, 'd20', return_value=10):
                    self.assertGreater(self.e.use_move(attacker, actor, 'move/물기'), 0)
                self.assertTrue(actor.fainted)
                self.assertEqual(actor.stages['spa'], stage)


if __name__ == '__main__':
    unittest.main()

