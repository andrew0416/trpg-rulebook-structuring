"""Native Set-Up state, source-specific preparation and resumed resolution."""
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
from grid import Grid
import state_codec as CODEC

BLADE = 'move/솔라블레이드'
BEAM = 'move/솔라빔'


class NativeSetupStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')

    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def fixture(self, role):
        self.e = Engine(self.r, seed=363)
        self.e.grid = Grid(10, 10)
        stats = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20)
        owner = self.add(build_trainer(
            self.r, 'setup owner', 20, stats,
            extra={'moves': [BLADE, BEAM], 'side': 'party', 'pos': (2, 2)}))
        self.a = owner
        if role == 'pokemon':
            owner.pos = (0, 0)
            self.a = self.add(build_pokemon(
                self.r, '이브이', 20, moves=[BLADE, BEAM], abilities=[],
                extra={'trainer_id': owner.entity_id, 'side': 'party', 'pos': (2, 2)}))
            self.e.gm.observe_loyalty(self.a, 6, reason='actual current owner')
        self.b = self.add(build_trainer(
            self.r, 'setup target', 50,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 40),
            extra={'moves': [], 'side': 'opponent', 'pos': (3, 2)}))
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def state(self):
        return deepcopy((self.a.setup_move, self.a.stages, self.a.budget,
                         self.a.move_uses, self.a.last_move, self.b.hp,
                         self.e.rng.getstate()))

    def next_turn(self):
        self.e.end_of_turn(self.a)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def test_actual_blade_preparation_survives_both_restores_and_resolves_once(self):
        for role in ('trainer', 'pokemon'):
            for restoration in ('gm', 'json'):
                with self.subTest(role=role, restoration=restoration):
                    self.fixture(role)
                    hp = self.b.hp
                    stages = deepcopy(self.a.stages)
                    rng = self.e.rng.getstate()
                    with patch.object(self.e, 'd20', return_value=10) as roll:
                        self.assertEqual(self.e.use_move(self.a, self.b, BLADE), 0)
                    roll.assert_not_called()
                    self.assertEqual(self.e.rng.getstate(), rng)
                    self.assertEqual(self.a.setup_move, BLADE)
                    self.assertEqual(self.a.stages['atk'], stages['atk'] + 1)
                    self.assertEqual(self.a.stages['spd'], stages['spd'] + 1)
                    self.assertEqual(self.b.hp, hp)
                    self.assertEqual(self.a.move_uses, {})
                    self.assertIsNone(self.a.last_move)
                    self.assertEqual(self.a.budget['standard'], 0)
                    prepared = self.state()
                    with patch.object(self.e, 'd20', return_value=10) as roll:
                        self.assertEqual(self.e.use_move(self.a, self.b, BLADE), 0)
                    roll.assert_not_called()
                    self.assertEqual(self.state(), prepared)
                    if restoration == 'gm':
                        self.e.gm.snapshot('actual setup')
                        self.a.setup_move = None
                        self.a.stages['atk'] = -2
                        self.e.gm.restore('actual setup')
                    else:
                        aid, bid = self.a.entity_id, self.b.entity_id
                        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(
                            CODEC.dump_engine(self.e), ensure_ascii=False)))
                        by_id = {c.entity_id: c for c in self.e.everyone}
                        self.a, self.b = by_id[aid], by_id[bid]
                    self.assertEqual(self.state(), prepared)
                    self.next_turn()
                    with patch.object(self.e, 'd20', return_value=10) as roll:
                        self.e.use_move_on(self.a, self.b, BLADE, self.e.everyone)
                    roll.assert_called_once()
                    self.assertLess(self.b.hp, hp)
                    self.assertIsNone(self.a.setup_move)
                    self.assertEqual(self.a.move_uses[BLADE], 1)
                    self.assertEqual(self.a.last_move, BLADE)
                    self.assertEqual(self.a.stages['atk'], stages['atk'] + 1)
                    self.assertEqual(self.a.stages['spd'], stages['spd'] + 1)

    def test_actual_beam_miss_clears_setup_and_the_next_use_prepares_again(self):
        for role in ('trainer', 'pokemon'):
            with self.subTest(role=role):
                self.fixture(role)
                hp = self.b.hp
                self.assertEqual(self.e.use_move(self.a, self.b, BEAM), 0)
                self.assertEqual(self.a.setup_move, BEAM)
                self.assertEqual(self.a.move_uses, {})
                self.next_turn()
                with patch.object(self.e, 'd20', return_value=1) as roll:
                    self.assertEqual(self.e.use_move(self.a, self.b, BEAM), 0)
                roll.assert_called_once()
                self.assertIsNone(self.a.setup_move)
                self.assertEqual(self.a.move_uses[BEAM], 1)
                self.assertEqual(self.b.hp, hp)
                self.next_turn()
                # Scene moves retain their existing ban on consecutive uses.
                before = self.state()
                with patch.object(self.e, 'd20', return_value=10) as roll:
                    self.assertEqual(self.e.use_move(self.a, self.b, BEAM), 0)
                roll.assert_not_called()
                self.assertEqual(self.state(), before)
                self.next_turn()
                with patch.object(self.e, 'd20', return_value=10) as roll:
                    self.assertEqual(self.e.use_move(self.a, self.b, BEAM), 0)
                roll.assert_not_called()
                self.assertEqual(self.a.setup_move, BEAM)
                self.assertEqual(self.a.move_uses[BEAM], 1)
                self.next_turn()
                with patch.object(self.e, 'd20', return_value=10) as roll:
                    self.assertGreater(self.e.use_move(self.a, self.b, BEAM), 0)
                roll.assert_called_once()
                self.assertIsNone(self.a.setup_move)
                self.assertEqual(self.a.move_uses[BEAM], 2)
                self.next_turn()
                before = self.state()
                with patch.object(self.e, 'd20', return_value=10) as roll:
                    self.assertEqual(self.e.use_move(self.a, self.b, BEAM), 0)
                roll.assert_not_called()
                self.assertEqual(self.state(), before)

    def test_actual_sunny_exception_resolves_without_granting_preparation_stages(self):
        for role in ('trainer', 'pokemon'):
            for move in (BLADE, BEAM):
                with self.subTest(role=role, move=move):
                    self.fixture(role)
                    self.e.gm.set_weather('sunny', rounds=3)
                    stages, hp = deepcopy(self.a.stages), self.b.hp
                    with patch.object(self.e, 'd20', return_value=10) as roll:
                        self.assertGreater(self.e.use_move(self.a, self.b, move), 0)
                    roll.assert_called_once()
                    self.assertIsNone(self.a.setup_move)
                    self.assertEqual(self.a.stages, stages)
                    self.assertEqual(self.a.move_uses[move], 1)
                    self.assertLess(self.b.hp, hp)


if __name__ == '__main__':
    unittest.main()

