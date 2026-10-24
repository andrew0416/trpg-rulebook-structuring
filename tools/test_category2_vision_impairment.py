"""Direct contract checks for C07-165 Blindness."""
from pathlib import Path
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
CANON = STAGE
sys.path[:0] = [str(STAGE / "engine"), str(CANON / "engine")]

from engine import Combatant, Engine, Rules
import effects_ext as EXT
from grid import Grid
import survivalist_features as SURVIVALIST
import turn as TURN
import vision_impairment as VISION


STATS = dict(hp=30, atk=10, **{"def": 10}, spa=10, spd=10, spe=10)


def combatant(rules, identity, *, pos, capabilities=()):
    return Combatant(rules, {
        "id": "trainer/" + identity, "name": identity, "kind": "trainer",
        "size": "중형", "level": 20, "stats": dict(STATS),
        "skills": {"곡예": 4, "육상": 4, "집중": 3},
        "movement": {"land": 6}, "movement_basis": "current",
        "moves": ["move/몸통박치기"],
        "capabilities": list(capabilities), "pos": pos,
    })


class VisionImpairmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(CANON), ruleset="core")

    def fresh(self, *, grid=None, capabilities=()):
        engine = Engine(self.r, 719)
        actor = combatant(self.r, "vision-actor", pos=(0, 1), capabilities=capabilities)
        target = combatant(self.r, "vision-target", pos=(4, 1))
        actor.side = "players"; target.side = "enemies"
        engine.everyone = engine.gm.everyone = [actor, target]
        engine.grid = grid
        return engine, actor, target

    def accuracy_bonus(self, engine, actor, target):
        move = engine.r.move("move/몸통박치기")
        mech, _ = engine.r.move_mech(move["id"])
        return EXT.accuracy_hook(
            engine, actor, target, move, mech,
            {"attacker": actor, "target": target, "hit": True,
             "nat": 10, "engine": engine, "move": move})[2]

    def test_accuracy_has_one_blindness_contribution_and_sensory_precedence(self):
        engine, actor, target = self.fresh()
        self.assertTrue(engine.apply_status(
            actor, "실명", parameters={"cause": "external"}))
        self.assertEqual(self.accuracy_bonus(engine, actor, target), -6)

        engine.cure_status(actor, "실명")
        self.assertTrue(engine.apply_status(
            actor, "완전 실명", parameters={"cause": "darkness"}))
        self.assertEqual(self.accuracy_bonus(engine, actor, target), -10)
        self.assertNotEqual(self.accuracy_bonus(engine, actor, target), -16)

        protected, aware, destination = self.fresh(capabilities=("Blindsense",))
        self.assertFalse(protected.apply_status(
            aware, "실명", parameters={"cause": "external"}))
        self.assertEqual(self.accuracy_bonus(protected, aware, destination), 0)

    def test_observed_darkness_uses_the_same_accuracy_consumer_and_darkvision_exception(self):
        engine, actor, target = self.fresh()
        SURVIVALIST.observe_environment(
            engine, actor, terrains=["urban"], light="low_light",
            reason="observed dim warehouse")
        self.assertEqual(self.accuracy_bonus(engine, actor, target), -6)

        dark, aware, destination = self.fresh(capabilities=("Darkvision",))
        SURVIVALIST.observe_environment(
            dark, aware, terrains=["cave"], light="complete_darkness",
            reason="observed unlit cave")
        self.assertEqual(self.accuracy_bonus(dark, aware, destination), 0)
        self.assertEqual(VISION.accuracy_level(dark, aware), "none")

    def test_actual_rough_path_requires_dc10_and_failure_trips(self):
        engine, actor, target = self.fresh(grid=Grid(6, 1, rough={(1, 0)}))
        actor.pos = (0, 0); target.pos = (4, 0)
        actor.conditions.add("실명")
        TURN.reset_budget(engine, actor)
        options = {
            "movement_id": "blind-success", "frequency": "once_per_shift",
            "reason": "one continuous rough route",
            "check_options": [{"skill": "곡예", "fixed": [3, 3, 3, 3]}],
        }
        engine.approach(actor, target, blindness_options=options)
        self.assertEqual(actor.pos, (3, 0))
        self.assertNotIn("넘어짐", actor.conditions)
        self.assertEqual(actor.spec["_survivalist_shift"]["checks"][0]["result"].total, 12)

        failed, subject, destination = self.fresh(grid=Grid(6, 1, rough={(1, 0)}))
        subject.pos = (0, 0); destination.pos = (4, 0)
        subject.conditions.add("실명")
        TURN.reset_budget(failed, subject)
        options["movement_id"] = "blind-failure"
        options["check_options"] = [{"skill": "곡예", "fixed": [1, 1, 1, 1]}]
        failed.approach(subject, destination, blindness_options=options)
        self.assertEqual(subject.pos, (1, 0))
        self.assertIn("넘어짐", subject.conditions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
