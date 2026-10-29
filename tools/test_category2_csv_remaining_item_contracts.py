"""Reviewed copy with the corrected DC16 Unown relationship oracle."""
from pathlib import Path
import io
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch


STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
if not (ROOT/'data').is_dir() or not (ROOT/'output').is_dir():ROOT=Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

import csv_item_contract_policy as POLICY
import csv_item_physical_contracts as PHYSICAL
import csv_item_food_contracts as FOOD
import csv_item_form_contracts as FORMS
import csv_item_capability_contracts as CAP
import equipment_variant_contracts as VARIANTS
import items as ITEMS
import weather_state as WEATHER
import world_entities as WORLD
import pokemon_entities as POKEMON_ENTITIES
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules


class RemainingCsvItemContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")

    def test_warm_item_policies_reject_changed_current_status_bytes(self):
        path = ROOT / 'data/verification/category2-item-table-status.json'
        original_bytes = path.read_bytes()
        original_open = open
        for owner in (POLICY, VARIANTS):
            with self.subTest(owner=owner.__name__):
                expected = owner.policy(self.r)
                clause = next(iter(expected['rows'].values()))['clause_id']
                changed = json.loads(original_bytes)
                row = next(row for row in changed['new_clauses'] if row['clause_id'] == clause)
                row['source'][0]['raw_cells_sha256'] = 'x' * 64
                current = original_bytes

                def read_current(file, mode='r', *args, **kwargs):
                    if Path(file).resolve() == path.resolve():
                        return io.BytesIO(current) if 'b' in mode else io.StringIO(current.decode('utf-8'))
                    return original_open(file, mode, *args, **kwargs)

                with patch('builtins.open', side_effect=read_current):
                    self.assertEqual(owner.policy(self.r), expected)
                    current = json.dumps(changed, ensure_ascii=False).encode('utf-8')
                    with self.assertRaisesRegex(ValueError, 'source provenance changed'):
                        owner.policy(self.r)
                self.assertEqual(owner.policy(self.r), expected)

    def trainer(self, name, *, capabilities=(), items=None, moves=("move/몸통박치기",)):
        spec = build_trainer(self.r, name, 30,
            {"hp": 80, "atk": 20, "def": 20, "spa": 20, "spd": 20, "spe": 20},
            extra={"moves": list(moves), "movement": {"land": 6, "power": 7, "high_jump": 1, "long_jump": 1},
                   "power_basis": "current", "capabilities": list(capabilities), "items": dict(items or {}),
                   "skills": {"은신": 3, "지각": 3, "집중": 3, "오컬트": 3}})
        return Combatant(self.r, spec)

    def pokemon(self, name, *, capabilities=(), level=30, types=("노말",), items=None, abilities=(), moves=("move/몸통박치기",), species="피카츄"):
        spec = build_pokemon(self.r, species, level, name=name, moves=list(moves), abilities=list(abilities),
            extra={"types": list(types), "capabilities": list(capabilities), "items": dict(items or {}),
                   "movement": {"land": 6, "power": 4, "high_jump": 1, "long_jump": 1},
                   "skills": {"운동": 3, "곡예": 3, "전투": 3, "은신": 3, "지각": 3, "집중": 3}})
        return Combatant(self.r, spec)

    def fixture(self, *actors):
        engine = Engine(self.r, seed=3401054)
        for actor in actors:
            engine.gm.add_combatant(actor)
        return engine

    def physical(self, engine, owner, uid, item_id, *, kind="item_instance"):
        if kind == "item_instance":
            WORLD.register_object(engine, uid, location={"kind": "unknown"}, reason="remaining CSV direct fixture",
                kind=kind, item_rule_id=item_id, owner_id=owner.entity_id)
        else:
            WORLD.register_object(engine, uid, location={"kind": "unknown"}, reason="remaining CSV direct fixture",
                kind="physical_object", owner_id=owner.entity_id)
            engine._physical_objects[uid]["csv_form_item_id"] = item_id
        return engine._physical_objects[uid]

    def egg(self, engine, owner, *, remaining=172800):
        row = POKEMON_ENTITIES.prepare_egg(engine, owner, {
            "id": "csv-egg", "source": "remaining CSV direct fixture", "hatched": False,
            "hatch_remaining_seconds": remaining,
        })
        owner.spec.setdefault("eggs", []).append(row)
        return row

    def equip(self, engine, owner, uid, item_id, *, held=True):
        self.physical(engine, owner, uid, item_id)
        ITEMS.register_item(engine, owner, item_id, source_instance_id=uid, as_held=held)
        return engine._physical_objects[uid]

    def hit_receipt(self, move_id="move/몸통박치기", multiplier=1.0):
        return {"observation_boundary": "native_attack_application_including_its_hooks", "source": move_id,
                "damage_class": "물리", "requested": 10, "net_hp_loss": 10,
                "net_temporary_hp_loss": 0, "type_multiplier": multiplier}

    def test_policy_anchors_exact_remaining_34_and_every_domain(self):
        policy = POLICY.policy(self.r)
        self.assertEqual(len(policy["rows"]), 34)
        self.assertEqual(set(row["domain"] for row in policy["rows"].values()),
                         {"physical", "food", "form", "capability", "environment"})
        status = json.loads((ROOT / "data/verification/category2-item-table-status.json").read_text(encoding="utf-8"))
        # This reviewed source set remains fixed when implementation status changes.
        reviewed_ids = {
            "C2CSV/inventory:100:17",
            "C2CSV/inventory:111:17",
            "C2CSV/inventory:114:17",
            "C2CSV/inventory:124:10",
            "C2CSV/inventory:125:10",
            "C2CSV/inventory:127:10",
            "C2CSV/inventory:129:10",
            "C2CSV/inventory:130:10",
            "C2CSV/inventory:131:10",
            "C2CSV/inventory:132:10",
            "C2CSV/inventory:231:10",
            "C2CSV/inventory:232:10",
            "C2CSV/inventory:40:17",
            "C2CSV/inventory:70:1",
            "C2CSV/inventory:91:7",
            "C2CSV/inventory:92:7",
            "C2CSV/item-data:178:5",
            "C2CSV/item-data:25:5",
            "C2CSV/item-data:26:5",
            "C2CSV/item-data:66:1",
            "C2CSV/item-data:77:5",
            "C2CSV/item-data:78:5",
            "C2CSV/item-data:79:5",
            "C2CSV/item-data:80:5",
            "C2CSV/item-data:81:5",
            "C2CSV/item-data:82:5",
            "C2CSV/item-data:83:5",
            "C2CSV/item-data:84:5",
            "C2CSV/item-data:85:5",
            "C2CSV/item-data:87:5",
            "C2CSV/item-data:88:5",
            "C2CSV/item-data:89:5",
            "C2CSV/item-data:91:5",
            "C2CSV/item-data:92:5",
        }
        self.assertEqual(set(policy["rows"]), reviewed_ids)
        registered = {row["clause_id"]: row for row in status["new_clauses"]}
        self.assertEqual(len(registered), len(status["new_clauses"]))
        matched = {}
        for clause_id, row in policy["rows"].items():
            source_name = Path(row["source_file"]).stem
            first_column, last_column = row["source_columns"]
            self.assertEqual(clause_id, f"C2CSV/{source_name}:{row['source_row']}:{first_column}")
            actual = registered[clause_id]
            self.assertEqual(actual["clause_id"], clause_id)
            self.assertEqual(actual["source_entry_id"],
                             f"C2TAB/{source_name}:{row['source_row']}:{first_column}-{last_column}")
            self.assertEqual(len(actual["source"]), 1)
            anchor = actual["source"][0]
            expected = (row["source_file"], row["source_row"], row["source_columns"], row["source_row_sha256"])
            observed = (anchor["file"], anchor["row"], anchor["columns"], anchor["raw_cells_sha256"])
            self.assertEqual(observed, expected)
            file_hash = policy["inventory_file_sha256"] if source_name == "inventory" else policy["item_data_file_sha256"]
            self.assertEqual(anchor["file_sha256"], file_hash)
            matched[clause_id] = observed
        self.assertEqual(set(matched), reviewed_ids)

    def test_cannon_manual_booster_and_band_use_actual_objects_and_receipts(self):
        trainer = self.trainer("physical-tools")
        target = self.pokemon("fire-target", types=("불꽃",))
        engine = self.fixture(trainer, target)
        cannon = self.equip(engine, trainer, "csv/cannon", "item/몬스터볼-캐논", held=False)
        ball = self.physical(engine, trainer, "csv/ball", "item/몬스터볼-2")
        engine.start_round([trainer, target]); engine.start_of_turn(trainer, initiative_count=20)
        loaded = PHYSICAL.load_cannon(engine, trainer, "csv/cannon", "csv/ball")
        self.assertTrue(loaded["loaded"])
        profile = PHYSICAL.cannon_profile(engine, trainer, "csv/cannon", projectile="ball")
        self.assertEqual((profile["accuracy_bonus"], profile["range_m"], profile["fixed_damage"]), (1, 15, "2d6"))
        self.assertEqual(cannon[PHYSICAL.OBJECT_STATE]["loaded_ball_instance_id"], "csv/ball")
        PHYSICAL.fire_cannon(engine, trainer, "csv/cannon", ball_instance_id="csv/ball")
        self.assertIsNone(cannon[PHYSICAL.OBJECT_STATE]["loaded_ball_instance_id"])

        other = self.trainer("manual-owner")
        other.spec["skills"]["포켓몬학"] = 5
        engine.gm.add_combatant(other)
        self.physical(engine, other, "csv/manual", "item/타입-공부-메뉴얼-1")
        PHYSICAL.configure_type_manual(engine, other, "csv/manual", "불꽃", 2)
        self.assertEqual(PHYSICAL.manual_capture_modifier(engine, other, target, "csv/manual"), -5)
        self.assertEqual(PHYSICAL.manual_training_level(engine, other, target, "csv/manual"), 1)
        self.assertEqual(PHYSICAL.manual_training_level(engine, other, target, "csv/manual", baby_food=True), 0)

        booster = self.trainer("booster")
        engine.gm.add_combatant(booster)
        self.equip(engine, booster, "csv/booster", "item/부스트에너지", held=False)
        PHYSICAL.activate_booster(engine, booster, "비")
        self.assertEqual(PHYSICAL.effective_environment(engine, booster, "쾌청"), "rain")
        PHYSICAL.switched_or_fainted(booster)
        self.assertEqual(PHYSICAL.effective_environment(engine, booster, "쾌청"), "sunny")

        band = self.trainer("band")
        engine.gm.add_combatant(band)
        self.equip(engine, band, "csv/band", "item/다이맥스벤드", held=False)
        self.assertTrue(PHYSICAL.dynamax_authorized(engine, band))

    def test_held_reactions_cover_damage_stage_switch_weather_and_multihit(self):
        move = self.r.move("move/몸통박치기")
        for item_id, kind in (("item/풍선", "air_balloon"), ("item/약점보험", "weakness_policy"),
                              ("item/탈출버튼", "eject_button"), ("item/레드카드", "red_card")):
            with self.subTest(item=item_id):
                attacker = self.pokemon("attacker-" + kind)
                holder = self.pokemon("holder-" + kind)
                engine = self.fixture(attacker, holder)
                attacker.on_field = holder.on_field = True
                obj = self.equip(engine, holder, "csv/" + kind, item_id)
                PHYSICAL.after_attack_damage(engine, attacker, holder, move, self.hit_receipt(multiplier=2.0))
                if kind == "air_balloon":
                    self.assertIn("destroyed", obj)
                elif kind == "weakness_policy":
                    PHYSICAL.resolve_pending(engine, holder, kind, accept=True)
                    self.assertEqual(PHYSICAL.damage_roll_bonus(engine, holder, move), 10)
                elif kind == "eject_button":
                    before = engine.export_state()
                    with self.assertRaisesRegex(ValueError, "replacement"):
                        PHYSICAL.resolve_pending(engine, holder, kind, accept=True)
                    self.assertEqual(engine.export_state(), before)
                    self.assertTrue(holder.on_field)
                    self.assertNotIn("consumed", obj)
                else:
                    self.assertNotIn("red_card", holder.spec.get(PHYSICAL.PENDING, {}))
                    self.assertTrue(attacker.on_field)
                    self.assertIn("consumed", obj)

        holder = self.pokemon("stage-holder")
        engine = self.fixture(holder); holder.on_field = True
        pack = self.equip(engine, holder, "csv/eject-pack", "item/탈출팩")
        PHYSICAL.after_stage_change(engine, holder, "atk", 0, -1)
        before = engine.export_state()
        with self.assertRaisesRegex(ValueError, "replacement"):
            PHYSICAL.resolve_pending(engine, holder, "eject_pack", accept=True)
        self.assertEqual(engine.export_state(), before)
        self.assertTrue(holder.on_field); self.assertNotIn("consumed", pack)

        umbrella = self.trainer("umbrella")
        engine = self.fixture(umbrella)
        self.equip(engine, umbrella, "csv/umbrella", "item/만능우산", held=False)
        self.assertIsNone(PHYSICAL.effective_environment(engine, umbrella, "비"))

        dice = self.pokemon("dice")
        engine = self.fixture(dice)
        self.equip(engine, dice, "csv/dice", "item/속임수주사위")
        self.assertEqual(PHYSICAL.loaded_dice_hits(engine, dice, fixed=(2, 8))["hits"], 5)

    def test_assault_vest_lock_and_all_four_selected_food_variants(self):
        pokemon = self.pokemon("vest")
        engine = self.fixture(pokemon)
        before = pokemon.stats["spd"]
        self.equip(engine, pokemon, "csv/vest", "item/돌격조끼")
        self.assertEqual(pokemon.stats["spd"], before + 5)
        self.assertIn("난동", pokemon.conditions)
        ITEMS.unregister_item(engine, pokemon, "item/돌격조끼")
        self.assertEqual(pokemon.stats["spd"], before)
        with self.assertRaisesRegex(ValueError, "cannot be cured"):
            PHYSICAL.before_cure_status(engine, pokemon, "난동")
        PHYSICAL.end_encounter(pokemon)
        self.assertNotIn("난동", pokemon.conditions)

        import food_effects as COMMON, condition_recovery as RECOVERY
        for item in ("item/다이버섯","item/흉내허브","item/회복허브","item/단맛-과자"):
            eater=self.pokemon("food-eater",items={item:1},
                species="Venusaur" if item=="item/다이버섯" else "피카츄")
            if item=="item/단맛-과자":
                eater.spec['nature']=next(name for name,row in self.r.mech('pokemon/natures')['by_name'].items()
                    if row.get('likes','').replace(' ','')=='단맛' and row['up']!=row['down'])
            source=self.pokemon("stage-source")
            engine=self.fixture(eater,source)
            result=engine.use_item(eater,item,food_policy=FOOD.definition(self.r,item)['clause_id'],
                duration_minutes=1,duration_reason='actual GM Extended intake')
            buff=COMMON.get_buff(eater,result['buff_id'])
            self.assertEqual((engine.elapsed_seconds,COMMON.slots(eater)),(60,1))
            if item=="item/다이버섯":
                with self.assertRaisesRegex(ValueError,"excludes"):
                    FOOD.forbid_external_operation(eater,buff['id'],"steal")
                engine.start_round([eater,source]);engine.start_of_turn(eater,initiative_count=20)
                engine.enter_gigantamax(eater,source_id=item,reason='actual source designated form')
            elif item=="item/흉내허브":
                with patch.object(engine.rulings,"decide",return_value=True):
                    engine.change_stage(source,"atk",2)
                self.assertEqual(eater.stages['atk'],2)
            elif item=="item/회복허브":
                engine.consume_food_buff(eater,buff_id=buff['id'],save_condition='마비')
                self.assertEqual(RECOVERY.saving_check(engine,eater,'마비',11,fixed=9)['food_bonus'],2)
            else:
                engine.start_round([eater,source]);engine.start_of_turn(eater,initiative_count=20)
                self.assertEqual(engine.consume_food_buff(eater,buff_id=buff['id'])['evasion'],2)
            self.assertEqual(COMMON.slots(eater),0)
            self.assertEqual(len(eater.spec['food_consumption_receipts']),1)

    def test_all_five_form_relations_are_reversible_and_source_bound(self):
        necrozma = self.pokemon("necrozma", capabilities=("바이러스 합체",), species="네크로즈마")
        partner = self.pokemon("partner", types=("에스퍼", "고스트"), species="루나아라")
        engine = self.fixture(necrozma, partner)
        FORMS.merge_necrozma(engine, necrozma, partner, willing=True)
        self.assertFalse(partner.on_field); self.assertIn("고스트", necrozma.types)
        FORMS.release_necrozma(engine, necrozma); self.assertTrue(partner.on_field)

        zacian = self.pokemon("zacian", capabilities=("무기합일",), species="자시안")
        engine = self.fixture(zacian)
        self.physical(engine, zacian, "csv/rusted-sword", "item/녹슨검", kind="physical_object")
        FORMS.weapon_union(engine, zacian, "csv/rusted-sword")
        self.assertEqual(zacian.form, "검왕")
        FORMS.end_weapon_union(engine, zacian)

        zygarde = self.pokemon("zygarde", capabilities=("지가르데 세포",), species="지가르데")
        engine = self.fixture(zygarde)
        cube = self.physical(engine, zygarde, "csv/cube", "item/지가르데큐브", kind="physical_object")
        cube["zygarde_cells"] = {"available": 100, "assemblies": []}
        row = FORMS.configure_zygarde(engine, zygarde, "csv/cube", cells=100, form_percent=10, power_construct=True)
        self.assertFalse(row["decomposable"])
        with self.assertRaisesRegex(ValueError, "cannot be decomposed"):
            FORMS.configure_zygarde(engine, zygarde, "csv/cube", cells=100, form_percent=10, power_construct=True, decompose=True)

        rider = self.pokemon("rider", capabilities=("혼연일체",), species="버드렉스")
        mount = self.pokemon("mount", abilities=("흑의울음",), capabilities=("탑승 2",), species="레이스포스")
        engine = self.fixture(rider, mount)
        FORMS.mount_as_one(engine, rider, mount, ability="흑의울음")
        self.assertFalse(mount.on_field)
        FORMS.dismount_as_one(engine, rider); self.assertTrue(mount.on_field)

        tera = self.pokemon("tera", capabilities=("테라체인지",))
        engine = self.fixture(tera)
        engine.tera_exit(tera)
        FORMS.encounter_join(engine, tera)
        self.assertEqual(tera.form, "테라스탈")

    def test_capability_actions_cover_language_egg_juicer_unown_poison_life_scavenger_tinkerer(self):
        actor = self.pokemon("capability-owner", capabilities=("언어", "알부화기", "과즙기", "안농모으기",
            "독샘", "생명감지", "청소부", "땜장이"), level=30, species='단단지')
        target = self.pokemon("life-target")
        egg_owner = self.trainer("egg-owner")
        engine = self.fixture(actor, target, egg_owner)
        self.assertTrue(CAP.language(actor)["speaks_human"])
        egg = self.egg(engine, egg_owner)
        self.assertEqual(CAP.heat_egg(engine, actor, egg["entity_id"], fixed_d2=2)["reduced_seconds"], 86400)
        engine.session_frequency=True
        engine.defer_session_refresh=False
        engine.begin_session('csv/session/0',[actor,target,egg_owner])
        berry = self.equip(engine, actor, "csv/berry", "item/오랭열매")
        CAP.juicer_begin(engine, actor, "csv/berry")
        engine.begin_session('csv/session/1',[actor,target,egg_owner])
        self.assertEqual(CAP.juicer_session(engine, actor)["phase"], "juice")
        for number in range(2,6):
            engine.begin_session('csv/session/'+str(number),[actor,target,egg_owner])
            result = CAP.juicer_session(engine, actor)
        self.assertEqual(result["phase"], "candy")

        unown = self.pokemon("random-unown", level=15, species="안농")
        engine.start_round([actor, target]); engine.start_of_turn(actor, initiative_count=20)
        self.assertTrue(CAP.gather_unown(engine, actor, unown, occult_total=16)["immediate_ally"])
        self.assertEqual(CAP.hidden_power_frequency(actor, "Scene"), "At-Will")
        self.assertEqual(CAP.poison_glands_profile(actor)["type"], "독")
        self.assertTrue(CAP.poison_glands_eligible({"name": "독찌르기"}))
        self.assertTrue(CAP.sense_life(engine, actor, target, distance_m=5,gm_basis='GM observed living target distance')["located"])
        engine.end_of_turn(actor);engine.end_encounter(round_elapsed_seconds=0)
        self.assertEqual(engine.scavenge(actor, fixed_d20=20, duration_minutes=5,
            duration_reason='GM observed five-minute pickup activity')["item_id"], "item/이상한사탕")
        profile = CAP.configure_tinkerer(engine, actor, weapon_class="large_melee", proficient_move="move/강타", steel=True)
        self.assertTrue(profile["unstealable"])
        self.assertEqual(CAP.tinkerer_move(actor, self.r.move("move/강타"),engine=engine)["type"], "강철")

    def test_muscle_essence_hazards_and_psychic_navigation_close_numeric_and_exception_consumers(self):
        actor = self.pokemon("numeric-owner", capabilities=("개선된 인조 근육", "함정내성", "에스퍼 네비게이터"))
        engine = self.fixture(actor)
        self.assertEqual(CAP.muscle_power_bonus(actor), 2)
        self.assertEqual(CAP.muscle_jump_bonus(actor), {"high_jump": 1, "long_jump": 1})
        self.assertEqual(CAP.injury_recovery_seconds(actor, 86400), 43200)
        self.assertEqual(CAP.daily_injury_heal(actor, 1), 2)
        actor.spec["essence"] = 2
        self.assertEqual(CAP.essence_view(actor)["base_injuries"], 1)
        self.assertEqual(CAP.essence_effectiveness(actor, "고스트", 0.0), 1.0)
        self.assertFalse(CAP.essence_move_allowed(actor, {"type": "고스트", "keywords": []}))
        self.assertEqual(CAP.toxic_environment(actor, "high", {"middle": ["poison"]})["effective"], "middle")
        immune = self.pokemon("hazard-immune", capabilities=("함정면역",))
        self.assertIsNone(CAP.toxic_environment(immune, "high", {"high": ["poison"]})["effective"])
        CAP.start_navigation(engine, actor, "route/alpha", lightyears=2)
        row = CAP.navigation_check(engine, actor, "route/alpha", skill="지각", total=30)
        self.assertTrue(row["completed"])
        self.assertTrue(CAP.navigation_jump(actor, "route/alpha")["safe"])

    def test_world_validation_rejects_tampered_projection(self):
        actor = self.pokemon("restore-holder")
        engine = self.fixture(actor)
        self.equip(engine, actor, "csv/dice-restore", "item/속임수주사위")
        VARIANTS.validate_world(engine, {actor.entity_id: actor})
        registration = next(iter(actor._item_reg.values()))
        registration["csv_item_projection"]["item_id"] = "item/풍선"
        with self.assertRaisesRegex(ValueError, "projection"):
            VARIANTS.validate_world(engine, {actor.entity_id: actor})

    def test_failed_switch_and_tutor_payment_are_atomic(self):
        attacker = self.pokemon("atomic-attacker")
        holder = self.pokemon("atomic-holder")
        invalid_send = self.pokemon("invalid-send")
        engine = self.fixture(attacker, holder, invalid_send)
        attacker.on_field = holder.on_field = invalid_send.on_field = True
        obj = self.equip(engine, holder, "csv/atomic-button", "item/탈출버튼")
        move = self.r.move("move/몸통박치기")
        PHYSICAL.after_attack_damage(engine, attacker, holder, move, self.hit_receipt())
        before_pending = deepcopy(holder.spec[PHYSICAL.PENDING])
        with self.assertRaisesRegex(ValueError, "replacement"):
            PHYSICAL.resolve_pending(engine, holder, "eject_button", send=invalid_send)
        self.assertEqual(holder.spec[PHYSICAL.PENDING], before_pending)
        self.assertEqual(obj.get("equipped_by"), holder.entity_id)
        self.assertNotIn("consumed", obj)
        self.assertTrue(holder.on_field)

        zygarde = self.pokemon("atomic-zygarde", capabilities=("지가르데 세포",), species="지가르데")
        engine = self.fixture(zygarde)
        cube = self.physical(engine, zygarde, "csv/atomic-cube", "item/지가르데큐브",
                             kind="physical_object")
        cube["zygarde_cells"] = {"available": 10, "assemblies": []}
        FORMS.configure_zygarde(engine, zygarde, "csv/atomic-cube", cells=10,
                                form_percent=10, power_construct=False)
        zygarde.spec["tutor_points"] = 0
        before_form = deepcopy(zygarde.spec[FORMS.STATE])
        with self.assertRaisesRegex(ValueError, "insufficient"):
            FORMS.teach_zygarde_move(engine, zygarde, "move/코어퍼니셔", tutor_points=1)
        self.assertEqual(zygarde.spec["tutor_points"], 0)
        self.assertEqual(zygarde.spec[FORMS.STATE], before_form)

    def test_failed_form_grants_restore_both_participants(self):
        necrozma = self.pokemon("atomic-necrozma", capabilities=("바이러스 합체",), species="네크로즈마")
        partner = self.pokemon("atomic-lunala", types=("에스퍼", "고스트"), species="루나아라")
        engine = self.fixture(necrozma, partner)
        before_necrozma = (list(necrozma.types), necrozma.movement, deepcopy(necrozma.spec))
        before_partner = (partner.on_field, deepcopy(partner.spec))
        with patch("state_grants.grant_moves", side_effect=ValueError("late grant failure")):
            with self.assertRaisesRegex(ValueError, "late grant failure"):
                FORMS.merge_necrozma(engine, necrozma, partner, willing=True,
                                      signature_move="move/섀도레이")
        self.assertEqual((list(necrozma.types), necrozma.movement, necrozma.spec), before_necrozma)
        self.assertEqual((partner.on_field, partner.spec), before_partner)

        rider = self.pokemon("atomic-rider", capabilities=("혼연일체",), species="버드렉스")
        mount = self.pokemon("atomic-mount", abilities=("흑의울음",), capabilities=("탑승 2",), species="레이스포스")
        engine = self.fixture(rider, mount)
        before_rider = (list(rider.types), rider.movement, deepcopy(rider.spec))
        before_mount = (mount.on_field, deepcopy(mount.spec))
        with patch("state_grants.grant", side_effect=ValueError("late mount failure")):
            with self.assertRaisesRegex(ValueError, "late mount failure"):
                FORMS.mount_as_one(engine, rider, mount, ability="흑의울음")
        self.assertEqual((list(rider.types), rider.movement, rider.spec), before_rider)
        self.assertEqual((mount.on_field, mount.spec), before_mount)


