"""Direct observable tests for the eight optional state-effect contracts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

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
        self.assertEqual(record["expires_round"], e.round_no + 2)
        e.round_no = record["expires_round"]
        OPTIONAL.finish_round(e)
        self.assertEqual((target.stages["atk"], target.stages["spe"]), (2, 2))
        self.assertFalse(OPTIONAL.records(target))
        self.assertGreater(target.staged("atk"), before[0])

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
        self.assertEqual(OPTIONAL.attack_modifiers(a, self.rules.move("move/몸통박치기"))[0], -2)
        self.assertEqual(OPTIONAL.attack_modifiers(foe, self.rules.move("move/몸통박치기"))[0], 0)
        self.assertFalse(FREQUENCY.activation_allowed(owner, "SB-107", {"kind": "daily", "uses": 1}, engine=e))
        expiry = OPTIONAL.records(a)[0]["expires_round"]
        e.round_no = expiry
        OPTIONAL.finish_round(e)
        self.assertEqual(EXT.movement_profile(e, a, 4, 0)[0], base_move)
        self.assertEqual(a.staged("atk"), base_atk)

    def test_black_yin_projects_three_round_movement_replacement_and_evasion(self):
        feature = "feat/제크로무의-메이저-기프트-검은-음"
        e, owner, a, b, _ = self.fixture(feature)
        before_evasion = a.evasion("물리")
        e.activate_optional_state_effect(owner, "SB-110", targets=(a, b))
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 1)
        self.assertEqual(a.evasion("물리"), min(9, before_evasion + 2))
        expiry = OPTIONAL.records(a)[0]["expires_round"]
        e.round_no = expiry
        OPTIONAL.finish_round(e)
        self.assertEqual(EXT.movement_profile(e, a, 8, 0)[0], 8)
        self.assertEqual(a.evasion("물리"), before_evasion)

    def test_aiming_down_sights_consumes_only_next_ranged_weapon_attack_or_next_turn(self):
        feature = "feat/시야-아래-조준"
        e, owner, _, _, enemy = self.fixture(feature)
        e.activate_optional_state_effect(owner, "FAN-104")
        ordinary = self.rules.move("move/몸통박치기")
        self.assertEqual(OPTIONAL.attack_modifiers(owner, ordinary), (0, 0))
        self.assertTrue(OPTIONAL.records(owner, feature))
        import turn as TURN
        import weapon_actions as WEAPONS
        bow = TURN.equip_weapon(e, owner, {
            "name": "actual short-range bow", "kind": "단거리 사격무기",
            "grade": "간단", "slot": "주요손", "moves": [],
        })
        ranged = WEAPONS.prepare(e, owner, self.rules.move(bow), bow)
        self.assertEqual(OPTIONAL.attack_modifiers(owner, ranged), (2, 2))
        hit, natural, critical = e._accuracy_check_native(owner, enemy, ranged, fixed_roll=18)
        self.assertTrue(hit)
        self.assertEqual(natural, 18)
        self.assertTrue(critical)
        self.assertFalse(OPTIONAL.records(owner, feature))

        e, owner, _, _, _ = self.fixture(feature)
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
