"""Current CS reaches native movement consumers without granting absent modes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:/trpg-rulebook-structuring/ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Combatant, Engine, Rules
from builder import build_pokemon, build_trainer
from grid import cheb
import campaign_injury_policy as INJURY
import injury_recovery as RECOVERY
import grapple_state as GRAPPLE
import test_category2_setup_move_state as setup_fixture
import test_category2_ability_native_actions as ability_fixture
import test_foundation_maneuvers_grapple as grapple_fixture
import test_core_power_herb_skip as herb_fixture


class CurrentMovementProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")

    def actor(self, kind="trainer", values=None):
        e = Engine(self.r, seed=413)
        if kind == "trainer":
            spec = build_trainer(self.r, "current movement", 20,
                                 dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 40), moves=[],
                                 extra={"movement": values or {"land": 6}})
        else:
            spec = build_pokemon(self.r, "이브이", 20, abilities=[], moves=[])
        a = Combatant(self.r, spec)
        e.gm.add_combatant(a)
        e.gm.set_movement_capabilities(a, values or {"land": 6}, basis="current",
                                       reason="observed current movement")
        return e, a

    def legs(self, e, a, count=2):
        INJURY.configure(e, injury_mode="localized", death_enabled=False,
                         center_heals_all=False, taskmaster_exempt=False,
                         recovery_order="oldest_first", reason="selected location injury rule")
        with patch.object(e.rng, "choice", return_value="spe"):
            e.gm.set_injuries(a, value=count, reason="actual leg injuries")

    def test_localized_injuries_and_actual_healing_change_all_owned_modes_for_both_kinds(self):
        values = {"land": 6, "sky": 6, "levitate": 6, "swim": 6, "burrow": 6, "teleport": 6}
        for kind in ("trainer", "pokemon"):
            with self.subTest(kind=kind):
                e, a = self.actor(kind, values)
                self.legs(e, a)
                self.assertEqual(INJURY.stage_penalty(a, "spe"), -2)
                self.assertEqual([e.move_profile(a, movement_mode=m)[0] for m in values], [5] * 6)
                # The odd negative stage is floored; healing one injury now crosses zero.
                e.gm.set_stage(a, "spe", value=1, reason="actual positive stage")
                self.assertEqual(e.move_profile(a, movement_mode="land")[0], 5)
                self.assertEqual(RECOVERY.heal(e, a, 1, source="actual_treatment"), 1)
                self.assertEqual([e.move_profile(a, movement_mode=m)[0] for m in values], [6] * 6)
                self.assertEqual(a.staged("spe"), a.stats["spe"])
                self.assertEqual(a.stages["spe"], 1)

    def test_current_stage_clamp_floor_slowed_and_absent_modes_preserve_order(self):
        for kind in ("trainer", "pokemon"):
            e, a = self.actor(kind, {"land": 6, "sky": 0, "swim": 1, "burrow": 2})
            self.legs(e, a)
            for stage, land, swim, burrow, stat_percent in ((-6, 3, 1, 2, 40), (-1, 4, 1, 2, 70),
                                                           (0, 5, 1, 2, 80), (1, 5, 1, 2, 90),
                                                           (6, 8, 3, 4, 180)):
                with self.subTest(kind=kind, stage=stage):
                    e.gm.set_stage(a, "spe", value=stage, reason="boundary current stage")
                    self.assertEqual([e.move_profile(a, movement_mode=m)[0] for m in ("land", "swim", "burrow")],
                                     [land, swim, burrow])
                    self.assertEqual(a.staged("spe"), max(1, a.stats["spe"] * stat_percent // 100))
                    with self.assertRaisesRegex(ValueError, "not possessed"):
                        e.move_profile(a, movement_mode="sky")
            e.gm.set_stage(a, "spe", value=-6)
            e.apply_status(a, "둔화")
            self.assertEqual([e.move_profile(a, movement_mode=m)[0] for m in ("land", "swim", "burrow")], [1, 1, 1])

    def test_base_campaign_injuries_do_not_add_optional_movement_penalty(self):
        e, a = self.actor()
        e.gm.set_injuries(a, value=2, reason="ordinary injuries without location policy")
        self.assertEqual((INJURY.stage_penalty(a, "spe"), e.move_profile(a)[0]), (0, 6))
        self.assertEqual(a.staged("spe"), a.stats["spe"])

    def test_load_and_injuries_share_current_cs_but_staggering_still_caps_last(self):
        e, a = self.actor(values={"land": 6, "power": 6})
        self.legs(e, a)
        e.gm.set_stage(a, "spe", value=1)
        e.gm.set_carried_objects(a, [{"id": "crate", "weight_kg": 40}], "weighed heavy crate")
        self.assertEqual((e.move_profile(a)[0], a.staged("spe")), (4, 28))
        e.gm.set_carried_objects(a, [], "released crate")
        self.assertEqual((e.move_profile(a)[0], a.staged("spe")), (5, 36))
        e.gm.set_carried_objects(a, [{"id": "crate", "weight_kg": 60}], "weighed staggering crate")
        self.assertEqual((e.move_profile(a)[0], a.staged("spe")), (1, 20))

    def setup_case(self, move_id, stage=0, injuries=False, slowed=False):
        case = setup_fixture.SetupMoveStateTests("test_fly_reuses_learned_sky_and_actual_paid_path_then_descends")
        case.r = self.r
        case.setUp()
        case.e.gm.set_stage(case.a, "spe", value=stage)
        if injuries:
            self.legs(case.e, case.a)
        if slowed:
            case.e.apply_status(case.a, "둔화")
        options = {}
        if move_id == setup_fixture.DIG:
            options = {"diggable": True, "reason": "observed loose earth"}
        elif move_id == setup_fixture.DIVE:
            case.e.observe_map_terrain([(x, 2) for x in range(2, 19)], base="underwater",
                                      reason="observed continuous deep-water lane")
            options = {"water_depth_m": 12, "reason": "measured twelve-metre water"}
        case.e.use_setup_move_on(case.a, case.b, move_id, case.e.everyone, setup_options=options)
        case.next_turn()
        return case

    def resolution_options(self, move_id, steps):
        path = [(x, 2) for x in range(3, 3 + steps)]
        if move_id == setup_fixture.FLY:
            return {"path": [{"position": point, "altitude": 25} for point in path]}
        if move_id == setup_fixture.DIG:
            return {"path": path, "diggable": True, "reason": "observed continuous loose-earth path"}
        return {"path": path}

    def test_setup_moves_use_current_capabilities_before_their_source_multiplier(self):
        rows = [(setup_fixture.FLY, (4, 14, 6, 4)),
                (setup_fixture.DIG, (2, 7, 3, 2)),
                (setup_fixture.DIVE, (2, 6, 2, 1))]
        variants = [dict(stage=-6), dict(stage=6), dict(injuries=True), dict(slowed=True)]
        for move_id, allowances in rows:
            for modifiers, allowance in zip(variants, allowances):
                with self.subTest(move=move_id, modifiers=modifiers):
                    case = self.setup_case(move_id, **modifiers)
                    case.b.pos = (4 + allowance, 2)
                    before = deepcopy((case.a.spec, case.a.custom_conditions, case.a.pos,
                                       case.a.budget, case.a.move_uses, case.e.rng.getstate()))
                    with self.assertRaisesRegex(ValueError, "path did not complete"):
                        case.e.use_setup_move_on(case.a, case.b, move_id, case.e.everyone,
                                                 setup_options=self.resolution_options(move_id, allowance + 1))
                    self.assertEqual((case.a.spec, case.a.custom_conditions, case.a.pos,
                                      case.a.budget, case.a.move_uses, case.e.rng.getstate()), before)
                    case.b.pos = (3 + allowance, 2)
                    with patch.object(case.e, "d20", return_value=10):
                        case.e.use_setup_move_on(case.a, case.b, move_id, case.e.everyone,
                                                 setup_options=self.resolution_options(move_id, allowance))
                    self.assertEqual(case.a.pos, (2 + allowance, 2))
                    self.assertEqual(case.a.move_uses[move_id], 1)
                    self.assertIsNone(setup_fixture.SETUP.pending(case.a))

    def test_frighten_uses_current_highest_owned_mode_before_its_new_slow(self):
        fixture = ability_fixture.AbilityNativeActionTests()
        fixture.r = self.r
        rows = [({"land": 4}, -6, False, False, "land", 2),
                ({"land": 1, "sky": 4}, -6, False, False, "sky", 2),
                ({"land": 1, "sky": 0}, 6, False, False, "land", 4),
                ({"land": 4}, -4, True, False, "land", 2),
                ({"land": 4}, -6, False, True, "land", 1)]
        for values, stage, injuries, slowed, mode, current in rows:
            with self.subTest(values=values, stage=stage, injuries=injuries, slowed=slowed):
                trainer = fixture.trainer("trainer", pos=(15, 5))
                user = fixture.pokemon("user", "겁주기", pos=(5, 5))
                target = fixture.pokemon("target", None, pos=(6, 5), side="wild",
                                         extra={"trainer_id": trainer.entity_id})
                e = fixture.engine(trainer, user, target)
                e.gm.set_movement_capabilities(target, values, basis="current", reason="observed current modes")
                e.gm.set_stage(target, "spe", value=stage)
                if injuries:
                    self.legs(e, target)
                if slowed:
                    e.apply_status(target, "둔화")
                fixture.turn(e, user)
                result = e.activate_ability(user, "겁주기", target)["details"]
                self.assertEqual((result["movement_mode"], result["movement_value"]), (mode, current))
                self.assertEqual(result["displacement"]["moved"], min(3, current))
                self.assertEqual(cheb((6, 5), target.pos), min(3, current))
                self.assertEqual(cheb(user.pos, target.pos), 1 + min(3, current))
                self.assertEqual(cheb(trainer.pos, target.pos), 9 - min(3, current))
                self.assertIn("둔화", target.conditions)

    def test_power_herb_skip_uses_the_same_current_distance_caps(self):
        for move_id, allowance in ((setup_fixture.FLY, 4), (setup_fixture.DIG, 2), (setup_fixture.DIVE, 2)):
            with self.subTest(move=move_id):
                case = herb_fixture.PowerHerbTests()
                case.r = self.r
                case.fixture(native=True)
                case.choose(move_id)
                if move_id == setup_fixture.FLY:
                    case.e.aerial_move(case.a, case.a.pos, mode="sky", altitude=2,
                                       reason_text="actual ordinary flight before skipping preparation")
                elif move_id == setup_fixture.DIVE:
                    case.e.observe_map_terrain([(x, 2) for x in range(2, 10)], base="underwater",
                                               reason="actual continuous deep water")
                self.legs(case.e, case.a)
                case.e.gm.set_stage(case.a, "spe", value=-4)
                case.b.pos = (4 + allowance, 2)
                def options(steps):
                    result = self.resolution_options(move_id, steps)
                    if move_id == setup_fixture.FLY:
                        for node in result["path"]:
                            node["altitude"] = 2
                    elif move_id == setup_fixture.DIVE:
                        result.update(water_depth_m=12, reason="measured twelve-metre water")
                    return result
                before = case.state()
                with self.assertRaisesRegex(ValueError, "path did not complete"):
                    case.e.use_setup_move_on(case.a, case.b, move_id, case.e.everyone,
                                             setup_options=options(allowance + 1))
                self.assertEqual(case.state(), before)
                case.b.pos = (3 + allowance, 2)
                with patch.object(Engine, "d20", return_value=10):
                    case.e.use_setup_move_on(case.a, case.b, move_id, case.e.everyone,
                                             setup_options=options(allowance))
                self.assertEqual(case.a.pos, (2 + allowance, 2))
                case.consumed(move_id)

    def grapple_case(self):
        case = grapple_fixture.GrappleTests()
        case.r = self.r
        case.setUp()
        return case

    def test_grapple_drag_subtracts_weight_after_current_movement_and_keeps_exception(self):
        case = self.grapple_case()
        declaration = GRAPPLE.native_policy()
        declaration["drag_penalties"] = {"2": 1}
        case.b.spec["weight_class"] = 2
        case.enter(declaration=declaration)
        case.turn_a_next()
        case.e.gm.set_stage(case.a, "spe", value=-6)
        path = [dict(actor=[1, y], partner=[2, y]) for y in range(2, 5)]
        before = case.snapshot()
        with self.assertRaisesRegex(ValueError, "exceeds reduced native movement"):
            case.e.grapple_action(case.a, "drag", path=path)
        self.assertEqual(case.snapshot(), before)
        case.e.grapple_action(case.a, "drag", path=path[:2])
        self.assertEqual((case.a.pos, case.b.pos, case.a.budget["shift"]), ((1, 3), (2, 3), 0))
        self.assertIsNotNone(GRAPPLE.relation(case.e, case.b))

    def test_phasing_escape_uses_current_range_without_ordinary_grapple_movement_ban(self):
        for stage, slowed, allowance in ((-6, False, 3), (0, True, 3), (-6, True, 1)):
            with self.subTest(stage=stage, slowed=slowed):
                case = self.grapple_case()
                case.enter()
                case.turn_b()
                case.b.spec["capabilities"] = ["Phasing"]
                case.e.gm.set_stage(case.b, "spe", value=stage)
                if slowed:
                    case.e.apply_status(case.b, "둔화")
                escape = dict(capability="Phasing", cost="shift", destination=[3 + allowance, 1])
                before = case.snapshot()
                with self.assertRaisesRegex(ValueError, "Phasing escape exceeds native movement"):
                    case.e.grapple_action(case.b, "escape", escape=escape)
                self.assertEqual(case.snapshot(), before)
                escape["destination"] = [2 + allowance, 1]
                self.assertTrue(case.e.grapple_action(case.b, "escape", escape=escape)["ended"])
                self.assertEqual((case.b.pos, case.b.budget["shift"]), ((2 + allowance, 1), 0))
                self.assertIsNone(GRAPPLE.relation(case.e, case.a))

    def test_phasing_rechecks_current_distance_after_actual_passage_observation(self):
        import cleanse_tags as CLEANSE
        case = self.grapple_case()
        case.enter()
        case.turn_b()
        case.b.spec["capabilities"] = ["Phasing"]
        original = CLEANSE.phasing_passage
        def passage(engine, actor, destination, **options):
            result = original(engine, actor, destination, **options)
            engine.gm.set_stage(actor, "spe", value=-6, reason="changed speed after passage observation")
            return result
        before = deepcopy((case.a.pos, case.b.pos, case.b.budget, GRAPPLE.relation(case.e, case.b)))
        with patch.object(CLEANSE, "phasing_passage", side_effect=passage):
            with self.assertRaisesRegex(ValueError, "Phasing escape exceeds native movement"):
                case.e.grapple_action(case.b, "escape",
                                      escape=dict(capability="Phasing", cost="shift", destination=[6, 1]))
        self.assertEqual((case.a.pos, case.b.pos, case.b.budget, GRAPPLE.relation(case.e, case.b)), before)
        self.assertEqual(case.b.stages["spe"], -6)


if __name__ == "__main__":
    unittest.main()
