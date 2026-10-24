"""Direct observable tests for the eight optional state-effect contracts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import effects_ext as EXT
import frequency as FREQUENCY
import optional_state_effect_contracts as OPTIONAL
import skill_modifiers as SKILL


class OptionalStateEffectEightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="all")

    def fixture(self, feature, *, choice=None):
        engine = Engine(self.rules, seed=2468)
        engine.grid = Grid(12, 8)
        extra = {
            "feats": [feature] if feature else [],
            "edges": [],
            "skills": {"매력": "숙련", "전투": "숙련", "집중": "숙련"},
            "optional_state_choices": {} if choice is None else {"ERRATA-056": choice},
        }
        owner = Combatant(
            self.rules,
            build_trainer(
                self.rules, "Owner", 30,
                {"hp": 40, "atk": 20, "def": 20, "spa": 20, "spd": 20, "spe": 20},
                moves=["몸통박치기"], abilities=[], skills=extra["skills"], extra=extra,
            ),
        )
        ally1 = Combatant(self.rules, build_pokemon(
            self.rules, "이상해씨", 20, name="Ally1", moves=["몸통박치기"], abilities=[],
            extra={"trainer_id": owner.entity_id, "trainer": owner.name},
        ))
        ally2 = Combatant(self.rules, build_pokemon(
            self.rules, "파이리", 20, name="Ally2", moves=["몸통박치기"], abilities=[],
            extra={"trainer_id": owner.entity_id, "trainer": owner.name},
        ))
        enemy = Combatant(self.rules, build_pokemon(
            self.rules, "꼬부기", 20, name="Enemy", moves=["몸통박치기"], abilities=[]
        ))
        for actor, pos, side in (
            (owner, (0, 0), "party"), (ally1, (1, 0), "party"),
            (ally2, (4, 0), "party"), (enemy, (2, 0), "foe"),
        ):
            engine.gm.add_combatant(actor, pos=pos, side=side, reason="optional state-effect fixture")
        for ally in (ally1,ally2):
            engine.gm.observe_sensory_environment(owner,ally,paths={"auditory":True},present=True,reason="actual errata Order delivery")
        engine.begin_encounter(engine.everyone)
        engine.start_round(engine.everyone)
        engine.start_of_turn(owner, initiative_count=20)
        return engine, owner, ally1, ally2, enemy

    def snapshot(self, engine, *actors):
        return (
            [deepcopy(actor.spec) for actor in actors],
            [deepcopy(getattr(actor, "budget", None)) for actor in actors],
            [deepcopy(getattr(actor, "_action_history", [])) for actor in actors],
            engine.rng.getstate(), list(engine.log_lines),
        )

    def test_policy_exact_eight_source_hashes_and_zero_credit_exclusions(self):
        policy = OPTIONAL._policy(self.rules)
        self.assertEqual(set(policy["completion_ids"]), OPTIONAL.COMPLETION_IDS)
        self.assertEqual(len(policy["clauses"]), 8)
        self.assertEqual(set(policy["excluded_zero_credit"]),
                         {"FAN-083", "FAN-084", "FAN-090", "FAN-092", "FAN-098", "FAN-113"})
        for relative, digest in policy["source_files"].items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)
        for clause_id, row in policy["clauses"].items():
            for source in row["sources"]:
                lines = (ROOT / source["file"]).read_text(encoding="utf-8").splitlines()
                excerpt = "\n".join(lines[source["start"] - 1:source["end"]])
                self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(), source["excerpt_sha256"], clause_id)

    def test_errata_global_conditions_use_native_initiative_action_frequency_and_evasion_contracts(self):
        self.assertTrue(OPTIONAL.validate_global_conditions(self.rules))
        e, owner, ally, _, _ = self.fixture(None)
        base = e.initiative_value(ally).value
        ally.conditions.add("마비")
        self.assertEqual(e.initiative_value(ally).value, base // 2)
        ally.conditions.discard("마비")
        ally.conditions.add("실명")
        self.assertEqual(ally.evasion("물리"), 0)
        suppression = self.rules.condition_effects("억압")
        self.assertEqual(next(row for row in suppression if row["type"] == "move_frequency_lock")["allowed"], ["임의"])
        self.assertEqual(next(row for row in suppression if row["type"] == "duration")["rounds"], 1)

    def test_go_fight_win_all_three_choices_and_failed_activation_are_atomic(self):
        feature = "feat/응원-문구-1"
        # Permanent selected Defense stage to every present ally, never the foe.
        e, owner, a, b, foe = self.fixture(feature, choice="def")
        result = e.activate_optional_state_effect(owner, "ERRATA-056", choice="defense")
        self.assertEqual(set(result["targets"]), {a.entity_id, b.entity_id})
        self.assertEqual((a.stages["def"], b.stages["def"], foe.stages["def"]), (1, 1, 0))
        self.assertFalse(FREQUENCY.activation_allowed(owner, "ERRATA-056:defense", {"kind": "scene", "uses": 1}, engine=e))

        # Temporary HP is the owner's actual Charm rank.
        e, owner, a, b, _ = self.fixture(feature)
        e.activate_optional_state_effect(owner, "ERRATA-056", choice="temp_hp")
        expected = SKILL.rank(self.rules, owner, "매력")[2]
        self.assertEqual((a.temp_hp, b.temp_hp), (expected, expected))

        # Evasion lasts one full round to its original initiative count.
        e, owner, a, b, _ = self.fixture(feature)
        before = a.evasion("물리")
        e.activate_optional_state_effect(owner, "ERRATA-056", choice="evasion")
        self.assertEqual(a.evasion("물리"), min(9, before + 2))
        e.end_of_turn(owner)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(owner, initiative_count=20)
        self.assertEqual(a.evasion("물리"), before)

        # Insufficient AP cannot consume action, frequency, RNG, or target state.
        e, owner, a, b, _ = self.fixture(feature, choice="def")
        owner.spec["ap_removed"] = owner.ap_account.maximum()
        frozen = self.snapshot(e, owner, a, b)
        with self.assertRaisesRegex(ValueError, "available AP"):
            e.activate_optional_state_effect(owner, "ERRATA-056", choice="defense")
        self.assertEqual(self.snapshot(e, owner, a, b), frozen)

    def test_virtuoso_errata_charm_restores_effective_eight_without_changing_six_dice(self):
        import state_grants as G,state_codec as CODEC
        e,owner,a,b,_=self.fixture("feat/응원-문구-1")
        e.gm.set_skill(owner,"매력",6,reason="actual Master Charm before Virtuoso acquisition")
        G.transition(e,owner,lambda engine,actor:actor.spec.update(
            edges=[*actor.spec.get("edges",[]),"edge/거장"],edge_choices={"edge/거장":["매력"]}))
        self.assertEqual(SKILL.effective_rank(e.r,owner,"매력"),8)
        ids=[actor.entity_id for actor in (owner,a,b)]
        e=CODEC.load_engine(Rules(str(e.r.root),ruleset="all"),json.loads(json.dumps(CODEC.dump_engine(e))))
        index={actor.entity_id:actor for actor in e.everyone};owner,a,b=[index[uid] for uid in ids]
        self.assertEqual(SKILL.rank(e.r,owner,"매력")[2],6)
        e.activate_optional_state_effect(owner,"ERRATA-056",choice="temp_hp")
        self.assertEqual((a.temp_hp,b.temp_hp),(8,8))
        CODEC.dump_engine(e)

    def test_colossus_march_halves_actual_stats_then_third_round_commits_two_stages(self):
        feature = "feat/메이저-기프트-거신의-행진"
        e, owner, target, _, _ = self.fixture(feature)
        before = (target.staged("atk"), target.staged("spe"))
        e.activate_optional_state_effect(owner, "SB-099", target=target)
        self.assertEqual((target.staged("atk"), target.staged("spe")),
                         (before[0] // 2, before[1] // 2))
        record = OPTIONAL.records(target)[0]
        self.assertEqual(record["expires_round"], e.round_no + 3)
        e.round_no = record["expires_round"]
        OPTIONAL.finish_round(e)
        self.assertEqual((target.stages["atk"], target.stages["spe"]), (2, 2))
        self.assertFalse(OPTIONAL.records(target))
        self.assertGreater(target.staged("atk"), before[0])

    def test_colossus_next_three_actual_rounds_end_after_the_third_upcoming_round(self):
        import action_points as AP
        e, owner, target, _, _ = self.fixture('feat/메이저-기프트-거신의-행진')
        before = (target.staged('atk'), target.staged('spe'))
        ap = AP.available(owner)
        e.activate_optional_state_effect(owner, 'SB-099', target=target)
        record = deepcopy(OPTIONAL.records(target)[0])
        self.assertEqual((AP.available(owner), owner.budget['standard']), (ap - 2, 0))
        self.assertEqual(record['round_counting'], 'following_rounds_v1')
        e.end_of_turn(owner)
        for _ in range(3):
            e.end_round()
            self.assertEqual(OPTIONAL.records(target), [record])
            self.assertEqual((target.stages['atk'], target.stages['spe']), (0, 0))
            e.start_round(e.everyone)
        self.assertEqual(e.round_no, record['created_round'] + 3)
        e.at_initiative_count(20)
        e.at_initiative_count(1)
        self.assertEqual((target.staged('atk'), target.staged('spe')),
                         (before[0] // 2, before[1] // 2))
        self.assertEqual(OPTIONAL.records(target), [record])
        e.end_round()
        self.assertFalse(OPTIONAL.records(target))
        self.assertEqual((target.stages['atk'], target.stages['spe']), (2, 2))
        self.assertTrue(e.validate_state()['valid'])

    def test_colossus_actual_legacy_and_new_producers_keep_deadlines_through_gm_and_fresh_rules(self):
        import world_entities as WORLD
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                e, owner, target, _, _ = self.fixture('feat/메이저-기프트-거신의-행진')
                # Execute the actual former producer, rather than editing a
                # historical record or pretending it selected a new policy.
                basis = None if legacy else OPTIONAL.COLOSSUS_ROUND_COUNTING
                with patch.object(OPTIONAL, 'COLOSSUS_ROUND_COUNTING', basis):
                    e.activate_optional_state_effect(owner, 'SB-099', target=target)
                record = deepcopy(OPTIONAL.records(target)[0])
                self.assertEqual('round_counting' in record, not legacy)
                self.assertEqual(record['expires_round'], record['created_round'] + (2 if legacy else 3))
                e.gm.snapshot('colossus-original')
                e.end_of_turn(owner)
                e.end_round()
                e.gm.restore('colossus-original')
                self.assertEqual(OPTIONAL.records(target), [record])
                saved = e.export_state()
                loaded = Engine.import_state(Rules(ROOT, ruleset='all'), json.loads(json.dumps(saved)))
                for actual in (e, loaded):
                    actual_target = WORLD.actor_index(actual)[target.entity_id]
                    actual_owner = WORLD.actor_index(actual)[owner.entity_id]
                    self.assertEqual(OPTIONAL.records(actual_target), [record])
                    self.assertTrue(actual.validate_state()['valid'])
                    actual.end_of_turn(actual_owner)
                    while actual.round_no < record['expires_round']:
                        actual.end_round()
                        self.assertEqual(OPTIONAL.records(actual_target), [record])
                        actual.start_round(actual.everyone)
                    actual.end_round()
                    self.assertFalse(OPTIONAL.records(actual_target))
                    self.assertEqual((actual_target.stages['atk'], actual_target.stages['spe']), (2, 2))
                # A lone deadline edit cannot silently change either basis.
                restored = Engine.import_state(Rules(ROOT, ruleset='all'), json.loads(json.dumps(saved)))
                restored_target = WORLD.actor_index(restored)[target.entity_id]
                OPTIONAL.records(restored_target)[0]['expires_round'] += 1
                self.assertFalse(restored.validate_state()['valid'])

    def test_colossus_march_low_stats_keep_one_after_its_actual_halving(self):
        import state_fields as F
        for kind in ('trainer', 'pokemon'):
            e, owner, pokemon, _, _ = self.fixture('feat/메이저-기프트-거신의-행진')
            target = owner if kind == 'trainer' else pokemon
            F.base_patch(target, {'stats': dict(target.spec['stats'], atk=1, spe=3)},
                         reason='observed low non-HP statistics')
            e.change_stage(target, 'spe', -6)
            defense = target.staged('def')
            e.activate_optional_state_effect(owner, 'SB-099', target=target)
            self.assertEqual((target.staged('atk'), target.staged('spe')), (1, 1))
            self.assertEqual(target.staged('def'), defense)
            self.assertEqual((target.stats['atk'], target.stats['spe']), (1, 3))
            self.assertEqual((target.stages['atk'], target.stages['spe']), (0, -6))
            e.round_no = OPTIONAL.records(target)[0]['expires_round']
            OPTIONAL.finish_round(e)
            self.assertFalse(OPTIONAL.records(target))
            self.assertEqual((target.stages['atk'], target.stages['spe']), (2, -4))
            self.assertEqual((target.staged('atk'), target.staged('spe')), (1, 1))

    def test_white_yang_projects_three_round_movement_stages_accuracy_and_daily_quota(self):
        feature = "feat/레시라무의-메이저-기프트-하얀-양"
        e, owner, a, b, foe = self.fixture(feature)
        base_move = EXT.movement_profile(e, a, 4, 0)[0]
        base_atk = a.staged("atk")
        result = e.activate_optional_state_effect(owner, "SB-107", targets=(a, b))
        self.assertEqual(set(result["targets"]), {a.entity_id, b.entity_id})
        self.assertEqual(EXT.movement_profile(e, a, 4, 0)[0], base_move + 2)
        self.assertGreater(a.staged("atk"), base_atk)
        import combat_modifiers as COMBAT_MODS
        self.assertEqual(COMBAT_MODS.accuracy_stage(a), -2)
        self.assertEqual(OPTIONAL.attack_modifiers(a, self.rules.move("move/몸통박치기"))[0], 0)
        self.assertEqual(OPTIONAL.attack_modifiers(foe, self.rules.move("move/몸통박치기"))[0], 0)
        self.assertFalse(FREQUENCY.activation_allowed(owner, "SB-107", {"kind": "daily", "uses": 1}, engine=e))
        self.assertEqual(OPTIONAL.records(a)[0]["count_deadline"], (4, 20))
        e.end_of_turn(owner)
        for _ in range(3):
            e.end_round()
            e.start_round(e.everyone)
        e.at_initiative_count(21)
        self.assertEqual(EXT.movement_profile(e, a, 4, 0)[0], base_move + 2)
        e.at_initiative_count(20)
        self.assertEqual(EXT.movement_profile(e, a, 4, 0)[0], base_move)
        self.assertEqual(a.staged("atk"), base_atk)

    def test_black_yin_projects_three_round_movement_replacement_and_evasion(self):
        feature = "feat/제크로무의-메이저-기프트-검은-음"
        e, owner, a, b, _ = self.fixture(feature)
        before_evasion = a.evasion("물리")
        e.activate_optional_state_effect(owner, "SB-110", targets=(a, b))
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 1)
        self.assertEqual(a.evasion("물리"), min(9, before_evasion + 2))
        self.assertEqual(OPTIONAL.records(a)[0]["count_deadline"], (4, 20))
        e.end_of_turn(owner)
        for _ in range(3):
            e.end_round()
            e.start_round(e.everyone)
        e.at_initiative_count(21)
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 1)
        e.at_initiative_count(20)
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 8)
        self.assertEqual(a.evasion("물리"), before_evasion)

    def test_yang_yin_breather_clears_combat_components_but_keeps_movement_clock(self):
        import combat_stage_sources as CS
        import combat_modifiers as MODS
        import state_codec as CODEC
        for clause_id, feature in (("SB-107", "feat/레시라무의-메이저-기프트-하얀-양"),
                                   ("SB-110", "feat/제크로무의-메이저-기프트-검은-음")):
            with self.subTest(clause=clause_id):
                e, owner, a, b, _ = self.fixture(feature)
                e.activate_optional_state_effect(owner, clause_id, targets=(a, b))
                deadline = OPTIONAL.records(a)[0]["count_deadline"]
                e.end_of_turn(owner)
                e.start_of_turn(a, initiative_count=15)
                e.apply_status(a, "구속")
                result = e.take_breather(a, request_id="blessing-breather:" + clause_id,
                    path=[a.pos], retreat_reason="Actual Stuck makes the furthest feasible retreat zero",
                    save_dc=16, save_reason="Actual table permission DC16 for Breather",
                    save_cost="full", fixed_save=20)
                self.assertTrue(result["completed"])
                self.assertEqual(CS.effective_stage(a, "atk"), 0)
                self.assertEqual(MODS.accuracy_stage(a), 0)
                record = OPTIONAL.records(a)[0]
                self.assertNotIn("evasion_modifier", record)
                self.assertNotIn("accuracy_modifier", record)
                self.assertEqual(record["count_deadline"], deadline)
                self.assertFalse(OPTIONAL.records(b)[0]["stages_reset"])
                self.assertEqual((OPTIONAL.movement_addition(a), OPTIONAL.movement_limit(a, 8)),
                                 (2, 8) if clause_id == "SB-107" else (0, 1))
                e = CODEC.load_engine(Rules(str(e.r.root), ruleset="all"),
                                      json.loads(json.dumps(CODEC.dump_engine(e))))
                a = next(actor for actor in e.everyone if actor.entity_id == a.entity_id)
                self.assertEqual(OPTIONAL.records(a)[0]["count_deadline"], deadline)
                self.assertTrue(OPTIONAL.records(a)[0]["stages_reset"])

    def test_yang_yin_recall_resets_combat_components_without_ending_movement(self):
        import combat_stage_sources as CS
        import combat_modifiers as MODS
        for clause_id, feature in (("SB-107", "feat/레시라무의-메이저-기프트-하얀-양"),
                                   ("SB-110", "feat/제크로무의-메이저-기프트-검은-음")):
            with self.subTest(clause=clause_id):
                e, owner, a, b, _ = self.fixture(feature)
                e.activate_optional_state_effect(owner, clause_id, targets=(a, b))
                deadline = OPTIONAL.records(a)[0]["count_deadline"]
                e.end_of_turn(owner)
                e.gm.recall(a, reason="actual recalled recipient with a three-round blessing")
                self.assertFalse(a.on_field)
                self.assertEqual((CS.effective_stage(a, "atk"), MODS.accuracy_stage(a)), (0, 0))
                self.assertEqual(OPTIONAL.records(a)[0]["count_deadline"], deadline)
                self.assertTrue(OPTIONAL.records(a)[0]["stages_reset"])
                e.gm.send_out(a)
                self.assertEqual(OPTIONAL.records(a)[0]["count_deadline"], deadline)
                e.end_encounter()
                self.assertFalse(OPTIONAL.records(a))

    def test_white_yang_native_accuracy_and_stages_obey_shared_caps(self):
        import combat_modifiers as MODS
        import combat_stage_sources as CS
        e, owner, a, _, foe = self.fixture("feat/레시라무의-메이저-기프트-하얀-양")
        e.gm.set_stage(a, "atk", value=6, reason="actual capped Attack stage")
        e.gm.set_stage(a, "acc", value=-6, reason="actual minimum Accuracy stage")
        e.activate_optional_state_effect(owner, "SB-107", targets=(a,))
        self.assertEqual((CS.effective_stage(a, "atk"), MODS.accuracy_stage(a)), (6, -6))
        e.accuracy_check(a, foe, self.rules.move("move/몸통박치기"), fixed_roll=10)
        self.assertTrue(any("명중 d20=10-6=4" in line for line in e.log_lines))

    def test_black_yin_extra_evasion_uses_shared_six_and_final_nine_caps(self):
        e, owner, a, _, _ = self.fixture("feat/제크로무의-메이저-기프트-검은-음")
        e.gm.set_stage(a, "eva", value=6, reason="actual capped extra Evasion")
        before = a.evasion("물리")
        e.activate_optional_state_effect(owner, "SB-110", targets=(a,))
        self.assertEqual(a.evasion("물리"), before)
        self.assertLessEqual(a.evasion("물리"), 9)

    def test_black_yin_both_source_choices_keep_their_movement_after_stage_reset(self):
        import state_codec as CODEC
        for variant, expected in (("korean_to_one", 1), ("english_decrease_one", 7)):
            with self.subTest(variant=variant):
                e, owner, a, _, _ = self.fixture("feat/제크로무의-메이저-기프트-검은-음")
                prepared = OPTIONAL.black_yin_source_options(e.r)
                choice = {"value": variant, "reason": "Explicit table selection of the conflicting Black Yin source",
                          "scope": prepared["decision_scope"]}
                e.activate_optional_state_effect(owner, "SB-110", targets=(a,), choice=choice)
                self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], expected)
                e.end_of_turn(owner)
                e.gm.recall(a, reason="actual recipient recall keeps the selected movement lifetime")
                e.gm.send_out(a)
                self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], expected)
                e = CODEC.load_engine(Rules(str(e.r.root), ruleset="all"),
                                      json.loads(json.dumps(CODEC.dump_engine(e))))
                a = next(actor for actor in e.everyone if actor.entity_id == a.entity_id)
                self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], expected)
                self.assertEqual(OPTIONAL.records(a)[0]["source_choice"]["receipt"]["values"]["variant"], variant)

    def test_black_yin_stale_source_scope_refuses_before_action_or_effect(self):
        import native_scenario_fixture as NATIVE
        e, owner, a, _, _ = self.fixture("feat/제크로무의-메이저-기프트-검은-음")
        scope = deepcopy(OPTIONAL.black_yin_source_options(e.r)["decision_scope"])
        scope["policy_id"] = "unrelated-source-policy"
        choice = {"value": "english_decrease_one", "reason": "actual conflicting-source choice", "scope": scope}
        NATIVE.assert_rejected_unchanged(e,
            lambda: e.activate_optional_state_effect(owner, "SB-110", targets=(a,), choice=choice),
            reason_pattern="scope")

    def test_three_round_blessings_keep_activation_count_when_owner_turn_changes(self):
        import state_codec as CODEC
        e, owner, a, _, _ = self.fixture("feat/레시라무의-메이저-기프트-하얀-양")
        e.activate_optional_state_effect(owner, "SB-107", targets=(a,))
        e.end_of_turn(owner)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(owner, initiative_count=30)
        self.assertEqual(OPTIONAL.records(a)[0]["count_deadline"], (4, 20))
        e.end_of_turn(owner)
        e = CODEC.load_engine(Rules(str(e.r.root), ruleset="all"),
                              json.loads(json.dumps(CODEC.dump_engine(e))))
        a = next(actor for actor in e.everyone if actor.entity_id == a.entity_id)
        for _ in range(2):
            e.end_round()
            e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=25)
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 10)
        e.end_of_turn(a)
        e.at_initiative_count(20)
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 8)
        self.assertFalse(OPTIONAL.records(a))

    def test_aiming_down_sights_consumes_only_next_ranged_weapon_attack_or_next_turn(self):
        feature = "feat/시야-아래-조준"
        from unittest.mock import patch
        import native_scenario_fixture as NATIVE
        import fast_combat as FAST
        def scene():
            declarations=[]
            for key,pos,side in (("owner",(2,2),"party"),("enemy",(8,2),"foe")):
                declarations.append({'key':key,'kind':'trainer','sheet':{
                    'name':key,'level':30,'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),
                    'moves':['move/몸통박치기'],'abilities':[],'pos':pos,'side':side,
                    'extra':{'feats':[feature] if key=='owner' else [],'skills':{'전투':4},
                             'movement':{'land':4,'power':2},'movement_basis':'current'}},
                    'body':{'size':'중형','offsets':[(0,0)],'reason':'actual long-range aiming actors'}})
            engine,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=2468,
                grid={'width':16,'height':10},actors=declarations)
            engine.start_round(engine.everyone);engine.start_of_turn(actors['owner'],initiative_count=20)
            return engine,actors['owner'],actors['enemy']
        e, owner, enemy = scene()
        e.activate_optional_state_effect(owner, "FAN-104")
        ordinary = self.rules.move("move/몸통박치기")
        self.assertEqual(OPTIONAL.attack_modifiers(owner, ordinary), (0, 0))
        self.assertTrue(OPTIONAL.records(owner, feature))
        import turn as TURN
        import weapon_actions as WEAPONS
        bow = TURN.equip_weapon(e, owner, {
            "name": "actual long-range bow", "kind": "장거리 사격무기",
            "grade": "간단", "slot": "주요손", "moves": [],
        })
        ranged = WEAPONS.prepare(e, owner, self.rules.move(bow), bow)
        self.assertEqual(OPTIONAL.attack_modifiers(owner, ranged), (2, 2))
        hit, natural, critical = e._accuracy_check_native(owner, enemy, ranged, fixed_roll=18)
        self.assertTrue(hit)
        self.assertEqual(natural, 18)
        self.assertTrue(critical)
        self.assertTrue(OPTIONAL.records(owner, feature))
        with patch.object(FAST, 'roll', return_value=18):
            e.use_move(owner, enemy, bow, weapon_id=bow, set_damage=True)
        self.assertFalse(OPTIONAL.records(owner, feature))

        e, owner, _ = scene()
        e.activate_optional_state_effect(owner, "FAN-104")
        e.end_of_turn(owner)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(owner, initiative_count=20)
        self.assertFalse(OPTIONAL.records(owner, feature))

    def test_state_validation_rejects_owner_or_policy_tampering(self):
        e, owner, a, _, _ = self.fixture("feat/메이저-기프트-거신의-행진")
        e.activate_optional_state_effect(owner, "SB-099", target=a)
        self.assertTrue(e.validate_optional_state_effect_contracts())
        OPTIONAL.records(a)[0]["owner_id"] = "missing-owner"
        with self.assertRaisesRegex(ValueError, "owner"):
            e.validate_optional_state_effect_contracts()


if __name__ == "__main__":
    unittest.main(verbosity=2)
