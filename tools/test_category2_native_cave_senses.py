"""Native species senses on the shared darkness and movement paths."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
import survivalist_features as V
import state_codec as CODEC

SOURCE = 'input/ch11-running-the-game.md:1780'


class NativeCaveSenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')

    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def fixture(self, species):
        self.e = Engine(self.r, seed=1176)
        self.e.grid = Grid(15, 10)
        self.owner = self.add(build_trainer(
            self.r, 'cave owner', 10,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            extra={'side': 'party', 'pos': (0, 0)}))
        self.a = self.add(build_pokemon(
            self.r, species, 10, moves=['move/몸통박치기'], abilities=[],
            extra={'trainer_id': self.owner.entity_id, 'side': 'party', 'pos': (3, 3)}))
        self.e.gm.observe_loyalty(self.a, 6, reason='actual current owner')
        self.target = self.add(build_trainer(
            self.r, 'cave target', 10,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            extra={'side': 'opponent', 'pos': (7, 3)}))
        V.observe_environment(self.e, self.a, terrains=['cave'],
                              light='complete_darkness', reason=SOURCE)

    def test_native_species_senses_distinguish_darkness_from_external_blindness(self):
        for species, blind, night in (
                ('주뱃', True, True), ('야부엉', False, True), ('잉어킹', False, False)):
            with self.subTest(species=species):
                self.fixture(species)
                # Capabilities come from build_pokemon's actual species definition.
                view = self.e.capability_traits(self.a)
                self.assertEqual((view['blindsense'], view['darkvision']), (blind, night))
                self.assertEqual(V.vision(self.e, self.a),
                                 ('none', False) if night else ('total', False))
                self.assertEqual(self.e.apply_status(
                    self.a, '실명', source=SOURCE, parameters={'cause': 'darkness'}), not night)
                self.assertEqual('실명' in self.a.conditions, not night)
                if not night:
                    self.e.cure_status(self.a, '실명')
                self.assertEqual(self.e.apply_status(
                    self.a, '실명', source='actual external obstruction',
                    parameters={'cause': 'external'}), not blind)
                self.assertEqual('실명' in self.a.conditions, not blind)
                if blind:
                    self.assertFalse(view['visual_reading'])
                    self.assertFalse(view['color_discrimination'])

    def test_native_darkvision_and_ordinary_species_keep_actual_shift_permissions_after_json(self):
        for species, allowed in (('야부엉', True), ('잉어킹', False)):
            for restored in (False, True):
                with self.subTest(species=species, restored=restored):
                    self.fixture(species)
                    self.e.grid.rough.update({(4, 3), (5, 3)})
                    if restored:
                        aid, tid = self.a.entity_id, self.target.entity_id
                        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(
                            CODEC.dump_engine(self.e), ensure_ascii=False)))
                        actors = {c.entity_id: c for c in self.e.everyone}
                        self.a, self.target = actors[aid], actors[tid]
                    self.e.start_round(self.e.everyone)
                    self.e.start_of_turn(self.a, initiative_count=20)
                    before = deepcopy((self.a.pos, self.a.budget,
                                       self.a.spec, self.e.rng.getstate()))
                    if allowed:
                        self.e.approach(self.a, self.target)
                        self.assertNotEqual(self.a.pos, before[0])
                        self.assertEqual(self.a.budget['shift'], 0)
                        self.assertEqual(self.e.rng.getstate(), before[3])
                    else:
                        with self.assertRaisesRegex(ValueError, 'Total Blindness'):
                            self.e.approach(self.a, self.target)
                        self.assertEqual((self.a.pos, self.a.budget,
                                          self.a.spec, self.e.rng.getstate()), before)


if __name__ == '__main__':
    unittest.main()

