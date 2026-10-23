"""Entity identity, authority and actual GM/native snapshot acceptance checks."""
from pathlib import Path
from copy import deepcopy
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from engine import Engine, Combatant, Rules
from grid import Grid
import builder, downtime, state_fields as S
import action_points as AP

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, 220)
        self.a = Combatant(self.r, builder.build_trainer(self.r, "same", 9, {k: 10 for k in S.STATS}, pos=(1, 2)))
        self.b = Combatant(self.r, builder.build_trainer(self.r, "same", 9, {k: 10 for k in S.STATS}, pos=(2, 2)))
        self.e.everyone = self.e.gm.everyone = [self.a, self.b]

    def test_same_name_builds_distinct_identity(self):
        self.assertNotEqual(self.a.entity_id, self.b.entity_id)
        identity = self.a.entity_id
        self.a.name = "new name"
        self.assertEqual(identity, self.a.entity_id)
        self.assertEqual("new name", self.a.spec["name"])

    def test_evolution_preserves_individual_id(self):
        spec = builder.build_pokemon(self.r, "뚜벅쵸", 25, name="nickname")
        uid = spec["id"]
        out = downtime.evolve(self.r, spec, "냄새꼬")
        self.assertEqual(spec["id"], uid)
        self.assertEqual(spec["species"], "pokemon/냄새꼬")

    def test_native_trainer_xp_level_is_seen_by_ap_consumer(self):
        self.assertEqual(AP.maximum(self.a), 6)
        self.a.spec["exp_bank"] = 0
        downtime.trainer_gain_exp(self.r, self.a.spec, 10)
        self.assertEqual(self.a.level, self.a.spec["level"])
        self.assertEqual(self.a.level, 10)
        self.assertEqual(AP.maximum(self.a), 7)

    def test_base_stat_edit_preserves_effective_addition(self):
        self.a.stats["atk"] += 5
        self.e.gm.set_stat(self.a, "atk", value=12, reason="GM confirms new permanent allocation")
        self.assertEqual(self.a.spec["stats"]["atk"], 12)
        self.assertEqual(self.a.stats["atk"], 17)
        self.assertEqual(self.a.staged("atk"), 17)

    def test_patch_rejection_is_atomic(self):
        before = deepcopy(vars(self.a))
        before.pop("r")
        for patch in ({"level": 101}, {"id": "replacement"}, {"stats": {"hp": 4}}, {"abilities": ["test"]}):
            with self.assertRaises(ValueError):
                S.base_patch(self.a, patch, reason="invalid test")
            after = deepcopy({k: v for k, v in vars(self.a).items() if k != "r"})
            self.assertEqual(before, after)

    def test_patch_request_retry_and_conflict(self):
        first = S.base_patch(self.a, {"name": "renamed"}, reason="nickname", request_id="r1", expected_revision=0)
        second = S.base_patch(self.a, {"name": "renamed"}, reason="nickname", request_id="r1", expected_revision=0)
        self.assertEqual(first, second)
        self.assertEqual(self.a._state_revision, 1)
        with self.assertRaises(ValueError):
            S.base_patch(self.a, {"name": "other"}, reason="nickname", request_id="r1")
        with self.assertRaises(ValueError):
            S.base_patch(self.a, {"name": "other"}, reason="nickname", expected_revision=0)

    def test_missing_position_is_unknown_without_affecting_nongeometric_action(self):
        spec = builder.build_trainer(self.r, "unknown", 1, {k: 5 for k in S.STATS})
        spec.pop("pos")
        c = Combatant(self.r, spec)
        self.assertEqual(c.location, {"kind": "unknown"})
        with self.assertRaises(ValueError):
            _ = c.pos
        self.e.gm.everyone.append(c)
        self.e.gm.snapshot("unknown")
        self.e.gm.set_position(c, (5, 5), reason="location observed")
        self.assertEqual(c.pos, (5, 5))
        self.e.gm.restore("unknown")
        self.assertEqual(c.location, {"kind": "unknown"})
        self.assertGreater(c.max_hp, 0)

    def test_snapshot_aliases_offfield_identity_rng_and_grid(self):
        self.e.grid = Grid(10, 12)
        original_grid = self.e.grid
        self.a.self_attributes = self.a.__dict__
        self.e.grid.self_attributes = self.e.grid.__dict__
        shared = {"target": self.b, "count": 2}
        self.a.custom_conditions["shared"] = shared
        self.e.delayed = [shared]
        self.e.gm.snapshot("all")
        expected = self.e.rng.randint(1, 1000000)
        epoch = self.e._root_common_epoch
        for _ in range(2):
            self.a.name = "changed"
            self.a.side = "other"
            self.a.new_dynamic_state = 4
            self.e.grid = Grid(1, 1)
            self.e.delayed[0]["count"] = 999
            self.e.gm.restore("all")
            self.assertIs(self.a.self_attributes, self.a.__dict__)
            self.assertIs(self.e.grid.self_attributes, self.e.grid.__dict__)
            self.assertEqual(self.a.name, "same")
            self.assertEqual(self.a.side, "party")
            self.assertFalse(hasattr(self.a, "new_dynamic_state"))
            self.assertIs(self.a.custom_conditions["shared"], self.e.delayed[0])
            self.assertIs(self.e.delayed[0]["target"], self.b)
            self.assertIs(self.e.grid, original_grid)
            self.assertEqual((self.e.grid.w, self.e.grid.h), (10, 12))
            self.assertEqual(self.e.rng.randint(1, 1000000), expected)
        self.assertGreater(self.e._root_common_epoch, epoch)

    def test_native_attack_receipt_keeps_actual_target(self):
        self.e.start_round([self.a, self.b])
        self.e.start_of_turn(self.a)
        self.e.use_move(self.a, self.b, "struggle", set_damage=True)
        packets = list(self.e._heavy_events.values())
        self.assertTrue(packets)
        self.assertIs(packets[-1]["target"], self.b)
        self.assertIs(packets[-1]["move"]["_actual_targets"][0], self.b)
        self.e.validate_state()

    def test_gm_registration_rejects_duplicate_identity_and_accepts_unknown_location(self):
        duplicate = Combatant(self.r, deepcopy(self.a.spec))
        before = list(self.e.everyone)
        with self.assertRaises(ValueError):
            self.e.gm.add_combatant(duplicate)
        self.assertEqual(self.e.everyone, before)
        spec = builder.build_trainer(self.r, "new", 1, {k: 5 for k in S.STATS})
        spec.pop("pos")
        c = Combatant(self.r, spec)
        self.e.gm.add_combatant(c, reason="GM imports a sheet")
        self.assertEqual(c.location, {"kind": "unknown"})
        self.assertIn(c, self.e.everyone)
        self.assertFalse(c._state_origin["creation_legality_certified"])
        self.e.gm.remove_combatant(c)
        self.assertNotIn(c, self.e.everyone)

    def test_soulless_zero_hp_template_and_native_life_consumers(self):
        import temporary_hp as TEMP, effects_ext as EXT
        c = Combatant(self.r, builder.build_pokemon(self.r, "껍질몬", 10))
        self.e.everyone = self.e.gm.everyone = [c]
        self.assertEqual(c.stats["hp"], 0)
        self.assertEqual(c.spec["stat_allocation"]["hp"], 0)
        self.assertEqual((c.hp, c.base_max_hp, c.max_hp), (1, 1, 1))
        self.assertEqual(TEMP.grant(self.e, c, 99), 0)
        self.e.death_enabled = True
        self.e.friendly_battle = False
        self.e.take_damage(c, 1000)
        EXT.h_injury(self.e, c, c, {"value": 3, "target": "self"}, {})
        self.assertEqual((c.injuries, c.dead, c.temp_hp), (0, False, 0))
        S.validate_actor(c)
        with self.assertRaises(ValueError):
            builder.add_stat_points(self.r, c.spec, 1, choice="hp")
        downtime.rest(self.e, c, 0)
        self.assertLess(c.hp, 0)
        downtime.rest(self.e, c, 30)
        self.assertEqual(c.hp, 1)
        self.assertFalse(c.fainted)
        self.assertEqual(c.spec["stat_allocation"]["hp"], 0)
        S.validate_actor(c)

    def test_narrative_description_preserves_unknowns_identity_and_mechanical_nature(self):
        self.assertEqual(self.e.gm.describe_actor(self.a)["description"],
                         {field: None for field in S.DESCRIPTION_FIELDS})
        self.a.spec["nature"] = "고집"
        original_id = self.a.entity_id
        values = {"appearance": "파란 외투", "personality": "낯을 가림", "background": None}
        receipt = self.e.gm.set_actor_description(self.a, values, reason="player supplied facts", request_id="description-1")
        self.assertEqual(receipt, self.e.gm.set_actor_description(self.a, values,
                         reason="player supplied facts", request_id="description-1"))
        self.assertEqual(self.a.entity_id, original_id)
        self.assertEqual(self.a.spec["nature"], "고집")
        self.assertEqual(self.e.gm.describe_actor(self.a)["description"], values)
        loaded = Engine.import_state(self.r, self.e.export_state())
        actor = next(c for c in loaded.everyone if c.entity_id == original_id)
        self.assertEqual(loaded.gm.describe_actor(actor)["description"], values)
        self.assertEqual(actor.spec["nature"], "고집")

    def test_invalid_narrative_update_is_atomic(self):
        before = deepcopy(self.a.spec)
        for changes in ({"personality": 3}, {"name": "unrelated"}, {"background": ["invalid"]}):
            with self.assertRaises(ValueError):
                self.e.gm.set_actor_description(self.a, changes, reason="invalid test")
            self.assertEqual(self.a.spec, before)

    def test_derived_movement_patch_preserves_granted_delta_and_live_skills(self):
        import state_grants as G, movement_actions as MOVE
        G.numeric(self.a, "movement", 2, "fixture:boots")
        self.assertEqual(self.a.movement, 7)
        S.base_patch(self.a, {"movement": {"power": 7}}, reason="observed Power")
        self.assertEqual(self.a.movement, 7)
        S.base_patch(self.a, {"skills": {"육상": 4, "곡예": 4}, "movement": {"power": 7}},
                     reason="observed new ranks and Power")
        self.assertEqual((self.a.movement, MOVE.capabilities(self.e, self.a)["land"]), (9, 9))
        loaded = Engine.import_state(self.r, self.e.export_state())
        actor = next(c for c in loaded.everyone if c.entity_id == self.a.entity_id)
        self.assertEqual(actor.movement, 9)
        G.remove_owned(loaded, actor, "fixture:boots")
        self.assertEqual(actor.movement, 7)
        self.assertEqual(actor._movement_delta, 0)

    def test_derived_movement_conflicts_reject_atomically(self):
        before = deepcopy(self.a.spec)
        revision = getattr(self.a, "_state_revision", 0)
        for field in ("land", "high_jump", "long_jump", "swim"):
            with self.assertRaisesRegex(ValueError, "derived trainer fields"):
                S.base_patch(self.a, {"name": "invalid", "movement": {field: 8}}, reason="invalid current value")
            self.assertEqual(self.a.spec, before)
            self.assertEqual(self.a.movement, 5)
            self.assertEqual(getattr(self.a, "_state_revision", 0), revision)

    def test_current_movement_patch_and_clear_keep_runtime_grant(self):
        import state_grants as G
        self.e.gm.set_movement_capabilities(self.a, {"land": 6}, basis="current", reason="observed sheet")
        G.numeric(self.a, "movement", 2, "fixture:boots")
        S.base_patch(self.a, {"movement": {"land": 8}}, reason="observed new base")
        self.assertEqual(self.a.movement, 10)
        S.base_patch(self.a, {"movement": {}}, reason="restore standard current-sheet fallback")
        self.assertEqual(self.a.movement, 6)
        G.remove_owned(self.e, self.a, "fixture:boots")
        self.assertEqual(self.a.movement, 4)

    def test_base_patch_does_not_guess_legacy_derived_delta(self):
        self.a.__dict__["movement"] = 4
        before = deepcopy(self.a.spec)
        with self.assertRaisesRegex(ValueError, "legacy derived movement"):
            S.base_patch(self.a, {"skills": {"육상": 4, "곡예": 4}}, reason="observed ranks")
        self.assertEqual(self.a.spec, before)
        self.assertEqual(self.a.__dict__["movement"], 4)

    def test_gm_accuracy_stage_uses_source_bounds(self):
        self.e.gm.set_stage(self.a, "acc", value=10)
        self.assertEqual(self.a.accuracy_stage, 6)
        self.e.gm.set_stage(self.a, "acc", delta=-30)
        self.assertEqual(self.a.accuracy_stage, -6)

if __name__ == "__main__":
    unittest.main(verbosity=2)