class RegisteredItemRowsTests(unittest.TestCase):
    def test_parse_reuse_reads_live_bytes_is_detached_bounded_and_not_mtime_based(self):
        POLICY._item_status_index.cache_clear()
        self.addCleanup(POLICY._item_status_index.cache_clear)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'data/verification/category2-item-table-status.json'
            path.parent.mkdir(parents=True)
            raw = json.dumps({'new_clauses': [{'clause_id': 'one', 'source': [{'file': 'old'}]},
                                             {'clause_id': 'two', 'source': []}]}).encode('utf-8')
            path.write_bytes(raw)
            rules = SimpleNamespace(root=str(root))
            reads = []

            # builtin open is intentional: each call must open/read the current file.
            original_open = open
            def opened(file, *args, **kwargs):
                if Path(file) == path:
                    reads.append(Path(file))
                return original_open(file, *args, **kwargs)

            with patch('builtins.open', side_effect=opened), \
                 patch.object(POLICY.json, 'loads', wraps=json.loads) as parsed:
                first = POLICY.registered_item_rows(rules, ['one', 'missing'])
                self.assertEqual(set(first), {'one'})
                first['one']['source'][0]['file'] = 'poisoned returned copy'
                second = POLICY.registered_item_rows(rules, ['one', 'two'])
                self.assertEqual(second['one']['source'][0]['file'], 'old')
                self.assertEqual(len(reads), 2)
                self.assertEqual(parsed.call_count, 1)
                stamp = path.stat()
                path.write_bytes(raw.replace(b'old', b'new'))
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                self.assertEqual(path.stat().st_size, stamp.st_size)
                self.assertEqual(POLICY.registered_item_rows(rules, ['one'])['one']['source'][0]['file'], 'new')
                self.assertEqual(parsed.call_count, 2)
                self.assertEqual(len(reads), 3)
                self.assertEqual(POLICY._item_status_index.cache_info().currsize, 1)
                path.write_bytes(b'{invalid')
                for _ in range(2):
                    with self.assertRaises(json.JSONDecodeError):
                        POLICY.registered_item_rows(rules, ['one'])
                self.assertEqual(parsed.call_count, 4, 'failed parses must not become cached decisions')
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    POLICY.registered_item_rows(rules, ['one'])


if __name__ == "__main__":
    unittest.main()
