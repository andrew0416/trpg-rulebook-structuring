"""Underdog qualification uses actual capability, including catalog exceptions."""
from copy import deepcopy
from pathlib import Path
import unittest

from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer, species_lookup
import growth_stats as GS
import state_grants as G
import underdog_edges as U

ROOT = Path(__file__).resolve().parents[1]


class CoreUnderdogEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def test_native_natural_above45_underdog_accepts_strength_without_catalog_edits(self):
        e = Engine(self.r, seed=1288)

        def add(spec):
            actor = Combatant(self.r, spec)
            e.gm.add_combatant(actor, pos=(0, 0), side='party', reason='actual qualification boundary')
            return actor

        trainer = add(build_trainer(self.r, 'underdog-qualification-trainer', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            skills={'명령': 4, '포켓몬학': 4, '생존': 4}, extra={'items': {}, 'edges': []}))
        catalog = deepcopy(species_lookup(self.r, '절벼게'))
        self.assertEqual(sum(catalog['base_stats'].values()), 47)
        self.assertIn('약골', catalog['capabilities'])
        target = add(build_pokemon(self.r, '절벼게', 35, moves=[], abilities=[],
            extra={'trainer_id': trainer.entity_id, 'tutor_points': 8}))
        self.assertIn('약골', target.spec['capabilities'])
        self.assertTrue(U.owned(target))
        self.assertIn('약골', G.effective_capabilities(target))
        self.assertFalse(target.spec.get(G.KEY, {}).get('sources'))
        old = GS.project(self.r, target.spec)
        hp = target.hp

        out = e.pokemon_activity(trainer, 'teach_edge', target=target, edge=U.STRENGTH, safe=True)

        now = e.growth_stat_projection(target)['permanent']
        self.assertEqual((out['edge'], out['definition_origin']['record']), (U.STRENGTH, 26))
        self.assertEqual((target.spec['tutor_points'], e.elapsed_seconds, target.hp), (7, 3600, hp))
        self.assertEqual(now['species_base'], catalog['base_stats'])
        self.assertEqual(now['investment'], old['investment'])
        self.assertEqual(target.stats, {stat: value + 1 for stat, value in old['stats'].items()})
        self.assertTrue(U.owned(target))
        self.assertTrue(U.blocks_evolution(self.r, target.spec))
        self.assertEqual(U.records(target.spec)[0]['status'], 'active')
        self.assertEqual(species_lookup(self.r, '절벼게'), catalog)

    def loss_fixture(self):
        from grid import Grid
        import cleanse_tags as TAG
        e = Engine(self.r, seed=1289)
        e.grid = Grid(90, 90)

        def add(spec):
            actor = Combatant(self.r, spec)
            e.gm.add_combatant(actor, pos=(0, 0), side='party', reason='actual capability-loss boundary')
            return actor

        trainer = add(build_trainer(self.r, 'actual-tag-maker', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            skills={'오컬트학': 5, '명령': 4, '포켓몬학': 4, '생존': 4},
            extra={'items': {}, 'edges': [TAG.SOURCE], 'money': 0}))
        target = add(build_pokemon(self.r, '고오스', 35, moves=[], abilities=[],
            extra={'trainer_id': trainer.entity_id, 'tutor_points': 8}))
        self.assertTrue({'약골', '투명', '페이징'}.issubset(target.spec['capabilities']))
        return e, trainer, target

    def partial_loss_clock(self, e, trainer):
        e.advance_time(295)
        e.start_round(e.gm.everyone)
        e.start_of_turn(trainer, initiative_count=10)
        e.end_encounter()

    def test_actual_cleanse_burn_uncertainty_keeps_unrelated_underdog_teaching_eligible(self):
        import cleanse_tags as TAG
        import skill_modifiers as SKILL
        import world_entities as WORLD
        e, trainer, target = self.loss_fixture()
        TAG.craft(e, trainer, event_id='actual-qualification-tag', instance_id='qualification-tag',
            work={'source': 'gm/observation', 'paper': True, 'prayer': True, 'seconds': 37,
                  'reason': 'GM observed the actual tag manufacture work'}, skill_options={'fixed': [3] * 5})
        WORLD.observe_location(e, e._physical_objects['qualification-tag'],
            {'kind': 'grid', 'cell': [0, 0]}, reason='GM observed the actual tag within reach')
        rank = SKILL.effective_rank(self.r, target, '집중')
        burn = e.gm.observe_cleanse_burn(trainer, 'qualification-tag', event_id='actual-qualification-burn',
            reason='GM observed this actual manufactured original tag burned',
            checks={target.entity_id: {'fixed': [1] * rank}})
        self.assertTrue(burn['targets'][target.entity_id]['result']['lost'])
        self.partial_loss_clock(e, trainer)
        loss = next(iter(G.capability_losses(target).values()))
        self.assertLess(loss['elapsed_bounds'][0], loss['duration'])
        self.assertGreaterEqual(loss['elapsed_bounds'][1], loss['duration'])
        with self.assertRaisesRegex(ValueError, 'observe actual'):
            G.effective_capabilities(target)
        self.assertTrue(U.owned(target))
        before = deepcopy(target.stats)
        out = e.pokemon_activity(trainer, 'teach_edge', target=target, edge=U.STRENGTH, safe=True)
        self.assertEqual(out['edge'], U.STRENGTH)
        self.assertEqual(target.spec['tutor_points'], 7)
        self.assertEqual(target.stats, {stat: value + 1 for stat, value in before.items()})
        self.assertEqual(U.records(target.spec)[0]['status'], 'active')

    def test_actual_owner_loss_clock_keeps_underdog_itself_uncertain_and_refuses_before_cost(self):
        e, trainer, target = self.loss_fixture()
        # Test the existing source-loss owner's admitted extension API directly.
        # This fixture does not claim Cleanse Tag or a core rule removes Underdog.
        G.transition(e, target, lambda staged, actor: G.capability_loss(staged, actor,
            'qualification-owner-boundary', ['capability/약골'], rule_id='capability/약골',
            receipt='qualification-owner-api-receipt', duration=300))
        self.partial_loss_clock(e, trainer)
        self.assertTrue(e.validate_state()['valid'])
        before = deepcopy((e.elapsed_seconds, e.rng.getstate(), target.spec, trainer.spec, e.log_lines))
        with self.assertRaisesRegex(ValueError, 'observe actual'):
            U.owned(target)
        with self.assertRaisesRegex(ValueError, 'observe actual'):
            e.pokemon_activity(trainer, 'teach_edge', target=target, edge=U.STRENGTH, safe=True)
        self.assertEqual((e.elapsed_seconds, e.rng.getstate(), target.spec, trainer.spec, e.log_lines), before)


if __name__ == '__main__':
    unittest.main()
