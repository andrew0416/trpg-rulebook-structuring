"""Direct tests for the exact CSV class-passive combat projection cluster."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "input").is_dir():
    ROOT = Path(r"D:/trpg-rulebook-structuring/ptk-structure-experiment")
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import class_passive_combat as C
import combat_precision_features as CPF
import items as ITEMS
import state_codec as CODEC
import state_grants as GRANTS
import turn as TURN
import world_entities as WORLD


CLAUSE_IDS = set(C.CLAUSE_BY_RULE.values())


class ClassPassiveCombatBulkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="all")

    def fixture(self, *, feats=(), gifts=(), techniques=(), choices=None,
                pokemon_types=None, enemy_types=None, pokemon_moves=(), trainer_moves=()):
        engine = Engine(self.rules, seed=1717)
        engine.grid = Grid(12, 8)
        trainer = Combatant(
            self.rules,
            build_trainer(
                self.rules,
                "Owner",
                30,
                {"hp": 40, "atk": 12, "def": 12, "spa": 12, "spd": 12, "spe": 12},
                moves=list(trainer_moves),
                abilities=[],
                skills={"명령": "숙련", "집중": "숙련", "생존": "숙련", "육상": "숙련", "협박": "숙련"},
                extra={
                    "feats": list(feats),
                    "edges": [],
                    "gifts": [] if C.BLESSED_RESILIENCE in gifts else list(gifts),
                    "techniques": list(techniques),
                    "class_passive_choices": deepcopy(choices or {}),
                    "type_link_skills": {"벌레": "명령", "불꽃": "집중", "얼음": "생존"},
                },
            ),
        )
        pokemon_extra = {"trainer_id": trainer.entity_id, "trainer": trainer.name}
        if pokemon_types is not None:
            pokemon_extra["types"] = list(pokemon_types)
        pokemon = Combatant(
            self.rules,
            build_pokemon(self.rules, "이상해씨", 20, name="Partner",
                          moves=list(pokemon_moves), abilities=[], extra=pokemon_extra),
        )
        enemy_extra = {}
        if enemy_types is not None:
            enemy_extra["types"] = list(enemy_types)
        enemy = Combatant(
            self.rules,
            build_pokemon(self.rules, "꼬부기", 20, name="Enemy",
                          moves=["몸통박치기", "화염방사", "은빛바람"], abilities=[], extra=enemy_extra),
        )
        for actor, pos, side in ((trainer, (0, 0), "party"), (pokemon, (1, 0), "party"),
                                 (enemy, (2, 0), "foe")):
            engine.gm.add_combatant(actor, pos=pos, side=side, reason="actual class passive fixture")
        if C.BLESSED_RESILIENCE in gifts:
            patron = Combatant(self.rules, build_pokemon(self.rules, "스이쿤", 30, moves=[], abilities=[]))
            engine.gm.add_combatant(patron, pos=(10, 7), side="party", reason="actual divine Water patron")
            trainer.spec["gifts"] = ["gift/축복받은-힘", *gifts]
            trainer.spec["gift_patrons"] = {C.BLESSED_RESILIENCE: patron.entity_id}
            choice = trainer.spec["class_passive_choices"][C.BLESSED_RESILIENCE]
            choice.update(patron_id=patron.entity_id, eligible_types=["불꽃", "물", "얼음", "강철"])
            engine.confirm_blessing_gift(trainer, C.BLESSED_RESILIENCE, reason="actual patron resistance domain and role choice")
        for actor in (trainer, pokemon, enemy):
            engine.register_abilities(actor)
        engine.gm.observe_sensory_environment(trainer,pokemon,paths={"auditory":True},present=True,reason="actual Order delivery")
        return engine, trainer, pokemon, enemy

    def activate(self, engine, trainer, pokemon, uid):
        if not engine.encounter_active:
            engine.begin_encounter(engine.everyone)
        if engine.round_start_seconds is None:
            engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        return engine.activate_class_passive(trainer, pokemon, uid)

    def snapshot(self, engine, *actors):
        return (
            [deepcopy(actor.spec) for actor in actors],
            [deepcopy(getattr(actor, "budget", None)) for actor in actors],
            [deepcopy(getattr(actor, "_action_history", [])) for actor in actors],
            engine.rng.getstate(),
            list(engine.log_lines),
        )

    def test_exact_twelve_policy_rows_hashes_and_selected_sources(self):
        policy = C._policy(self.rules)
        self.assertEqual(set(policy["completion_ids"]), CLAUSE_IDS)
        self.assertEqual(len(policy["clauses"]), 12)
        for relative, digest in policy["source_files"].items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)
        registry = json.loads(
            (ROOT / "data/verification/category2-class-csv-clause-status.json").read_text(encoding="utf-8")
        )
        indexed = {row["id"]: row for row in registry["rows"]}
        source_rows = {}
        for source_file in ("input/db/feats.csv", "input/db/class-data.csv"):
            with (ROOT / source_file).open(encoding="utf-8-sig", newline="") as handle:
                source_rows[source_file] = list(csv.reader(handle))
        for uid, clause_id in C.CLAUSE_BY_RULE.items():
            source = indexed[clause_id]
            actual = [source_rows[source["file"]][source["csv_record"] - 1][column - 1]
                      for column in source["columns"]]
            digest = hashlib.sha256(
                json.dumps(actual, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest()
            self.assertEqual(digest, source["cell_sha256"])
            self.assertEqual(policy["clauses"][clause_id]["cell_sha256"], digest)
            self.assertTrue(source["include_category2"])
            self.assertEqual(source["status"], "implemented")
            self.assertIsNone(source["dedupe_target"])
            self.assertEqual(self.rules._selected_rule(uid), uid)

    def test_species_savant_projects_all_six_stats_once_and_retracts(self):
        choices = {C.SPECIES_SAVANT: {"evolution_group": "pokemon/이상해씨"}}
        e, t, p, q = self.fixture(feats=[C.SPECIES_SAVANT], choices=choices)
        for field in ("hp", "atk", "def", "spa", "spd", "spe"):
            self.assertEqual(p.stats[field], p.spec["stats"][field] + 1)
            self.assertEqual(q.stats[field], q.spec["stats"][field])
        e.register_abilities(p)
        self.assertEqual(p.stats["atk"], p.spec["stats"]["atk"] + 1)
        source = next(sid for sid, row in GRANTS.state(p)["sources"].items()
                      if row.get("rule_id") == C.SPECIES_SAVANT)
        GRANTS.revoke(p, source, engine=e)
        self.assertEqual(p.stats, p.spec["stats"])

    def test_all_five_stratagems_share_atomic_two_ap_owner_target_lifetime(self):
        for uid in sorted(C.STRATAGEMS):
            with self.subTest(uid=uid):
                e, t, p, _ = self.fixture(feats=[uid])
                e.begin_encounter(e.everyone)
                e.start_round(e.everyone)
                e.start_of_turn(t)
                before = self.snapshot(e, t, p)
                t.spec["ap_removed"] = t.ap_account.maximum()
                rejected = self.snapshot(e, t, p)
                with self.assertRaisesRegex(ValueError, "two available AP"):
                    e.activate_class_passive(t, p, uid)
                self.assertEqual(self.snapshot(e, t, p), rejected)
                t.spec["ap_removed"] = 0
                self.assertEqual(e.activate_class_passive(t, p, uid), (1, 0))
                row = p.spec[C.STATE]["sustains"][uid]
                self.assertEqual(t.spec["ap_bound"][row["instance"]], 2)
                self.assertEqual(row["clause_id"], C.CLAUSE_BY_RULE[uid])
                with self.assertRaisesRegex(ValueError, "only one Stratagem"):
                    e.activate_class_passive(t, p, uid)
                self.assertEqual(e.release_class_passive(t, p, uid), (1, 0))
                self.assertFalse(p.spec[C.STATE]["sustains"])
                self.assertFalse(t.spec["ap_bound"])

    def test_reckless_advance_consumes_damage_hit_and_round_status_paths(self):
        e, t, p, q = self.fixture(feats=[C.RECKLESS], pokemon_moves=["몸통박치기"])
        self.activate(e, t, p, C.RECKLESS)
        move = self.rules.move("move/몸통박치기")
        baseline = C.damage_roll_modifier(e, p, q, move, 1.0)
        self.assertEqual(baseline, 8)
        e.end_of_turn(t)
        e.start_of_turn(p, initiative_count=10)
        C.after_move(e, p, q, move, self.rules.move_mech(move["id"])[0], 18, 5)
        self.assertIn("넘어짐", q.conditions)
        self.assertIn("취약", p.conditions)
        records = p.custom_conditions.get("combat_timed_effects", [])
        self.assertTrue(any(row.get("source") == C.RECKLESS and row.get("statuses") == ["취약"]
                            for row in records))
        e.end_of_turn(p)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(t, initiative_count=20)
        self.assertIn("취약", p.conditions)
        e.end_of_turn(t)
        e.start_of_turn(p, initiative_count=10)
        self.assertNotIn("취약", p.conditions)

    def test_trick_shot_and_capricious_whirl_use_native_accuracy_consumers(self):
        e, t, p, q = self.fixture(feats=[C.TRICK_SHOT], pokemon_moves=["화염방사"])
        self.activate(e, t, p, C.TRICK_SHOT)
        move = self.rules.move("move/화염방사")
        hit, natural, critical = e._accuracy_check_native(p, q, move, fixed_roll=17)
        self.assertTrue(hit)
        self.assertEqual(natural, 17)
        self.assertTrue(critical)
        self.assertTrue(any("AC 4+" in line for line in e.log_lines))

        e, t, p, q = self.fixture(feats=[C.CAPRICIOUS], pokemon_moves=["몸통박치기"])
        self.activate(e, t, p, C.CAPRICIOUS)
        attack = self.rules.move("move/몸통박치기")
        hit, _, _ = e._accuracy_check_native(q, p, attack, fixed_roll=5)
        self.assertFalse(hit)
        self.assertEqual(C.damage_roll_modifier(e, p, q, attack, 1.0), -5)

    def test_virtuoso_adaptive_neutral_bug_damage_recomputes_eight_after_restore_without_eight_dice(self):
        import skill_modifiers as SKILL
        e,t,p,q=self.fixture(feats=[C.ADAPTIVE],pokemon_moves=["은빛바람"])
        e.gm.set_skill(t,"명령",6,reason="actual Master Type Link skill before Virtuoso acquisition")
        GRANTS.transition(e,t,lambda engine,owner:owner.spec.update(
            edges=[*owner.spec["edges"],"edge/거장"],edge_choices={"edge/거장":["명령"]}))
        self.assertEqual(SKILL.effective_rank(e.r,t,"명령"),8)
        self.activate(e,t,p,C.ADAPTIVE);ids=[a.entity_id for a in (t,p,q)]
        e=CODEC.load_engine(Rules(str(e.r.root),ruleset="all"),json.loads(json.dumps(CODEC.dump_engine(e))))
        index=WORLD.actor_index(e);t,p,q=[index[uid] for uid in ids]
        self.assertEqual(SKILL.rank(e.r,t,"명령")[2],6)
        self.assertEqual(e.type_multiplier("벌레",q)[0],1.0)
        self.assertEqual(C.damage_roll_modifier(e,p,q,e.r.move("move/은빛바람"),1.0),8)

    def test_adaptive_evolution_uses_post_hook_effectiveness_for_all_three_branches(self):
        e, t, p, q = self.fixture(feats=[C.ADAPTIVE], enemy_types=["풀"], pokemon_moves=["은빛바람"])
        self.activate(e, t, p, C.ADAPTIVE)
        move = self.rules.move("move/은빛바람")
        mechanics = self.rules.move_mech(move["id"])[0]
        self.assertEqual(C.accuracy_bonus(e, p, q, move, mechanics), 2)
        q._types = ["노말"]
        self.assertEqual(C.damage_roll_modifier(e, p, q, move, 1.0), 4)
        q._types = ["불꽃"]
        multiplier = e.type_multiplier("벌레", q)[0]
        self.assertLess(multiplier, 1)
        self.assertEqual(C.effectiveness_modifier(e, p, move, multiplier), 1.0)

    def test_virtuoso_shining_flame_recomputes_eight_after_restore_without_eight_dice(self):
        import skill_modifiers as SKILL
        e,t,p,q=self.fixture(feats=[C.SHINING_FLAME],pokemon_moves=["니트로차지"])
        e.gm.set_skill(t,"집중",6,reason="actual Master Type Link skill before Virtuoso acquisition")
        GRANTS.transition(e,t,lambda engine,owner:owner.spec.update(
            edges=[*owner.spec["edges"],"edge/거장"],edge_choices={"edge/거장":["집중"]}))
        self.assertEqual(SKILL.effective_rank(e.r,t,"집중"),8)
        q.conditions.add("화상");ids=[a.entity_id for a in (t,p,q)]
        e=CODEC.load_engine(Rules(str(e.r.root),ruleset="all"),json.loads(json.dumps(CODEC.dump_engine(e))))
        index=WORLD.actor_index(e);t,p,q=[index[uid] for uid in ids]
        self.assertEqual(SKILL.rank(e.r,t,"집중")[2],6)
        self.assertEqual(C.damage_roll_modifier(e,p,q,e.r.move("move/니트로차지"),1.0),8)

    def test_shining_flame_and_burning_brand_split_owner_scope_and_burn_move_exception(self):
        e, t, p, q = self.fixture(feats=[C.SHINING_FLAME], pokemon_moves=["니트로차지", "불꽃세례"])
        fire = self.rules.move("move/니트로차지")
        C.after_move(e, p, q, fire, self.rules.move_mech(fire["id"])[0], 18, 5)
        self.assertIn("화상", q.conditions)
        q.conditions.discard("화상")
        ember = self.rules.move("move/불꽃세례")
        self.assertEqual(CPF.effect_natural(e, p, ember, 15), 18)
        self.assertEqual(C.effect_range_bonus(e, p, ember, self.rules.move_mech(ember["id"])[0]), 3)
        q.conditions.add("화상")
        self.assertEqual(C.damage_roll_modifier(e, p, q, fire, 1.0), 4)

        e, t, p, q = self.fixture(feats=[C.BURNING_BRAND], trainer_moves=["니트로차지", "불꽃세례"])
        fire = self.rules.move("move/니트로차지")
        C.after_move(e, t, q, fire, self.rules.move_mech(fire["id"])[0], 19, 5)
        self.assertIn("화상", q.conditions)
        ember = self.rules.move("move/불꽃세례")
        self.assertEqual(CPF.effect_natural(e, t, ember, 16), 18)

    def test_virtuoso_glacial_type_link_recomputes_eight_after_restore_without_eight_dice(self):
        import skill_modifiers as SKILL
        e,t,p,q=self.fixture(feats=[C.GLACIAL_ICE],pokemon_types=["얼음"])
        e.gm.set_skill(t,"생존",6,reason="actual Master Type Link skill before Virtuoso acquisition")
        GRANTS.transition(e,t,lambda engine,owner:owner.spec.update(
            edges=[*owner.spec["edges"],"edge/거장"],edge_choices={"edge/거장":["생존"]}))
        self.assertEqual(SKILL.effective_rank(e.r,t,"생존"),8)
        ids=[a.entity_id for a in (t,p,q)]
        e=CODEC.load_engine(Rules(str(e.r.root),ruleset="all"),json.loads(json.dumps(CODEC.dump_engine(e))))
        index=WORLD.actor_index(e);t,p,q=[index[uid] for uid in ids]
        self.assertEqual(SKILL.rank(e.r,t,"생존")[2],6)
        move=e.r.move("move/화염방사");multiplier=e.type_multiplier("불꽃",p)[0]
        self.assertGreater(multiplier,1)
        self.assertEqual(C.damage_reduction(e,q,p,move,multiplier,False),8)

    def test_glacial_ice_uses_actual_super_effective_type_and_type_link_rank(self):
        e, t, p, q = self.fixture(feats=[C.GLACIAL_ICE], pokemon_types=["얼음"])
        fire = self.rules.move("move/화염방사")
        multiplier = e.type_multiplier("불꽃", p)[0]
        self.assertGreater(multiplier, 1)
        self.assertEqual(C.damage_reduction(e, q, p, fire, multiplier, False), 4)
        neutral = dict(fire, type="노말")
        self.assertEqual(C.damage_reduction(e, q, p, neutral, 1.0, False), 0)

    def test_perfectly_ordinary_maximizes_first_damage_instance_and_survives_codec(self):
        e, t, p, q = self.fixture(feats=[C.PERFECT], pokemon_moves=["몸통박치기"])
        self.activate(e, t, p, C.PERFECT)
        move = self.rules.move("move/몸통박치기")
        before_rng = e.rng.getstate()
        single = C.perfect_damage(e, p, move, "2d6+8", 1)
        self.assertEqual(single, (20, [6, 6]))
        self.assertEqual(e.rng.getstate(), before_rng)
        critical = C.perfect_damage(e, p, move, "2d6+8", 2, fixed=[1, 1, 2, 2])
        self.assertEqual(critical[0], 32)
        payload = json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False))
        loaded = CODEC.load_engine(self.rules, payload)
        index = WORLD.actor_index(loaded)
        lp = index[p.entity_id]
        self.assertIsNotNone(C._active(loaded, lp, C.PERFECT))

    def test_blessed_resilience_roles_selection_failure_atomicity_and_scene_end(self):
        messiah_choice = {C.BLESSED_RESILIENCE: {
            "role": "messiah", "eligible_types": ["불꽃", "물", "풀"],
            "selected_types": ["불꽃", "물"],
        }}
        e, t, _, q = self.fixture(gifts=[C.BLESSED_RESILIENCE], choices=messiah_choice)
        self.assertEqual(C.resistance_steps(e, t, "불꽃"), 1)
        self.assertEqual(C.resistance_steps(e, t, "전기"), 0)

        contractor_choice = {C.BLESSED_RESILIENCE: {
            "role": "contractor", "eligible_types": ["불꽃", "물", "풀"],
        }}
        e, t, _, q = self.fixture(gifts=[C.BLESSED_RESILIENCE], choices=contractor_choice)
        e.begin_encounter(e.everyone); e.start_round(e.everyone); e.start_of_turn(t)
        t.budget["standard"] = 0
        before = self.snapshot(e, t)
        self.assertEqual(e.activate_blessed_resilience(t, "불꽃"), (0, 1))
        after = self.snapshot(e, t)
        self.assertEqual(after[:4], before[:4])
        self.assertGreater(len(after[4]), len(before[4]))
        t.budget["standard"] = 1
        import action_points as AP
        available = AP.available(t)
        self.assertEqual(e.activate_blessed_resilience(t, "불꽃"), (1, 0))
        self.assertEqual(AP.available(t), available - 1)
        self.assertEqual(C.resistance_steps(e, t, "불꽃"), 1)
        e.end_scene(e.everyone)
        self.assertEqual(C.resistance_steps(e, t, "불꽃"), 0)

    def test_hat_trick_and_reinforced_clothing_use_real_equipment_price_slot_and_nonstack(self):
        e, t, p, q = self.fixture(techniques=[C.HAT_TRICK, C.REINFORCED_CLOTHING])
        physical = self.rules.move("move/몸통박치기")
        self.assertEqual(C.damage_reduction(e, q, t, physical, 1.0, True), 0)
        ITEMS.register_item(e, t, "item/선글라스")
        self.assertEqual(C.damage_reduction(e, q, t, physical, 1.0, True), 15)
        ITEMS.register_item(e, t, "item/경갑")
        self.assertEqual(C.damage_reduction(e, q, t, physical, 1.0, False), 0)
        special = self.rules.move("move/화염방사")
        self.assertEqual(C.damage_reduction(e, q, t, special, 1.0, False), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)

