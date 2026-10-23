"""Actual regional fishing selection, identity, RNG and persistence boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'output/ruleunits.jsonl').is_file():
    sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import encounter_candidates as CANDIDATES
import test_category3_pokemon_activities as BASE
from state_codec import dump_engine, load_engine
from builder import species_lookup


class FishingCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.PokemonActivityTests.setUpClass()

    def setUp(self):
        f = BASE.PokemonActivityTests()
        f.setUp()
        self.f = f
        self.e, self.a, self.p, self.q, self.r = f.e, f.a, f.p, f.q, f.rules
        self.a.spec['items'].update({'대단한낚싯대': 1, '루어': 1})
        self.p.spec.update(species='잉어킹', evolved=False)
        self.q.spec.update(species='셀러', evolved=False, wild=True)
        self.q.side = 'wild'

    def act(self, **options):
        return self.e.pokemon_activity(self.a, 'fishing', **options)

    def habitat(self, water='fresh', **changes):
        return dict(region='river/north', water=water, add=[], remove=[], reason='GM observed local ecology', **changes)

    def start(self, habitat=None):
        return self.act(phase='start', rod='대단한낚싯대', attachment='루어',
                        habitat=habitat if habitat is not None else self.habitat())

    def hooked(self, habitat=None):
        self.start(habitat)
        self.act(phase='wait', roll_d20=15)

    def snapshot(self):
        return deepcopy((self.e.export_state(), self.e.rng.getstate()))

    def test_both_printed_pools_and_independent_regional_deviations(self):
        for water, count in [('fresh', 10), ('salt', 15)]:
            with self.subTest(water=water):
                pool = CANDIDATES.fishing_pool(self.r, self.habitat(water))
                names = [species_lookup(self.r, uid)['name'] for uid in pool['candidates']]
                self.assertEqual(names, list(CANDIDATES.DEFAULTS[water]))
                self.assertEqual(len(names), count)
        declaration = self.habitat()
        declaration.update(add=['피카츄'], remove=['잉어킹'])
        state = self.start(declaration)
        ids = state['regional_candidates']['candidates']
        self.assertIn(species_lookup(self.r, '피카츄')['id'], ids)
        self.assertNotIn(species_lookup(self.r, '잉어킹')['id'], ids)
        self.assertIn(species_lookup(self.r, '잉어킹')['id'], CANDIDATES.fishing_pool(self.r, self.habitat('salt'))['candidates'])
        declaration['add'].append('셀러')
        self.assertEqual(self.a.spec['fishing_session']['regional_candidates']['declaration']['add'], ['피카츄'])

    def test_gm_choice_drives_actual_reel_and_keeps_existing_skill_costs(self):
        self.hooked()
        rng = self.e.rng.getstate()
        result = self.act(phase='select', choice='잉어킹')
        self.assertEqual(result['regional_selection']['species_id'], species_lookup(self.r, '잉어킹')['id'])
        self.assertEqual(self.e.rng.getstate(), rng)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'differs from'):
            self.act(phase='reel', target=self.q, fixed=[2] * 4)
        self.assertEqual(self.snapshot(), before)
        result = self.act(phase='reel', target=self.p, fixed=[2] * 4)
        self.assertEqual(result['status'], 'landed')
        self.assertEqual(result['target_id'], self.p.entity_id)
        self.assertEqual(self.e.elapsed_seconds, 300)
        self.assertFalse(self.p.captured)

    def test_random_selection_uses_host_rng_once_and_cannot_be_replaced(self):
        self.hooked()
        before = self.e.rng.getstate()
        result = self.act(phase='select', random_choice=True)
        self.assertNotEqual(self.e.rng.getstate(), before)
        state = self.snapshot()
        repeated = self.act(phase='select', random_choice=True)
        self.assertEqual(repeated, result)
        self.assertEqual(self.snapshot(), state)
        with self.assertRaisesRegex(ValueError, 'cannot replace'):
            self.act(phase='select', choice='잉어킹')
        self.assertEqual(self.snapshot(), state)
        self.p.spec['species'] = result['regional_selection']['species_id']
        self.assertEqual(self.act(phase='reel', target=self.p, fixed=[2] * 4)['status'], 'landed')

    def test_failed_lure_reel_and_json_restore_retain_same_species_and_actor(self):
        self.hooked()
        self.act(phase='select', choice='잉어킹')
        self.act(phase='reel', target=self.p, fixed=[1] * 4, escape_d20=11)
        self.e = load_engine(self.r, json.loads(json.dumps(dump_engine(self.e))))
        self.a, self.p, self.q = self.e.gm.everyone
        self.assertEqual(self.a.spec['fishing_session']['regional_selection']['mode'], 'gm')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.act(phase='reel', target=self.q, fixed=[2] * 4)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.act(phase='reel', target=self.p, fixed=[2] * 4)['status'], 'landed')

    def test_gm_snapshot_preserves_region_pool_and_committed_choice(self):
        self.hooked(self.habitat('salt'))
        self.act(phase='select', choice='잉어킹')
        self.e.gm.snapshot('hooked')
        self.act(phase='reel', target=self.p, fixed=[2] * 4)
        self.e.gm.restore('hooked')
        self.a, self.p, self.q = self.e.gm.everyone
        self.assertEqual(self.a.spec['fishing_session']['regional_candidates']['declaration']['water'], 'salt')
        self.assertEqual(self.act(phase='reel', target=self.p, fixed=[2] * 4)['status'], 'landed')

    def test_invalid_candidates_and_out_of_phase_decisions_are_atomic(self):
        bad = [dict(self.habitat(), water='ocean'), dict(self.habitat(), region=''),
               dict(self.habitat(), add=['not-a-species']), dict(self.habitat(), add=['피카츄', '피카츄']),
               dict(self.habitat(), remove=['피카츄']), dict(self.habitat(), remove=list(CANDIDATES.DEFAULTS['fresh']))]
        for habitat in bad:
            with self.subTest(habitat=habitat):
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.start(habitat)
                self.assertEqual(self.snapshot(), before)
        self.start()
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.act(phase='select', random_choice=True)
        self.assertEqual(self.snapshot(), before)
        self.act(phase='wait', roll_d20=15)
        for options in [dict(choice='피카츄'), dict(choice='잉어킹', random_choice=True), {},
                        dict(random_choice=True, roll_d20=20), dict(random_choice=1)]:
            with self.subTest(options=options):
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.act(phase='select', **options)
                self.assertEqual(self.snapshot(), before)

    def test_late_failure_after_random_draw_rolls_back_choice_and_rng(self):
        self.hooked()
        original = CANDIDATES.select
        before = self.snapshot()
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('after actual species draw')
        with patch.object(CANDIDATES, 'select', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'actual species draw'):
                self.act(phase='select', random_choice=True)
        self.assertEqual(self.snapshot(), before)

    def test_source_override_and_altered_pool_reject_before_consumption(self):
        with patch.object(self.r, '_selected_rule', return_value='changed-fishing-source'):
            with self.assertRaises(ValueError):
                self.start()
        self.start()
        self.a.spec['fishing_session']['regional_candidates']['candidates'].append('pokemon/피카츄')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'differs from'):
            self.act(phase='wait', roll_d20=15)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
