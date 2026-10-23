"""Owned Steel secondary-effect bonuses reuse feature registration and real attacks."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import combat_precision_features as PRECISION
import items as ITEMS
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD

SOURCE = 'feat/윤기나는-광택'
MOVES = ['아이언헤드', '코멧펀치', '전기쇼크']


class PolishedShineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='all')

    def setUp(self):
        self.encounter()

    def encounter(self, source=SOURCE):
        self.e = Engine(self.r, seed=1405)
        def trainer(name, feats=()):
            return Combatant(self.r, build_trainer(
                self.r, name, 30, {'hp': 80, 'atk': 20, 'def': 10, 'spa': 20, 'spd': 10, 'spe': 20},
                moves=MOVES, abilities=[], extra={'feats': list(feats)}))
        self.a = trainer('Actual acquired feature owner', [source])
        self.b = trainer('Actual other owner')
        self.t = trainer('Actual target')
        self.p = Combatant(self.r, build_pokemon(
            self.r, '브케인', 50, moves=MOVES, abilities=[],
            extra={'trainer_id': self.a.entity_id}))
        self.foreign = Combatant(self.r, build_pokemon(
            self.r, '브케인', 50, moves=MOVES, abilities=[],
            extra={'trainer_id': self.b.entity_id}))
        for actor, pos in ((self.a, (1, 2)), (self.b, (4, 0)), (self.t, (2, 2)),
                           (self.p, (2, 1)), (self.foreign, (3, 2))):
            self.e.gm.add_combatant(actor, pos=pos,
                side='wild' if actor is self.t else 'party', reason='actual acquired sheet and ownership')
        for actor in (self.p, self.foreign):
            self.e.gm.observe_loyalty(actor, 6, reason='actual owned attacker loyalty observed')
        self.e.register_abilities(self.a)

    def key(self):
        return 'feature:' + self.a.entity_id + ':' + SOURCE

    def attack(self, actor, move, face):
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor, initiative_count=20)
        hp = self.t.hp
        with patch.object(self.e, 'd20', return_value=face):
            self.e.use_move(actor, self.t, 'move/' + move, set_damage=True)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(actor.move_uses['move/' + move], 1)
        return hp - self.t.hp

    def bonus(self, actor, move='아이언헤드'):
        return PRECISION.effect_range_bonus(actor, self.r.move('move/' + move))

    def test_default_registration_is_owned_once_and_scoped_to_steel_moves(self):
        self.assertNotIn('trainer', self.p.spec)
        self.assertEqual((self.bonus(self.a), self.bonus(self.p), self.bonus(self.foreign)), (0, 2, 0))
        self.assertEqual(self.bonus(self.p, '전기쇼크'), 0)
        self.assertNotIn('강철', self.p.types)
        self.assertIn(self.key(), GRANTS.state(self.p)['sources'])
        before = deepcopy([(actor.spec, actor.modifiers, actor.stats, actor.conditions, actor.hp)
                           for actor in self.e.everyone])
        self.e.register_abilities(self.a)
        self.e.register_abilities(self.a)
        self.assertEqual(before, [(actor.spec, actor.modifiers, actor.stats, actor.conditions, actor.hp)
                                  for actor in self.e.everyone])

    def test_actual_target_condition_uses_expanded_threshold_only_for_owned_pokemon(self):
        for role, face, expected in (('p', 12, False), ('p', 13, True),
                                     ('a', 13, False), ('foreign', 13, False), ('foreign', 15, True)):
            with self.subTest(role=role, face=face):
                self.setUp()
                self.assertGreater(self.attack(getattr(self, role), '아이언헤드', face), 0)
                self.assertEqual('풀죽음' in self.t.conditions, expected)

    def test_actual_self_stage_branch_and_other_type_keep_distinct_thresholds(self):
        for move, face, expected in (('코멧펀치', 12, False), ('코멧펀치', 13, True),
                                      ('전기쇼크', 15, False), ('전기쇼크', 17, True)):
            with self.subTest(move=move, face=face):
                self.setUp()
                self.assertGreater(self.attack(self.p, move, face), 0)
                observed = self.p.stages['atk'] == 1 if move == '코멧펀치' else '마비' in self.t.conditions
                self.assertEqual(observed, expected)

    def test_actual_miss_accuracy_and_critical_use_the_original_face(self):
        move = self.r.move('move/아이언헤드')
        self.assertEqual(PRECISION.effect_natural(self.e, self.p, move, 18), 20)
        self.assertEqual(self.e.accuracy_check(self.p, self.t, move, fixed_roll=18), (True, 18, False))
        self.assertEqual(self.e.accuracy_check(self.p, self.t, move, fixed_roll=1), (False, 1, False))
        self.assertEqual(self.attack(self.p, '아이언헤드', 1), 0)
        self.assertNotIn('풀죽음', self.t.conditions)
        self.assertIsNone(PRECISION.effect_natural(self.e, self.p, move, None))

    def test_both_restores_and_source_withdrawal_keep_independent_contribution(self):
        GRANTS.apply_owned(self.e, self.p, 'fixture:independent-effect-range',
            lambda: self.p.modifiers.append({'type': 'effect_range_mod', 'value': 1}))
        self.assertEqual(self.bonus(self.p), 3)
        snapshot = self.e.gm.snapshot()
        self.e.gm.restore(snapshot)
        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        index = WORLD.actor_index(self.e)
        self.a, self.p, self.t, self.foreign = [index[x.entity_id] for x in (self.a, self.p, self.t, self.foreign)]
        self.e.register_abilities(self.a)
        self.assertEqual(self.bonus(self.p), 3)
        self.assertEqual(self.bonus(self.p, '전기쇼크'), 1)
        key = self.key()
        def withdraw(engine, owner, pokemon):
            owner.spec['feats'].remove(SOURCE)
            GRANTS.revoke(pokemon, key, engine=engine)
        GRANTS.transition(self.e, self.a, withdraw, participants=(self.p,))
        self.assertEqual(self.bonus(self.p), 1)
        self.assertIn('fixture:independent-effect-range', GRANTS.state(self.p)['effects'])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_ownership_loss_retracts_only_the_old_trainer_contribution(self):
        GRANTS.revoke_owner(self.e, self.p, self.a.entity_id, 'actual ownership ends')
        self.p.spec['trainer_id'] = self.b.entity_id
        ITEMS.register_feats(self.e, self.a, pokemon=[self.p, self.foreign])
        self.assertEqual(self.bonus(self.p), 0)
        self.assertNotIn(self.key(), GRANTS.state(self.p)['sources'])

    def test_unreviewed_move_filters_remain_pending_and_do_not_become_global_effect_ranges(self):
        for source in ('feat/빛나는-화염', 'feat/불타는-낙인'):
            with self.subTest(source=source):
                self.encounter(source)
                self.assertGreater(self.attack(self.a, '전기쇼크', 14), 0)
                self.assertNotIn('마비', self.t.conditions)
                self.assertEqual(self.bonus(self.a, '전기쇼크'), 0)
                pending = [effect for effect in self.a.registry if effect.get('type') == 'effect_range_mod']
                self.assertEqual(len(pending), 1)
                self.assertTrue(pending[0]['moves'])
                self.assertFalse(any(effect.get('type') == 'effect_range_mod' for effect in self.a.modifiers))

    def test_legacy_unsupported_effect_record_does_not_modify_actual_attacks_after_restore(self):
        GRANTS.apply_owned(self.e, self.a, 'fixture:legacy-scoped-effect-range',
            lambda: self.a.modifiers.append({'type': 'effect_range_mod', 'value': 3,
                'moves': '불꽃 moves that already burn'}))
        snapshot = self.e.gm.snapshot()
        self.e.gm.restore(snapshot)
        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        index = WORLD.actor_index(self.e)
        self.a, self.t = [index[x.entity_id] for x in (self.a, self.t)]
        self.assertGreater(self.attack(self.a, '전기쇼크', 14), 0)
        self.assertNotIn('마비', self.t.conditions)
        self.assertEqual(self.bonus(self.a, '전기쇼크'), 0)


if __name__ == '__main__':
    unittest.main()
