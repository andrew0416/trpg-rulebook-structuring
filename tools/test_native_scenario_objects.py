"""Native fixture identity and registration contracts, not item-rule coverage."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from engine import Rules, Engine, Combatant
from native_scenario_fixture import prepare_object
import frequency as FREQ
import world_entities as WORLD


class ObjectFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.rules)
        self.actor = Combatant(self.rules, dict(
            name='object observer', level=3, kind='trainer',
            stats={'hp': 9, 'atk': 5, 'def': 5, 'spa': 5, 'spd': 5, 'spe': 5},
            types=['노말'], moves=[]))
        self.e.everyone = self.e.gm.everyone = [self.actor]

    def test_quota_binds_to_the_live_registered_object(self):
        obj = prepare_object(self.e, 'observed-tool', location={'kind': 'unknown'},
                             reason='observed physical tool', owner_id=self.actor.entity_id)
        self.assertIs(obj, WORLD.entity_index(self.e)['observed-tool'])
        with self.assertRaisesRegex(ValueError, 'physical frequency requires an actual registered object'):
            FREQ.bind_physical(self.e, deepcopy(obj), self.actor,
                               'test_fixture/observation', '하루', used=1)
        FREQ.bind_physical(self.e, obj, self.actor, 'test_fixture/observation', '하루', used=1)
        self.assertIs(obj['frequency_state'],
                      self.e._physical_objects['observed-tool']['frequency_state'])
        self.assertFalse(FREQ.physical_activation_allowed(
            self.e, obj, 'test_fixture/observation', '하루'))

    def test_public_return_stays_detached_and_reobservation_preserves_identity(self):
        obj = prepare_object(self.e, 'observed-tool', location={'kind': 'unknown'},
                             reason='initial observation', weight_kg=3)
        detached = WORLD.register_object(self.e, 'observed-tool',
            location={'kind': 'unknown'}, reason='public observation', weight_kg=4)
        self.assertIsNot(detached, obj)
        detached['weight_kg'] = 99
        self.assertEqual(obj['weight_kg'], 4)
        again = prepare_object(self.e, 'observed-tool', location={'kind': 'unknown'},
                               reason='fixture reobservation', weight_kg=5)
        self.assertIs(again, obj)
        self.assertEqual(obj['weight_kg'], 5)

    def test_invalid_native_observation_does_not_register_an_object(self):
        before = deepcopy(self.e._physical_objects)
        with self.assertRaisesRegex(ValueError, 'object owner identity must resolve'):
            prepare_object(self.e, 'invalid-tool', location={'kind': 'unknown'},
                           reason='invalid owner observation', owner_id='missing-actor')
        self.assertEqual(self.e._physical_objects, before)


if __name__ == '__main__':
    unittest.main()
