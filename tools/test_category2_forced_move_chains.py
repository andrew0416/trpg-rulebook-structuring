"""Direct contracts for Ice Ball and Rollout forced repeat chains."""
from pathlib import Path
from unittest.mock import patch
import json
import os
import sys
import unittest


HERE = Path(__file__).resolve()
STAGE = HERE.parents[1]
ROOT = Path(os.environ.get("PTK_EXPERIMENT_ROOT") or
            (STAGE if (STAGE / "data").exists() else Path(os.environ["PTK_EXPERIMENT_ROOT"])))
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
import forced_move_lock as FORCED_MOVE


class ForcedMoveChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.by_eng = {move.get("eng"): move["id"] for move in cls.r.moves.values()}
        cls.ice_ball = cls.by_eng["Ice Ball"]
        cls.rollout = cls.by_eng["Rollout"]
        cls.tackle = cls.by_eng["Tackle [SM]"]

    def add(self, name, side, pos, moves=()):
        spec = build_trainer(self.r, name, 30,
            {key: 30 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            moves=list(moves), pos=pos, side=side, extra={"abilities": []})
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        self.e = Engine(self.r, seed=421746)
        self.e.grid = Grid(12, 12)
        self.a = self.add("repeat user", "party", (2, 2),
                          (self.ice_ball, self.rollout, self.tackle))
        self.b = self.add("first target", "enemy", (3, 2))
        self.c = self.add("second target", "enemy", (3, 3))
        self.begin_turn()

    def begin_turn(self):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=30)

    def next_turn(self):
        self.e.end_of_turn(self.a)
        self.e.end_round()
        self.begin_turn()

    def use(self, move_id, target, *, hit=True, amount=5):
        bases = []

        def damage(engine, attacker, actual_target, move, *args, **kwargs):
            bases.append(engine.damage_base(attacker, move, target=actual_target))
            return amount

        if move_id == self.rollout:
            direction = 1 if self.a.pos[0] <= 7 else -1
            x,y = self.a.pos
            self.e.gm.set_position(target,(x+direction,y),reason='actual next Rollout recipient on the complete Pass route')
            other = self.c if target is self.b else self.b
            self.e.gm.set_position(other,(10,10),reason='actual other recipient outside this Pass route')
            self._pass_request = getattr(self,'_pass_request',0)+1
        with patch.object(Engine, "d20", return_value=10 if hit else 1), \
             patch.object(Engine, "roll_damage", autospec=True, side_effect=damage):
            if move_id == self.rollout:
                receipt = self.e.use_pass_move(self.a,move_id,(x+2*direction,y),
                    event_id='forced-chain-pass:'+str(self._pass_request),object_adjudications={},
                    source='gm/observed-object-hits',reason='actual complete repeat-chain Pass route')
                creatures = [row for row in receipt['results'] if row['kind']=='creature']
                self.assertEqual([row['id'] for row in creatures],[target.entity_id])
                self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0))
                result = sum(row['dealt'] for row in creatures)
            else:
                result = self.e.use_move(self.a, target, move_id)
        return result, bases

    def progression(self, move_id, expected):
        seen = []
        for index in range(len(expected)):
            result, bases = self.use(move_id, self.b if index % 2 == 0 else self.c)
            self.assertGreater(result, 0)
            seen.extend(bases)
            self.assertEqual(self.a.locked_move, move_id)
            if index + 1 < len(expected):
                self.next_turn()
        self.assertEqual(seen, expected)

    def test_both_moves_share_receipt_based_escalation_and_keep_their_values(self):
        self.progression(self.ice_ball, [3, 6, 9, 12, 15])
        self.setUp()
        self.progression(self.rollout, [3, 7, 11, 15, 15])

    def test_other_ordinary_move_is_rejected_before_budget_frequency_or_rng(self):
        self.use(self.ice_ball, self.b)
        self.next_turn()
        before_budget = dict(self.a.budget)
        before_uses = dict(self.a.move_uses)
        with patch.object(self.e, "d20") as accuracy, patch.object(self.e, "roll_damage") as damage:
            self.assertEqual(self.e.use_move(self.a, self.b, self.tackle), 0)
        accuracy.assert_not_called()
        damage.assert_not_called()
        self.assertEqual(self.a.budget, before_budget)
        self.assertEqual(self.a.move_uses, before_uses)
        self.assertEqual(self.a.locked_move, self.ice_ball)

    def test_actual_miss_releases_choice_and_resets_damage_chain(self):
        self.use(self.rollout, self.b)
        self.next_turn()
        result, bases = self.use(self.rollout, self.b, hit=False)
        self.assertEqual(result, 0)
        self.assertEqual(bases, [])
        self.assertIsNone(self.a.locked_move)
        self.assertIsNone(FORCED_MOVE.current(self.e, self.a))
        self.next_turn()
        self.assertEqual(self.use(self.rollout, self.c)[1], [3])

    def test_no_active_target_releases_at_use_move_on_before_spending(self):
        self.use(self.ice_ball, self.b)
        self.next_turn()
        self.b.on_field = False
        self.c.on_field = False
        before_budget = dict(self.a.budget)
        before_uses = dict(self.a.move_uses)
        self.assertEqual(self.e.use_move_on(
            self.a, self.a, self.ice_ball, self.e.everyone), 0)
        self.assertIsNone(self.a.locked_move)
        self.assertEqual(self.a.budget, before_budget)
        self.assertEqual(self.a.move_uses, before_uses)
        self.c.on_field = True
        self.assertGreater(self.use(self.tackle, self.c)[0], 0)

    def test_lock_and_escalation_survive_json_restore(self):
        self.use(self.ice_ball, self.b)
        self.e.end_of_turn(self.a)
        self.e.end_round()
        restored = Engine.import_state(
            self.r, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        self.e = restored
        self.a = next(actor for actor in restored.everyone if actor.name == "repeat user")
        self.b = next(actor for actor in restored.everyone if actor.name == "first target")
        self.c = next(actor for actor in restored.everyone if actor.name == "second target")
        self.begin_turn()
        self.assertEqual(FORCED_MOVE.current(self.e, self.a), self.ice_ball)
        self.assertEqual(self.use(self.ice_ball, self.c)[1], [6])


if __name__ == "__main__":
    unittest.main(verbosity=2)
