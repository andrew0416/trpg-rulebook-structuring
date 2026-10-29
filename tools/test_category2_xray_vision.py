"""Direct contract tests for X-Ray Vision clauses C10-156 and C10-157."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

import test_category2_body_modes as BODY_FIXTURE
import perception_observe as OBSERVE
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD
import xray_vision as XRAY


class XRayVisionTests(unittest.TestCase):
    setUpClass = classmethod(BODY_FIXTURE.Tests.setUpClass.__func__)
    add = BODY_FIXTURE.Tests.add
    pokemon = BODY_FIXTURE.Tests.pokemon
    restored = BODY_FIXTURE.Tests.restored

    def setUp(self):
        BODY_FIXTURE.Tests.setUp(self)
        self.observer = self.p
        self.target = self.t
        GRANTS.replace_baseline(self.e, self.observer, "capabilities", ["엑스레이 시야"])

    def snapshot(self):
        return CODEC.dump_engine(self.e)

    def environment(self, material, *, present=True):
        return self.e.gm.observe_sensory_environment(
            self.observer,
            self.target,
            paths={"visual": False},
            medium=material,
            present=present,
            reason="actual observed barrier material and target presence",
        )

    def test_easy_authored_materials_share_one_presence_only_white_silhouette_contract(self):
        self.target.spec.update(hidden_identity="private identity", hidden_species="private species", hidden_text="private text")
        for material in ("wood", "종이", "drywall"):
            self.environment(material)
            before = self.snapshot()
            with patch.object(OBSERVE, "observe", wraps=OBSERVE.observe) as common:
                result = XRAY.observe(self.e, self.observer, self.target)
            self.assertEqual(common.call_count, 1)
            self.assertEqual((result["status"], result["reason"]),
                             ("observed", "xray_indistinct_white_silhouette"))
            self.assertEqual(result["values"], {"presence": True, "silhouette": "indistinct_white"})
            self.assertNotIn(self.target.entity_id, str(result))
            for secret in ("private identity", "private species", "private text"):
                self.assertNotIn(secret, str(result))
            self.assertEqual(self.snapshot(), before)

    def test_lead_and_tungsten_are_nearly_opaque_without_leaking_presence_or_detail(self):
        self.target.spec["hidden_memory"] = "never reveal"
        for material in ("납", "tungsten"):
            self.environment(material)
            result = XRAY.observe(self.e, self.observer, self.target)
            self.assertEqual((result["status"], result["reason"], result["values"]),
                             ("not_observable", "xray_material_nearly_opaque", {}))
            self.assertNotIn("never reveal", str(result))
            self.assertNotIn(self.target.entity_id, str(result))

    def test_unlisted_material_stays_qualitatively_unresolved_without_invented_threshold(self):
        self.environment("reinforced concrete")
        result = XRAY.observe(self.e, self.observer, self.target)
        self.assertEqual((result["status"], result["reason"], result["values"]),
                         ("unknown", "xray_material_accuracy_unresolved", {}))
        self.assertEqual(result["unknown_fields"], ["silhouette"])
        for invalid in (None, "", True):
            with self.assertRaises(ValueError):
                XRAY.material_policy(invalid)

    def test_actual_pair_capability_and_selected_source_are_required_atomically(self):
        self.environment("paper")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            XRAY.observe(self.e, copy(self.observer), self.target)
        with self.assertRaises(ValueError):
            XRAY.observe(self.e, self.observer, copy(self.target))
        self.assertEqual(self.snapshot(), before)
        GRANTS.replace_baseline(self.e, self.observer, "capabilities", [])
        without_capability = self.snapshot()
        with self.assertRaisesRegex(ValueError, "capability"):
            XRAY.observe(self.e, self.observer, self.target)
        self.assertEqual(self.snapshot(), without_capability)
        GRANTS.replace_baseline(self.e, self.observer, "capabilities", ["X-Ray Vision"])
        with_capability = self.snapshot()
        selected = self.r._selected_rule
        with patch.object(self.r, "_selected_rule",
                          side_effect=lambda uid: uid + "/other" if uid == XRAY.SOURCE else selected(uid)):
            with self.assertRaises(ValueError):
                XRAY.observe(self.e, self.observer, self.target)
        self.assertEqual(self.snapshot(), with_capability)

    def test_presence_and_current_world_context_gate_the_silhouette(self):
        self.assertEqual(XRAY.observe(self.e, self.observer, self.target)["reason"], "medium_unknown")
        self.environment("wood", present=None)
        self.assertEqual(XRAY.observe(self.e, self.observer, self.target)["reason"], "presence_unknown")
        self.environment("wood", present=False)
        absent = XRAY.observe(self.e, self.observer, self.target)
        self.assertEqual((absent["status"], absent["values"]), ("absent", {"presence": False}))
        self.environment("wood")
        self.target.pos = (8, 3)
        self.assertEqual(XRAY.observe(self.e, self.observer, self.target)["reason"], "medium_unknown")

    def test_signed_environment_json_and_gm_restore_preserve_exact_bounded_result(self):
        self.environment("회벽")
        expected = XRAY.observe(self.e, self.observer, self.target)
        saved = self.e.gm.snapshot()
        loaded = self.restored()
        actors = WORLD.actor_index(loaded)
        self.assertEqual(XRAY.observe(loaded, actors[self.observer.entity_id], actors[self.target.entity_id]), expected)
        self.e.gm.set_actor_description(self.target, {"appearance": "changed body"}, reason="temporary change")
        self.e.gm.restore(saved)
        self.assertEqual(XRAY.observe(self.e, self.observer, self.target), expected)
        row = getattr(self.e, OBSERVE.ENV)[OBSERVE.environment_key(self.observer.entity_id, self.target.entity_id)]
        row["facts"]["medium"] = "lead"
        with self.assertRaises(ValueError):
            XRAY.observe(self.e, self.observer, self.target)
        self.assertFalse(self.e.validate_state()["valid"])


if __name__ == "__main__":
    unittest.main()
