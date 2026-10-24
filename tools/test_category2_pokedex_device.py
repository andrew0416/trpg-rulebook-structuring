"""C09-002/003 new physical-device connections; existing owners are reused."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from grid import Grid
import common_checks as C
import items as ITEMS
import pokedex_device as DEX
import world_entities as W


class PokedexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=72003)
        stats = dict(hp=10, atk=10, **{'def': 10}, spa=10, spd=10, spe=10)
        self.a = Combatant(self.r, dict(id='trainer/a', name='A', kind='trainer', level=1,
            stats=stats, skills={'포켓몬학': 1}, items={}, money=500, pos=(0, 0)))
        self.b = Combatant(self.r, dict(id='trainer/b', name='B', kind='trainer', level=1,
            stats=stats, skills={'포켓몬학': 1}, items={}, pos=(0, 1)))
        self.p = Combatant(self.r, dict(id='pokemon/p', name='P', kind='pokemon', level=5,
            stats=stats, species='pokemon/이상해씨', height_m=0.8, weight_kg=7.2,
            moves=['move/몸통박치기'], pos=(10, 0)))
        self.e.everyone = self.e.gm.everyone = [self.a, self.b, self.p]
        self.e.grid = Grid(30, 30)
        self.e.gm.grant_starting_pokedex(self.a, 'dex/a', starting_character=True,
                                       reason='GM grants the new character starting equipment')

    def observation(self):
        return dict(species='pokemon/이상해씨', average=dict(height_m=0.7, weight_kg=6.9),
                    individual=dict(height_m=0.8, weight_kg=7.2), learnable_moves=None,
                    knowledge={'biology': 'GM 공개: 등에 씨앗이 있다'},
                    source='gm/scan-observation: species averages and observed individual measurements')

    def scan(self, **options):
        kwargs = dict(recognized=True, readout=self.observation(), reason='actual recognized camera scan')
        kwargs.update(options)
        return self.e.scan_pokedex(self.a, self.p, 'dex/a', **kwargs)

    def device(self, identity='dex/a'):
        return self.e._physical_objects[identity][DEX.FIELD]

    def function(self, name, **options):
        return self.e.use_pokedex(self.a, 'dex/a', name, reason='GM observed device function', **options)

    def test_starting_grant_is_free_real_held_minimum_value_and_only_once(self):
        self.assertEqual(self.a.spec['money'], 500)
        self.assertEqual(self.a.spec['items'], {})
        self.assertEqual(self.a.spec['pokedex_starting_instance'], 'dex/a')
        self.assertEqual(self.device()['value_points'], 12000)
        self.assertEqual(self.e._physical_objects['dex/a']['equipped_by'], self.a.entity_id)
        before = self.e.export_state()
        for uid in ('dex/a', 'dex/another'):
            with self.assertRaisesRegex(ValueError, 'already received'):
                self.e.gm.grant_starting_pokedex(self.a, uid, starting_character=True, reason='repeat')
            self.assertEqual(self.e.export_state(), before)
        for value in (11999, True):
            with self.assertRaises(ValueError):
                self.e.gm.grant_starting_pokedex(self.b, 'dex/b', starting_character=True,
                                               value_points=value, reason='bad value')
        with self.assertRaises(ValueError):
            self.e.gm.grant_starting_pokedex(self.b, 'dex/b', starting_character=False, reason='not starting')
        self.assertEqual(self.e.export_state(), before)
        before_rulings = deepcopy(vars(self.e.rulings))
        before_logs = list(self.e.log_lines)
        before_spec = deepcopy(self.b.spec)
        before_held = deepcopy(getattr(self.b, '_item_reg', {}))
        recorded = []
        original_rec = type(self.e.gm)._rec
        def fail_after_record(gm, what, *args, **kwargs):
            original_rec(gm, what, *args, **kwargs)
            if what == 'starting Pokedex':
                subject = W.actor_index(gm.e)['trainer/b']
                recorded.append(dict(rulings=len(gm.e.rulings.log), logs=len(gm.e.log_lines),
                    physical=gm.e._physical_objects['dex/b']['equipped_by'],
                    held=deepcopy(subject._item_reg), marker=subject.spec['pokedex_starting_instance']))
                raise RuntimeError('late starting Pokedex GM record failure')
        with patch.object(type(self.e.gm), '_rec', fail_after_record):
            with self.assertRaisesRegex(RuntimeError, 'late starting Pokedex GM record failure'):
                self.e.gm.grant_starting_pokedex(self.b, 'dex/b', starting_character=True,
                    value_points=14000, reason='GM record succeeds before this injected failure')
        self.assertEqual(len(recorded), 1)
        self.assertGreater(recorded[0]['rulings'], len(before_rulings['log']))
        self.assertGreater(recorded[0]['logs'], len(before_logs))
        self.assertEqual((recorded[0]['physical'], recorded[0]['marker']), (self.b.entity_id, 'dex/b'))
        self.assertTrue(recorded[0]['held'])
        self.assertEqual(vars(self.e.rulings), before_rulings)
        self.assertEqual(self.e.log_lines, before_logs)
        self.assertNotIn('dex/b', self.e._physical_objects)
        self.assertEqual(self.b.spec, before_spec)
        self.assertEqual(getattr(self.b, '_item_reg', {}), before_held)
        self.assertEqual(self.e.export_state(), before)
        result = self.e.gm.grant_starting_pokedex(self.b, 'dex/b', starting_character=True,
                                                value_points=14000, reason='GM optional starting grant')
        self.assertEqual((result['price_paid'], result['value_points']), (0, 14000))

    def test_actual_standard_scan_at_ten_meters_discloses_catalog_learnset_not_known_slots(self):
        self.p.spec['hidden_item'] = 'PRIVATE ITEM'
        self.p.spec['hidden_knowledge'] = 'PRIVATE KNOWLEDGE'
        rng = self.e.rng.getstate()
        self.e.start_round([self.a, self.p])
        self.e.start_of_turn(self.a, initiative_count=20)
        result = self.scan()
        self.assertEqual(result['distance_m'], 10)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertTrue(self.a.took_standard)
        readout = result['readout']
        catalog = self.r.learnset_links['이상해씨']['moves']
        expected = list(dict.fromkeys(row['to'] for row in catalog
                                     if row.get('source') == 'level_up' and row.get('to')))
        self.assertEqual(readout['learnable_moves'], expected)
        # Actual non-Level-Up species entries must not leak into this readout.
        for source in ('tm', 'egg', 'tutor'):
            excluded = {row['to'] for row in catalog
                        if row.get('source') == source and row.get('to')} - set(expected)
            self.assertTrue(excluded, source)
            self.assertTrue(excluded.isdisjoint(readout['learnable_moves']), source)
        future = {row['to'] for row in catalog if row.get('source') == 'level_up'
                  and row.get('level', 0) > self.p.level and row.get('to')}
        self.assertTrue(future)
        self.assertTrue(future.issubset(readout['learnable_moves']))
        self.assertGreater(len(expected), len(self.p.moves))
        self.assertEqual(readout['learnset_source'], 'output/entities/learnset_links.json#이상해씨')
        self.assertEqual((readout['average']['height_m'], readout['individual']['height_m']), (0.7, 0.8))
        self.assertNotIn('PRIVATE', repr(result))
        self.assertEqual(self.e.rng.getstate(), rng)
        result['readout']['learnable_moves'].clear()
        self.assertEqual(self.device()['scans'][0]['readout']['learnable_moves'], expected)

    def test_scan_range_recognition_and_unknown_geometry_never_invent_success(self):
        self.p.pos = (11, 0)
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, '10m'):
            self.scan()
        self.assertEqual(self.e.export_state(), before)
        self.p.pos = (10, 0)
        for changes in ({'recognized': None}, {'recognized': False}, {'readout': None}):
            result = self.scan(**changes)
            self.assertIsInstance(result, C.PendingDecision)
        self.p.location = {'kind': 'unknown'}
        self.assertIsInstance(self.scan(), C.PendingDecision)
        self.assertFalse(self.device()['scans'])
        self.assertFalse(self.a.took_standard)

    def test_scan_unpaid_or_inconsistent_observation_leaves_device_and_budget(self):
        self.a.budget = {'standard': 0, 'shift': 1, 'swift': 1}
        self.assertIsInstance(self.scan(), C.PendingDecision)
        self.assertFalse(self.device()['scans'])
        self.a.budget = {'standard': 1, 'shift': 1, 'swift': 1}
        before = deepcopy(self.device())
        for change in ('species', 'measurement', 'known_slots', 'blocked_path'):
            observed = self.observation()
            if change == 'species': observed['species'] = 'pokemon/파이리'
            if change == 'measurement': observed['individual']['weight_kg'] = 100
            if change == 'known_slots': observed['known_moves'] = list(self.p.moves)
            if change == 'blocked_path': self.e.grid.blocking.add((5, 0))
            with self.assertRaises(ValueError): self.scan(readout=observed)
            self.assertEqual(self.device(), before)
            self.assertEqual(self.a.budget['standard'], 1)
        self.e.grid.blocking.clear()
        self.a.hp = 0
        self.assertIsInstance(self.scan(), C.PendingDecision)
        self.assertEqual(self.device(), before)

    def test_saved_scan_feeds_existing_knowledge_reader_without_another_scan_action(self):
        self.e.start_round([self.a, self.p])
        self.e.start_of_turn(self.a, initiative_count=20)
        self.scan()
        budget = deepcopy(self.a.budget)
        history = list(self.a._action_history)
        result = self.e.pokemon_knowledge(self.a, self.p, 'learnset', method='pokedex',
            device_selection='dex/a', reason='read existing scan entry')
        self.assertIsInstance(result, C.ActionOutcome)
        self.assertIsNone(result.check)
        self.assertIn('move/씨뿌리기', result.description)
        self.assertEqual(result.basis['knowledge']['pokedex_instance_id'], 'dex/a')
        result = self.e.pokemon_knowledge(self.a, self.p, 'biology', method='pokedex',
            device_selection='dex/a', reason='read disclosed existing biology')
        self.assertEqual(result.description, 'GM 공개: 등에 씨앗이 있다')
        self.assertEqual((self.a.budget, self.a._action_history), (budget, history))
        result = self.e.pokemon_knowledge(self.a, self.p, 'growth_abilities', method='pokedex',
            device_selection='dex/a', reason='not disclosed by prior scan')
        self.assertIsInstance(result, C.PendingDecision)

    def test_physical_device_access_and_source_selection_are_not_quantity_or_forged_copies(self):
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.e.scan_pokedex(self.b, self.p, 'dex/a', recognized=True, readout=self.observation(), reason='wrong holder')
        with self.assertRaises(ValueError):
            self.e.scan_pokedex(self.a, self.p, 'missing', recognized=True, readout=self.observation(), reason='no actual device')
        self.assertEqual(self.e.export_state(), before)
        obj = self.e._physical_objects['dex/a']
        obj['disabled'] = True
        with self.assertRaisesRegex(ValueError, 'unavailable'): self.scan()
        obj.pop('disabled')
        original = self.r._selected_rule
        def excluded(uid, *args, **kwargs):
            if uid == DEX.RULE: raise ValueError('excluded Pokedex')
            return original(uid, *args, **kwargs)
        with patch.object(self.r, '_selected_rule', excluded):
            with self.assertRaisesRegex(ValueError, 'excluded'): self.scan()
        self.assertEqual(self.e.export_state(), before)

    def test_builtins_consume_actual_service_observations_without_invented_connectivity(self):
        self.e.start_round([self.a, self.p])
        self.e.start_of_turn(self.a, initiative_count=20)
        budget = deepcopy(self.a.budget)
        for name in ('phone', 'radio', 'internet'):
            self.assertIsInstance(self.function(name), C.PendingDecision)
            unavailable = dict(source='gm/no-service', available=False, content=None)
            result = self.function(name, observation=unavailable)
            self.assertFalse(result['observation']['available'])
            observed = dict(source='gm/observed-' + name, available=True, content='GM 공개 ' + name)
            result = self.function(name, observation=observed)
            self.assertEqual(result['observation']['content'], 'GM 공개 ' + name)
        self.assertEqual(self.a.budget, budget)
        self.assertFalse(self.a.took_standard)
        self.assertEqual(len(self.device()['uses']), 6)

    def test_additional_app_requires_completed_download_on_same_actual_device(self):
        observation = dict(source='gm/application-result', available=True, content='GM 공개 app result')
        with self.assertRaisesRegex(ValueError, 'not downloaded'):
            self.function('app:map', observation=observation)
        result = self.e.download_pokedex_app(self.a, 'dex/a', 'map', download_completed=False,
            source='gm/pending-download', reason='download not complete')
        self.assertIsInstance(result, C.PendingDecision)
        self.assertFalse(self.device()['apps'])
        self.e.download_pokedex_app(self.a, 'dex/a', 'map', download_completed=True,
            source='gm/actual-download', reason='GM observed completed app transfer')
        self.assertEqual(self.function('app:map', observation=observation)['function'], 'app:map')
        self.e.gm.grant_starting_pokedex(self.b, 'dex/b', starting_character=True, reason='other new character')
        with self.assertRaisesRegex(ValueError, 'not downloaded'):
            self.e.use_pokedex(self.b, 'dex/b', 'app:map', observation=observation, reason='separate device')

    def test_new_device_state_survives_gm_and_cold_restore_and_invalid_projection_rejects(self):
        self.scan()
        self.e.download_pokedex_app(self.a, 'dex/a', 'map', download_completed=True,
            source='gm/actual-download', reason='completed app')
        saved = self.e.export_state()
        self.e.gm.snapshot('pokedex')
        self.function('phone', observation=dict(source='gm/call', available=True, content='GM accepted call'))
        self.e.gm.restore('pokedex', reason='restore actual Pokedex state')
        self.assertFalse(self.device()['uses'])
        cold = Engine.import_state(Rules(str(ROOT), ruleset='core'), saved)
        a, p = W.actor_index(cold)['trainer/a'], W.actor_index(cold)['pokemon/p']
        self.assertEqual(cold.use_pokedex(a, 'dex/a', 'app:map', observation=dict(
            source='gm/restored-service', available=True, content='restored app'), reason='actual restored app')['function'], 'app:map')
        self.assertIn('씨뿌리기', cold.pokemon_knowledge(a, p, 'learnset', method='pokedex',
            device_selection='dex/a', reason='restored scan entry').description)
        cold._physical_objects['dex/a'][DEX.FIELD]['builtin_functions'].append('invented')
        self.assertIn('pokedex_device', {issue['code'] for issue in W.validate_world(cold)['issues']})
        with self.assertRaises(ValueError): cold.export_state()

    def test_existing_device_configuration_cannot_reset_downloads_or_lower_value(self):
        W.register_object(self.e, 'dex/existing', kind='item_instance', item_rule_id=DEX.RULE,
            owner_id=self.b.entity_id, location={'kind': 'unknown'}, reason='existing actual device')
        ITEMS.register_item(self.e, self.b, DEX.RULE, source_instance_id='dex/existing', as_held=True)
        self.e.configure_pokedex(self.b, 'dex/existing', value_points=15000, reason='GM observed existing device')
        self.e.download_pokedex_app(self.b, 'dex/existing', 'map', download_completed=True,
            source='gm/existing-download', reason='completed app')
        old = deepcopy(self.device('dex/existing'))
        self.e.configure_pokedex(self.b, 'dex/existing', value_points=15000, reason='same device observation')
        self.assertEqual(self.device('dex/existing'), old)
        with self.assertRaisesRegex(ValueError, 'cannot reset'):
            self.e.configure_pokedex(self.b, 'dex/existing', value_points=12000, reason='changed value')

    def test_source_freshness_and_new_state_trust_boundaries_fail_before_device_mutation(self):
        before = self.e.export_state()
        original = Path.read_bytes
        for filename in ('ch09-equipment.md', 'pokedex-core-1.05.txt'):
            def changed(path):
                content = original(path)
                return content + b' changed' if path.name == filename else content
            with self.subTest(source=filename), patch.object(Path, 'read_bytes', changed):
                with self.assertRaisesRegex(ValueError, 'source changed'): self.scan()
            self.assertEqual(self.e.export_state(), before)
        invalid = dict(source='gm/no-service', available=False, content='invented result')
        with self.assertRaises(ValueError): self.function('internet', observation=invalid)
        with self.assertRaises(ValueError):
            self.e.download_pokedex_app(self.a, 'dex/a', 'phone', download_completed=True,
                source='gm/download', reason='builtin is not an additional app')
        self.assertEqual(self.e.export_state(), before)
