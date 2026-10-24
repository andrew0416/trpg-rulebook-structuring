"""Direct checks for the optional Baby Template's seven source clauses."""
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools"), str(ROOT / "examples")]

import test_category2_progression_state as PROGRESSION_FIX
from builder import build_pokemon, STATS
import baby_templates as BABY
import body_state as BODY
import capability_actions as CAP
import downtime as D
import growth_stats as GROWTH
import skill_modifiers as SKILLS
import state_codec as CODEC


class BabyTemplateTests(unittest.TestCase):
    setUpClass = classmethod(PROGRESSION_FIX.ProgressionStateTests.setUpClass.__func__)
    add = PROGRESSION_FIX.ProgressionStateTests.add

    def setUp(self):
        PROGRESSION_FIX.ProgressionStateTests.setUp(self)

    def pokemon(self, level=4, species="pokemon/automateon", **extra):
        values = {"trainer_id": self.a.entity_id, "height_m": 2.0, "weight_kg": 40.0, **extra}
        return self.add(build_pokemon(self.r, species, level, moves=[], abilities=[], extra=values))

    def skill(self, actor):
        return max(actor.spec["skills"], key=lambda name: SKILLS.rank(self.r, actor, name)[2])

    def snapshot(self):
        return json.dumps(CODEC.dump_engine(self.e), sort_keys=True, ensure_ascii=False)

    def restored_actor(self, actor):
        restored = CODEC.load_engine(self.r, json.loads(self.snapshot()))
        return next(row for row in restored.gm.everyone if row.entity_id == actor.entity_id)

    def test_explicit_choice_applies_all_native_stat_skill_power_and_body_consumers(self):
        pokemon = self.pokemon(); untouched = self.pokemon()
        skill = self.skill(pokemon)
        before_stats = dict(pokemon.stats); before_rank = SKILLS.rank(self.r, pokemon, skill)[2]
        before_power = CAP.power(pokemon)
        self.assertNotIn(BABY.KEY, untouched.spec)
        result = BABY.apply(self.e, pokemon, stat_reduction=3, height_reduction=.5,
            weight_reduction=.25, reason="GM explicitly chose the optional template")
        self.assertEqual(pokemon.stats, {stat: before_stats[stat] - 3 for stat in STATS})
        self.assertEqual(SKILLS.rank(self.r, pokemon, skill)[2], max(1, before_rank - 1))
        self.assertEqual(self.e.plan_skill_check(pokemon, skill, purpose="Baby Template direct check")["ordinary_rank"], max(1, before_rank - 1))
        self.assertEqual(CAP.power(pokemon), max(1, before_power - 2))
        self.assertEqual((BODY.projection(pokemon)["height_m"], BODY.projection(pokemon)["weight_kg"]), (1.0, 30.0))
        self.assertEqual(pokemon.weight_class, 3)
        self.assertEqual(tuple(result["clauses"]), BABY.CLAUSES)
        self.assertEqual(result["stat_penalty_remaining"], 3)
        self.assertNotIn(BABY.KEY, untouched.spec)
        self.assertEqual(BODY.projection(untouched)["baby_template"], None)

    def test_each_fifth_level_restores_every_base_stat_and_full_recovery_releases_skill_and_power(self):
        pokemon = self.pokemon(); skill = self.skill(pokemon)
        original_rank = SKILLS.rank(self.r, pokemon, skill)[2]; original_power = CAP.power(pokemon)
        BABY.apply(self.e, pokemon, stat_reduction=2, reason="recovering baby")
        reduced = dict(pokemon.stats)
        D.gain_exp_combatant(self.e, pokemon, "to next level")
        self.assertEqual((pokemon.level, pokemon.spec[BABY.KEY]["stat_penalty_remaining"]), (5, 1))
        self.assertTrue(all(pokemon.stats[stat] >= reduced[stat] + 1 for stat in STATS))
        self.assertEqual(SKILLS.rank(self.r, pokemon, skill)[2], max(1, original_rank - 1))
        D.gain_exp_combatant(self.e, pokemon, D.exp_for_level(self.r, 10) - pokemon.spec["exp"])
        self.assertEqual(pokemon.spec[BABY.KEY]["level_recoveries"], [5, 10])
        self.assertEqual(pokemon.spec[BABY.KEY]["stat_penalty_remaining"], 0)
        self.assertEqual(SKILLS.rank(self.r, pokemon, skill)[2], original_rank)
        self.assertEqual(CAP.power(pokemon), original_power)
        self.assertEqual(GROWTH.project_actor(self.e, pokemon)["permanent"]["stats"], pokemon.spec["stats"])

    def test_unspecified_physical_growth_is_pending_until_observed_and_survives_save(self):
        pokemon = self.pokemon()
        BABY.apply(self.e, pokemon, stat_reduction=2, height_reduction=.5,
            weight_reduction=.5, permanent_height_reduction=.1,
            permanent_weight_reduction=.1, reason="baby body selected")
        D.gain_exp_combatant(self.e, pokemon, "to next level")
        self.assertEqual(pokemon.spec[BABY.KEY]["pending_growth_levels"], [5])
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "increase height or weight"):
            BABY.record_growth(self.e, pokemon, level=5, height_reduction=.5,
                weight_reduction=.5, reason="not actually larger")
        self.assertEqual(self.snapshot(), before)
        result = BABY.record_growth(self.e, pokemon, level=5, height_reduction=.25,
            weight_reduction=.2, reason="GM observed the fifth-level growth")
        self.assertEqual((result["height_m"], result["weight_kg"]), (1.5, 32.0))
        self.assertEqual(pokemon.spec[BABY.KEY]["pending_growth_levels"], [])
        restored = self.restored_actor(pokemon)
        self.assertEqual(BODY.projection(restored)["height_m"], 1.5)
        self.assertEqual(BODY.projection(restored)["weight_kg"], 32.0)
        self.assertEqual((pokemon.spec['weight_class'], pokemon.weight_class, restored.weight_class), (3, 3, 3))
        self.assertEqual(restored.spec[BABY.KEY]["physical_growth"][0]["level"], 5)
        payload=json.loads(self.snapshot());actor_node=next(x for x in payload["nodes"].values() if x.get("kind")=="actor" and x.get("entity_id")==pokemon.entity_id)
        attrs_node=payload["nodes"][actor_node["attrs"]["$ref"]]
        spec_ref=next(pair for pair in attrs_node["items"] if pair[0]=="spec")[1]["$ref"];spec_node=payload["nodes"][spec_ref]
        baby_pair=next(pair for pair in spec_node["items"] if pair[0]==BABY.KEY);baby_node=payload["nodes"][baby_pair[1]["$ref"]]
        remaining=next(pair for pair in baby_node["items"] if pair[0]=="stat_penalty_remaining");remaining[1]=0
        with self.assertRaisesRegex(CODEC.StateCodecError,"stat recovery count"):
            CODEC.load_engine(self.r,payload)

    def test_partial_and_full_permanence_keep_the_selected_remainder(self):
        partial = self.pokemon(level=9); skill = self.skill(partial)
        partial_power = CAP.power(partial)
        BABY.apply(self.e, partial, stat_reduction=4, permanent_stat_reduction=2,
            reason="partially permanent baby form")
        D.gain_exp_combatant(self.e, partial, D.exp_for_level(self.r, 15) - partial.spec["exp"])
        self.assertEqual(partial.spec[BABY.KEY]["stat_penalty_remaining"], 2)
        self.assertEqual(partial.spec[BABY.KEY]["level_recoveries"], [10, 15])
        self.assertEqual(SKILLS.rank(self.r, partial, skill)[2], max(1,
            int(partial.spec["skills"][skill].split("d6")[0]) - 1))
        self.assertEqual(CAP.power(partial), max(1, partial_power - 2))
        species = next(row for row in sorted(self.r.species.values(), key=lambda x: x["id"])
            if sum(row.get("base_stats", {}).values()) > 60 and min(row["base_stats"].values()) >= 5)
        permanent = self.pokemon(level=14, species=species["id"])
        BABY.apply(self.e, permanent, stat_reduction=4, permanent_stat_reduction=4,
            height_reduction=.5, weight_reduction=.5,
            permanent_height_reduction=.5, permanent_weight_reduction=.5,
            reason="permanent legendary-scale baby form")
        D.gain_exp_combatant(self.e, permanent, "to next level")
        row = permanent.spec[BABY.KEY]
        self.assertTrue(row["high_base_total"])
        self.assertEqual((row["stat_penalty_remaining"], row["level_recoveries"]), (4, [15]))
        self.assertEqual(row["pending_growth_levels"], [])
        self.assertEqual(BODY.projection(permanent)["baby_template"]["permanence"], "permanent")

    def test_invalid_or_duplicate_choices_are_atomic_and_weak_species_is_not_auto_adjusted(self):
        weak = self.add(build_pokemon(self.r, "잉어킹", 1, moves=[], abilities=[],
            extra={"trainer_id": self.a.entity_id}))
        self.assertNotIn(BABY.KEY, weak.spec)
        for kwargs, message in (({"stat_reduction": 1}, "2, 3, or 4"),
                ({"stat_reduction": 2, "height_reduction": .51}, "between 0 and 0.5"),
                ({"stat_reduction": 4}, "lower than 1")):
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, message):
                BABY.apply(self.e, weak, reason="invalid explicit choice", **kwargs)
            self.assertEqual(self.snapshot(), before)
        pokemon = self.pokemon(); BABY.apply(self.e, pokemon, stat_reduction=2, reason="first choice")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "already applied"):
            BABY.apply(self.e, pokemon, stat_reduction=2, reason="duplicate choice")
        self.assertEqual(self.snapshot(), before)

    def test_rank_names_numbers_aliases_and_species_pools_lose_one_rank_on_native_walk(self):
        from declared_skill_ranks import configure
        from native_scenario_fixture import assert_rejected_unchanged
        with patch.object(self.r, 'rulings', deepcopy(self.r.rulings)):
            configure(self.r)
            cases = (({'육상': '초보'}, 2, 0), ({'육상': 3}, 2, 0),
                     ({'육상': '3d6+2'}, 2, 2), ({'육상': '1d6-2'}, 1, -2),
                     ({'육상': '8d6+3'}, 7, 3), ({'육상': 7}, 6, 0),
                     ({'육상': 10}, 6, 0), ({'육상': '초보', 'Athletics': '3d6'}, 2, 0))
            for skills, dice, bonus in cases:
                with self.subTest(skills=skills):
                    pokemon = self.pokemon(skills=skills)
                    original = deepcopy(pokemon.spec['skills'])
                    BABY.apply(self.e, pokemon, stat_reduction=2, reason='observed newborn handicap')
                    plan = self.e.plan_skill_check(pokemon, '육상', purpose='Baby rank pool walk')
                    self.assertEqual((plan['ordinary_rank'], plan['dice_count'], plan['modifier']), (dice, dice, bonus))
                    roll = self.e.skill_roll(pokemon, '육상', fixed=[2]*dice)
                    self.assertEqual((roll.rank, len(roll.faces), roll.total), (dice, dice, 2*dice+bonus))
                    self.assertEqual(pokemon.spec['skills'], original)
            conflict = self.pokemon(skills={'육상': '초보', 'Athletics': '3d6+1'})
            BABY.apply(self.e, conflict, stat_reduction=2, reason='newborn with conflicting imported aliases')
            assert_rejected_unchanged(self.e, lambda:self.e.skill_roll(conflict, '육상', fixed=[2]*2),
                                      reason_pattern='conflicting Pokemon skill pool aliases')

    def test_actual_pushed_training_adds_one_die_after_baby_penalty_and_recovery_restores_pool(self):
        from builder import build_trainer
        import researcher_features as RF
        trainer = self.add(build_trainer(self.r, 'baby skill trainer', 20, dict.fromkeys(STATS, 10),
            skills={'포켓몬학':3, '명령':3}, extra={'classes':[RF.RESEARCHER],
            'feats':[RF.PUSHER, RF.SKILL_TRAINER], 'edges':['edge/미용사'], 'items':{'미용사 킷':1},
            'feature_choices':{RF.RESEARCHER:[['pokemon_caretaking', 'paleontology']]}}))
        pokemon = self.pokemon(level=4, trainer_id=trainer.entity_id, skills={'육상':'3d6+2'})
        BABY.apply(self.e, pokemon, stat_reduction=2, reason='actual trained baby')
        self.e.pokemon_activity(trainer, 'groom', targets=[pokemon],
                                pushed_skills={pokemon.entity_id:'육상'}, safe=True)
        plan = self.e.plan_skill_check(pokemon, '육상', purpose='pushed baby skill')
        self.assertEqual((plan['ordinary_rank'], plan['dice_count'], plan['modifier']), (2, 3, 2))
        roll = self.e.skill_roll(pokemon, '육상', fixed=[2]*3)
        self.assertEqual((roll.rank, len(roll.faces), roll.total), (2, 3, 8))
        out = self.e.common_action(pokemon, '육상', 8, mode='extended', task_id='baby-pushed-task',
            interval_id='one', interval={'amount':1, 'unit':'minute'}, interval_completed=True,
            complexity=2, limited=True, fixed=[2]*3)
        self.assertEqual(out.result.attempt_limit, 1)
        D.gain_exp_combatant(self.e, pokemon, D.exp_for_level(self.r, 10)-pokemon.spec['exp'])
        self.assertEqual(pokemon.spec[BABY.KEY]['stat_penalty_remaining'], 0)
        self.assertEqual(SKILLS.rank(self.r, pokemon, '육상')[2], 3)
        self.assertEqual(pokemon.spec['skills']['육상'], '3d6+2')

    def test_mass_class_crossings_growth_endpoints_and_ordered_grants_use_existing_owners(self):
        from native_scenario_fixture import assert_rejected_unchanged
        import state_grants as GRANTS
        pokemon = self.pokemon(weight_kg=88, weight_class=4)
        BABY.apply(self.e, pokemon, stat_reduction=2, weight_reduction=.5,
                   permanent_weight_reduction=.1, reason='actual forty four kg baby')
        self.assertEqual((BODY.weight_kg(pokemon), pokemon.spec['weight_class'], pokemon.weight_class), (44, 3, 3))
        D.gain_exp_combatant(self.e, pokemon, 'to next level')
        BABY.record_growth(self.e, pokemon, level=5, height_reduction=0,
                           weight_reduction=.1, reason='observed growth to permanent floor')
        self.assertAlmostEqual(BODY.weight_kg(pokemon), 79.2)
        self.assertEqual((pokemon.spec['weight_class'], pokemon.weight_class), (4, 4))
        restored = self.restored_actor(pokemon)
        self.assertEqual((restored.weight_class, restored.spec[BABY.KEY]['weight_reduction']), (4, .1))
        edge = self.pokemon(weight_kg=100, weight_class=4)
        assert_rejected_unchanged(self.e, lambda:BABY.apply(self.e, edge, stat_reduction=2,
            weight_reduction=.5, reason='ambiguous fifty kg endpoint'), reason_pattern='shared Weight Class boundary')
        for bad in (1, 7, True):
            assert_rejected_unchanged(self.e, lambda bad=bad:BABY.apply(self.e, edge, stat_reduction=2,
                weight_reduction=.5, weight_class=bad, reason='wrong endpoint observation'),
                reason_pattern='disagrees with actual mass interval')
        BABY.apply(self.e, edge, stat_reduction=2, weight_reduction=.5, weight_class=3,
                   reason='GM observed lower shared endpoint class')
        self.assertEqual((BODY.weight_kg(edge), edge.weight_class), (50, 3))
        D.gain_exp_combatant(self.e, edge, 'to next level')
        assert_rejected_unchanged(self.e, lambda:BABY.record_growth(self.e, edge, level=5,
            height_reduction=0, weight_reduction=0, reason='growth onto shared hundred kg endpoint'),
            reason_pattern='shared Weight Class boundary')
        BABY.record_growth(self.e, edge, level=5, height_reduction=0, weight_reduction=0,
            weight_class=4, reason='GM observed hundred kg class on actual growth')
        self.assertEqual((BODY.weight_kg(edge), edge.weight_class), (100, 4))
        metal = self.pokemon(weight_kg=88, weight_class=4)
        GRANTS._source(metal, 'fixture/existing-weight-replacement', 'effect')
        GRANTS.weight(metal, 7, 'fixture/existing-weight-replacement')
        BABY.apply(self.e, metal, stat_reduction=2, weight_reduction=.5, reason='baby beneath existing weight effect')
        self.assertEqual((metal.spec['weight_class'], metal.weight_class), (3, 7))
        GRANTS.revoke(metal, 'fixture/existing-weight-replacement', engine=self.e)
        self.assertEqual(metal.weight_class, 3)


if __name__ == "__main__":
    unittest.main()
