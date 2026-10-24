"""Direct native-path checks for the nine exact optional fantasy clauses."""
from pathlib import Path
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import frequency as FREQ
import items as ITEMS
import optional_physical_equipment as OPTIONAL
import state_grants as GRANTS
import weapon_actions as WEAPONS
import world_entities as WORLD


CLAUSES = {"FAN-035", "FAN-036", "FAN-042", "FAN-043", "FAN-044",
           "FAN-045", "FAN-046", "FAN-047", "FAN-049"}
ITEMS_IN_BATCH = {item_id for item_id, kind in OPTIONAL.KINDS.items()
                  if kind in {"spread_needle", "nine_flames_staff", "blood_scythe", "shadow_walkers",
                              "fairy_fire_sword", "candy_hammer", "kaladanda", "svalinn",
                              "yata_mirror", "ruyi_staff", "chaos_dunker"}}


class OptionalCatalogNineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")

    def actor(self, name, *, types=("노말",)):
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 25)
        spec = build_trainer(self.r, name, 30, stats, extra={
            "moves": ["move/몸통박치기"], "abilities": [], "edges": ["edge/원소-교감"],
            "edge_choices": {"edge/원소-교감": "노말"},
            "features": ["feat/아케인-훈련"], "feats": ["feat/아케인-훈련"],
            "skills": {"전투": 4, "오컬트학": 4, "집중": 3, "명령": 3},
            "movement": {"land": 6}, "movement_basis": "current", "types": list(types),
        })
        value = Combatant(self.r, spec)
        value.types = list(types)
        return value

    def fixture(self):
        engine = Engine(self.r, seed=113809)
        engine.grid = Grid(30, 15)
        actor = self.actor("catalog-owner-" + str(id(engine)))
        ally = self.actor("catalog-ally-" + str(id(engine)))
        enemy = self.actor("catalog-enemy-" + str(id(engine)), types=("에스퍼",))
        actor.side = ally.side = "player"; enemy.side = "wild"
        actor.pos = (2, 2); ally.pos = (3, 2); enemy.pos = (5, 2)
        for value in (actor, ally, enemy):
            engine.gm.add_combatant(value)
        return engine, actor, ally, enemy

    def equip(self, engine, actor, item_id, suffix):
        uid = "catalog-nine/" + suffix
        WORLD.register_object(engine, uid, kind="item_instance", item_rule_id=item_id,
                              owner_id=actor.entity_id, location={"kind": "unknown"},
                              reason="catalog-nine direct fixture")
        ITEMS.register_item(engine, actor, item_id, source_instance_id=uid)
        self.assertEqual(engine._physical_objects[uid]["equipped_by"], actor.entity_id)
        return uid

    def registration_key(self, actor, uid):
        return next(key for key, row in actor._item_reg.items() if row.get("instance_id") == uid)

    def start_turn(self, engine, actor):
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=20)

    def restored(self, engine):
        return Engine.import_state(self.r, json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))

    def test_policy_exact_sources_and_excluded_mismap(self):
        policy = OPTIONAL.policy(self.r)
        rows = {key: value for key, value in policy["rows"].items() if key in ITEMS_IN_BATCH}
        self.assertEqual(set(rows), ITEMS_IN_BATCH)
        self.assertEqual({row["clause_id"] for row in rows.values()}, CLAUSES)
        self.assertNotIn("FAN-039", {row["clause_id"] for row in rows.values()})
        self.assertIn("FAN-039", policy["excluded_catalog_mappings"])
        status = json.loads((ROOT / "data/verification/category2-optional-clause-status.json").read_text(encoding="utf-8"))
        indexed = {row["clause_id"]: row for row in status["rows"]}
        for row in rows.values():
            expected = [(x["file"], x["start"], x["end"], x["excerpt_sha256"]) for x in indexed[row["clause_id"]]["source"]]
            actual = [(x["file"], x["start"], x["end"], x["excerpt_sha256"]) for x in row["source"]]
            self.assertEqual(actual, expected)

    def test_inactive_optional_catalog_does_not_break_other_rulesets(self):
        rules = Rules(str(ROOT), ruleset="polygon")
        engine = Engine(rules, seed=113810)
        self.assertTrue(OPTIONAL.validate_world(engine, {}))
        self.assertTrue(WORLD.validate_world(engine)["valid"])
        loaded = Engine.import_state(rules, json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))
        self.assertTrue(loaded.validate_state()["valid"])

    def test_live_optional_equipment_still_requires_its_source(self):
        rules = Rules(str(ROOT), ruleset="polygon")
        engine = Engine(rules, seed=113811)
        stats = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 25)
        spec = build_trainer(rules, "inactive-source-owner", 30, stats, extra={
            "moves": ["move/몸통박치기"], "abilities": [], "edges": ["edge/원소-교감"],
            "edge_choices": {"edge/원소-교감": "노말"}, "features": [], "feats": [],
            "skills": {"전투": 4}, "movement": {"land": 6}, "movement_basis": "current",
        })
        actor = Combatant(rules, spec)
        item_id = "crafted_item/스톰-글러브"
        instance_id = "inactive-source/storm-gloves"
        actor.registry.append({
            "type": "optional_physical_equipment", "kind": OPTIONAL.KINDS[item_id],
            "item_id": item_id, "instance_id": instance_id,
        })
        actor._item_reg = {"inactive-source": {"item_id": item_id, "instance_id": instance_id}}
        engine._physical_objects = {instance_id: {
            "kind": "item_instance", "item_rule_id": item_id, "owner_id": actor.entity_id,
            "carrier_id": actor.entity_id, "equipped_by": actor.entity_id,
        }}
        with self.assertRaisesRegex(ValueError, "Excluded rule selection"):
            OPTIONAL.validate_world(engine, {actor.entity_id: actor})

    def test_all_recipe_grants_are_source_owned_and_revoke(self):
        granted = {
            "crafted_item/스프레드-니들": (["move/구슬던지기"], [], []),
            "crafted_item/나인플레임의-스태프": (["move/불꽃튀기기"], ["여우불 [Playtest]"], []),
            "crafted_item/피의-낫": (["move/베어가르기"], [], []),
            "crafted_item/요정의-엉덩이-차는-거친-불검": (["move/베어가르기"], [], []),
            "crafted_item/캔디-해머": ([], [], []),
            "crafted_item/카라단다": (["move/고스트다이브", "move/섀도클로", "move/섀도다이브"], [], []),
            "crafted_item/스-발린": ([], [], []),
            "crafted_item/야타의-거울": ([], [], []),
            "crafted_item/여의금고봉": (["move/마하펀치", "move/불꽃펀치", "move/깨트리기"], [], []),
            "crafted_item/카오스-던커": (["move/지진", "move/그라운드포스", "move/단애의칼"], [], []),
        }
        for index, (item_id, (moves, abilities, capabilities)) in enumerate(granted.items()):
            with self.subTest(item=item_id):
                engine, actor, _, _ = self.fixture()
                uid = self.equip(engine, actor, item_id, "grant-" + str(index))
                for move in moves:self.assertIn(move, actor.moves)
                for ability in abilities:self.assertIn(ability, actor.abilities)
                for capability in capabilities:self.assertIn(capability, GRANTS.effective(actor, "capabilities"))
                ITEMS.unregister_item(engine, actor, registration_key=self.registration_key(actor, uid))
                for move in moves:self.assertNotIn(move, actor.moves)
                for ability in abilities:self.assertNotIn(ability, actor.abilities)
                self.assertNotIn("equipped_by", engine._physical_objects[uid])

    def test_shadow_walkers_retain_one_actual_base_and_remove_both(self):
        engine, actor, _, _ = self.fixture()
        base = self.equip(engine, actor, "crafted_item/경쟁-부츠", "shadow-base")
        shadow = self.equip(engine, actor, "crafted_item/섀도우-워커", "shadow")
        self.assertIn("그림자숨기", GRANTS.effective(actor, "capabilities"))
        base_key = self.registration_key(actor, base)
        self.assertEqual(actor._item_reg[base_key]["retained_by_shadow_walkers"], shadow)
        loaded = self.restored(engine)
        self.assertTrue(loaded.validate_state()["valid"])
        loaded_actor = next(x for x in loaded.everyone if x.entity_id == actor.entity_id)
        ITEMS.unregister_item(loaded, loaded_actor, registration_key=self.registration_key(loaded_actor, shadow))
        self.assertFalse(loaded_actor._item_reg)
        self.assertNotIn("그림자숨기", GRANTS.effective(loaded_actor, "capabilities"))
        self.assertNotIn("equipped_by", loaded._physical_objects[base])
        self.assertNotIn("equipped_by", loaded._physical_objects[shadow])

    def test_weapon_profiles_cover_arcane_fire_candy_ruyi_and_chaos(self):
        cases = (
            ("crafted_item/나인플레임의-스태프", "move/불꽃튀기기", "nine", "특수"),
            ("crafted_item/요정의-엉덩이-차는-거친-불검", "move/베어가르기", "fire", "물리"),
            ("crafted_item/여의금고봉", "move/마하펀치", "ruyi", "물리"),
            ("crafted_item/카오스-던커", "move/지진", "chaos", "물리"),
        )
        for item_id, move_id, suffix, move_class in cases:
            with self.subTest(item=item_id):
                engine, actor, _, enemy = self.fixture()
                uid = self.equip(engine, actor, item_id, suffix)
                move = WEAPONS.prepare(engine, actor, self.r.move(move_id), weapon_id=uid)
                self.assertEqual(move["class"], move_class)
                self.assertEqual(move["_optional_crafted_equipment"]["item_id"], item_id)
                if suffix == "fire":
                    self.assertEqual(move["type"], "불꽃")
                    enemy.types = ["페어리"]
                    self.assertGreaterEqual(OPTIONAL.effectiveness(engine, enemy, move, 0.5), 1.5)
                if suffix == "ruyi":self.assertEqual(move["_weapon_attack"]["range"]["origin"], 5)
                if suffix == "chaos":
                    enemy.types = ["비행"]
                    self.assertEqual(OPTIONAL.effectiveness(engine, enemy, move, 0.0), 1.0)
                    self.assertTrue(OPTIONAL.bypass_ability_immunity(move, "땅"))
        engine, actor, _, enemy = self.fixture()
        uid = self.equip(engine, actor, "crafted_item/캔디-해머", "candy-profile")
        entry = next(x for x in actor.custom_conditions["equipped_weapons"].values() if x["instance_id"] == uid)
        move = WEAPONS.prepare(engine, actor, self.r.move(entry["struggle_id"]), weapon_id=uid)
        self.assertEqual(OPTIONAL.effectiveness(engine, enemy, move, 3.0), 1.0)

    def test_spread_needle_shared_activation_and_failed_selection_are_atomic(self):
        engine, actor, ally, enemy = self.fixture()
        uid = self.equip(engine, actor, "crafted_item/스프레드-니들", "spread")
        ally.side = enemy.side = "wild"
        self.start_turn(engine, actor)
        before = json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "more distinct targets"):
            OPTIONAL.activate_spread_needle(engine, actor, (ally, enemy), fixed_strikes=1)
        self.assertEqual(json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True), before)
        result = OPTIONAL.activate_spread_needle(engine, actor, (enemy,), fixed_strikes=1)
        self.assertTrue(result["activated"])
        self.assertEqual((result["rolled_strikes"], result["targets"], result["damage_base"]),
                         (1, [enemy.entity_id], 2))
        self.assertEqual(actor.move_uses.get("move/구슬던지기"), 1)
        self.assertEqual(next(x for x in actor.custom_conditions["equipped_weapons"].values() if x["instance_id"] == uid)["item_id"],
                         "crafted_item/스프레드-니들")

    def test_blood_scythe_bonus_pending_heal_and_scene_quota(self):
        engine, actor, _, enemy = self.fixture()
        uid = self.equip(engine, actor, "crafted_item/피의-낫", "blood")
        move = WEAPONS.prepare(engine, actor, self.r.move("move/베어가르기"), weapon_id=uid)
        self.assertEqual(OPTIONAL.damage_roll_bonus(engine, actor, enemy, move), 5)
        actor.hp -= 20
        OPTIONAL.observe_attack_damage(engine, actor, enemy, move, {"net_hp_loss": 11})
        out = OPTIONAL.claim_blood_scythe_healing(engine, actor)
        self.assertEqual((out["eligible_damage"], out["healed"]), (11, 5))
        OPTIONAL.observe_attack_damage(engine, actor, enemy, move, {"net_hp_loss": 8})
        snapshot = json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "scene healing spent"):
            OPTIONAL.claim_blood_scythe_healing(engine, actor)
        self.assertEqual(json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True), snapshot)

    def test_candy_daily_heal_svalinn_fire_protection_and_release(self):
        engine, actor, ally, _ = self.fixture()
        candy = self.equip(engine, actor, "crafted_item/캔디-해머", "candy-use")
        actor.hp -= engine.tick(actor) * 3
        self.start_turn(engine, actor)
        out = OPTIONAL.lick_candy_hammer(engine, actor)
        self.assertTrue(out["activated"]); self.assertEqual(out["healed"], engine.tick(actor) * 2)
        with self.assertRaisesRegex(ValueError, "daily lick spent"):
            OPTIONAL.lick_candy_hammer(engine, actor)
        ITEMS.unregister_item(engine, actor, registration_key=self.registration_key(actor, candy))

        svalinn = self.equip(engine, actor, "crafted_item/스-발린", "svalinn")
        self.assertFalse(engine.apply_status(actor, "화상", source="move/불꽃펀치", applied_by=ally))
        self.assertEqual(OPTIONAL.resistance_steps(engine, ally, "불꽃"), 1)
        ITEMS.unregister_item(engine, actor, registration_key=self.registration_key(actor, svalinn))
        self.assertEqual(OPTIONAL.resistance_steps(engine, ally, "불꽃"), 0)

    def test_kaladanda_no_awakening_persists_and_expires_at_24_hours(self):
        engine, actor, _, enemy = self.fixture()
        uid = self.equip(engine, actor, "crafted_item/카라단다", "kaladanda")
        move = WEAPONS.prepare(engine, actor, self.r.move("move/섀도클로"), weapon_id=uid)
        enemy.hp = 0; enemy.conditions.add("기절")
        OPTIONAL.observe_attack_damage(engine, actor, enemy, move, {"net_hp_loss": 10})
        engine.heal(enemy, 5, source_kind="feature")
        self.assertIn("기절", enemy.conditions)
        self.assertFalse(__import__("life").revive(engine, enemy, 10))
        loaded = self.restored(engine)
        loaded_enemy = next(x for x in loaded.everyone if x.entity_id == enemy.entity_id)
        self.assertTrue(loaded.validate_state()["valid"])
        loaded.advance_time(24 * 60 * 60, (loaded_enemy,))
        self.assertNotIn("기절", loaded_enemy.conditions)
        self.assertNotIn(OPTIONAL.NO_AWAKENING, loaded_enemy.custom_conditions)

    def test_yata_reflection_truth_daily_and_ruyi_scene_bounds(self):
        engine, actor, ally, enemy = self.fixture()
        yata = self.equip(engine, actor, "crafted_item/야타의-거울", "yata")
        enemy.custom_conditions["transformed"] = {"source": "test", "copied_actor_id": ally.entity_id, "lifetime": "scene"}
        reflected = OPTIONAL.reveal_observation(engine, actor, enemy, {"status": "unknown", "values": {}})
        self.assertTrue(reflected["yata_reflection"]["transformed"])
        self.start_turn(engine, actor)
        answer = OPTIONAL.ask_yata_truth(engine, actor, enemy, question="누가 보냈나?", truthful_answer="아무도 없다", looking=True)
        self.assertTrue(answer["activated"])
        with self.assertRaisesRegex(ValueError, "daily truth spent"):
            OPTIONAL.ask_yata_truth(engine, actor, enemy, question="다시?", truthful_answer="아니", looking=True)
        ITEMS.unregister_item(engine, actor, registration_key=self.registration_key(actor, yata))

        ruyi = self.equip(engine, actor, "crafted_item/여의금고봉", "ruyi-use")
        enemy.pos = (3, 2); ally.pos = (8, 2)
        engine.end_of_turn(actor); engine.end_round()
        engine.start_round(engine.everyone); engine.start_of_turn(actor, initiative_count=20)
        result = OPTIONAL.activate_ruyi_smite(engine, actor, enemy, "move/마하펀치", engine.everyone,
                                              mode="burst", size=1)
        self.assertTrue(result["activated"]); self.assertTrue(result["smite"])
        engine.end_of_turn(actor); engine.end_round()
        engine.start_round(engine.everyone); engine.start_of_turn(actor, initiative_count=20)
        result = OPTIONAL.activate_ruyi_smite(engine, actor, enemy, "move/불꽃펀치", engine.everyone,
                                              mode="close_blast", size=2)
        self.assertTrue(result["activated"])
        snapshot = json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True)
        with self.assertRaisesRegex(ValueError, "scene frequency spent"):
            OPTIONAL.activate_ruyi_smite(engine, actor, enemy, "move/깨트리기", engine.everyone,
                                          mode="burst", size=1)
        self.assertEqual(json.dumps(engine.export_state(), ensure_ascii=False, sort_keys=True), snapshot)
        self.assertEqual(FREQ.state(actor)["activations"]["optional-equipment:ruyi-smite:" + ruyi]["used"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
