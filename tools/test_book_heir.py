"""C03-128 uses the real Mega form and existing command/GM consumers."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "input").is_dir():
    ROOT = Path(r"D:/trpg-rulebook-structuring/ptk-structure-experiment")
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Engine, Rules
from builder import build_pokemon, build_trainer
import common_checks as CHECKS
import mega_forms as MEGA
import pokemon_activities as ACTIVITIES
import state_grants as GRANTS
import trainer_feature_acquisition as FEATURES
import trainer_retraining as RETRAINING
import world_entities as WORLD
import test_category2_mega_forms as fixture


class BookHeirTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset="core")

    add = fixture.MegaFormTests.add
    equip = fixture.MegaFormTests.equip
    turn = fixture.MegaFormTests.turn
    activate = fixture.MegaFormTests.activate

    def setUp(self):
        fixture.MegaFormTests.setUp(self)
        self.t.spec["skills"] = {"명령": "숙련", "협박": "숙련"}
        self.t.spec.setdefault("feats", [])
        self.t.spec["exp_bank"] = 10
        self.q = self.add(build_pokemon(self.r, "파오리", 30, name="actual command target",
            moves=[], abilities=[], wild=True, side="wild", pos=(3, 1)))
        self.e.gm.observe_loyalty(self.p, 5, reason="actual prior trainer relationship")

    def active(self, *, heir=False):
        if heir:
            self.acquire()
        self.e.begin_encounter([self.t, self.p, self.q])
        self.turn(self.t)
        result = self.activate()
        self.turn(self.p)
        return result

    def command(self, **options):
        return self.e.pokemon_activity(self.t, "command_move", pokemon=self.p,
            target=self.q, move_id="struggle", set_damage=True, **options)

    def force(self, **options):
        return self.e.pokemon_activity(self.t, "resolve_disobedience", pokemon=self.p,
            reason="GM explicitly chooses the uncontrolled Mega action", **options)

    def cost_state(self):
        return deepcopy((self.e.rng.getstate(), self.q.hp, self.p.move_uses, self.p.budget))

    def acquire(self, feature=MEGA.HEIR, *, trainer=None, request="heir/acquire", **options):
        return FEATURES.acquire_static(self.e, trainer or self.t, feature,
            acquisition_request_id=request, **options)

    def trainer(self, level, command="숙련", intimidate="숙련"):
        return self.add(build_trainer(self.r, "registration boundary", level,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[], abilities=[], skills={"명령": command, "협박": intimidate},
            extra={"feats": [], "edges": [], "exp_bank": 10}))

    def test_missing_heir_allows_real_mega_but_failed_dc20_command_cannot_spend_move(self):
        result = self.active()
        self.assertEqual(result["definition"], "mega/리자몽-x")
        self.assertEqual(self.p.spec["loyalty"], 5)
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e, self.p), 0)
        before = self.cost_state()
        result = self.command(obedience_options={"fixed": [1] * 4})
        self.assertEqual(result["status"], "disobedient")
        self.assertEqual(result["obedience"]["check"].dc, 20)
        self.assertIsInstance(result["obedience"]["failure"], CHECKS.PendingDecision)
        self.assertEqual(self.cost_state(), before)
        self.e.use_move(self.p, self.q, "struggle", set_damage=True)
        self.assertEqual(self.cost_state(), before)
        self.assertEqual(self.p.spec["loyalty"], 5)
        self.assertEqual(self.force(decision="idle")["status"], "idle")

    def test_missing_heir_success_uses_one_native_move_and_preserves_secret_relationship(self):
        self.active()
        self.e.rng.seed(5)
        before = self.q.hp
        result = self.command(obedience_options={"fixed": [5] * 4})
        self.assertEqual(result["status"], "submitted")
        self.assertTrue(result["obedience"]["obeys"])
        self.assertEqual(result["obedience"]["check"].dc, 20)
        self.assertLess(self.q.hp, before)
        self.assertEqual(self.p.move_uses["struggle"], 1)
        self.assertEqual(self.p.budget["standard"], 0)
        self.assertEqual(self.p.spec["loyalty"], 5)
        self.assertEqual(getattr(self.e, "_obedience_receipts", []), [])

    def test_gm_can_choose_actual_attack_without_a_prior_failed_command(self):
        for incapacitated in (False, True):
            with self.subTest(trainer_incapacitated=incapacitated):
                self.setUp()
                self.active()
                self.assertNotIn("pending_disobedience", self.p.spec)
                target = self.q if incapacitated else self.t
                if incapacitated:
                    self.e.gm.set_hp(self.t, value=0, reason="the actual trainer fainted; GM still controls the Mega")
                    self.assertTrue(self.t.fainted)
                    self.assertFalse(self.p.fainted)
                    before = self.cost_state()
                    with self.assertRaisesRegex(ValueError, "conscious trainer"):
                        self.command(obedience_options={"fixed": [5] * 4})
                    self.assertEqual(self.cost_state(), before)
                self.e.rng.seed(5)
                before = target.hp
                result = self.force(decision="action", target=target, move_id="struggle", set_damage=True)
                self.assertEqual(result["status"], "submitted")
                self.assertLess(target.hp, before)
                self.assertEqual(self.p.move_uses["struggle"], 1)
                self.assertEqual(self.p.budget["standard"], 0)
                self.assertNotIn("pending_disobedience", self.p.spec)
                self.assertEqual(getattr(self.e, "_obedience_receipts", []), [])
                self.assertEqual(self.p.spec["loyalty"], 5)
        self.setUp()
        self.e.gm.observe_loyalty(self.p, 0, reason="ordinary disobedience without Mega")
        self.e.begin_encounter([self.t, self.p, self.q])
        self.turn(self.p)
        self.assertEqual(self.command(obedience_options={"fixed": [1] * 4})["status"], "disobedient")
        self.e.gm.set_hp(self.t, value=0, reason="ordinary failed-command trainer fainted")
        with self.assertRaisesRegex(ValueError, "conscious trainer"):
            self.command()
        before = self.q.hp
        self.e.rng.seed(5)
        self.assertEqual(self.force(decision="action", target=self.q, move_id="struggle", set_damage=True)["status"], "submitted")
        self.assertLess(self.q.hp, before)
        self.assertNotIn("pending_disobedience", self.p.spec)

    def test_gm_force_needs_actual_owner_explicit_target_and_learned_move(self):
        self.active()
        before = self.cost_state()
        for options in ({"decision": "action"},
                        {"decision": "action", "target": self.t, "move_id": "화염방사"},
                        {"decision": "action", "target": self.t, "move_id": "struggle", "free_action": True}):
            with self.assertRaises(ValueError):
                self.force(**options)
            self.assertEqual(self.cost_state(), before)
            self.assertNotIn("pending_disobedience", self.p.spec)
        with self.assertRaisesRegex(ValueError, "actual registered"):
            self.e.pokemon_activity(copy(self.t), "resolve_disobedience", pokemon=self.p,
                decision="idle", reason="a cloned sheet is not the actual GM-selected owner")
        self.assertEqual(self.cost_state(), before)

    def test_owned_heir_uses_actual_loyalty_and_does_not_give_gm_free_force_authority(self):
        self.active(heir=True)
        self.assertFalse(MEGA.uncontrolled(self.e, self.p))
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e, self.p), 5)
        with self.assertRaisesRegex(ValueError, "unresolved failed command"):
            self.force(decision="action", target=self.t, move_id="struggle")
        self.e.rng.seed(5)
        result = self.command()
        self.assertTrue(result["obedience"]["obeys"])
        self.assertIsNone(result["obedience"]["check"])

    def test_owned_heir_does_not_override_an_actual_low_or_unknown_loyalty(self):
        self.active(heir=True)
        self.e.gm.observe_loyalty(self.p, 1, reason="actual relationship changed independently")
        result = self.command(obedience_options={"fixed": [1] * 4})
        self.assertEqual(result["obedience"]["check"].dc, 8)
        self.assertEqual(result["status"], "disobedient")
        self.force(decision="idle")
        self.e.gm.observe_loyalty(self.p, None, reason="current relationship unknown")
        self.assertIsInstance(ACTIVITIES.loyalty_pending(self.e, self.p), CHECKS.PendingDecision)

    def test_unknown_loyalty_fallback_survives_both_restores_and_ends_with_the_form(self):
        self.e.gm.observe_loyalty(self.p, None, reason="GM has not established relationship rank")
        self.active()
        self.assertIsNone(ACTIVITIES.loyalty_pending(self.e, self.p))
        identities = [c.entity_id for c in (self.t, self.p, self.q)]
        self.e.gm.restore(self.e.gm.snapshot())
        index = WORLD.actor_index(self.e)
        self.t, self.p, self.q = [index[uid] for uid in identities]
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e, self.p), 0)
        self.e = Engine.import_state(Rules(ROOT, ruleset="core"), json.loads(json.dumps(self.e.export_state())))
        index = WORLD.actor_index(self.e)
        self.t, self.p, self.q = [index[uid] for uid in identities]
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e, self.p), 0)
        self.assertIsNone(self.p.spec["loyalty"])
        self.e.end_scene()
        self.assertIsNone(self.p.spec["loyalty"])
        self.assertIsInstance(ACTIVITIES.loyalty_pending(self.e, self.p), CHECKS.PendingDecision)
        with self.assertRaisesRegex(ValueError, "unresolved failed command"):
            self.force(decision="idle")

    def test_current_owned_feature_controls_fallback_without_rechecking_acquisition_prerequisites(self):
        self.active(heir=True)
        self.t.spec["skills"]["명령"] = "초보"
        self.assertFalse(MEGA.uncontrolled(self.e, self.p))
        self.e.retrain_trainer_source(self.t, MEGA.HEIR, request_id="heir/withdraw",
            reason="actual Feature retraining", gm_decision={"allowed": True, "reason": "GM reviewed removal"},
            retained_dependencies={})
        self.assertTrue(MEGA.uncontrolled(self.e, self.p))
        self.assertEqual(self.p.spec["loyalty"], 5)

    def test_changed_heir_source_cannot_silently_reuse_the_command_exception(self):
        self.active()
        original = self.e.r._selected_rule
        with patch.object(self.e.r, "_selected_rule", side_effect=lambda uid: "feat/other-heir" if uid == MEGA.HEIR else original(uid)):
            with self.assertRaisesRegex(ValueError, "selected static Feature"):
                ACTIVITIES.command_loyalty_value(self.e, self.p)
        with patch.dict(FEATURES.STATIC_SOURCE, sha256="0" * 64):
            with self.assertRaisesRegex(ValueError, "source changed"):
                ACTIVITIES.command_loyalty_value(self.e, self.p)

    def test_static_registration_checks_both_real_definitions_without_completing_legendary_commands(self):
        for feature, level, command, allowed in (
                (MEGA.HEIR, 9, "숙련", False), (MEGA.HEIR, 10, "초보", False),
                (MEGA.HEIR, 10, "숙련", True),
                ("feat/전설의-트레이너", 19, "미숙", False),
                ("feat/전설의-트레이너", 20, "미숙", True)):
            with self.subTest(feature=feature, level=level, command=command):
                trainer = self.trainer(level, command)
                before = deepcopy(trainer.spec)
                if not allowed:
                    with self.assertRaises(ValueError):
                        self.acquire(feature, trainer=trainer)
                    self.assertEqual(trainer.spec, before)
                else:
                    result = self.acquire(feature, trainer=trainer)
                    self.assertEqual(result["status"], "acquired")
                    self.assertEqual(trainer.spec["feats"], [feature])
                    self.assertEqual(result["snapshot"]["level"], level)
                    self.assertNotIn(FEATURES.LEDGER_KEY, trainer.spec)
                    self.assertNotIn(FEATURES.PROJECTION_KEY, trainer.spec)
                    self.assertNotIn("selection", result)

    def test_static_registration_replay_preserves_historical_qualification_and_rejects_relabeling(self):
        result = self.acquire()
        self.t.spec["skills"]["명령"] = "미숙"
        self.assertEqual(self.acquire(), result)
        self.assertEqual(result["snapshot"]["rank"], 4)
        before = deepcopy(self.t.spec)
        for options in ({"request": "heir/duplicate"},
                        {"prerequisite_source": FEATURES.BEAST_HEIR_SOURCE}):
            with self.assertRaises(ValueError):
                self.acquire(**options)
            self.assertEqual(self.t.spec, before)
        with self.assertRaisesRegex(ValueError, "replay cannot change"):
            self.acquire("feat/전설의-트레이너")
        with self.assertRaisesRegex(ValueError, "definition required"):
            self.acquire("feat/invented", request="unreviewed")
        self.assertEqual(self.t.spec, before)

    def test_csv_beast_master_substitutes_only_its_reviewed_heir_acquisition_prerequisite(self):
        trainer = self.trainer(10, "미숙")
        for options in ({}, {"prerequisite_source": FEATURES.BEAST_HEIR_SOURCE}):
            before = deepcopy(trainer.spec)
            with self.assertRaises(ValueError):
                self.acquire(trainer=trainer, **options)
            self.assertEqual(trainer.spec, before)
        trainer.spec["edges"].append("edge/비스트-마스터")
        before = deepcopy(trainer.spec)
        with self.assertRaises(ValueError):
            self.acquire(trainer=trainer)
        self.assertEqual(trainer.spec, before)
        result = self.acquire(trainer=trainer, prerequisite_source=FEATURES.BEAST_HEIR_SOURCE)
        self.assertEqual(result["snapshot"]["skill"], "협박")
        self.assertEqual(result["snapshot"]["rank"], 4)
        self.assertEqual(result["prerequisite_source"], FEATURES.BEAST_HEIR_SOURCE)
        novice = self.trainer(10, "미숙", "초보")
        novice.spec["edges"].append("edge/비스트-마스터")
        before = deepcopy(novice.spec)
        with self.assertRaisesRegex(ValueError, "Adept"):
            self.acquire(trainer=novice, prerequisite_source=FEATURES.BEAST_HEIR_SOURCE)
        self.assertEqual(novice.spec, before)
        with self.assertRaisesRegex(ValueError, "only the exact"):
            self.acquire("feat/전설의-트레이너", trainer=self.t, request="legendary/invalid-substitution",
                prerequisite_source=FEATURES.BEAST_HEIR_SOURCE)

    def test_static_registration_late_owner_failure_rolls_back_the_new_owned_feature(self):
        before = deepcopy(self.e.export_state())
        with patch.object(RETRAINING, "owned_source", side_effect=RuntimeError("actual source registration failed")):
            with self.assertRaisesRegex(RuntimeError, "registration failed"):
                self.acquire()
        self.assertEqual(self.e.export_state(), before)

    def test_static_sources_coexist_with_actual_selection_receipt_through_both_restores(self):
        self.t.spec["skills"]["일반 지식"] = "초보"
        moves = [self.r.move_id(name) for name in ("몸통박치기", "울음소리", "방어")]
        GRANTS.replace_baseline(self.e, self.t, "moves", moves)
        selected = FEATURES.acquire_personal_tutor(self.e, self.t,
            acquisition_request_id="tutor/coexist", selected_values=moves, source_clause_id="C03-127",
            lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_UNRESOLVED))
        heir = self.acquire()
        legendary = self.acquire("feat/전설의-트레이너", request="legendary/coexist")
        other = self.trainer(30)
        other_record = self.acquire(trainer=other, request="other/heir")
        other_identity = other.entity_id
        self.assertNotEqual(heir["actor_id"], other_record["actor_id"])
        self.assertEqual(FEATURES.receipts(self.t), [selected])
        identity = self.t.entity_id
        self.e.gm.restore(self.e.gm.snapshot())
        self.t = WORLD.actor_index(self.e)[identity]
        self.e = Engine.import_state(Rules(ROOT, ruleset="core"), json.loads(json.dumps(self.e.export_state())))
        self.t = WORLD.actor_index(self.e)[identity]
        self.assertEqual(FEATURES.receipts(self.t), [selected])
        self.assertEqual(self.acquire(), heir)
        self.assertEqual(self.acquire("feat/전설의-트레이너", request="legendary/coexist"), legendary)
        other = WORLD.actor_index(self.e)[other_identity]
        self.assertEqual(self.acquire(trainer=other, request="other/heir"), other_record)
        before = deepcopy(self.e.export_state())
        transplanted = deepcopy(before)
        def source_node(owner):
            return next(node for node in transplanted["nodes"].values() if node["kind"] == "dict"
                and ["owner_id", owner] in node["items"] and ["rule_id", MEGA.HEIR] in node["items"]
                and any(key == "static_acquisition" for key, _ in node["items"]))
        copied_fields = {"actor_id", "request_id", "integrity"}
        self.assertEqual({k: v for k, v in heir.items() if k not in copied_fields},
                         {k: v for k, v in other_record.items() if k not in copied_fields})
        recipient = next(value for key, value in source_node(other_identity)["items"] if key == "static_acquisition")
        # Preserve graph reachability while transplanting A's complete valid evidence into B's own row.
        for pair in transplanted["nodes"][recipient["$ref"]]["items"]:
            if pair[0] in copied_fields:
                pair[1] = heir[pair[0]]
        with self.assertRaisesRegex(ValueError, "source or owner changed"):
            Engine.import_state(Rules(ROOT, ruleset="core"), transplanted)
        self.assertEqual(self.e.export_state(), before)
        name = self.e.gm.snapshot("static-acquisition-transplant")
        saved = self.e.gm.snapshots[name]["combatants"]
        donor = saved[id(self.t)]["spec"][GRANTS.KEY]["sources"]["feature:" + identity + ":" + MEGA.HEIR]
        recipient = saved[id(other)]["spec"][GRANTS.KEY]["sources"]["feature:" + other_identity + ":" + MEGA.HEIR]
        recipient["static_acquisition"] = deepcopy(donor["static_acquisition"])
        before = deepcopy(self.e.export_state())
        with self.assertRaisesRegex(ValueError, "source or owner changed"):
            self.e.gm.restore(name)
        self.assertEqual(self.e.export_state(), before)
        source = self.t.spec[GRANTS.KEY]["sources"]["feature:" + identity + ":" + MEGA.HEIR]
        source["static_acquisition"]["snapshot"]["rank"] = 3
        with self.assertRaises(ValueError):
            self.e.export_state()

    def test_native_retraining_archives_registration_and_new_request_requalifies(self):
        self.active(heir=True)
        result = self.e.retrain_trainer_source(self.t, MEGA.HEIR, request_id="heir/withdraw",
            reason="actual Feature retraining", gm_decision={"allowed": True, "reason": "GM reviewed removal"},
            retained_dependencies={})
        self.assertGreater(result["xp_paid"], 0)
        self.assertTrue(MEGA.uncontrolled(self.e, self.p))
        self.assertEqual(self.acquire()["status"], "withdrawn")
        self.assertNotIn(MEGA.HEIR, self.t.spec["feats"])
        renewed = self.acquire(request="heir/reacquired")
        self.assertEqual(renewed["status"], "acquired")
        self.assertFalse(MEGA.uncontrolled(self.e, self.p))
        identity = self.t.entity_id
        self.e = Engine.import_state(Rules(ROOT, ruleset="core"), json.loads(json.dumps(self.e.export_state())))
        self.t = WORLD.actor_index(self.e)[identity]
        self.assertEqual(self.acquire()["status"], "withdrawn")
        self.assertEqual(self.acquire(request="heir/reacquired"), renewed)


if __name__ == "__main__":
    unittest.main()
