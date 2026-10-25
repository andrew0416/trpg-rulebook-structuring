"""Projection aliases never select an excluded edition before native registration."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from builder import build_pokemon
from engine import Combatant, Engine, Rules
from encounter import load_encounter
from grid import Grid
from ruleset import ExcludedRuleSelection, RuleFilter, RuleSelection, UnresolvedRuleSelection
import ability_state_projection as P
import ability_transitions as A
import cheerleader
import capacity_abilities as CAP
import world_entities as WORLD

CORE = 'ability/엽록소'
PLAYTEST = 'ability/엽록소-playtest'


class ProjectionSourceAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = Rules(ROOT, ruleset='core')
        cls.playtest = Rules(ROOT, ruleset='playtest')

    def actor(self, rules, ability):
        engine = Engine(rules, 79)
        engine.grid = Grid(10, 10)
        spec = build_pokemon(rules, '이상해씨', 20, name='projection-alias',
                             moves=['move/몸통박치기'],
                             extra={'abilities': [ability], 'pos': (2, 2), 'side': 'party'})
        actor = Combatant(rules, spec)
        engine.gm.add_combatant(actor)
        return engine, actor

    def test_core_unqualified_encounter_snapshot_and_cold_restore_keep_core_source(self):
        fixture = {'name': 'core-projection-alias', 'seed': 79, 'party': [{
            'species': '이상해씨', 'level': 20, 'abilities': ['엽록소'],
            'moves': ['move/몸통박치기'], 'pos': [2, 2]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'encounter.json'
            path.write_text(json.dumps(fixture, ensure_ascii=False), encoding='utf-8')
            engine, _, party, wild = load_encounter(ROOT, str(path), ruleset='core')
        self.assertEqual(wild, [])
        actor = party[0]
        self.assertIs(WORLD.require_actors(engine, actor)[actor.entity_id], actor)
        self.assertEqual(engine.gm.everyone, party + wild)
        self.assertEqual(engine.everyone, party + wild)
        self.assertIsNone(P.ability_registration(engine.r, '엽록소'))
        self.assertIsNone(P.ability_registration(engine.r, 'Chlorophyll'))
        self.assertEqual(A.ability_id(engine.r, '엽록소'), CORE)
        self.assertEqual(set(A.project_components(actor)), {CORE})
        self.assertIsNone(cheerleader.support_snapshot(engine, actor))
        self.assertIn('엽록소', actor.spec['state_grants']['ability_receipts'])
        self.assertNotIn(P.KEY, actor.spec)
        engine.gm.set_weather('sunny', rounds=5, reason='native core source check')
        self.assertEqual(actor.stages['spe'], 4)
        engine.gm.snapshot('core alias')
        engine.gm.restore('core alias', reason='same core registration')
        saved = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        restored = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        current = next(value for value in restored.everyone if value.entity_id == actor.entity_id)
        self.assertEqual(set(A.project_components(current)), {CORE})
        self.assertEqual(current.stages['spe'], 4)
        self.assertNotIn(P.KEY, current.spec)
        restored.gm.set_weather(None, reason='core source ends with actual weather')
        self.assertEqual(current.stages['spe'], 0)
        self.assertTrue(restored.validate_state()['valid'])

    def test_selected_playtest_name_english_and_exact_ID_keep_playtest_registration(self):
        for alias in ('엽록소 [Playtest]', 'Chlorophyll', PLAYTEST):
            with self.subTest(alias=alias):
                registered = P.ability_registration(self.playtest, alias)
                self.assertEqual(registered, {'name': '엽록소 [Playtest]',
                    'source_id': PLAYTEST, 'equivalent_source_ids': [PLAYTEST]})
        engine, actor = self.actor(self.playtest, PLAYTEST)
        self.assertEqual(A.ability_id(self.playtest, PLAYTEST), PLAYTEST)
        self.assertEqual(set(A.project_components(actor)), {PLAYTEST})
        self.assertIn('엽록소 [Playtest]', actor.spec['state_grants']['ability_receipts'])
        engine.gm.set_weather('sunny', rounds=5, reason='selected playtest is not core stages')
        self.assertEqual(actor.stages['spe'], 0)
        self.assertTrue(engine.validate_state()['valid'])

    def test_explicit_excluded_projection_ID_stays_fail_closed_and_read_only(self):
        engine, actor = self.actor(self.core, '엽록소')
        before = engine.export_state()
        for resolver in (P.ability_registration, A.ability_id):
            with self.subTest(resolver=resolver.__name__):
                with self.assertRaises(ExcludedRuleSelection):
                    resolver(self.core, PLAYTEST)
                self.assertEqual(engine.export_state(), before)
        self.assertEqual(set(A.project_components(actor)), {CORE})

    def test_real_unresolved_variant_choice_and_stale_selection_are_not_exclusions(self):
        source = {'file': 'db/abilities.csv'}
        rows = [
            {'id': 'ability/멀티타입', 'name': '멀티타입', 'eng': 'Multitype', 'source': source},
            {'id': 'ability/멀티타입-playtest', 'name': '멀티타입 [Playtest]', 'source': source},
            {'id': 'ability/멀티타입-홈브류', 'name': '멀티타입 [홈브류]', 'source': source},
        ]
        rule_filter = RuleFilter({'sources': ['core'], 'variants': ['playtest', '홈브류'],
                                  'variant_replaces_core': True})
        selection = RuleSelection(rule_filter, rows)
        self.assertIn('ability/멀티타입', selection.conflicts)
        rules = SimpleNamespace(selection=selection, _selected_rule=selection.require_supported_version,
                                ability_state_projection_targets={rows[0]['id']: rows[0]})
        with self.assertRaises(UnresolvedRuleSelection):
            P.ability_registration(rules, 'Multitype')
        stale_filter = RuleFilter({'sources': ['core'], 'variants': []})
        stale = RuleSelection(stale_filter, [rows[0]])
        stale_filter.exclude_units.add(rows[0]['id'])
        rules.selection = stale
        rules._selected_rule = stale.require_supported_version
        with self.assertRaises(UnresolvedRuleSelection):
            P.ability_registration(rules, 'Multitype')

    def test_replaced_alias_outside_projection_catalog_is_not_claimed(self):
        rows = [
            {'id': 'ability/멀티타입', 'name': '멀티타입', 'eng': 'Multitype',
             'source': {'file': 'db/abilities.csv'}},
            {'id': 'ability/멀티타입-playtest', 'name': '멀티타입 [Playtest]',
             'source': {'file': 'db/abilities.csv'}},
        ]
        selection = RuleSelection(RuleFilter({'sources': ['core'], 'variants': ['playtest'],
                                              'variant_replaces_core': True}), rows)
        rules = SimpleNamespace(selection=selection, _selected_rule=selection.require_supported_version,
                                ability_state_projection_targets={rows[0]['id']: rows[0]})
        before = deepcopy(rules.ability_state_projection_targets)
        self.assertIsNone(P.ability_registration(rules, 'Multitype'))
        self.assertEqual(rules.ability_state_projection_targets, before)

    def test_native_capacity_english_alias_uses_actual_selected_core_or_playtest_source(self):
        for rules, uid, name in ((self.core, 'ability/먹보', '먹보'),
                                 (self.playtest, 'ability/먹보-playtest', '먹보 [Playtest]')):
            with self.subTest(profile=rules.ruleset.name):
                self.assertEqual(CAP.registration(rules, 'Gluttony'), {'name': name, 'source_id': uid})
                engine, actor = self.actor(rules, 'Gluttony')
                self.assertEqual(A.ability_id(rules, 'Gluttony'), uid)
                self.assertEqual(set(A.project_components(actor)), {uid})
                self.assertIn(name, actor.spec['state_grants']['ability_receipts'])
                capacity = CAP.food_capacity(engine, actor)
                if uid == 'ability/먹보':
                    self.assertIsNone(capacity['stored'])
                    self.assertEqual(capacity['per_encounter'], 3)
                    self.assertNotIn('per_scene', capacity)
                else:
                    self.assertEqual((capacity['stored'], capacity['per_scene']), (3, 3))
                    self.assertNotIn('per_encounter', capacity)
                saved = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
                restored = Engine.import_state(Rules(ROOT, ruleset=rules.ruleset.name), saved)
                current = next(value for value in restored.everyone if value.entity_id == actor.entity_id)
                self.assertEqual(CAP.food_capacity(restored, current), capacity)
                self.assertTrue(engine.validate_state()['valid'])

    def test_capacity_explicit_excluded_ID_and_real_ambiguous_english_alias_fail_closed(self):
        engine, _ = self.actor(self.core, '엽록소')
        before = engine.export_state()
        with self.assertRaises(ExcludedRuleSelection):
            CAP.registration(self.core, 'ability/먹보-playtest')
        self.assertEqual(engine.export_state(), before)
        with self.assertRaises(UnresolvedRuleSelection):
            CAP.registration(Rules(ROOT, ruleset='all'), 'Gluttony')


if __name__ == '__main__':
    unittest.main()
