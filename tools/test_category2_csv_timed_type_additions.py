"""Direct contracts for the four CSV five-turn additive-type Moves."""
from pathlib import Path
from unittest.mock import patch
import builtins
import json
import os
import tempfile
import unittest


HERE = Path(__file__).resolve()
STAGE = HERE.parents[1]
ROOT = Path(os.environ["PTK_EXPERIMENT_ROOT"])
sys_path = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]
import sys
sys.path[:0] = sys_path

from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
from report_category2_progress import collect as collect_category2


ROWS = {
    "C2CSV-MOVE-R0326": ("move/핼러윈", "고스트", "노말"),
    "C2CSV-MOVE-R0338": ("move/숲의저주", "풀", "불꽃"),
    "C2CSV-MOVE-R0694": ("move/마법가루", "에스퍼", "악"),
    "C2CSV-MOVE-R0817": ("move/물붓기", "물", "전기"),
}


class CsvTimedTypeAdditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        canonical_reviewed = (ROOT / "data/moves-reviewed.json").resolve()
        stage_reviewed = STAGE / "data/moves-reviewed.json"
        original_open = builtins.open

        def overlay_open(file, *args, **kwargs):
            try:
                actual = Path(file).resolve()
            except (TypeError, OSError):
                actual = None
            if actual == canonical_reviewed:
                file = stage_reviewed
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=overlay_open):
            cls.r = Rules(str(ROOT), ruleset="all")

    def add(self, name, side, pos, *, moves=(), types=()):
        spec = build_trainer(
            self.r,
            name,
            30,
            {key: 30 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            moves=list(moves),
            pos=pos,
            side=side,
            extra={"abilities": [], "types": list(types)},
        )
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def setUp(self):
        self.e = Engine(self.r, seed=2442)
        self.e.grid = Grid(12, 12)

    def begin_round_and_turn(self, actor, participants):
        self.e.start_round(participants)
        self.e.start_of_turn(actor, initiative_count=30)

    def finish_round(self, user, target):
        self.e.end_of_turn(user)
        self.e.start_of_turn(target, initiative_count=20)
        self.e.end_of_turn(target)
        self.e.end_round()

    def advance_round(self, user, target):
        self.begin_round_and_turn(user, [user, target])
        self.finish_round(user, target)

    def test_all_four_rows_share_one_reviewed_five_target_turn_contract(self):
        reviewed = json.loads((STAGE / "data/moves-reviewed.json").read_text(encoding="utf-8"))["moves"]
        expected_until = {"event": "turn_end", "owner": "target", "after": 5}
        for clause_id, (move_id, added_type, _) in ROWS.items():
            with self.subTest(clause_id=clause_id):
                self.assertEqual(
                    reviewed[move_id],
                    {
                        "effects": [{
                            "type": "type_change",
                            "add_type": added_type,
                            "target": "target",
                            "until": expected_until,
                        }],
                        "type_lifetime_ready": True,
                        "note": "CSV source row: add the declared type alongside existing types for exactly five actual target turns; the target fifth turn_end revokes only this source-owned contribution.",
                        "reviewer": "category2 csv timed type-addition batch",
                    },
                )
                mechanics, confidence = self.r.move_mech(move_id)
                self.assertEqual(confidence, "reviewed")
                self.assertEqual(mechanics["effects_exec"], reviewed[move_id]["effects"])

    def test_actual_hit_adds_type_changes_native_matchup_and_expires_on_fifth_target_turn(self):
        for clause_id, (move_id, added_type, attack_type) in ROWS.items():
            with self.subTest(clause_id=clause_id):
                self.setUp()
                user = self.add("type user", "party", (2, 2), moves=(move_id,), types=("노말",))
                target = self.add("type target", "enemy", (3, 2), types=("노말",))
                before = self.e.type_multiplier(attack_type, target)[0]
                self.assertEqual(before, 1.0)
                self.begin_round_and_turn(user, [user, target])
                with patch.object(self.e, "d20", return_value=10):
                    self.e.use_move(user, target, move_id)
                self.assertEqual(target.types, ["노말", added_type])
                self.assertEqual(self.e.type_multiplier(attack_type, target)[0], 0.0 if added_type == "고스트" else 1.5)
                self.finish_round(user, target)
                self.assertIn(added_type, target.types)
                for _ in range(3):
                    self.advance_round(user, target)
                    self.assertIn(added_type, target.types)
                self.advance_round(user, target)
                self.assertEqual(target.types, ["노말"])
                self.assertEqual(self.e.type_multiplier(attack_type, target)[0], 1.0)

    def test_miss_does_not_install_a_type_source_or_timing_record(self):
        move_id = ROWS["C2CSV-MOVE-R0326"][0]
        user = self.add("miss user", "party", (2, 2), moves=(move_id,), types=("노말",))
        target = self.add("miss target", "enemy", (3, 2), types=("노말",))
        self.begin_round_and_turn(user, [user, target])
        with patch.object(self.e, "d20", return_value=1):
            self.e.use_move(user, target, move_id)
        self.assertEqual(target.types, ["노말"])
        self.assertNotIn("type_sources", target.spec.get("state_grants", {}))
        self.assertEqual(target.custom_conditions.get("timed_effects", []), [])

    def test_independent_type_source_expiry_preserves_later_baseline_change(self):
        move_id, added_type, _ = ROWS["C2CSV-MOVE-R0338"]
        user = self.add("baseline user", "party", (2, 2), moves=(move_id,), types=("노말",))
        target = self.add("baseline target", "enemy", (3, 2), types=("노말",))
        self.begin_round_and_turn(user, [user, target])
        with patch.object(self.e, "d20", return_value=10):
            self.e.use_move(user, target, move_id)
        self.assertEqual(target.types, ["노말", added_type])
        import state_grants as grants
        target.spec["types"] = ["강철"]
        target._types = grants.prepare_type_baseline(target, ["강철"])
        grants.commit_type_baseline(target)
        self.assertEqual(target.types, ["강철", added_type])
        self.finish_round(user, target)
        for _ in range(4):
            self.advance_round(user, target)
        self.assertEqual(target.types, ["강철"])

    def test_report_collect_adds_exactly_four_denominator_completions(self):
        before = collect_category2(ROOT)
        self.assertTrue(before["denominator_frozen"])
        self.assertEqual(before["denominator"], 2352)
        selected = set(ROWS)
        with tempfile.TemporaryDirectory(prefix="csv-timed-type-report-", dir=STAGE) as tmp:
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
                if row.get("row_id") in selected:
                    self.assertTrue(row["category2_included"])
                    self.assertEqual(row["denominator_contribution"], 1)
                    self.assertEqual(row["category2_status"], "incomplete")
                    row["category2_status"] = "implemented"
                    found.add(row["row_id"])
            self.assertEqual(found, selected)
            registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            after = collect_category2(shadow)
        self.assertEqual(after["validation_errors"], [])
        self.assertEqual(after["denominator"], before["denominator"])
        self.assertEqual(after["completed_clause_count"] - before["completed_clause_count"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
