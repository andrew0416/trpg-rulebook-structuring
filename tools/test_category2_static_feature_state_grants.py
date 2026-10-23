"""Direct contracts for the hash-pinned Static Feature state table."""
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import sys
import tempfile
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_trainer
from engine import Combatant, Engine, Rules
from tools.report_category2_progress import collect as collect_category2, SOURCES as PROGRESS_SOURCES
import ability_transitions as ABILITIES
import effects_ext as EXT
import encounter
import items as ITEMS
import movement_actions as MOVEMENT
import state_codec as CODEC
import state_grants as GRANTS
import static_feature_state_grants as STATIC
import tk_mastery as TK_MASTERY
import trainer_feature_acquisition as ACQUISITION


COMPLETION_IDS = {
    "C2CSV/input/db/feats.csv:R404:main",
    "C2CSV/input/db/feats.csv:R507:main",
    "C2CSV/input/db/feats.csv:R513:main",
    "C2CSV/input/db/feats.csv:R587:main",
    "C2CSV/input/db/feats.csv:R623:main",
    "C2CSV/input/db/feats.csv:R643:main",
    "C2CSV/input/db/feats.csv:R644:main",
    "C2CSV/input/db/class-data.csv:R30:blessing",
    "C2CSV/input/db/class-data.csv:R44:blessing",
    "C2CSV/input/db/class-data.csv:R97:blessing",
    "input/ch04-trainer-classes.md:3136-3138",
    "C05-039",
}


class StaticFeatureStateGrantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.policy = json.loads((STAGE / "data/static-feature-state-grants-policy.json").read_text(encoding="utf-8"))

    def fixture(self, cid, *, choice=None, seed=3700):
        row = STATIC.rules(self.rules)[cid]
        owner = cid if row.get("explicit_source") else row.get("owner_id") or cid
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10)
        spec = build_trainer(
            self.rules, "owner-" + str(seed), 30, stats, moves=[], abilities=[],
            extra={
                "classes": [], "feats": [], "edges": [], "feature_choices": {},
                "static_feature_choices": {}, "skills": {"전투": 6, "집중": 6},
                "movement": {"land": 4, "high_jump": 0, "long_jump": 0, "power": 4},
                "movement_basis": "current", "power_basis": "current",
            },
        )
        field = "gifts" if str(owner).startswith("gift/") else "classes" if str(owner).startswith("class/") else "feats"
        spec[field] = [owner]
        if row.get("stat_choice"):
            spec["static_feature_choices"][owner] = choice or row["stat_choice"][0]
        elif row.get("mode") == "class_branch":
            spec["static_feature_choices"][owner] = choice or next(iter(row["branches"]))
        engine = Engine(self.rules, seed=seed)
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        if field == "gifts":
            patrons = {"gift/마이너-기프트-로얄-하트": "라티아스",
                       "gift/메이저-기프트-순수-호흡": "쉐이미",
                       "gift/마이너-기프트-드림-마스터리": "크레세리아"}
            actor.spec["gift_patrons"] = {owner: patrons[owner]}
            if owner == "gift/메이저-기프트-순수-호흡":
                prerequisite = "gift/마이너-기프트-식물-직감"
                actor.spec["gifts"].append(prerequisite)
                actor.spec["gift_patrons"][prerequisite] = "쉐이미"
                engine.confirm_blessing_gift(actor, prerequisite, reason="actual acquired Shaymin prerequisite")
            engine.confirm_blessing_gift(actor, owner, reason="actual acquired Gift and named patron permission")
        return engine, actor, row, owner, field

    @staticmethod
    def source_row(actor, cid):
        found = [row for row in actor.spec[GRANTS.KEY]["sources"].values()
                 if row.get("clause_id") == cid]
        if len(found) != 1:
            raise AssertionError((cid, found))
        return found[0]

    def test_exact_37_rule_policy_hashes_catalog_bindings_and_12_completion_ids(self):
        rows = STATIC.rules(self.rules)
        # Original 37 rows and their historical completion scope are retained;
        # two Ability lessons and ranked Athletic HP reuse only printed tags.
        self.assertEqual(len(rows), 47)
        self.assertEqual(sum(row["source_file"].endswith(".csv") for row in rows.values()), 37)
        self.assertEqual(set(self.policy["completion_ids"]), COMPLETION_IDS)
        self.assertEqual(len(self.policy["deduped_consumers"]), 26)
        for cid, row in rows.items():
            with self.subTest(clause=cid):
                self.assertEqual(row["id"], cid)
                acquisition = cid if row.get("explicit_source") else row.get("owner_id") or cid
                self.assertEqual(STATIC.identity(self.rules, acquisition), cid)

    def test_profile_excluded_static_dependencies_do_not_block_other_actors(self):
        rules = Rules(str(ROOT), ruleset="core")
        row = STATIC.rules(rules)["C2CSV/input/db/feats.csv:R513:main"]
        self.assertEqual(row["abilities"][0]["id"], "ability/트랜스포터-playtest")
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10)
        spec = build_trainer(
            rules, "profile-owner", 30, stats, moves=[], abilities=[],
            extra={"classes": [], "feats": [row["owner_id"]], "edges": [],
                   "feature_choices": {}, "static_feature_choices": {},
                   "skills": {"전투": 6, "집중": 6},
                   "movement": {"land": 4, "high_jump": 0, "long_jump": 0, "power": 4},
                   "movement_basis": "current", "power_basis": "current"},
        )
        actor = Combatant(rules, spec)
        engine = Engine(rules, seed=4050)
        engine.everyone = engine.gm.everyone = [actor]
        self.assertEqual(STATIC.plan(actor), {})
        self.assertEqual(STATIC.register_all(engine, actor), 0)
        self.assertTrue(STATIC.validate(actor))

    def test_all_23_fixed_move_stat_rows_use_native_moves_stats_and_owner_lifetime(self):
        rows = {cid: row for cid, row in STATIC.rules(self.rules).items()
                if row.get("moves") and row.get("stat") and not row.get("stat_choice")}
        self.assertEqual(len(rows), 23)
        for index, (cid, row) in enumerate(rows.items()):
            with self.subTest(clause=cid):
                engine, actor, _, owner, field = self.fixture(cid, seed=4100 + index)
                before = actor.stats[row["stat"]]
                self.assertGreaterEqual(ITEMS.register_feats(engine, actor), 1)
                self.assertTrue(set(row["moves"]).issubset(encounter.usable_moves(engine, actor)))
                self.assertEqual(actor.stats[row["stat"]], before + 1)
                receipt = self.source_row(actor, cid)
                self.assertEqual((receipt["source_contract"], receipt["lifetime"]),
                                 ("acquired_static_feature_state_projection", "while_owned"))
                stable = deepcopy(actor.spec[GRANTS.KEY])
                ITEMS.register_feats(engine, actor)
                self.assertEqual(actor.spec[GRANTS.KEY], stable)
                actor.spec[field].remove(owner)
                ITEMS.register_feats(engine, actor)
                self.assertFalse(set(row["moves"]) & set(actor.moves))
                self.assertEqual(actor.stats[row["stat"]], before)

    def test_stored_power_pair_is_exact_and_not_the_old_psyshock_mismatch(self):
        cid = "C2CSV/input/db/feats.csv:R507:main"
        engine, actor, row, _, _ = self.fixture(cid)
        ITEMS.register_feats(engine, actor)
        self.assertEqual(row["moves"], [self.rules.move_id("신통력"), self.rules.move_id("어시스트파워")])
        self.assertNotIn(self.rules.move_id("사이코쇼크"), row["moves"])
        self.assertTrue(set(row["moves"]).issubset(encounter.usable_moves(engine, actor)))

    def test_four_stat_choices_are_separate_from_move_choices_and_fail_atomically(self):
        rows = {cid: row for cid, row in STATIC.rules(self.rules).items() if row.get("stat_choice")}
        self.assertEqual(len(rows), 4)
        for index, (cid, row) in enumerate(rows.items()):
            with self.subTest(clause=cid):
                engine, actor, _, owner, _ = self.fixture(cid, seed=5100 + index)
                selected, replacement = row["stat_choice"]
                ITEMS.register_feats(engine, actor)
                self.assertEqual(actor.stats[selected], 11)
                if cid.endswith("R597:main") or cid.endswith("R598:main"):
                    self.assertEqual(set(self.source_row(actor, cid)["grants"]["moves"]), set(row["moves"]))
                actor.spec["static_feature_choices"][owner] = replacement
                before = deepcopy((actor.spec, actor.stats, actor.moves, actor.abilities,
                                   getattr(actor, "status_immune", set()),
                                   getattr(actor, "weather_immune", set()), engine.rng.getstate()))
                with self.assertRaisesRegex(ValueError, "source identity|immutable"):
                    ITEMS.register_feats(engine, actor)
                self.assertEqual((actor.spec, actor.stats, actor.moves, actor.abilities,
                                  getattr(actor, "status_immune", set()),
                                  getattr(actor, "weather_immune", set()), engine.rng.getstate()), before)
        cid = next(iter(rows))
        engine, actor, _, owner, _ = self.fixture(cid, seed=5199)
        actor.spec["static_feature_choices"].pop(owner)
        before = deepcopy((actor.spec, actor.stats, actor.moves, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "explicit Static Feature stat choice"):
            ITEMS.register_feats(engine, actor)
        self.assertEqual((actor.spec, actor.stats, actor.moves, engine.rng.getstate()), before)

    def test_farcast_ability_and_both_class_branch_tables_use_native_ability_consumers(self):
        cid = "C2CSV/input/db/feats.csv:R513:main"
        engine, actor, row, owner, field = self.fixture(cid)
        ITEMS.register_feats(engine, actor)
        aid = row["abilities"][0]["id"]
        self.assertIn(aid, ABILITIES.known(actor))
        actor.spec[field].remove(owner)
        ITEMS.register_feats(engine, actor)
        self.assertNotIn(aid, ABILITIES.known(actor))
        for cid in ("C2CSV/input/db/feats.csv:R587:main", "C2CSV/input/db/feats.csv:R643:main"):
            row = STATIC.rules(self.rules)[cid]
            for offset, (branch, declaration) in enumerate(row["branches"].items()):
                with self.subTest(clause=cid, branch=branch):
                    engine, actor, _, _, _ = self.fixture(cid, choice=branch, seed=5300 + offset)
                    child = next(uid for uid, unit in self.rules.selection.units.items()
                                 if uid.startswith("feat/") and any(
                                     str(part).split("(", 1)[0].strip() == row["class_marker"]
                                     for part in (unit.get("source", {}).get("path", ()) or ())))
                    actor.spec["feats"].append(child)
                    STATIC.register_all(engine, actor)
                    self.assertIn(declaration["abilities"][0]["id"], ABILITIES.known(actor))
                    self.assertEqual(actor.stats[declaration["stat"]], 12)
                    STATIC.validate(actor)

    def test_martial_receipt_drives_six_stat_mappings_and_dynamic_feature_count(self):
        cid = "C2CSV/input/db/feats.csv:R404:main"
        row = STATIC.rules(self.rules)[cid]
        for index, (ability, stat) in enumerate(row["stat_by_ability"].items()):
            with self.subTest(ability=ability):
                stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10)
                spec = build_trainer(self.rules, "martial-" + str(index), 30, stats, moves=[],
                                     extra={"classes": [], "feats": [], "edges": ["edge/기본-무술"],
                                            "skills": {"전투": 6}, "feature_choices": {},
                                            "static_feature_choices": {}})
                engine = Engine(self.rules, seed=6000 + index)
                actor = Combatant(self.rules, spec)
                engine.everyone = engine.gm.everyone = [actor]
                ACQUISITION.acquire_martial_artist(
                    engine, actor, acquisition_request_id="martial/" + str(index),
                    selected_ability=ability,
                    lifecycle_policy=ACQUISITION.LIFECYCLE_WHILE_OWNED,
                )
                STATIC.register_all(engine, actor)
                self.assertEqual(actor.stats[stat], 11)
                child = next(uid for uid, unit in self.rules.selection.units.items()
                             if uid.startswith("feat/") and any(
                                 str(part).split("(", 1)[0].strip() == self.rules.selection.units["class/무술가"]["title"]
                                 for part in (unit.get("source", {}).get("path", ()) or ())))
                actor.spec["feats"].append(child)
                STATIC.register_all(engine, actor)
                self.assertEqual(actor.stats[stat], 12)
                STATIC.validate(actor)

    def test_capability_status_keyword_and_weather_consumers_follow_source_lifetime(self):
        from grid import Grid
        import turn
        for cid in ("C2CSV/input/db/feats.csv:R623:main", "C2CSV/input/db/feats.csv:R644:main",
                    "C2CSV/input/db/feats.csv:R651:main", "C2CSV/input/db/feats.csv:R658:main"):
            engine, actor, row, owner, field = self.fixture(cid)
            engine.grid = Grid(4, 2)
            engine.grid.slow = {(1, 0)}
            ITEMS.register_feats(engine, actor)
            self.assertTrue(set(row.get("capabilities", ())).issubset(GRANTS.effective_capabilities(actor)))
            for capability in row.get("capabilities", ()):
                match = re.search(r"자연걸음\s*\(([^)]+)\)", capability)
                if match:
                    MOVEMENT.observe_cell_terrain(engine, [(1, 0)], [match.group(1)], "exact reviewed terrain")
                    self.assertEqual(MOVEMENT.slow_terrain_penalty(engine, actor, (1, 0), "육상"), 0)
            for status in row.get("status_immune", ()):
                engine.apply_status(actor, status)
                self.assertNotIn(status, actor.conditions)
            if row.get("keyword_immune"):
                move = self.rules.move("move/독가루")
                self.assertTrue(EXT.blocks_hit(engine, actor, actor, move, self.rules.move_mech(move["id"])[0]))
            if row.get("weather_immune"):
                engine.weather = "hail"
                hp = actor.hp
                turn.weather_turn_start(engine, actor)
                self.assertEqual(actor.hp, hp)
            actor.spec[field].remove(owner)
            ITEMS.register_feats(engine, actor)
            self.assertFalse(set(row.get("capabilities", ())) & set(GRANTS.effective_capabilities(actor)))

    def test_all_12_move_immunities_block_hit_boundary_and_revoke_cleanly(self):
        total = 0
        for cid in ("C2CSV/input/db/class-data.csv:R44:blessing", "C2CSV/input/db/class-data.csv:R97:blessing"):
            engine, actor, row, owner, field = self.fixture(cid)
            ITEMS.register_feats(engine, actor)
            for move_id in row["move_immune"]:
                with self.subTest(clause=cid, move=move_id):
                    move = self.rules.move(move_id)
                    mechanics = self.rules.move_mech(move_id)[0]
                    self.assertEqual(EXT.blocks_hit(engine, actor, actor, move, mechanics),
                                     "state/move_immunity:" + move_id)
                    total += 1
            sample = self.rules.move(row["move_immune"][0])
            self.assertFalse(engine.accuracy_check(actor, actor, sample, fixed_roll=20)[0])
            actor.spec[field].remove(owner)
            ITEMS.register_feats(engine, actor)
            self.assertIsNone(EXT.blocks_hit(engine, actor, actor, sample,
                                             self.rules.move_mech(sample["id"])[0]))
        self.assertEqual(total, 12)

    def test_telekinetic_class_and_actual_equipment_close_human_capability_sources(self):
        cid = "input/ch04-trainer-classes.md:3136-3138"
        engine, actor, row, owner, field = self.fixture(cid)
        ITEMS.register_feats(engine, actor)
        self.assertIn("염력", GRANTS.effective_capabilities(actor))
        self.assertTrue(TK_MASTERY.owned(actor))
        import telekinetic_load as TK_LOAD
        TK_LOAD.require(engine, actor)
        actor.spec[field].remove(owner)
        ITEMS.register_feats(engine, actor)
        self.assertFalse(TK_MASTERY.owned(actor))
        self.assertGreaterEqual(ITEMS.register_item(engine, actor, "item/암시고글"), 1)
        self.assertIn("암흑시야", GRANTS.effective_capabilities(actor))
        ITEMS.unregister_item(engine, actor, "item/암시고글")
        self.assertNotIn("암흑시야", GRANTS.effective_capabilities(actor))

    def test_source_removal_preserves_baselines_and_codec_restore_validates_receipts(self):
        cid = "C2CSV/input/db/feats.csv:R623:main"
        engine, actor, row, owner, field = self.fixture(cid)
        actor.spec["capabilities"] = [row["capabilities"][0]]
        actor.status_immune = set(row["status_immune"])
        ITEMS.register_feats(engine, actor)
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)))
        copy = loaded.everyone[0]
        STATIC.validate(copy)
        copy.spec[field].remove(owner)
        ITEMS.register_feats(loaded, copy)
        self.assertIn(row["capabilities"][0], GRANTS.effective_capabilities(copy))
        self.assertIn(row["status_immune"][0], copy.status_immune)
        self.assertEqual(copy.stats[row["stat_choice"][0]], 10)
        self.assertTrue(loaded.validate_state()["valid"])

    def test_shadow_progress_adds_exactly_12_without_counting_26_deduped_rows(self):
        with tempfile.TemporaryDirectory(prefix="static-feature-") as tmp:
            shadow = Path(tmp)
            plan_path = ROOT / "data/verification/category2-edge-work-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            files = {p for p in (ROOT / "input").rglob("*") if p.is_file()}
            files.update(ROOT / "data/verification" / name for _, name, _ in PROGRESS_SOURCES)
            files.update((plan_path, ROOT / "data/verification/category2-scope-freeze.json"))
            files.update(ROOT / proof["log"] for route in plan["post_foundation_reuse"]["itemized_audit"]["routes"].values()
                         for proof in route["evidence"])
            for source in sorted(files):
                target = shadow / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source, target)
                except OSError:
                    target.write_bytes(source.read_bytes())
            # Seed only the exact historical targets; keep every deduped row unchanged.
            registries = {}
            found = set()
            csv_path = shadow / "data/verification/category2-class-csv-clause-status.json"
            data = json.loads(csv_path.read_text(encoding="utf-8")); csv_path.unlink()
            csv_rows = data.get("rows", data.get("entries", data.get("new_clauses", [])))
            for entry in csv_rows:
                if entry.get("id") in COMPLETION_IDS:
                    self.assertTrue(entry["include_category2"])
                    self.assertIsNone(entry["dedupe_target"])
                    entry["status"] = "incomplete"; found.add(entry["id"])
            registries[csv_path] = (data, csv_rows, "id", "status")
            csv_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            class_path = shadow / "data/verification/category2-class-clause-status.json"
            data = json.loads(class_path.read_text(encoding="utf-8")); class_path.unlink()
            for entry in data["entries"]:
                if entry["source_clause_id"] in COMPLETION_IDS:
                    self.assertTrue(entry["include_category2"])
                    entry["status"] = "incomplete"; found.add(entry["source_clause_id"])
            registries[class_path] = (data, data["entries"], "source_clause_id", "status")
            class_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            core_path = shadow / "data/verification/category2-core-clause-status.json"
            data = json.loads(core_path.read_text(encoding="utf-8")); core_path.unlink()
            for entry in data["clause_mappings"]:
                if entry["clause_id"] == "C05-039":
                    self.assertTrue(entry["category2_included"])
                    entry["category2_implemented"] = None
                    entry["category2_status"] = "incomplete"; found.add(entry["clause_id"])
            registries[core_path] = (data, data["clause_mappings"], "clause_id", "category2_status")
            core_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assertEqual(found, COMPLETION_IDS)
            before = collect_category2(shadow)
            self.assertEqual(before["validation_errors"], [])
            self.assertTrue(before["denominator_frozen"])
            self.assertEqual(before["denominator"], 2352)
            for path, (data, rows, identity, status) in registries.items():
                for entry in rows:
                    if entry[identity] in COMPLETION_IDS:
                        entry[status] = "implemented"
                        if status == "category2_status": entry["category2_implemented"] = True
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            after = collect_category2(shadow)
        self.assertEqual(after["validation_errors"], [])
        self.assertEqual(after["denominator"], before["denominator"])
        self.assertEqual(after["included_clause_ids"], before["included_clause_ids"])
        self.assertEqual(after["completed_clause_count"] - before["completed_clause_count"], 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
