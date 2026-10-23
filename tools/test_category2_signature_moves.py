"""Exact R41 acquisition, actual learned grants and native frequency consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import signature_moves as SIGNATURE
import trainer_feature_acquisition as ACQUISITION
import state_grants as GRANTS
import state_codec as CODEC
import frequency as FREQUENCY
import items as ITEMS
import static_feature_state_grants as STATIC


class SignatureMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.engine = Engine(self.rules, seed=4100)
        self.actor = self.add(build_trainer(self.rules, "signature-maker", 30,
            dict.fromkeys(SIGNATURE.STATS, 10),
            moves=["방어지령", "단단해지기", "코튼가드", "회복지령"],
            extra={"classes": [], "feats": [], "edges": [], "items": {},
                   "feature_choices": {}, "skills": {"곡예": 6, "육상": 6, "은신": 6},
                   "movement_basis": "current", "power_basis": "current"}))

    def add(self, spec):
        actor = Combatant(self.rules, spec)
        self.engine.gm.add_combatant(actor, pos=(0, 0), side="party", reason="actual test participant")
        return actor

    def acquire(self, move="move/방어지령", stat="atk", request="signature/1", **kwargs):
        return SIGNATURE.acquire(self.engine, self.actor,
            acquisition_request_id=request, selected_move=move, stat=stat,
            lifecycle_policy=deepcopy(ACQUISITION.LIFECYCLE_UNRESOLVED), **kwargs)

    def state(self):
        return deepcopy((self.engine.elapsed_seconds, self.engine.rng.getstate(),
                         [vars(c) for c in self.engine.everyone], self.engine.log_lines),
                        {id(self.rules): self.rules})

    def turn(self):
        active = getattr(self.engine, "_active_turn_actor", None)
        if active is not None:
            self.engine.end_of_turn(active)
        if self.engine.round_start_seconds is not None:
            self.engine.end_round()
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.actor)

    def native_state(self):
        # Existing native rejection can log its reason and retain transient
        # declaration diagnostics.  Its actual cost, rules state and dice stay
        # untouched; this is the same boundary as FrequencyStateTests.state.
        return deepcopy((self.actor.spec, self.actor.hp, self.actor.stages,
                         self.actor.budget, self.actor._action_history,
                         self.actor.move_uses, self.engine.rng.getstate()))

    def cast(self, move):
        if move == "move/회복지령":
            self.actor.hp = max(1, self.actor.base_max_hp // 3)
        return self.engine.use_move(self.actor, self.actor, move)

    def test_actual_class_learned_moves_qualify_and_one_selected_move_is_sealed(self):
        GRANTS.set_baseline(self.actor, "moves", ["방어지령", "단단해지기"])
        self.actor.spec["classes"] = ["class/로그"]
        ITEMS.register_feats(self.engine, self.actor)
        self.assertEqual({self.rules.move_id(value) for value in self.actor.moves if value != "struggle"}, {
            "move/방어지령", "move/단단해지기", "move/속여때리기", "move/도둑질"})
        row = self.acquire(move="move/도둑질")
        selection = row["selection"]
        self.assertEqual(selection["required_count"], 1)
        self.assertEqual(selection["values"], ["move/도둑질"])
        self.assertEqual(len(selection["acquisition_snapshot"]["canonical_values"]), 4)
        proofs = selection["proofs"][0]["origins"]
        self.assertTrue(any(p.get("rule_id") == "class/로그" and p["kind"] == "learned_grant" for p in proofs))
        self.assertEqual(ACQUISITION.selected_values(self.actor, SIGNATURE.FEATURE,
                         SIGNATURE.FEATURE + ":1"), ("move/도둑질",))
        self.assertEqual(self.actor.stats["atk"], 11)
        self.assertNotIn("vitamin_special_uses", self.actor.spec)

    def test_temporary_overlay_legacy_and_duplicate_sources_do_not_supply_four_learned(self):
        GRANTS.set_baseline(self.actor, "moves", ["방어지령", "단단해지기", "코튼가드"])
        GRANTS.grant_moves(self.actor, ["회복지령"], "test:temporary", "effect",
                           owner_id=self.actor.entity_id, lifetime="user_turn_end",
                           rule_id="move/회복지령", mode="permission")
        GRANTS.overlay(self.actor, "test:display", moves=["회복지령", "단단해지기", "코튼가드", "방어지령"])
        before = self.state()
        for move in ("move/방어지령", "move/회복지령"):
            with self.assertRaisesRegex(ValueError, "four permanent"):
                self.acquire(move=move)
            self.assertEqual(self.state(), before)
        GRANTS.revoke(self.actor, "test:display", engine=self.engine)
        GRANTS.revoke(self.actor, "test:temporary", engine=self.engine)
        self.actor.moves.append("move/회복지령")  # unverified live-only import is not evidence
        before = self.state()
        with self.assertRaisesRegex(ValueError, "four permanent"):
            self.acquire()
        self.assertEqual(self.state(), before)
        self.actor.moves.remove("move/회복지령")
        self.actor.spec["classes"] = ["class/로그"]
        ITEMS.register_feats(self.engine, self.actor)
        # One baseline overlaps a class learned source: it remains one identity.
        GRANTS.set_baseline(self.actor, "moves", ["속여때리기", "단단해지기"])
        before = self.state()
        with self.assertRaisesRegex(ValueError, "four permanent"):
            self.acquire(move="move/도둑질")
        self.assertEqual(self.state(), before)

    def test_invalid_selection_stat_source_provider_and_waiver_are_atomic(self):
        for options in ({"move": []}, {"move": ["방어지령", "코튼가드"]},
                        {"move": "move/not-a-move"}, {"stat": "accuracy"},
                        {"source_clause_id": "C03-127"}, {"waivers": [{"reason": "caller"}]}):
            with self.subTest(options=options):
                before = self.state()
                with self.assertRaises(ValueError):
                    self.acquire(**options)
                self.assertEqual(self.state(), before)
        other = self.add(build_trainer(self.rules, "not-provider", 20, dict.fromkeys(SIGNATURE.STATS, 10)))
        before = self.state()
        with self.assertRaises(ValueError):
            self.acquire(provider=other)
        self.assertEqual(self.state(), before)

    def test_replay_and_immutable_choice_survive_later_learning_changes(self):
        row = self.acquire()
        self.engine.gm.set_move(self.actor, "move/방어지령", False, reason="actual forgetting")
        before = self.state()
        self.assertEqual(self.acquire(), row)
        self.assertEqual(self.state(), before)
        for options in ({"move": "move/코튼가드"}, {"stat": "hp"}, {"request": "signature/2"}):
            with self.assertRaisesRegex(ValueError, "replay|immutable"):
                self.acquire(**options)
            self.assertEqual(self.state(), before)
        self.assertEqual(FREQUENCY.move_frequency(self.engine, "move/방어지령", self.actor), ("at_will", 1))

    def test_six_stat_choices_repeated_registration_hp_and_independent_source(self):
        for stat in SIGNATURE.STATS:
            with self.subTest(stat=stat):
                self.setUp()
                GRANTS._source(self.actor, "gm:independent", "effect", owner_id=self.actor.entity_id,
                               lifetime="permanent", rule_id="move/단단해지기", tutor_points=0)
                GRANTS.stat(self.actor, stat, 2, "gm:independent", operation_id="observed")
                old_max = self.actor.base_max_hp
                self.acquire(stat=stat)
                self.assertEqual(self.actor.stats[stat], 13)
                if stat == "hp":
                    self.assertEqual(self.actor.base_max_hp, old_max + 3)
                before = self.state()
                ITEMS.register_feats(self.engine, self.actor)
                ITEMS.register_feats(self.engine, self.actor)
                self.assertEqual(self.state(), before)
                self.assertEqual(self.actor.spec[GRANTS.KEY]["stat_sources"][stat]["sources"]["gm:independent"],
                                 {"observed": {"delta": 2, "minimum": None}})

    def test_native_eot_becomes_at_will_but_still_pays_standard(self):
        mid = "move/방어지령"
        self.acquire(mid)
        for count in (1, 2):
            self.turn()
            self.cast(mid)
            self.assertEqual(self.actor.move_uses[mid], count)
            self.assertEqual(self.actor.stages["def"], count)
            self.assertEqual(self.actor.budget["standard"], 0)
            before = self.native_state()
            self.cast(mid)
            self.assertEqual(self.native_state(), before)
        self.assertEqual(FREQUENCY.move_frequency(self.engine, "move/코튼가드", self.actor), ("scene", 1))

    def test_native_scene_allowance_and_intervening_turn_are_preserved(self):
        mid = "move/코튼가드"
        self.acquire(mid)
        self.assertEqual(FREQUENCY.move_frequency(self.engine, mid, self.actor), ("scene", 2))
        self.turn(); self.cast(mid)
        self.turn()
        before = self.native_state(); self.cast(mid)
        self.assertEqual(self.native_state(), before)
        self.turn(); self.cast(mid)
        self.assertEqual(self.actor.move_uses[mid], 2)
        self.turn(); self.turn()
        before = self.native_state(); self.cast(mid)
        self.assertEqual(self.native_state(), before)

    def test_native_daily_allowance_still_allows_only_one_per_scene(self):
        mid = "move/회복지령"
        base = FREQUENCY.move_frequency(self.engine, mid, self.actor)
        self.acquire(mid)
        self.assertEqual(FREQUENCY.move_frequency(self.engine, mid, self.actor), ("daily", base[1] + 1))
        for count in range(1, base[1] + 2):
            if count > 1:
                self.engine.end_scene()
            self.turn(); self.cast(mid)
            self.assertEqual(self.actor.move_uses[mid], count)
            self.turn()
            before = self.native_state()
            self.engine.use_move(self.actor, self.actor, mid)
            self.assertEqual(self.native_state(), before)
        self.engine.end_scene(); self.turn()
        before = self.native_state(); self.engine.use_move(self.actor, self.actor, mid)
        self.assertEqual(self.native_state(), before)

    def test_at_will_choice_locks_without_item_charge_or_extra_frequency(self):
        self.acquire("move/단단해지기")
        self.assertEqual(FREQUENCY.move_frequency(self.engine, "move/단단해지기", self.actor), ("at_will", 1))
        self.assertEqual(self.actor.spec["items"], {})
        self.assertNotIn("vitamins", self.actor.spec)
        before = self.state()
        with self.assertRaises(ValueError):
            self.acquire("move/코튼가드", request="second")
        self.assertEqual(self.state(), before)

    def test_real_pp_up_trainer_rejection_and_pokemon_native_consumer_remain_separate(self):
        self.acquire()
        self.actor.spec["items"] = {"item/pp업": 2}
        before = self.state()
        with self.assertRaisesRegex(ValueError, "Pokemon"):
            self.engine.use_item(self.actor, "item/pp업", self.actor, selected_move="move/방어지령")
        self.assertEqual(self.state(), before)
        pokemon = self.add(build_pokemon(self.rules, "이브이", 20, moves=["방어지령"], abilities=[]))
        self.assertEqual(self.engine.use_item(self.actor, "item/pp업", pokemon,
                                           selected_move="move/방어지령"), (1, 0))
        self.assertEqual(FREQUENCY.move_frequency(self.engine, "move/방어지령", pokemon), ("at_will", 1))
        before = self.state()
        with self.assertRaisesRegex(ValueError, "trainer"):
            SIGNATURE.acquire(self.engine, pokemon, acquisition_request_id="pokemon-signature",
                              selected_move="move/방어지령", stat="atk",
                              lifecycle_policy=ACQUISITION.LIFECYCLE_UNRESOLVED)
        self.assertEqual(self.state(), before)

    def test_gm_and_json_fresh_rules_restore_choice_stat_and_native_used_pool(self):
        mid = "move/코튼가드"
        row = self.acquire(mid, stat="hp")
        self.turn(); self.cast(mid)
        self.engine.gm.snapshot("signature-native")
        payload = json.loads(json.dumps(CODEC.dump_engine(self.engine), ensure_ascii=False))
        fresh = Rules(str(ROOT), ruleset="core")
        restored = CODEC.load_engine(fresh, payload)
        self.engine.gm.restore("signature-native", reason="restore original receipt")
        for e in (self.engine, restored):
            self.engine = e
            self.actor = next(c for c in e.everyone if c.entity_id == row["actor_id"])
            self.assertEqual(SIGNATURE.receipt(self.actor), row)
            self.assertEqual(self.actor.stats["hp"], 11)
            self.assertEqual(self.actor.move_uses[mid], 1)
            self.turn(); self.turn(); self.cast(mid)
            self.assertEqual(self.actor.move_uses[mid], 2)
            self.assertTrue(e.validate_state()["valid"])

    def test_tampered_receipt_unreceipted_feature_and_late_failure_reject_atomically(self):
        self.actor.spec["feats"].append(SIGNATURE.FEATURE)
        before = self.state()
        with self.assertRaisesRegex(ValueError, "receipt"):
            self.acquire()
        self.assertEqual(self.state(), before)
        self.actor.spec["feats"].clear()
        before = self.state()
        original = STATIC._install
        def fail_after(*args, **kwargs):
            original(*args, **kwargs)
            raise ValueError("injected after actual stat installation")
        with patch.object(STATIC, "_install", side_effect=fail_after):
            with self.assertRaisesRegex(ValueError, "injected"):
                self.acquire()
        self.assertEqual(self.state(), before)
        self.acquire()
        self.actor.spec[ACQUISITION.LEDGER_KEY]["signature/1"]["selection"]["values"] = ["move/코튼가드"]
        before = self.state()
        for check in (lambda: SIGNATURE.stat_choice(self.actor), self.engine.export_state,
                      lambda: FREQUENCY.move_frequency(self.engine, "move/방어지령", self.actor)):
            with self.assertRaisesRegex(ValueError, "integrity"):
                check()
            self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
