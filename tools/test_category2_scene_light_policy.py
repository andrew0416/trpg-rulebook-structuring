"""Exact source adapter tests; no scene/accuracy completion claim."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from engine import Rules, Engine, Combatant
import scene_light_policy as LIGHT
import state_grants as GRANTS
from state_codec import dump_engine


class SceneLightPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 741)

    def pokemon(self, *, size='중형', capabilities=None, abilities=None, moves=None):
        actor = Combatant(self.r, {'name': 'actual light source', 'kind': 'pokemon',
            'level': 10, 'size': size, 'stats': {'hp': 20, 'atk': 10, 'def': 10,
            'spa': 10, 'spd': 10, 'spe': 10}, 'types': ['노말'], 'pos': (3,3),
            'movement': {'land': 4}, 'capabilities': capabilities or [],
            'abilities': abilities or [], 'moves': moves or []})
        self.e.gm.add_combatant(actor)
        return actor

    def test_every_printed_kind_size_and_automatic_actual_illuminate_bonus(self):
        self.assertEqual(LIGHT.radius(self.e, kind='lantern')['radius'], 2)
        self.assertEqual(LIGHT.radius(self.e, kind='strong_artificial')['radius'], 3)
        for size, expected in [('소형',2),('중형',2),('대형',3),('거대',4)]:
            with self.subTest(size=size):
                owner = self.pokemon(size=size, capabilities=['반짝임'], abilities=['발광'])
                facts = LIGHT.radius(self.e, kind='glow', owner=owner)
                self.assertEqual(facts['base_radius'], expected)
                self.assertEqual(facts['radius'], expected+1)
                self.assertEqual(facts['capability_source'], LIGHT.GLOW)
                self.assertEqual(facts['ability_source'], LIGHT.ILLUMINATE)
                self.assertTrue(facts['eligible'])
        self.assertEqual(LIGHT.radius(self.e, kind='strong_artificial', owner=owner)['radius'], 4)

    def test_actual_learned_glow_reuses_existing_source_and_independent_capability(self):
        owner = self.pokemon(moves=['move/플래시'])
        self.assertEqual(LIGHT.radius(self.e, kind='glow', owner=owner)['radius'], 2)
        self.assertIn('반짝임', GRANTS.effective_capabilities(owner))
        owner.spec['moves'] = owner.moves = []
        self.assertFalse(LIGHT.radius(self.e, kind='glow', owner=owner)['eligible'])
        # A second independent innate capability keeps this source qualified.
        owner.spec['capabilities'] = ['반짝임']
        self.assertEqual(LIGHT.radius(self.e, kind='glow', owner=owner)['radius'], 2)

    def test_current_ability_suppression_and_glow_withdrawal_do_not_create_charge_semantics(self):
        owner = self.pokemon(capabilities=['반짝임'], abilities=['발광'])
        self.assertEqual(LIGHT.radius(self.e, kind='glow', owner=owner)['radius'], 3)
        owner.abilities_suppressed = True
        self.assertEqual(LIGHT.radius(self.e, kind='glow', owner=owner)['radius'], 2)
        owner.abilities_suppressed = False
        self.assertEqual(LIGHT.radius(self.e, kind='glow', owner=owner)['radius'], 3)
        owner.spec['abilities'] = owner.abilities = []
        self.assertEqual(LIGHT.radius(self.e, kind='glow', owner=owner)['radius'], 2)
        owner.spec['capabilities'] = []
        facts = LIGHT.radius(self.e, kind='glow', owner=owner)
        self.assertFalse(facts['eligible'])
        self.assertIsNone(facts['radius'])

    def test_invalid_kind_size_owner_and_radiant_assertion_are_read_only(self):
        owner = self.pokemon(capabilities=['반짝임'])
        for options in [dict(kind='radiant'),dict(kind='glow'),
                dict(kind='glow',owner=owner,size='대형'),
                dict(kind='lantern',size='중형'),dict(kind='lantern',radiant=True),
                dict(kind='glow',owner=owner,radiant=1)]:
            before = dump_engine(self.e)
            with self.subTest(options=options), self.assertRaises(ValueError):
                LIGHT.radius(self.e, **options)
            self.assertEqual(before, dump_engine(self.e))


if __name__ == '__main__':
    unittest.main()
