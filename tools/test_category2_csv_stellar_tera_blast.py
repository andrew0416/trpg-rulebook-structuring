"""Direct producer/consumer checks for Stellar Blast and three Tera Blast rows."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_pokemon
from engine import Combatant, Engine, Rules
from grid import Grid
import effects as FX
import effects_ext as EXT
import homebrew_state as HOME
import stellar_tera_blast as STELLAR


class FixedRng:
    def __init__(self, faces):
        self.faces = list(faces)

    def randint(self, low, high):
        value = self.faces.pop(0)
        if not low <= value <= high:
            raise AssertionError((low, high, value))
        return value

    def getstate(self):
        return tuple(self.faces)

    def setstate(self, state):
        self.faces = list(state)


class StellarTeraBlastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="homebrew")

    def setUp(self):
        self.engine = Engine(self.rules, seed=610)
        self.owner = Combatant(self.rules, build_pokemon(
            self.rules, "이상해씨", 20, name="owner", side="party", pos=(2, 2),
            abilities=["스텔라버스트"],
            moves=["move/몸통박치기", "move/테라버스트", "move/테라버스트-물리", "move/테라버스트-특수"],
        ))
        self.ally = Combatant(self.rules, build_pokemon(
            self.rules, "꼬렛", 20, name="ally", side="party", pos=(4, 2),
            moves=["move/불꽃세례"], abilities=[],
        ))
        self.far = Combatant(self.rules, build_pokemon(
            self.rules, "꼬렛", 20, name="far", side="party", pos=(8, 8),
            moves=["move/불꽃세례"], abilities=[],
        ))
        self.foe = Combatant(self.rules, build_pokemon(
            self.rules, "파이리", 20, name="foe", side="wild", pos=(3, 2),
            moves=["move/몸통박치기"], abilities=[],
        ))
        self.engine.grid = Grid(12, 12)
        self.engine.everyone = self.engine.gm.everyone = [self.owner, self.ally, self.far, self.foe]
        self.engine.register_abilities(self.owner)
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.owner, initiative_count=20)

    def opportunity(self):
        self.engine.rng = FixedRng([20])
        self.engine.use_move(self.owner, self.foe, "move/몸통박치기", set_damage=True)
        rows = self.owner.spec[STELLAR.STATE]["opportunities"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def radiate(self, value="불꽃"):
        row = self.opportunity()
        return self.engine.gm.activate_stellar_blast(
            self.owner, row["id"], value, reason="chosen actual type from completed enemy hit"
        )

    def test_policy_exact_four_rows_and_source_hashes(self):
        policy = json.loads((ROOT / STELLAR.POLICY).read_text(encoding="utf-8"))
        self.assertEqual(policy["ability"]["clause_id"], "C2CSV-ABILITY-R0663")
        self.assertEqual(
            [row["clause_id"] for row in policy["moves"]],
            ["C2CSV-MOVE-R0610", "C2CSV-MOVE-R0911", "C2CSV-MOVE-R0912"],
        )
        self.assertEqual(len({row["source_row_sha256"] for row in policy["moves"]}), 3)
        self.assertEqual(set(STELLAR.rows(self.rules)), {
            "move/테라버스트", "move/테라버스트-물리", "move/테라버스트-특수",
        })

    def test_completed_enemy_hit_produces_snapshot_and_miss_or_ally_does_not(self):
        self.engine.rng = FixedRng([1])
        self.engine.use_move(self.owner, self.foe, "move/몸통박치기", set_damage=True)
        self.assertNotIn(STELLAR.STATE, self.owner.spec)
        self.setUp()
        self.engine.rng = FixedRng([20])
        self.engine.use_move(self.owner, self.ally, "move/몸통박치기", set_damage=True)
        self.assertNotIn(STELLAR.STATE, self.owner.spec)
        self.setUp()
        self.engine.rng = FixedRng([20])
        self.engine.use_move(self.owner, self.foe, "move/몸통박치기", set_damage=True)
        row = self.owner.spec[STELLAR.STATE]["opportunities"][0]
        self.assertEqual((row["target_id"], row["types"], row["consumed"]), (self.foe.entity_id, ["불꽃"], False))
        self.assertTrue(row["completion_id"].startswith("move-complete:"))

    def test_swift_activation_consumes_one_actual_opportunity_and_is_atomic(self):
        row = self.opportunity()
        before = deepcopy((self.owner.spec, self.owner.budget))
        with self.assertRaises(ValueError):
            self.engine.gm.activate_stellar_blast(self.owner, row["id"], "물", reason="not target type")
        self.assertEqual((self.owner.spec, self.owner.budget), before)
        receipt = self.engine.gm.activate_stellar_blast(self.owner, row["id"], "불꽃", reason="actual target type")
        self.assertEqual(receipt["action"], "swift")
        self.assertEqual(self.owner.budget["swift"], 0)
        self.assertEqual(STELLAR.active_radiation(self.engine, self.owner)["radiated_type"], "불꽃")
        after = deepcopy((self.owner.spec, self.owner.budget))
        with self.assertRaises(ValueError):
            self.engine.gm.activate_stellar_blast(self.owner, row["id"], "불꽃", reason="duplicate")
        self.assertEqual((self.owner.spec, self.owner.budget), after)

    def test_radiation_projects_exact_type_without_mutating_stab_or_types(self):
        original_types = list(self.owner.types)
        original_stab = HOME.stab_types(self.owner)
        self.radiate()
        for move_id in STELLAR.rows(self.rules):
            move = STELLAR.prepare(self.engine, self.owner, self.rules.move(move_id), True)
            mm, _ = self.rules.move_mech(move_id)
            self.assertEqual(EXT.effective_type(self.engine, self.owner, self.foe, move, mm, consume=False), "불꽃")
        self.assertEqual(self.owner.types, original_types)
        self.assertEqual(HOME.stab_types(self.owner), original_stab)

    def test_main_and_variant_stab_contracts_remain_distinct(self):
        self.radiate()
        main = self.rules.move("move/테라버스트")
        physical = self.rules.move("move/테라버스트-물리")
        special = self.rules.move("move/테라버스트-특수")
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, main))
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, physical))
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, special))
        HOME.observe_type(self.engine, self.owner, '물', reason='actual permanent Tera type')
        HOME.observe_active(self.engine, self.owner, True, reason='actual Terastal state')
        self.assertTrue(EXT.grants_stab(self.engine, self.owner, main))
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, physical))
        self.assertFalse(EXT.grants_stab(self.engine, self.owner, special))

    def test_radiation_preserves_pre_radiation_stab_for_actual_native_damage_and_restore(self):
        for species, foe_species, radiated, tera, stab in (
                ('이상해씨', '이상해씨', '풀', None, False),
                ('꼬렛', '파이리', '불꽃', None, True),
                ('이상해씨', '파이리', '불꽃', None, False),
                ('이상해씨', '이상해씨', '풀', '물', False),
                ('이상해씨', '파이리', '불꽃', '풀', True)):
            with self.subTest(species=species, radiated=radiated, tera=tera):
                e = Engine(self.rules, seed=610);e.grid = Grid(12, 12)
                user = Combatant(self.rules, build_pokemon(self.rules, species, 20,
                    name='radiating user', side='party', pos=(2, 2), abilities=['스텔라버스트'],
                    moves=['move/몸통박치기', 'move/테라버스트', 'move/테라버스트-물리', 'move/테라버스트-특수']))
                target = Combatant(self.rules, build_pokemon(self.rules, foe_species, 20,
                    name='actual foe', side='wild', pos=(3, 2), abilities=[]))
                for actor in (user, target):e.gm.add_combatant(actor)
                if tera is not None:
                    HOME.observe_type(e,user,tera,reason='actual permanent Tera type')
                    HOME.observe_active(e,user,True,reason='actual pre-radiation Terastal state')
                e.start_round([user,target]);e.start_of_turn(user, initiative_count=20)
                e.rng.seed(0);e.use_move(user,target,'move/몸통박치기',set_damage=True)
                opportunity = user.spec[STELLAR.STATE]['opportunities'][0]
                e.gm.activate_stellar_blast(user,opportunity['id'],radiated,reason='actual hit type')
                e.gm.snapshot('radiation');e.gm.restore('radiation',reason='preserve source STAB')
                e = Engine.import_state(self.rules,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
                user = next(c for c in e.everyone if c.entity_id == user.entity_id)
                target = next(c for c in e.everyone if c.entity_id == target.entity_id)
                for move_id in STELLAR.rows(self.rules):
                    move = STELLAR.prepare(e,user,self.rules.move(move_id),True)
                    prepared = EXT.prepare_versatile_move(e,move,'atk') if move_id=='move/테라버스트' else move
                    expected_stab = stab or (tera is not None and move_id=='move/테라버스트')
                    self.assertEqual(e.damage_base(user,prepared,target=target),8+(2 if expected_stab else 0))
                    before=len(e.log_lines);e.roll_damage(user,target,prepared,set_damage=True)
                    self.assertEqual(any('자속보정' in line for line in e.log_lines[before:]),expected_stab)
                self.assertTrue(e.validate_state()['valid'],e.validate_state())

    def test_burst_two_allies_gain_one_matching_type_bonus_and_far_or_other_type_do_not(self):
        self.radiate()
        fire = self.rules.move("move/불꽃세례")
        grass = self.rules.move("move/덩굴채찍")
        for actor, expected in ((self.owner, 10), (self.ally, 10), (self.far, 0)):
            ctx = {"actual_damage_type": "불꽃"}
            self.assertEqual(FX.passive_damage_mods(self.engine, actor, self.foe, fire, ctx)[1], expected)
        self.assertEqual(FX.passive_damage_mods(
            self.engine, self.ally, self.foe, grass, {"actual_damage_type": "풀"}
        )[1], 0)

    def test_native_plasma_owns_stab_over_radiation_even_when_both_choose_electric(self):
        import math
        import declarative_move_contracts as DECLARATIVE
        import state_grants as GRANTS
        from tools import test_actual_damage_type_revision as NATIVE_FIXTURE
        fixture = NATIVE_FIXTURE.ActualDamageTypeRevisionTests();fixture.rules = self.rules
        for own_type, radiated, plasma in (
                ('전기','풀',True),('노말','풀',True),
                ('전기','전기',True),('노말','전기',True),
                ('전기','풀',False),('노말','풀',False)):
            with self.subTest(own_type=own_type,radiated=radiated,plasma=plasma):
                move_id = 'move/테라버스트-물리'
                e,user,target = fixture.world(['move/몸통박치기',move_id],types=(own_type,),
                    target_types=(radiated,),target_moves=('move/플라스마피스트',))
                GRANTS.replace_baseline(e,user,'abilities',['스텔라버스트'])
                fixture.hit(e,user,target,'move/몸통박치기')
                opportunity = user.spec[STELLAR.STATE]['opportunities'][0]
                e.gm.activate_stellar_blast(user,opportunity['id'],radiated,reason='actual hit radiation')
                e.end_of_turn(user)
                if plasma:
                    e.start_of_turn(target,initiative_count=19)
                    fixture.hit(e,target,user,'move/플라스마피스트');e.end_of_turn(target)
                    self.assertEqual(len(DECLARATIVE.live(user,'next_normal_attack_type')),1)
                e.start_round(e.everyone);e.start_of_turn(user,initiative_count=20)
                e,user,target = fixture.restore(e,user,target)
                move = STELLAR.prepare(e,user,self.rules.move(move_id),True)
                actual_type = '전기' if plasma else radiated
                stab_type = actual_type if plasma else '노말'
                db = move['damage_base']+(math.floor(e.formula('stab')) if own_type==stab_type else 0)
                before = e.export_state(); before_logs = list(e.log_lines)
                self.assertEqual(EXT.effective_type(e,user,target,move,self.rules.move_mech(move_id)[0],consume=False),actual_type)
                self.assertEqual(e.damage_base(user,move,target=target),db)
                expected_logs = ([f"    자속보정: DB {move['damage_base']} → {db}  => [combat/stab]"]
                                 if own_type == stab_type else [])
                self.assertEqual(e.log_lines, before_logs + expected_logs)
                with patch.object(e, 'log_lines', before_logs):
                    self.assertEqual(e.export_state(),before)
                expected = math.floor(fixture.expected(e,user,target,move_id,db,
                    bonus=10 if actual_type==radiated else 0)*e.type_multiplier(actual_type,target)[0])
                self.assertEqual(fixture.hit(e,user,target,move_id,use_radiated_type=True),expected)
                self.assertFalse(DECLARATIVE.live(user,'next_normal_attack_type'))
                if plasma:
                    consumed = [row for row in DECLARATIVE.history(user) if row['operation']=='next_normal_attack_type']
                    self.assertEqual(len(consumed),1)
                    self.assertEqual(consumed[0]['payload']['consumed_by']['move_id'],move_id)
                self.assertTrue(e.validate_state()['valid'],e.validate_state())

    def test_ordinary_tera_type_projects_all_three_and_main_forces_stab(self):
        HOME.observe_type(self.engine, self.owner, "물", reason="established ordinary Tera type")
        HOME.observe_active(self.engine, self.owner, True, reason="actual active Terastal state")
        for move_id, force_stab in (
            ("move/테라버스트", True),
            ("move/테라버스트-물리", False),
            ("move/테라버스트-특수", False),
        ):
            move = self.rules.move(move_id)
            mm, _ = self.rules.move_mech(move_id)
            self.assertEqual(EXT.effective_type(self.engine, self.owner, self.foe, move, mm, consume=False), "물")
            self.assertEqual(EXT.grants_stab(self.engine, self.owner, move), force_stab)

    def test_stellar_effectiveness_uses_actual_form_evidence_and_caps_at_double(self):
        self.radiate()
        move = self.rules.move("move/테라버스트-특수")
        mm, _ = self.rules.move_mech(move["id"])
        self.foe.form = "actual-battle-form"
        ctx = {}
        self.assertEqual(EXT.effectiveness_hook(self.engine, self.owner, self.foe, move, mm, 1.5, ctx), 2.0)
        self.assertEqual(ctx["stellar_tera_blast"]["cap"], 2.0)
        ctx = {}
        self.assertEqual(EXT.effectiveness_hook(self.engine, self.owner, self.foe, move, mm, 2.0, ctx), 2.0)
        self.foe.form = None
        self.assertEqual(EXT.effectiveness_hook(self.engine, self.owner, self.foe, move, mm, 1.0, {}), 1.0)

    def test_encounter_lifetime_disables_aura_and_projection_without_deleting_audit(self):
        self.radiate()
        saved = deepcopy(self.owner.spec[STELLAR.STATE])
        self.engine.end_encounter(self.engine.everyone)
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
        self.assertEqual(self.owner.spec[STELLAR.STATE], saved)
        self.engine.begin_encounter(self.engine.everyone)
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))

    def test_state_roundtrip_validation_and_tamper_rejection(self):
        self.radiate()
        self.engine.gm.snapshot("stellar")
        self.owner.spec[STELLAR.STATE]["active"]["radiated_type"] = "물"
        with self.assertRaises(ValueError):
            STELLAR.validate_actor(self.engine, self.owner)
        self.engine.gm.restore("stellar")
        self.assertTrue(STELLAR.validate_world(self.engine))
        self.assertEqual(STELLAR.active_radiation(self.engine, self.owner)["radiated_type"], "불꽃")


if __name__ == "__main__":
    unittest.main()
