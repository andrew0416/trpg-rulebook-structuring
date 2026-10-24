"""Direct producer/consumer/lifetime checks for the Exhaust keyword debt."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from state_codec import dump_engine, load_engine
from grid import Grid
import exhaust_moves as EXHAUST
import turn as TURN


class ExhaustActionDebtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.exhaust_ids = tuple(sorted(
            move["id"] for move in cls.r.moves.values()
            if "탈진" in move.get("keywords", ())))

    def fixture(self):
        engine = Engine(self.r, seed=316)
        engine.grid = Grid(16, 16)
        trainer = Combatant(self.r, build_trainer(self.r, "trainer", 20,
            {key: 20 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            skills={"명령": "숙련"}, abilities=[]))
        user = Combatant(self.r, build_pokemon(self.r, "보만다", 50,
            moves=["move/파괴광선", "struggle"], abilities=[],
            extra={"trainer_id": trainer.entity_id, "loyalty": 2}))
        target = Combatant(self.r, build_trainer(self.r, "target", 50,
            {key: 80 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            abilities=[]))
        for actor, side, pos in ((trainer, "party", (0, 0)),
                                 (user, "party", (1, 0)),
                                 (target, "enemy", (3, 0))):
            engine.gm.add_combatant(actor, side=side, pos=pos,
                                    reason="actual Exhaust test actor")
        actors = [trainer, user, target]
        engine.begin_encounter(actors)
        engine.start_round(actors)
        engine.start_of_turn(user)
        return engine, trainer, user, target

    @staticmethod
    def next_user_turn(engine, actors, user):
        engine.end_of_turn(user)
        engine.end_round()
        engine.start_round(actors)
        engine.start_of_turn(user)

    def test_keyword_catalog_and_actual_miss_schedule_one_source_owned_debt(self):
        expected = {
            "move/무한다이빔", "move/시간의포효", "move/스타어설트", "move/블라스트번",
            "move/하드플랜트", "move/기가임팩트", "move/파괴광선", "move/프리즘레이저",
            "move/암석포", "move/하이드로캐논",
        }
        self.assertEqual(set(self.exhaust_ids), expected)
        engine, _, user, target = self.fixture()
        with patch.object(engine, "d20", return_value=1):
            engine.use_move(user, target, "move/파괴광선")
        row = user.spec[EXHAUST.KEY]
        self.assertEqual(row, {"source": EXHAUST.SOURCE, "actor_id": user.entity_id,
            "move_id": "move/파괴광선", "issued_turn": 1, "due_turn": 2,
            "phase": "pending", "policy_variant": "korean_standard_swift",
            "source_choice": None, "debt": {"standard": 1, "swift": 1}})
        self.assertEqual(user.pending_action_loss, {"standard": 1, "swift": 1})
        self.assertEqual(user.move_uses["move/파괴광선"], 1)

    def test_next_actual_turn_pays_without_fake_actions_blocks_command_then_expires(self):
        engine, trainer, user, target = self.fixture()
        engine.use_move(user, target, "move/파괴광선")
        actors = [trainer, user, target]
        self.next_user_turn(engine, actors, user)
        self.assertEqual(user.budget, {"standard": 0, "shift": 1, "swift": 0})
        self.assertEqual(user._action_history, [])
        self.assertEqual(user.spec[EXHAUST.KEY]["phase"], "active")
        with self.assertRaisesRegex(ValueError, "Exhaust prevents"):
            engine.pokemon_activity(trainer, "command_move", pokemon=user,
                target=target, move_id="struggle")
        engine.end_of_turn(user)
        self.assertNotIn(EXHAUST.KEY, user.spec)
        engine.end_round(); engine.start_round(actors); engine.start_of_turn(user)
        submitted = engine.pokemon_activity(trainer, "command_move", pokemon=user,
            target=target, move_id="struggle")
        self.assertEqual(submitted["status"], "submitted")

    def test_prior_swift_consumption_fails_before_frequency_rng_or_debt(self):
        engine, _, user, target = self.fixture()
        self.assertTrue(TURN.spend(engine, user, "swift", "actual prior Swift"))
        before = (deepcopy(user.budget), deepcopy(user.move_uses), engine.rng.getstate(), target.hp)
        self.assertEqual(engine.use_move(user, target, "move/파괴광선"), 0)
        self.assertEqual(before, (user.budget, user.move_uses, engine.rng.getstate(), target.hp))
        self.assertIsNone(getattr(user, "pending_action_loss", None))
        self.assertNotIn(EXHAUST.KEY, user.spec)

    def test_existing_other_debt_rejects_before_move_cost(self):
        engine, _, user, target = self.fixture()
        user.pending_action_loss = {"standard": 1}
        before = (deepcopy(user.budget), deepcopy(user.move_uses), engine.rng.getstate(), target.hp)
        with self.assertRaisesRegex(ValueError, "overlap"):
            engine.use_move(user, target, "move/파괴광선")
        self.assertEqual(before, (user.budget, user.move_uses, engine.rng.getstate(), target.hp))
        self.assertEqual(user.pending_action_loss, {"standard": 1})

    def test_pending_and_active_debt_survive_json_restore_and_end_encounter_clears(self):
        engine, trainer, user, target = self.fixture()
        engine.use_move(user, target, "move/파괴광선")
        restored = load_engine(self.r, json.loads(json.dumps(dump_engine(engine), ensure_ascii=False)))
        index = {actor.entity_id: actor for actor in restored.everyone}
        trainer, user, target = (index[x.entity_id] for x in (trainer, user, target))
        actors = restored.everyone
        self.next_user_turn(restored, actors, user)
        again = load_engine(self.r, json.loads(json.dumps(dump_engine(restored), ensure_ascii=False)))
        index = {actor.entity_id: actor for actor in again.everyone}
        user = index[user.entity_id]
        self.assertEqual(user.spec[EXHAUST.KEY]["phase"], "active")
        self.assertEqual(user.budget, {"standard": 0, "shift": 1, "swift": 0})
        again.end_encounter(again.everyone)
        self.assertNotIn(EXHAUST.KEY, user.spec)
        self.assertIsNone(user.pending_action_loss)


if __name__ == "__main__":
    unittest.main(verbosity=2)
