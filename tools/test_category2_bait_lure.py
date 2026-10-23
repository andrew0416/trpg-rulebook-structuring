"""C09-006/009 consumers of the existing attraction, regional and fishing owners."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_category3_pokemon_activities as fixture
import encounter_candidates as CANDIDATES
import world_entities as WORLD
from engine import Engine
from builder import species_lookup


class BaitLureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.PokemonActivityTests.setUpClass()

    def setUp(self):
        f = fixture.PokemonActivityTests()
        f.setUp()
        self.e, self.a, self.p, self.q, self.r = f.e, f.a, f.p, f.q, f.rules
        self.a.spec['items'].update({'미끼': 3, '루어': 1, '대단한낚싯대': 1})
        self.p.spec.update(species='잉어킹', evolved=False)
        self.q.spec.update(species='피카츄', trainer_id=self.a.entity_id)
        self.e.pokemon_activity(self.a, 'party_policy', mode='unlimited',
                                reason='GM current travelling roster', roster=[self.q])

    def fish(self, **options):
        return self.e.pokemon_activity(self.a, 'fishing', **options)

    def bait(self, phase, **options):
        return self.e.pokemon_activity(self.a, 'attract_bait', phase=phase, bait_id='bait', **options)

    def habitat(self):
        return {'region': 'north river', 'water': 'fresh', 'add': [], 'remove': [], 'reason': 'GM local water ecology'}

    def start(self, attachment='루어', source='item/미끼'):
        return self.fish(phase='start', rod='대단한낚싯대', attachment=attachment,
                         source_policy=source, habitat=self.habitat())

    def hook(self, attachment='루어', source='item/미끼'):
        self.start(attachment, source)
        self.fish(phase='wait', roll_d20=15)
        chosen = self.fish(phase='select', random_choice=True)
        self.p.spec['species'] = chosen['regional_selection']['species_id']

    def reel(self, passed=True, **options):
        state = self.a.spec['fishing_session']
        if state['source'] == 'item/미끼' and 'target_id' not in state:
            options.update(party=[self.q], level_match_reason='GM compares actual level20 party and target')
        return self.fish(phase='reel', target=self.p, fixed=[2 if passed else 1] * 4, **options)

    def snapshot(self):
        return deepcopy((self.e.export_state(), self.e.rng.getstate()))

    def test_placed_bait_random_selection_reaches_actual_target_and_carried_party(self):
        result = self.bait('place', habitat={'region': 'north bank', 'species': ['잉어킹', '셀러'], 'reason': 'GM local species'})
        self.assertEqual(result['unit_price'], 250)
        self.assertEqual(self.a.spec['items']['미끼'], 2)
        self.bait('wait', fixed=15)
        self.assertEqual(self.e.elapsed_seconds, 900)
        before = self.snapshot()
        select = CANDIDATES.select
        def fail_after_draw(*args, **kwargs):
            select(*args, **kwargs)
            raise RuntimeError('after actual bait species draw')
        with patch.object(CANDIDATES, 'select', side_effect=fail_after_draw):
            with self.assertRaisesRegex(RuntimeError, 'actual bait species draw'):
                self.bait('select')
        self.assertEqual(self.snapshot(), before)
        rng = self.e.rng.getstate()
        choice = self.bait('select')
        self.assertNotEqual(self.e.rng.getstate(), rng)
        before = self.snapshot()
        self.assertEqual(self.bait('select'), choice)
        self.assertEqual(self.snapshot(), before)
        self.p.spec['species'] = choice['regional_selection']['species_id']
        result = self.bait('encounter', target=self.p, party=[self.q], level_match_reason='GM comparable actual party')
        self.assertIs(result['target'], self.p)
        self.assertEqual(result['party_levels'], {self.q.entity_id: self.q.level})
        self.assertEqual(result['target_level'], self.p.level)
        self.assertFalse(result['captured'])

    def test_ch09_fishing_source_keeps_fifteen_minutes_and_ch05_keeps_five(self):
        for source, seconds in [(CANDIDATES.FISHING, 300), ('item/미끼', 900)]:
            with self.subTest(source=source):
                self.setUp()
                self.start(source=source)
                self.fish(phase='wait', roll_d20=14)
                self.assertEqual(self.e.elapsed_seconds, seconds)
                self.fish(phase='wait', roll_d20=15)
                if source == 'item/미끼':
                    before = self.snapshot()
                    with self.assertRaisesRegex(ValueError, 'random regional'):
                        self.fish(phase='select', choice='잉어킹')
                    self.assertEqual(self.snapshot(), before)
                chosen = self.fish(phase='select', random_choice=True)
                self.p.spec['species'] = chosen['regional_selection']['species_id']
                self.assertEqual(self.reel()['status'], 'landed')
                self.assertEqual(self.e.elapsed_seconds, seconds * 2)
                self.assertFalse(self.p.captured)

    def test_ch09_three_misses_consume_bait_and_lure_reuses_after_landing(self):
        for attachment in ('미끼', '루어'):
            with self.subTest(attachment=attachment):
                self.setUp()
                self.start(attachment)
                for _ in range(3):
                    result = self.fish(phase='wait', roll_d20=14)
                self.assertEqual(self.e.elapsed_seconds, 2700)
                self.assertEqual(result['status'], 'bait_consumed' if attachment == '미끼' else 'waiting')
                self.assertEqual(self.a.spec['items'][attachment], 2 if attachment == '미끼' else 1)
                if attachment == '루어':
                    self.fish(phase='wait', roll_d20=15)
                    chosen = self.fish(phase='select', random_choice=True)
                    self.p.spec['species'] = chosen['regional_selection']['species_id']
                    self.assertEqual(self.reel()['unit_price'], 1500)
                    self.assertEqual(self.start()['status'], 'waiting')
                    self.assertEqual(self.a.spec['items']['루어'], 1)

    def test_random_target_and_actual_party_are_required_without_invented_level_margin(self):
        self.hook()
        before = self.snapshot()
        for party in ([], [self.p], [deepcopy(self.q)]):
            with self.subTest(party=party):
                with self.assertRaises(ValueError):
                    self.fish(phase='reel', target=self.p, party=party, level_match_reason='GM ruling', fixed=[2] * 4)
                self.assertEqual(self.snapshot(), before)
        selected = self.a.spec['fishing_session']['regional_selection']['species_id']
        self.p.spec['species'] = '피카츄'
        changed = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'differs from'):
            self.reel()
        self.assertEqual(self.snapshot(), changed)
        self.p.spec['species'] = selected
        self.assertEqual(self.reel()['party_levels'], {self.q.entity_id: 20})

    def test_actual_escape_allows_gm_lure_retention_or_loss_without_extra_rng(self):
        for source, lost in [(CANDIDATES.FISHING, True), ('item/미끼', False), ('item/미끼', True)]:
            with self.subTest(source=source, lost=lost):
                self.setUp()
                self.hook(source=source)
                self.assertEqual(self.reel(False, escape_d20=10)['status'], 'escaped')
                self.assertEqual(self.a.spec['items']['루어'], 1)
                before = self.snapshot()
                if source == 'item/미끼':
                    with self.assertRaisesRegex(ValueError, 'resolve possible lure loss'):
                        self.start()
                    self.assertEqual(self.snapshot(), before)
                result = self.fish(phase='lure_loss', target=self.p, cause='escaped', lost=lost,
                                   reason='GM observed escaped fish; lure ' + ('gone' if lost else 'retrieved'))
                self.assertEqual(result['lure_loss']['lost'], lost)
                self.assertEqual(self.a.spec['items']['루어'], 0 if lost else 1)
                self.assertEqual(self.e.rng.getstate(), before[1])

    def test_observed_line_break_uses_actual_hook_and_only_gm_loss_consumes_lure(self):
        for lost in (False, True):
            with self.subTest(lost=lost):
                self.setUp()
                self.hook()
                before = self.snapshot()
                result = self.fish(phase='lure_loss', target=self.p, cause='line_broken', lost=lost,
                                   party=[self.q], level_match_reason='GM comparable actual party',
                                   reason='GM observed this hooked fishing line snap')
                self.assertEqual(result['status'], 'line_broken')
                self.assertEqual(result['target_id'], self.p.entity_id)
                self.assertEqual(self.a.spec['items']['루어'], 0 if lost else 1)
                self.assertEqual(self.e.rng.getstate(), before[1])
                after = self.snapshot()
                with self.assertRaises(ValueError):
                    self.fish(phase='lure_loss', target=self.p, cause='line_broken', lost=lost, reason='same break')
                self.assertEqual(self.snapshot(), after)

    def test_lure_loss_requires_real_cause_target_boolean_and_observation(self):
        self.hook()
        for options in [dict(cause='escaped', lost=True, reason='no actual escape'),
                        dict(cause='line_broken', lost=1, reason='not a boolean'),
                        dict(cause='line_broken', lost=True, reason='')]:
            before = self.snapshot()
            with self.assertRaises(ValueError):
                self.fish(phase='lure_loss', target=self.p, **options)
            self.assertEqual(self.snapshot(), before)
        self.reel(False, escape_d20=11)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'actual fishing escape'):
            self.fish(phase='lure_loss', target=self.p, cause='escaped', lost=True, reason='fish remained hooked')
        self.assertEqual(self.snapshot(), before)

    def test_new_source_state_continues_after_native_json_restore_and_rejects_source_switch(self):
        self.start()
        self.fish(phase='wait', roll_d20=14)
        self.e = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
        actors = WORLD.actor_index(self.e)
        self.a, self.p, self.q = (actors[c.entity_id] for c in (self.a, self.p, self.q))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'another source'):
            self.fish(phase='wait', source_policy=CANDIDATES.FISHING, roll_d20=15)
        self.assertEqual(self.snapshot(), before)
        self.fish(phase='wait', roll_d20=15)
        self.assertEqual(self.e.elapsed_seconds, 1800)
        chosen = self.fish(phase='select', random_choice=True)
        self.p.spec['species'] = chosen['regional_selection']['species_id']
        self.assertEqual(self.reel()['status'], 'landed')

    def test_equipment_replacement_is_rejected_before_bait_or_clock_changes(self):
        original = self.r._selected_rule
        before = self.snapshot()
        def selected(uid, **kwargs):
            return 'item/미끼-2' if uid == 'item/미끼' else original(uid, **kwargs)
        with patch.object(self.r, '_selected_rule', side_effect=selected):
            with self.assertRaises(ValueError):
                self.bait('place', habitat={'region': 'bank', 'species': ['잉어킹'], 'reason': 'local ecology'})
            with self.assertRaises(ValueError):
                self.start()
        self.assertEqual(self.snapshot(), before)

    def test_legacy_placed_bait_adds_missing_region_without_repaying_time_or_inventory(self):
        self.a.spec['placed_bait'] = {'bait': {'id': 'bait', 'source': 'item/미끼',
            'owner_id': self.a.entity_id, 'placed_at': 0, 'misses': 2, 'status': 'placed', 'checks': []}}
        self.bait('wait', fixed=15)
        before = (self.e.elapsed_seconds, self.a.spec['items']['미끼'])
        chosen = self.bait('select', habitat={'region': 'old bank', 'species': ['잉어킹'], 'reason': 'GM current local ecology'})
        self.assertEqual((self.e.elapsed_seconds, self.a.spec['items']['미끼']), before)
        self.assertEqual(chosen['misses'], 2)
        self.assertEqual(chosen['regional_selection']['species_id'], species_lookup(self.r, '잉어킹')['id'])


if __name__ == '__main__':
    unittest.main()
