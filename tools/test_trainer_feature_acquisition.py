"""Direct checks for selection-only trainer Feature acquisition receipts."""
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
PROJECT = STAGE if (STAGE / "data" / "core-rules.json").exists() else Path(
    os.environ.get("PTK_CANONICAL_ROOT", r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
)
sys.path[:0] = [str(STAGE / "engine"), str(PROJECT / "engine"), str(PROJECT / "tools")]

from engine import Combatant, Engine, Rules
from state_codec import dump_engine, load_engine


def _overlay(name):
    """engine.py puts its canonical directory first; replace only owned modules."""
    import importlib.util
    path = STAGE / "engine" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FEATURES = _overlay("trainer_feature_acquisition")
_overlay("acquisition_ledger")
ACQUIRED = _overlay("acquired_features")


class TrainerFeatureAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(PROJECT), ruleset="all")
        cls.moves = list(cls.rules.moves)[:5]

    def actor(self, name="owner", *, moves=None, novice=True):
        return Combatant(self.rules, {
            "id": "trainer/" + name,
            "name": name,
            "kind": "trainer",
            "level": 10,
            "stats": {key: 10 for key in ("hp", "atk", "def", "spa", "spd", "spe")},
            "types": [],
            "moves": list(self.moves[:4] if moves is None else moves),
            "abilities": [],
            "capabilities": [],
            "movement": {"land": 4},
            "skills": {"일반 지식": "초보" if novice else "미숙"},
            "feats": [],
        })

    def fixture(self, *, novice=True):
        engine = Engine(self.rules, seed=41)
        actor = self.actor(novice=novice)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    def state(self, actor):
        return deepcopy((actor.spec.get("feats", []),
                         actor.spec.get(FEATURES.LEDGER_KEY),
                         actor.spec.get(FEATURES.PROJECTION_KEY)))

    def acquire(self, engine, actor, *, request="request/1", selected=None,
                source="C03-127", **options):
        return FEATURES.acquire_personal_tutor(
            engine, actor,
            acquisition_request_id=request,
            selected_values=list(self.moves[:3] if selected is None else selected),
            source_clause_id=source,
            lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_UNRESOLVED),
            **options,
        )

    def test_both_reviewed_sources_commit_ownership_receipt_and_projection(self):
        for source in FEATURES.PERSONAL_TUTOR_SOURCES:
            with self.subTest(source=source):
                engine, actor = self.fixture()
                receipt = self.acquire(engine, actor, source=source)
                self.assertEqual(actor.spec["feats"], [FEATURES.PERSONAL_TUTOR])
                self.assertTrue(receipt["committed"])
                self.assertEqual(receipt["source"]["clause_id"], source)
                self.assertEqual(receipt["actor_id"], actor.entity_id)
                self.assertEqual(receipt["provider"], {"actor_id": actor.entity_id, "mode": "self_acquisition"})
                self.assertEqual(receipt["selection"]["values"], self.moves[:3])
                self.assertEqual(receipt["selection"]["required_count"], 3)
                self.assertEqual(ACQUIRED.selected_at_acquisition(
                    actor, FEATURES.PERSONAL_TUTOR, "feat/개인-지도:1"), tuple(self.moves[:3]))
                projected = ACQUIRED.selection_only_projection(actor, FEATURES.PERSONAL_TUTOR)
                self.assertEqual(projected["feat/개인-지도:1"]["values"], self.moves[:3])
                ledger_row = next(row for row in engine.acquisition_receipts(actor)
                                  if row.get("basis") == "trainer_feature_selection")
                self.assertEqual(ledger_row, receipt)

    def test_exact_selection_count_rejects_two_and_four_without_mutation(self):
        for selected in (self.moves[:2], self.moves[:4]):
            with self.subTest(count=len(selected)):
                engine, actor = self.fixture()
                before = self.state(actor)
                with self.assertRaisesRegex(ValueError, "exactly three"):
                    self.acquire(engine, actor, selected=selected)
                self.assertEqual(self.state(actor), before)

    def test_duplicate_unknown_and_not_permanently_known_reject_atomically(self):
        cases = [
            ([self.moves[0], self.moves[0], self.moves[1]], "distinct"),
            ([self.moves[0], self.moves[1], "move/not-a-real-move"], "unknown"),
            ([self.moves[0], self.moves[1], self.moves[4]], "not permanently known"),
        ]
        for selected, message in cases:
            with self.subTest(message=message):
                engine, actor = self.fixture()
                before = self.state(actor)
                with self.assertRaisesRegex(ValueError, message):
                    self.acquire(engine, actor, selected=selected)
                self.assertEqual(self.state(actor), before)

    def test_provider_and_waiver_forgery_reject_without_mutation(self):
        engine, actor = self.fixture()
        other = self.actor("other")
        engine.everyone = engine.gm.everyone = [actor, other]
        before = self.state(actor)
        with self.assertRaisesRegex(ValueError, "provider"):
            self.acquire(engine, actor, provider=other)
        self.assertEqual(self.state(actor), before)
        forged = [{"source_id": "C03-127", "checks": ["general_education"], "reason": "caller said so"}]
        with self.assertRaisesRegex(ValueError, "waiver"):
            self.acquire(engine, actor, waivers=forged)
        self.assertEqual(self.state(actor), before)

    def test_request_replay_is_idempotent_and_payload_collision_rejects(self):
        engine, actor = self.fixture()
        first = self.acquire(engine, actor)
        after = dump_engine(engine)
        replay = self.acquire(engine, actor)
        self.assertEqual(replay, first)
        self.assertEqual(dump_engine(engine), after)
        with self.assertRaisesRegex(ValueError, "waiver"):
            self.acquire(engine, actor, waivers=[{"reason": "forged replay"}])
        self.assertEqual(dump_engine(engine), after)
        with self.assertRaisesRegex(ValueError, "different payload"):
            self.acquire(engine, actor, selected=self.moves[1:4])
        self.assertEqual(dump_engine(engine), after)

    def test_new_request_cannot_reselect_or_reacquire_feature(self):
        engine, actor = self.fixture()
        self.acquire(engine, actor)
        before = dump_engine(engine)
        with self.assertRaisesRegex(ValueError, "immutable|reselection"):
            self.acquire(engine, actor, request="request/2", selected=self.moves[1:4])
        self.assertEqual(dump_engine(engine), before)

    def test_acquisition_snapshot_survives_later_known_move_change(self):
        engine, actor = self.fixture()
        receipt = self.acquire(engine, actor)
        original = deepcopy(receipt["selection"])
        actor.spec["moves"] = [self.moves[1], self.moves[2], self.moves[3], self.moves[4]]
        actor.moves = list(actor.spec["moves"])
        self.assertEqual(ACQUIRED.selected_at_acquisition(
            actor, FEATURES.PERSONAL_TUTOR, "feat/개인-지도:1"), tuple(self.moves[:3]))
        self.assertEqual(FEATURES.receipts(actor)[0]["selection"], original)
        self.assertEqual(self.acquire(engine, actor)["selection"], original)

    def test_save_restore_retains_receipt_integrity_and_projection(self):
        engine, actor = self.fixture()
        receipt = self.acquire(engine, actor, source="C2CSV/input/db/feats.csv:R8:main")
        payload = dump_engine(engine)
        restored = load_engine(self.rules, payload)
        restored_actor = next(value for value in restored.everyone if value.entity_id == actor.entity_id)
        self.assertEqual(FEATURES.receipts(restored_actor), [receipt])
        self.assertEqual(ACQUIRED.selected_at_acquisition(
            restored_actor, FEATURES.PERSONAL_TUTOR, "feat/개인-지도:1"), tuple(self.moves[:3]))
        restored_again = load_engine(self.rules, dump_engine(restored))
        actor_again = next(value for value in restored_again.everyone if value.entity_id == actor.entity_id)
        self.assertEqual(FEATURES.receipts(actor_again), [receipt])
        self.assertEqual(ACQUIRED.selection_only_projection(actor_again),
                         ACQUIRED.selection_only_projection(restored_actor))

    def test_projection_and_receipt_tampering_are_detected(self):
        for tamper in ("projection", "provider", "waiver"):
            with self.subTest(tamper=tamper):
                engine, actor = self.fixture()
                self.acquire(engine, actor)
                if tamper == "projection":
                    actor.spec[FEATURES.PROJECTION_KEY][FEATURES.PERSONAL_TUTOR]["feat/개인-지도:1"]["values"][0] = self.moves[4]
                elif tamper == "provider":
                    actor.spec[FEATURES.LEDGER_KEY]["request/1"]["provider"]["actor_id"] = "trainer/forged"
                else:
                    actor.spec[FEATURES.LEDGER_KEY]["request/1"]["qualification"]["waivers"].append({"reason": "forged"})
                with self.assertRaises(ValueError):
                    FEATURES.validate_actor(actor)
                with self.assertRaises(Exception):
                    dump_engine(engine)

    def test_prerequisite_and_lifecycle_policy_failures_are_atomic(self):
        engine, actor = self.fixture(novice=False)
        before = self.state(actor)
        with self.assertRaisesRegex(ValueError, "Novice"):
            self.acquire(engine, actor)
        self.assertEqual(self.state(actor), before)
        engine, actor = self.fixture()
        before = self.state(actor)
        with self.assertRaisesRegex(ValueError, "removal/reacquisition"):
            FEATURES.acquire_personal_tutor(
                engine, actor, acquisition_request_id="request/policy",
                selected_values=self.moves[:3], source_clause_id="C03-127",
                lifecycle_policy={"removal": "delete", "reacquisition": "allow"},
            )
        self.assertEqual(self.state(actor), before)

    def test_existing_unreceipted_ownership_cannot_be_forged_retroactively(self):
        engine, actor = self.fixture()
        actor.spec["feats"].append(FEATURES.PERSONAL_TUTOR)
        before = self.state(actor)
        with self.assertRaisesRegex(ValueError, "retroactively"):
            self.acquire(engine, actor)
        self.assertEqual(self.state(actor), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
