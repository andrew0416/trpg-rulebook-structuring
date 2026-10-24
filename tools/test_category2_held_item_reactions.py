"""Direct native-path checks for reviewed held-item event reactions."""
from pathlib import Path
import json
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

# Seed staged replacements before engine.py promotes its canonical directory.
import held_item_reactions as REACTIONS
import items as ITEMS
import effect_lifetimes as LIFETIMES
from builder import build_pokemon
from engine import Combatant, Engine, Rules
import world_entities as WORLD


CLAUSES = {"C2CSV/inventory:128:10", "C2CSV/inventory:133:10"}


class HeldItemReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def fixture(self):
        engine = Engine(self.r, seed=128133)
        actor = Combatant(self.r, build_pokemon(
            self.r, "피카츄", 30, name="Actor",
            moves=["move/드래곤클로", "move/요정의바람"], abilities=["정전기"]
        ))
        target = Combatant(self.r, build_pokemon(
            self.r, "이상해씨", 30, name="Target",
            moves=["move/드래곤클로", "move/요정의바람"], abilities=["심록"], side="wild"
        ))
        engine.gm.add_combatant(actor)
        engine.gm.add_combatant(target)
        return engine, actor, target

    def equip(self, engine, actor, item_id, suffix):
        uid = "held-item-reaction/" + suffix
        WORLD.register_object(
            engine, uid, kind="item_instance", item_rule_id=item_id,
            owner_id=actor.entity_id, location={"kind": "unknown"},
            reason="actual reviewed held-item reaction fixture",
        )
        ITEMS.register_item(engine, actor, item_id, source_instance_id=uid, as_held=True)
        self.assertEqual(engine._physical_objects[uid]["equipped_by"], actor.entity_id)
        return uid

    def restored(self, engine):
        payload = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        return Engine.import_state(self.r, payload)

    def test_exact_source_provenance(self):
        policy = REACTIONS.policy(self.r)
        self.assertEqual({row["clause_id"] for row in policy["rows"].values()}, CLAUSES)
        status = json.loads((ROOT / "data/verification/category2-item-table-status.json").read_text(encoding="utf-8"))
        indexed = {row["clause_id"]: row for row in status["new_clauses"]}
        for row in policy["rows"].values():
            self.assertIn(indexed[row["clause_id"]]["status"], {"incomplete", "implemented"})
            self.assertEqual(indexed[row["clause_id"]]["source"][0]["raw_cells_sha256"], row["source_row_sha256"])

    def test_blunder_policy_actual_miss_once_scene_persists_unequip_restore_then_expires(self):
        engine, actor, target = self.fixture()
        self.equip(engine, actor, "item/허탕보험", "blunder")
        base = engine.initiative_value(actor).value
        self.assertIsNotNone(base)
        self.assertEqual(actor.initiative_bonus, 0, "registration must not apply the triggered bonus immediately")
        engine.start_round([actor, target])
        engine.start_of_turn(actor, initiative_count=20)
        engine.d20 = lambda: 1
        self.assertEqual(engine.use_move(actor, target, "move/드래곤클로"), 0)
        del engine.d20
        self.assertEqual(engine.initiative_value(actor).value, base + 10)
        self.assertEqual(len(actor.spec["held_item_reaction_history"]), 1)
        REACTIONS.after_accuracy(engine, actor, target, self.r.move("move/드래곤클로"), False, 1)
        self.assertEqual(len(actor.spec["held_item_reaction_history"]), 1)
        ITEMS.unregister_item(engine, actor, "item/허탕보험")
        self.assertEqual(engine.initiative_value(actor).value, base + 10)
        loaded = self.restored(engine)
        loaded_actor = next(c for c in loaded.everyone if c.entity_id == actor.entity_id)
        self.assertEqual(loaded.initiative_value(loaded_actor).value, base + 10)
        loaded.end_encounter()
        self.assertEqual(loaded.initiative_value(loaded_actor).value, base)

    def test_rocky_helmet_positive_damage_melee_only_and_restore(self):
        engine, attacker, holder = self.fixture()
        uid = self.equip(engine, holder, "item/울퉁불퉁멧", "helmet")
        engine.start_round([attacker, holder])
        engine.start_of_turn(attacker, initiative_count=20)
        engine.d20 = lambda: 20
        before = attacker.hp
        dealt = engine.use_move(attacker, holder, "move/드래곤클로", set_damage=True)
        del engine.d20
        self.assertGreater(dealt, 0)
        self.assertEqual(attacker.hp, before - engine.tick(attacker))
        self.assertEqual(holder.spec["held_item_reaction_history"][-1]["instance_id"], uid)
        loaded = self.restored(engine)
        loaded_holder = next(c for c in loaded.everyone if c.entity_id == holder.entity_id)
        loaded_attacker = next(c for c in loaded.everyone if c.entity_id == attacker.entity_id)
        hp = loaded_attacker.hp
        REACTIONS.after_hit(loaded, loaded_attacker, loaded_holder, self.r.move("move/요정의바람"), 1)
        REACTIONS.after_hit(loaded, loaded_attacker, loaded_holder, self.r.move("move/드래곤클로"), 0)
        self.assertEqual(loaded_attacker.hp, hp)
        ITEMS.unregister_item(loaded, loaded_holder, "item/울퉁불퉁멧")
        REACTIONS.after_hit(loaded, loaded_attacker, loaded_holder, self.r.move("move/드래곤클로"), 1)
        self.assertEqual(loaded_attacker.hp, hp)


if __name__ == "__main__":
    unittest.main()
