"""Category2 completion proof for ch04:1283-1287, Let's Be Friends!.

The runtime path was already completed and frozen by C3-EX-063.  This suite
reuses that direct consumer proof, binds it to the whole Category2 source
clause, and adds the durable-state boundary that the earlier proof did not
exercise.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "tools"))
warnings.simplefilter("ignore", ResourceWarning)

import test_category3_friendship_completion as CATEGORY3
from engine import Engine
import contest_features as FEATURES
import world_entities as WORLD


SOURCE_ID = "input/ch04-trainer-classes.md:1283-1287"
SOURCE_SHA256 = "497fa5fd051a373751d00f31b5c6d30cff2f7e735b7510521c0df51afc7ee576"


class FriendshipFeatureTests(CATEGORY3.Tests):
    """Run the frozen whole-scope proof and the missing persistence boundary."""

    def test_category2_whole_clause_is_bound_to_the_completed_category3_scope(self):
        registry = json.loads(
            (ROOT / "data/verification/category2-class-clause-status.json").read_text(encoding="utf-8")
        )
        row = next(x for x in registry["entries"] if x["source_clause_id"] == SOURCE_ID)
        self.assertTrue(row["include_category2"])
        self.assertEqual(row["source_sha256"], hashlib.sha256((ROOT / row["source_file"]).read_bytes()).hexdigest())
        anchor = row["anchors"][0]
        lines = (ROOT / anchor["file"]).read_text(encoding="utf-8-sig").splitlines()
        excerpt = "\n".join(lines[anchor["start"] - 1 : anchor["end"]])
        self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(), SOURCE_SHA256)
        self.assertEqual(anchor["sha256"], SOURCE_SHA256)

        category3 = json.loads(
            (ROOT / "data/verification/category3-register.json").read_text(encoding="utf-8")
        )
        evidence = next(x for x in category3["entries"] if x["id"] == "C3-EX-063")
        self.assertEqual(evidence["status"], "completed")
        self.assertTrue(evidence["review"]["full_scope_verified"])
        self.assertEqual(evidence["review"]["remaining_obligations"], [])
        self.assertEqual(self.r._selected_rule(FEATURES.FRIENDS), FEATURES.FRIENDS)

        # The separate CSV inventory says Daily/5.  Its reviewed row is outside
        # this Category2 Markdown clause and must never silently override the
        # selected Scene source used by this completion.
        csv_registry = json.loads(
            (ROOT / "data/verification/category2-class-csv-clause-status.json").read_text(encoding="utf-8")
        )
        csv_row = next(x for x in csv_registry["rows"] if x["name"] == "우리 친구 하자!")
        self.assertFalse(csv_row["include_category2"])
        self.assertEqual(csv_row["status"], "other-category")
        self.assertIn("하루/5", csv_row["source_text"])

        definition = json.loads((ROOT / "data/feats-mech.json").read_text(encoding="utf-8"))[
            FEATURES.FRIENDS
        ]
        self.assertEqual(
            definition["header"],
            {
                "frequency": {"raw": "장면 - 자유 행동", "kind": "scene", "uses": 1, "action": "free"},
                "trigger": None,
                "target": "당신의 포켓몬",
                "prereq": "귀여운 포옹 랭크1",
                "condition": None,
            },
        )

    def test_failure_disposition_frequency_and_action_survive_gm_and_json_restore(self):
        failed = self.friends(fixed=[1] * 5)
        self.assertFalse(failed["check"].passed)
        expected = {
            "dispositions": {"pokemon:pokemon/p": "중립"},
            "failures": ["pokemon:pokemon/p"],
            "frequency": deepcopy(self.t.spec["frequency_state"]),
            "actions": ["free"],
        }
        self.assertEqual(self.used(FEATURES.FRIENDS), 1)

        self.e.gm.snapshot("friendship-failed")
        self.w.spec["dispositions"]["pokemon:pokemon/p"] = "매우 우호적"
        self.w.spec["befriend_failures"].clear()
        self.t.spec["frequency_state"].clear()
        self.t._action_history.clear()
        self.e.gm.restore("friendship-failed", reason="restore exact failed performer state")
        self.assertEqual(self.w.spec["dispositions"], expected["dispositions"])
        self.assertEqual(self.w.spec["befriend_failures"], expected["failures"])
        self.assertEqual(self.t.spec["frequency_state"], expected["frequency"])
        self.assertEqual(self.t._action_history, expected["actions"])

        payload = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        loaded = Engine.import_state(self.r, payload)
        actors = WORLD.actor_index(loaded)
        trainer, performer, target = (actors[x] for x in (self.t.entity_id, self.p.entity_id, self.w.entity_id))
        self.assertEqual(target.spec["dispositions"], expected["dispositions"])
        self.assertEqual(target.spec["befriend_failures"], expected["failures"])
        self.assertEqual(trainer.spec["frequency_state"], expected["frequency"])
        self.assertEqual(trainer._action_history, expected["actions"])
        self.assertTrue(loaded.validate_state()["valid"], loaded.validate_state())

        before = loaded.export_state()
        with self.assertRaisesRegex(ValueError, "retry requires GM permission"):
            loaded.pokemon_activity(
                trainer,
                "befriend",
                target=target,
                friendship_performer=performer,
                friendship_audience="performer",
                fixed=[6] * 5,
            )
        self.assertEqual(loaded.export_state(), before)

        loaded.end_scene([trainer, performer, target])
        loaded.pokemon_activity(
            trainer,
            "disposition_ruling",
            target=target,
            disposition="중립",
            reason="GM confirms materially changed circumstances",
            allow_retry=True,
            friendship_performer=performer,
            friendship_audience="performer",
        )
        succeeded = loaded.pokemon_activity(
            trainer,
            "befriend",
            target=target,
            friendship_performer=performer,
            friendship_audience="performer",
            fixed=[2] * 5,
        )
        self.assertTrue(succeeded["check"].passed)
        self.assertEqual(target.spec["dispositions"], {"pokemon:pokemon/p": "우호적"})
        self.assertEqual(target.spec["befriend_failures"], [])
        self.assertEqual(
            trainer.spec["frequency_state"]["activations"][FEATURES.FRIENDS]["used"], 1
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
