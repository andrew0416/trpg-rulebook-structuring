"""Real reviewed registrar shapes retain selected source and alias boundaries."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from engine import Rules
import ability_transitions as A
import move_state as M


class AbilityRegistrationShapes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = {profile: Rules(str(ROOT), ruleset=profile)
                     for profile in ('core', 'playtest')}

    def test_native_exact_ids_and_aliases_use_actual_single_source_registration(self):
        cases = [('core', 'ability/먹보', ('먹보', 'Core Gluttony', 'Gluttony')),
                 ('playtest', 'ability/먹보-playtest', ('먹보 [Playtest]', 'Gluttony')),
                 ('playtest', 'ability/꿀파기-playtest', ('꿀파기 [Playtest]',)),
                 ('core', 'ability/클러스터마인드', ('클러스터마인드', 'Cluster Mind')),
                 ('core', 'ability/눈덮인달마', ('눈덮인달마',))]
        for profile, canonical, aliases in cases:
            for name in (canonical, *aliases):
                with self.subTest(profile=profile, name=name):
                    reg = M.ability_registration(self.rules[profile], name)
                    self.assertNotIn('equivalent_source_ids', reg)
                    self.assertEqual(reg['source_id'], canonical)
                    self.assertEqual(A.ability_id(self.rules[profile], name), canonical)

    def test_reviewed_duplicate_manual_sources_still_collapse_to_first_canonical_id(self):
        r = self.rules['core']
        for name in ('화학의힘', 'ability/화학의힘', 'ability/화학의힘-2'):
            with self.subTest(name=name):
                reg = M.ability_registration(r, name)
                self.assertEqual(reg['equivalent_source_ids'], ['ability/화학의힘', 'ability/화학의힘-2'])
                self.assertEqual(A.ability_id(r, name), 'ability/화학의힘')

    def test_unselected_native_version_still_rejects(self):
        for name in ('먹보 [Playtest]', 'ability/먹보-playtest'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    A.ability_id(self.rules['core'], name)

    def test_unknown_names_keep_existing_lookup_failure(self):
        r = self.rules['core']
        for name in ('registration-shape-unknown', 'ability/registration-shape-unknown'):
            with self.subTest(name=name):
                self.assertIsNone(M.ability_registration(r, name))
                with self.assertRaises(Exception):
                    A.ability_id(r, name)
