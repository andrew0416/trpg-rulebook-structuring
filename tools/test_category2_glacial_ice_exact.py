"""Exact book Glacial Ice over the existing source-owned DR consumer."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from builder import build_trainer
from engine import Combatant, Engine
import test_category2_class_passive_combat_bulk as FIXTURES
import class_passive_combat as C
import state_codec as CODEC
import state_grants as G
import world_entities as W
import pokemon_party as PARTY
import frequency as F
import csv_item_capability_contracts as CSV_CAPABILITIES
import weapon_actions as WEAPONS

CLAUSE = "input/ch04-trainer-classes.md:1677-1680"
ATTACKS = ("발경", "화염방사", "스톤샤워", "아이언헤드")
MOVES = (*ATTACKS, "몸통박치기", "물대포")


class GlacialIceExactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURES.ClassPassiveCombatBulkTests.setUpClass.__func__(cls)
        # Derived rule/ruling caches are shared with this Rules instance. Warm
        # the exact successful consumers before comparing failed authority graphs.
        e, t, p, q = cls.fixture(cls)
        for name in MOVES:
            e.roll_damage(q, p, cls.rules.move("move/" + name), set_damage=True)

    def fixture(self):
        e, t, p, q = FIXTURES.ClassPassiveCombatBulkTests.fixture(
            self, feats=[C.GLACIAL_ICE], pokemon_types=["얼음"])
        t.spec["classes"] = ["class/타입-에이스"]
        t.spec["feature_choices"] = {"class/타입-에이스": ["얼음"]}
        G.replace_baseline(e, q, "moves", ["move/" + name for name in MOVES])
        return e, t, p, q

    @staticmethod
    def raw_authority(engine):
        # Encode the complete declared native graph without treating an invalid
        # source observation as a valid save. This includes HP, AP, action and
        # frequency budgets, RNG, physical state, native receipts and aliases.
        encoder = CODEC._Encoder(engine)
        root = encoder.value(engine)
        return deepcopy({"root": root, "nodes": encoder.nodes,
                         "rules": CODEC.rules_fingerprint(engine.r)})

    def native_damage_pair(self, engine, trainer, partner, enemy, move_name):
        payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
        worlds = [CODEC.load_engine(self.rules, deepcopy(payload)) for _ in range(2)]
        damage = []
        for keep, world in zip((True, False), worlds):
            actors = W.actor_index(world)
            t, p, q = (actors[a.entity_id] for a in (trainer, partner, enemy))
            if not keep:
                t.spec["feats"] = []
                world.register_abilities(p)
            world.begin_encounter(world.everyone)
            world.start_round(world.everyone)
            world.start_of_turn(q, initiative_count=20)
            before = p.hp
            with patch.object(Engine, "d20", return_value=10):
                world.use_move_on(q, p, "move/" + move_name, world.everyone)
            damage.append(before - p.hp)
            self.assertEqual(q.budget["standard"], 0)
            self.assertEqual(q.move_uses["move/" + move_name], 1)
        return damage, worlds

    def test_book_source_binding_and_selected_ice_class_are_exact(self):
        e, t, p, q = self.fixture()
        policy = C._policy(self.rules)
        source = policy["native_sources"][C.GLACIAL_ICE]
        self.assertEqual((source["clause_id"], source["start"], source["end"]),
                         (CLAUSE, 1677, 1680))
        lines = (ROOT / source["file"]).read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(lines[1676:1680])
        self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(), source["excerpt_sha256"])
        self.assertEqual(self.rules._selected_rule(C.GLACIAL_ICE), C.GLACIAL_ICE)
        unit = self.rules.selection.units[C.GLACIAL_ICE]
        self.assertEqual(unit["source"]["lines"], [1677, 1680])
        self.assertEqual(t.spec["feature_choices"]["class/타입-에이스"], ["얼음"])
        row = G.state(p)["sources"][C._source_id(t, p, C.GLACIAL_ICE)]
        self.assertEqual((row["native_clause_id"], row["acquisition_source"], row["owner_id"]),
                         (CLAUSE, C.GLACIAL_ICE, t.entity_id))
        self.assertEqual(row["clause_id"], C.CLAUSE_BY_RULE[C.GLACIAL_ICE])
        self.assertEqual(row["lifetime"], "your_pokemon")
        self.assertIsNone(C._declaration(e, t, C.GLACIAL_ICE))
        self.assertIsNone(C._declaration(e, q, C.GLACIAL_ICE))

    def test_all_four_types_reduce_real_native_attack_damage_but_neutral_does_not(self):
        e, t, p, q = self.fixture()
        rank = C.type_link_rank(e, t, "얼음")
        for name in MOVES:
            with self.subTest(move=name):
                move = self.rules.move("move/" + name)
                mult = e.type_multiplier(move["type"], p)[0]
                values, worlds = self.native_damage_pair(e, t, p, q, name)
                expected = int(rank * mult) if name in ATTACKS else 0
                self.assertGreater(min(values), 0)
                self.assertEqual(values[1] - values[0], expected)
                dr_lines = [line for line in worlds[0].log_lines if "클래스 패시브 피해 감소" in line]
                self.assertEqual(bool(dr_lines), name in ATTACKS)

    def test_actual_type_and_live_link_rank_changes_reach_native_damage(self):
        e, t, p, q = self.fixture()
        fire = self.rules.move("move/화염방사")
        self.assertEqual(C.damage_reduction(e, q, p, fire, e.type_multiplier("불꽃", p)[0], False), 4)
        e.gm.set_types(p, ["얼음", "불꽃"], reason="actual neutral Fire matchup")
        values, _ = self.native_damage_pair(e, t, p, q, "화염방사")
        self.assertEqual(values[0], values[1])
        e.gm.set_types(p, ["풀"], reason="super-effective target without Ice typing")
        values, _ = self.native_damage_pair(e, t, p, q, "화염방사")
        self.assertEqual(values[0], values[1])
        e.gm.set_types(p, ["얼음"], reason="restore actual Ice target")
        e.gm.set_skill(t, "생존", "전문", reason="actual link skill growth", request_id="ice-link-growth")
        self.assertEqual(C.type_link_rank(e, t, "얼음"), 5)
        values, _ = self.native_damage_pair(e, t, p, q, "화염방사")
        self.assertIn(values[1] - values[0], (7, 8))  # native integer flooring after x1.5

    def test_neutral_dual_type_needs_no_link_selection_and_consumes_no_glacial_dr(self):
        e, t, p, q = self.fixture()
        e.gm.set_types(p, ["얼음", "불꽃"], reason="actual neutral dual-type Fire matchup")
        del t.spec["type_link_skills"]["얼음"]
        fire = self.rules.move("move/화염방사")
        self.assertEqual(e.type_multiplier("불꽃", p)[0], 1)
        self.assertEqual(C.damage_reduction(e, q, p, fire, 1, False), 0)
        before = self.raw_authority(e)
        C.preflight_glacial(e, q, p, fire, self.rules.move_mech(fire["id"])[0])
        self.assertEqual(before, self.raw_authority(e))
        values, worlds = self.native_damage_pair(e, t, p, q, "화염방사")
        self.assertGreater(values[0], 0)
        self.assertEqual(values[0], values[1])
        self.assertFalse(any("클래스 패시브 피해 감소" in line for line in worlds[0].log_lines))

    def test_tinkerer_attack_lookups_do_not_create_or_change_receipt_state(self):
        e, t, p, q = self.fixture()
        fire = self.rules.move("move/화염방사")
        self.assertNotIn(CSV_CAPABILITIES.STATE, q.spec)
        before = self.raw_authority(e)
        self.assertIsNone(CSV_CAPABILITIES.tinkerer_weapon(q))
        self.assertIsNone(CSV_CAPABILITIES.tinkerer_move(q, fire))
        self.assertEqual(WEAPONS.prepare(e, q, fire, None), fire)
        self.assertNotIn(CSV_CAPABILITIES.STATE, q.spec)
        self.assertEqual(before, self.raw_authority(e))
        q.spec[CSV_CAPABILITIES.STATE] = {"version": 1, "receipts": "invalid"}
        before = self.raw_authority(e)
        for lookup in (lambda: CSV_CAPABILITIES.tinkerer_weapon(q),
                       lambda: CSV_CAPABILITIES.tinkerer_move(q, fire)):
            with self.assertRaisesRegex(ValueError, "capability state"):
                lookup()
        self.assertEqual(before, self.raw_authority(e))

    def test_duplicate_registration_source_withdrawal_and_actual_owner_transfer(self):
        e, t, p, q = self.fixture()
        for _ in range(3):
            e.register_abilities(p)
        rows = [row for row in G.state(p)["sources"].values() if row.get("rule_id") == C.GLACIAL_ICE]
        self.assertEqual(len(rows), 1)
        t.spec["feats"] = []
        e.register_abilities(p)
        self.assertIsNone(C._declaration(e, p, C.GLACIAL_ICE))
        t.spec["feats"] = [C.GLACIAL_ICE]
        e.register_abilities(p)
        other = Combatant(self.rules, build_trainer(self.rules, "New Owner", 30,
            {"hp": 40, "atk": 12, "def": 12, "spa": 12, "spd": 12, "spe": 12},
            moves=[], abilities=[], extra={"feats": [], "edges": []}))
        e.gm.add_combatant(other, pos=(0, 1), side="party", reason="actual transfer receiver")
        PARTY.configure(e, t, mode="unlimited", reason="explicit old roster", roster=[p])
        PARTY.configure(e, other, mode="unlimited", reason="explicit new roster", roster=[])
        PARTY.transfer(e, t, target=p, new_owner=other, reason="observed transfer", request_id="ice-owner-transfer")
        e.register_abilities(p)
        self.assertEqual(p.spec["trainer_id"], other.entity_id)
        self.assertIsNone(C._declaration(e, p, C.GLACIAL_ICE))
        self.assertFalse(any(row.get("rule_id") == C.GLACIAL_ICE for row in G.state(p)["sources"].values()))
        self.assertIn("ice-owner-transfer", e._world_relation_receipts)

    def test_json_and_gm_restore_keep_native_binding_and_reject_forged_source(self):
        e, t, p, q = self.fixture()
        payload = json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False))
        e.gm.snapshot("ice")
        e.gm.set_types(p, ["노말"], reason="temporary explicit base edit")
        t.spec["feats"] = []
        e.register_abilities(p)
        e.gm.restore("ice", reason="restore the same acquired book source")
        loaded = CODEC.load_engine(self.rules, payload)
        for world in (e, loaded):
            actors = W.actor_index(world)
            lt, lp, lq = (actors[a.entity_id] for a in (t, p, q))
            row = C._declaration(world, lp, C.GLACIAL_ICE)[1]
            self.assertEqual(row["native_clause_id"], CLAUSE)
            self.assertEqual(lp.types, ["얼음"])
            self.assertEqual(C.damage_reduction(world, lq, lp, self.rules.move("move/화염방사"), 1.5, False), 4)
            self.assertTrue(W.validate_world(world)["valid"])
        row = G.state(p)["sources"][C._source_id(t, p, C.GLACIAL_ICE)]
        row["native_clause_id"] = "input/ch04-trainer-classes.md:1541-1544"
        self.assertFalse(W.validate_world(e)["valid"])
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_engine(e)

    def test_invalid_live_link_source_or_owner_fails_before_actions_rng_hp_and_receipts(self):
        for case in ("missing_link", "wrong_source", "stale_owner"):
            with self.subTest(case=case):
                e, t, p, q = self.fixture()
                e.begin_encounter(e.everyone)
                e.start_round(e.everyone)
                e.start_of_turn(q, initiative_count=20)
                F.move_allowed(e, q, "move/화염방사")
                if case == "missing_link":
                    del t.spec["type_link_skills"]["얼음"]
                elif case == "wrong_source":
                    G.state(p)["sources"][C._source_id(t, p, C.GLACIAL_ICE)]["native_clause_id"] = "forged"
                else:
                    t.spec["feats"] = []
                before = self.raw_authority(e)
                with self.assertRaises(ValueError):
                    e.use_move_on(q, p, "move/화염방사", e.everyone)
                self.assertEqual(before, self.raw_authority(e))


if __name__ == "__main__":
    unittest.main(verbosity=2)
