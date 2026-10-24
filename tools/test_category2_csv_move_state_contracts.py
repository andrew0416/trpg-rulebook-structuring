"""Direct contracts for reviewed CSV Move state groups."""
from pathlib import Path
from unittest.mock import patch
import os
import json
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve()
STAGE = HERE.parents[1]
ROOT = Path(os.environ.get("PTK_EXPERIMENT_ROOT") or
            (STAGE if (STAGE / "output").exists() else Path(os.environ["PTK_EXPERIMENT_ROOT"])))
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
from report_category2_progress import collect as collect_category2


class CsvMoveStateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.by_eng = {}
        for move in cls.r.moves.values():
            cls.by_eng.setdefault(move.get("eng"), []).append(move["id"])
        cls.fury = cls.by_eng["Fury Cutter"][0]
        cls.butterfly = cls.by_eng["Butterfly Knife*"][0]
        cls.hex = cls.by_eng["Hex"][0]
        cls.mould = cls.by_eng["Mould*"][0]
        cls.bitter = cls.by_eng["Bitter Malice"][0]
        cls.tackle = cls.by_eng["Tackle [SM]"][0]

    def add(self, name, side, pos, moves=()):
        spec = build_trainer(self.r, name, 30,
            {key: 30 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            moves=list(moves), pos=pos, side=side, extra={"abilities": []})
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        from copy import deepcopy
        original = self.r.rulings
        self.r.rulings = deepcopy(original)
        self.addCleanup(setattr, self.r, 'rulings', original)
        self.e = Engine(self.r, seed=244)
        self.e.grid = Grid(12, 12)
        moves = (self.fury, self.butterfly, self.hex, self.mould, self.bitter, self.tackle)
        self.a = self.add("csv move user", "party", (2, 2), moves)
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

    def use_damage_move(self, move_id, target, *, hit=True, amount=5):
        observed = []

        def damage(attacker, actual_target, move, *args, **kwargs):
            observed.append(self.e.damage_base(attacker, move, target=actual_target))
            return amount

        with patch.object(self.e, "d20", return_value=10 if hit else 1), \
             patch.object(self.e, "roll_damage", side_effect=damage):
            dealt = self.e.use_move(self.a, target, move_id)
        return dealt, observed

    def test_same_target_damage_streak_is_shared_by_fury_cutter_and_butterfly_knife(self):
        for move_id in (self.fury, self.butterfly):
            values = []
            for _ in range(4):
                dealt, observed = self.use_damage_move(move_id, self.b)
                self.assertGreater(dealt, 0)
                values.extend(observed)
                self.next_turn()
            self.assertEqual(values, [4, 8, 12, 16])
            self.setUp()

    def test_streak_resets_on_miss_no_damage_target_change_and_different_move(self):
        self.use_damage_move(self.fury, self.b)
        self.next_turn()
        _, observed = self.use_damage_move(self.fury, self.b, hit=False)
        self.assertEqual(observed, [])
        self.next_turn()
        self.assertEqual(self.use_damage_move(self.fury, self.b)[1], [4])
        self.next_turn()
        self.use_damage_move(self.fury, self.b, amount=0)
        self.next_turn()
        self.assertEqual(self.use_damage_move(self.fury, self.b)[1], [4])
        self.next_turn()
        self.assertEqual(self.use_damage_move(self.fury, self.c)[1], [4])
        self.next_turn()
        self.use_damage_move(self.tackle, self.b)
        self.next_turn()
        self.assertEqual(self.use_damage_move(self.fury, self.c)[1], [4])

    def test_hex_and_mould_share_affliction_predicate_but_keep_scene_limits_separate(self):
        self.e.rulings.add_answer('hex_damage_boost',True,reason='actual optional Hex selection',scope='permanent')
        self.e.apply_status(self.b, "화상", source="move/도깨비불", applied_by=self.a)
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.hex), target=self.b), 13)
        self.assertEqual(self.use_damage_move(self.hex, self.b)[1], [13])
        self.next_turn()
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.hex), target=self.b), 7)
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.mould), target=self.b), 7)
        self.e.gm.choose_optional_move_effect(self.a, self.mould, reason="choose the independent Mould boost")
        self.assertEqual(self.use_damage_move(self.mould, self.b)[1], [13])
        self.next_turn()
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.mould), target=self.b), 7)

    def test_unafflicted_target_does_not_spend_scene_replacement_and_scene_end_restores_it(self):
        self.e.rulings.add_answer('hex_damage_boost',True,reason='actual optional Hex selection',scope='permanent')
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.hex), target=self.b), 7)
        self.assertEqual(self.use_damage_move(self.hex, self.b)[1], [7])
        self.next_turn()
        self.use_damage_move(self.tackle, self.b)
        self.next_turn()
        self.e.apply_status(self.b, "화상", source="move/도깨비불", applied_by=self.a)
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.hex), target=self.b), 13)
        self.assertEqual(self.use_damage_move(self.hex, self.b)[1], [13])
        self.e.end_of_turn(self.a)
        self.e.end_scene([self.a, self.b, self.c])
        self.assertEqual(self.e.damage_base(self.a, self.r.move(self.hex), target=self.b), 13)

    def test_bitter_malice_uses_the_shared_scene_db_and_target_turn_status_lifetime(self):
        self.e.apply_status(self.b, "화상", source="move/도깨비불", applied_by=self.a)
        self.e.gm.choose_optional_move_effect(self.a, self.bitter, reason="choose the Bitter Malice boost")
        observed = []

        def damage(attacker, actual_target, move, *args, **kwargs):
            observed.append(self.e.damage_base(attacker, move, target=actual_target))
            return 5

        with patch.object(self.e, "d20", return_value=19), \
             patch.object(self.e, "roll_damage", side_effect=damage):
            self.e.use_move(self.a, self.b, self.bitter)
        self.assertEqual(observed, [12])
        self.assertTrue({"구속", "수렁"}.issubset(self.b.conditions))
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.e.end_of_turn(self.b)
        self.assertFalse({"구속", "수렁"}.intersection(self.b.conditions))

    def test_report_collect_adds_exactly_five_denominator_completions(self):
        before = collect_category2(ROOT)
        self.assertTrue(before["denominator_frozen"])
        self.assertEqual(before["denominator"], 2352)
        selected = {self.fury, self.butterfly, self.bitter, self.hex, self.mould}
        with tempfile.TemporaryDirectory(prefix="csv-move-state-report-", dir=STAGE) as tmp:
            shadow = Path(tmp)
            for tree in ("input", "data/verification"):
                for source in (ROOT / tree).rglob("*"):
                    if not source.is_file():
                        continue
                    target = shadow / source.relative_to(ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.link(source, target)
                    except OSError:
                        target.write_bytes(source.read_bytes())
            registry_path = shadow / "data/verification/category2-csv-abilities-moves-status.json"
            registry_path.unlink()
            registry = json.loads((ROOT / "data/verification/category2-csv-abilities-moves-status.json").read_text(encoding="utf-8"))
            found = set()
            for row in registry["rows"]:
                if row.get("extracted_entity_id") in selected and row.get("row_id") in {
                        "C2CSV-MOVE-R0009", "C2CSV-MOVE-R0301", "C2CSV-MOVE-R0306",
                        "C2CSV-MOVE-R1057", "C2CSV-MOVE-R1064"}:
                    self.assertTrue(row["category2_included"])
                    self.assertEqual(row["denominator_contribution"], 1)
                    self.assertEqual(row["category2_status"], "incomplete")
                    row["category2_status"] = "implemented"
                    found.add(row["row_id"])
            self.assertEqual(len(found), 5)
            registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            after = collect_category2(shadow)
        self.assertEqual(after["validation_errors"], [])
        self.assertTrue(after["denominator_frozen"])
        self.assertEqual(after["denominator"], before["denominator"])
        self.assertEqual(after["completed_clause_count"] - before["completed_clause_count"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
