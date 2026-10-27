"""Reconcile ten optional weather clauses with their native runtime path."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
CANON = Path(os.environ.get("PTK_CANONICAL_ROOT", STAGE))
sys.path[:0] = [str(STAGE / "engine"), str(CANON / "engine"), str(CANON / "tools"), str(CANON)]

# Import the staged adapter before canonical fixtures adjust sys.path.
import homebrew_weather as H
import tools.test_category2_homebrew_weather as _base_module
import blessing_effects as B
import weather_blessings as WB


EXPECTED = {
    "move/싸라기눈": ("CHB-WEATHER-001", "CHB-WEATHER-003", "CHB-WEATHER-007", "CHB-WEATHER-008"),
    "move/비바라기": ("CHB-WEATHER-001", "CHB-WEATHER-010", "CHB-WEATHER-011"),
    "move/모래바람": ("CHB-WEATHER-001", "CHB-WEATHER-013", "CHB-WEATHER-014"),
    "move/쾌청": ("CHB-WEATHER-001", "CHB-WEATHER-016", "CHB-WEATHER-017"),
}
ALL_IDS = {clause_id for rows in EXPECTED.values() for clause_id in rows}


class Tests(unittest.TestCase):
    setUpClass = classmethod(_base_module.Tests.setUpClass.__func__)
    fixture = _base_module.Tests.fixture
    cast = _base_module.Tests.cast
    restored = _base_module.Tests.restored

    def test_exact_source_rows_and_runtime_clause_map_have_the_same_ten_ids(self):
        registry = json.loads((CANON / "data/verification/category2-optional-clause-status.json").read_text(encoding="utf-8"))
        rows = {row["clause_id"]: row for row in registry["rows"]}
        self.assertEqual(ALL_IDS, {
            "CHB-WEATHER-001", "CHB-WEATHER-003", "CHB-WEATHER-007", "CHB-WEATHER-008",
            "CHB-WEATHER-010", "CHB-WEATHER-011", "CHB-WEATHER-013", "CHB-WEATHER-014",
            "CHB-WEATHER-016", "CHB-WEATHER-017",
        })
        self.assertEqual(H.CLAUSE_IDS, EXPECTED)
        for clause_id in ALL_IDS:
            row = rows[clause_id]
            self.assertTrue(row["category2_in_scope"])
            self.assertIn(row["status"], ("incomplete", "implemented"))
            self.assertTrue(row["statement"].strip())
            self.assertEqual({source["file_sha256"] for source in row["source"]}, {H.SOURCE_SHA256})
            self.assertEqual({source["file"] for source in row["source"]}, {"input/hb-weather.md"})

    def test_four_native_weather_producers_persist_exact_clause_provenance(self):
        for move_id, clause_ids in EXPECTED.items():
            with self.subTest(move_id=move_id):
                e, actor, other = self.fixture()
                self.cast(e, actor, other, move_id)
                active = e._weather_state["active"]
                pool = next(record for record in B.live(actor) if WB.is_weather(record))
                expected = H.provenance(move_id)
                self.assertEqual(expected["clause_ids"], list(clause_ids))
                self.assertEqual(active["policy"], expected)
                self.assertEqual(pool["weather_policy"], expected)
                self.assertEqual(B.remaining(pool), 2)
                restored = self.restored(e)
                restored_actor = next(row for row in restored.gm.everyone if row.entity_id == actor.entity_id)
                restored_pool = next(record for record in B.live(restored_actor) if WB.is_weather(record))
                self.assertEqual(restored._weather_state["active"]["policy"], expected)
                self.assertEqual(restored_pool["weather_policy"], expected)

    def test_provenance_rejects_non_native_weather_without_creating_trace(self):
        before = deepcopy(H.CLAUSE_IDS)
        with self.assertRaisesRegex(ValueError, "native Move"):
            H.provenance("move/not-a-reviewed-weather")
        self.assertEqual(H.CLAUSE_IDS, before)


if __name__ == "__main__":
    unittest.main()
