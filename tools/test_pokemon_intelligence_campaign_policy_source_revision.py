"""Current campaign admission never follows merely from a catalog skill pool."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from native_scenario_fixture import assert_rejected_unchanged
import pokemon_intelligence as INTELLIGENCE
import state_codec as CODEC
import world_entities as WORLD


class PokemonIntelligenceCampaignPolicySourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def scene(self, species='이상해씨'):
        e = Engine(self.rules, seed=542)
        trainer = Combatant(self.rules, build_trainer(
            self.rules, 'actual campaign Trainer', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            skills={'매력': 4}, abilities=[], pos=(0, 0)))
        e.gm.add_combatant(trainer, reason='actual current campaign participant')
        pokemon = Combatant(self.rules, build_pokemon(
            self.rules, species, 20, moves=[], abilities=[], pos=(2, 2),
            extra={'trainer_id': trainer.entity_id}))
        e.gm.add_combatant(pokemon, reason='actual catalog-built Pokemon with existing pools')
        return e, trainer, pokemon

    def configure(self, e, trainer, *, social, education, exceptions=None):
        return e.pokemon_activity(trainer, 'configure_intelligence',
            portrayal='actual discussed campaign portrayal', discussed_with=['GM', 'player'],
            social=social, education=education, exceptions=exceptions,
            reason='actual current campaign decision; no past assignment is inferred')

    def roll(self, e, actor, skill, dice, modifier=0):
        result = e.skill_roll(actor, skill, fixed=[2] * dice)
        self.assertEqual((result.rank, result.modifier, result.total), (dice, modifier, 2 * dice + modifier))

    def denied(self, e, actor, skill, *, reason='explicit current campaign Pokemon skill policy required'):
        assert_rejected_unchanged(e, lambda: e.skill_roll(actor, skill), reason_pattern=reason)

    def test_unset_policy_refuses_actual_optional_catalog_pools_and_plans_before_rng(self):
        e, trainer, pokemon = self.scene()
        sheet = deepcopy(pokemon.spec)
        self.assertIsNone(getattr(e, '_pokemon_intelligence_policy', None))
        for skill in ('매력', '의학', '생존', 'Survival'):
            with self.subTest(skill=skill):
                self.assertIsNone(INTELLIGENCE.eligibility(e, pokemon, skill))
                self.denied(e, pokemon, skill)
                assert_rejected_unchanged(e, lambda: e.plan_skill_check(
                    pokemon, skill, purpose='actual requested optional Pokemon check'),
                    reason_pattern='explicit current campaign Pokemon skill policy required')
        self.assertEqual(pokemon.spec, sheet)
        for skill, dice, modifier in (('육상', 3, 2), ('곡예', 2, 0), ('전투', 2, 0),
                                      ('은신', 2, 0), ('통찰', 2, 0), ('집중', 2, 1)):
            self.roll(e, pokemon, skill, dice, modifier)
        self.roll(e, trainer, '매력', 4)
        self.assertEqual(pokemon.spec['skills'], sheet['skills'])

    def test_all_source_given_porygon_technology_pools_work_without_policy_and_keep_guards(self):
        for species, dice, modifier in (('폴리곤', 3, 0), ('폴리곤2', 4, 1), ('폴리곤Z', 5, 3)):
            with self.subTest(species=species):
                e, trainer, pokemon = self.scene(species)
                self.assertIsNone(getattr(e, '_pokemon_intelligence_policy', None))
                self.assertIs(INTELLIGENCE.eligibility(e, pokemon, '기술학'), True)
                self.roll(e, pokemon, '기술학', dice, modifier)
                self.denied(e, pokemon, '매력')
                self.denied(e, pokemon, '의학')
                pokemon.spec['skills'].pop('기술학')  # Explicit imported sheet omits this pool.
                self.denied(e, pokemon, '기술학', reason='unassigned; no default 2d6')
        e, trainer, pokemon = self.scene('폴리곤')
        self.configure(e, trainer, social=False, education=False)
        policy = deepcopy(e._pokemon_intelligence_policy)
        e._pokemon_intelligence_policy['education'] = 'false'  # Corrupt declared policy is not an absent policy.
        before = deepcopy((pokemon.spec, e.rng.getstate(), e.log_lines))
        with self.assertRaisesRegex(ValueError, 'invalid campaign intelligence policy'):
            e.skill_roll(pokemon, '기술학')
        self.assertEqual((pokemon.spec, e.rng.getstate(), e.log_lines), before)
        e._pokemon_intelligence_policy = policy
        self.roll(e, pokemon, '기술학', 3)
        with patch.dict(self.rules.selection.aliases, {INTELLIGENCE.SOURCE: 'edge/미용사'}):
            before = deepcopy((pokemon.spec, e.rng.getstate(), e.log_lines))
            with self.assertRaisesRegex(ValueError, 'selected Pokemon intelligence source'):
                e.skill_roll(pokemon, '기술학')
            self.assertEqual((pokemon.spec, e.rng.getstate(), e.log_lines), before)

    def test_real_current_policy_choices_individual_exception_and_assignment_keep_sheet_history(self):
        e, trainer, pokemon = self.scene()
        other = Combatant(self.rules, build_pokemon(self.rules, '이상해씨', 20, moves=[], abilities=[]))
        e.gm.add_combatant(other, reason='actual separate individual for exception scope')
        sheet = deepcopy(pokemon.spec)
        self.configure(e, trainer, social=False, education=False)
        self.assertEqual(pokemon.spec, sheet)
        self.denied(e, pokemon, '매력', reason='does not authorize')
        self.configure(e, trainer, social=True, education=False)
        self.roll(e, pokemon, '매력', 2)
        self.denied(e, pokemon, '의학', reason='does not authorize')
        self.configure(e, trainer, social=False, education=True)
        self.denied(e, pokemon, '매력', reason='does not authorize')
        self.roll(e, pokemon, '의학', 1)
        self.roll(e, pokemon, '생존', 2)
        self.configure(e, trainer, social=False, education=False, exceptions={
            pokemon.entity_id: {'skills': ['매력'], 'reason': 'actual individual campaign exception'}})
        self.roll(e, pokemon, '매력', 2)
        self.denied(e, other, '매력', reason='does not authorize')
        self.denied(e, pokemon, '의학', reason='does not authorize')
        self.configure(e, trainer, social=True, education=True)
        self.assertEqual(pokemon.spec, sheet)
        e.pokemon_activity(trainer, 'assign_intelligence_skills', target=pokemon,
            skills={'의학': '4d6+2'}, reason='actual GM assigns one concrete current pool')
        self.roll(e, pokemon, '의학', 4, 2)
        assigned = deepcopy(pokemon.spec)
        self.assertEqual(assigned['intelligence_skill_assignments'][-1]['skills'], {'의학': '4d6+2'})
        self.configure(e, trainer, social=False, education=False)
        self.denied(e, pokemon, '의학', reason='does not authorize')
        self.assertEqual(pokemon.spec, assigned)
        self.configure(e, trainer, social=True, education=True)
        self.assertEqual(pokemon.spec, assigned)
        self.roll(e, pokemon, '의학', 4, 2)

    def test_actual_gm_and_fresh_rules_json_restore_keep_unset_or_declared_current_policy(self):
        for restoration in ('gm', 'json'):
            with self.subTest(restoration=restoration):
                e, trainer, pokemon = self.scene()
                identities = trainer.entity_id, pokemon.entity_id
                sheet = deepcopy(pokemon.spec)
                if restoration == 'gm':
                    e.gm.snapshot('actual unset campaign policy')
                    self.configure(e, trainer, social=True, education=True)
                    self.roll(e, pokemon, '매력', 2)
                    e.gm.restore('actual unset campaign policy')
                else:
                    e = CODEC.load_engine(Rules(ROOT, ruleset='core'), json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))
                index = WORLD.actor_index(e)
                trainer, pokemon = [index[identity] for identity in identities]
                self.assertIsNone(getattr(e, '_pokemon_intelligence_policy', None))
                self.assertEqual(pokemon.spec, sheet)
                self.denied(e, pokemon, '매력')
                self.configure(e, trainer, social=True, education=True)
                self.assertEqual(pokemon.spec, sheet)  # Current policy does not manufacture past individual assignments.
                if restoration == 'gm':
                    e.gm.snapshot('actual declared current campaign policy')
                    self.configure(e, trainer, social=False, education=False)
                    self.denied(e, pokemon, '매력', reason='does not authorize')
                    e.gm.restore('actual declared current campaign policy')
                else:
                    e = CODEC.load_engine(Rules(ROOT, ruleset='core'), json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))
                index = WORLD.actor_index(e)
                trainer, pokemon = [index[identity] for identity in identities]
                self.assertTrue(e._pokemon_intelligence_policy['social'])
                self.assertTrue(e._pokemon_intelligence_policy['education'])
                self.assertEqual(pokemon.spec, sheet)
                self.roll(e, pokemon, '매력', 2)


if __name__ == '__main__':
    unittest.main()
