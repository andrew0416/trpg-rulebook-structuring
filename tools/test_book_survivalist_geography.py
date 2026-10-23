"""Adaptive Geography (C04-093): Scene x2 Free Action as you or your Pokemon gain Initiative, one-turn
as-if terrain adjacent on the printed cycle, read by the Survivalist bonus, Naturewalk and Environ Moves
without changing the actual world terrain; both restores."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import environ_moves as ENV
import movement_actions as M
import survivalist_class as SC
import survivalist_features as V


class AdaptiveGeographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        SC.definitions(self.rules)

    def rejected(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def adapt(self, engine, trainer, terrain, **changes):
        options = dict(terrain_name=terrain, reason='GM observed the Initiative trigger')
        options.update(changes)
        return engine.survivalist_activity(trainer, 'adaptive_geography', **options)

    def world(self):
        """Survivalist with four Features plus Adaptive Geography, Forest mastered, standing on observed Wetland cells."""
        world = FIX.scene(self.rules, feats=FIX.CORE_FEATURES + (SC.ADAPTIVE,))
        engine, trainer, partner = world['engine'], world['trainer'], world['partner']
        FIX.master(engine, trainer, 'forest')
        M.observe_cell_terrain(engine, [(2, 2), (3, 2), (2, 1), (3, 1)], ['wetland'], 'GM actual marsh cells')
        for actor in (trainer, partner):
            FIX.env(engine, actor, 'wetland')
        engine.observe_environment('actual', dict(gravity=1, pressure=1, air_available=True, medium='air', environ='늪지'), source=ENV.NATURE, reason='GM observes the actual present environment')
        return world

    def test_trigger_is_the_turn_start_free_action_scene_twice_for_you_or_your_own_pokemon_on_an_adjacent_terrain(self):
        world = self.world()
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'forest'), 'gain Initiative')
        FIX.battle(engine, trainer)
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'cave'), 'adjacent')
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'forest', actual_terrain='ocean'), 'adjacent to an actual current terrain')
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'forest', target=foe), 'your own Pokemon')
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'forest', target=partner), 'gain Initiative')
        row = self.adapt(engine, trainer, 'forest')
        self.assertEqual((row['actual_terrain'], row['as_if_terrain'], row['subject_id'], row['owner_id'], row['round']), ('wetland', 'forest', trainer.entity_id, trainer.entity_id, 1))
        self.assertEqual(trainer._action_history, ['free'])
        self.assertEqual(trainer.budget['standard'], 1)
        self.assertEqual(SC.as_if(engine, trainer)['as_if_terrain'], 'forest')
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'ocean'), 'already shaped')
        engine.end_of_turn(trainer)
        self.assertIsNone(SC.as_if(engine, trainer))
        engine.start_of_turn(partner, initiative_count=15)
        second = self.adapt(engine, trainer, 'ocean', target=partner)
        self.assertEqual((second['actual_terrain'], second['as_if_terrain'], second['subject_id']), ('wetland', 'ocean', partner.entity_id))
        self.assertEqual(SC.as_if(engine, partner)['as_if_terrain'], 'ocean')
        self.assertIsNone(SC.as_if(engine, trainer))
        self.assertEqual(trainer._action_history, ['free', 'free'])
        engine.end_of_turn(partner)
        self.assertIsNone(SC.as_if(engine, partner))
        engine.start_of_turn(foe, initiative_count=10)
        engine.end_of_turn(foe)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.rejected(engine, lambda: self.adapt(engine, trainer, 'forest'), 'Scene frequency exhausted')
        engine.approach(trainer, foe)
        self.assertTrue(engine.validate_state()['valid'])

    def test_as_if_terrain_reaches_the_survivalist_bonus_naturewalk_and_environ_moves_without_changing_the_world(self):
        world = self.world()
        engine, trainer = world['engine'], world['trainer']
        engine.gm.set_move(trainer, ENV.NATURE, reason='actual learned Environ Move')
        FIX.battle(engine, trainer)
        self.assertEqual(engine.skill_roll(trainer, '생존', fixed=[1] * 6).total, 6)
        self.assertFalse(M.ordinary_terrain(engine, trainer, (2, 2)))
        self.assertEqual(ENV.prepare(engine, trainer, self.rules.move(ENV.NATURE))['_environ_selection']['environ'], '늪지')
        self.adapt(engine, trainer, 'forest')
        self.assertEqual(engine.skill_roll(trainer, '생존', fixed=[1] * 6).total, 8)
        self.assertEqual(engine.skill_roll(trainer, '집중', fixed=[1] * 3).total, 3)
        self.assertTrue(M.ordinary_terrain(engine, trainer, (2, 2)))
        self.assertFalse(M.ordinary_terrain(engine, world['partner'], (3, 2)))
        self.assertEqual(engine.grid.terrain_types['2,2'], ['wetland'])
        self.assertEqual(V.current_environment(engine, trainer)['terrains'], ('wetland',))
        self.assertEqual(SC.effective_environment(engine, trainer)['terrains'], ('forest',))
        move = ENV.prepare(engine, trainer, self.rules.move(ENV.NATURE))
        selection = move['_environ_selection']
        self.assertEqual((selection['environ'], selection['selected_move'], selection['adaptive_geography']['actual_environ']), ('숲', 'move/에너지볼', '늪지'))
        self.assertEqual(ENV.mechanics(engine, move, self.rules.move_mech(ENV.NATURE)[0]), self.rules.move_mech('move/에너지볼')[0])
        self.assertEqual(selection['effective_facts']['environ'], '늪지')
        tampered = deepcopy(move)
        tampered['_environ_selection']['adaptive_geography']['actual_environ'] = '산'
        with self.assertRaises(ValueError):
            ENV.mechanics(engine, tampered, self.rules.move_mech(ENV.NATURE)[0])
        engine.end_of_turn(trainer)
        self.assertEqual(engine.skill_roll(trainer, '생존', fixed=[1] * 6).total, 6)
        self.assertFalse(M.ordinary_terrain(engine, trainer, (2, 2)))
        self.assertEqual(ENV.prepare(engine, trainer, self.rules.move(ENV.NATURE))['_environ_selection']['environ'], '늪지')
        self.assertTrue(engine.validate_state()['valid'])

    def test_json_and_gm_restores_keep_the_turn_record_and_tampering_is_rejected(self):
        world = self.world()
        engine, trainer = world['engine'], world['trainer']
        FIX.battle(engine, trainer)
        row = self.adapt(engine, trainer, 'ocean')
        engine.gm.snapshot('shaped')
        loaded, index = FIX.restore(self.rules, engine)
        again = index[trainer.entity_id]
        self.assertEqual(SC.as_if(loaded, again), row)
        self.assertEqual(SC.effective_environment(loaded, again)['terrains'], ('ocean',))
        self.assertTrue(loaded.validate_state()['valid'])
        loaded.end_of_turn(again)
        self.assertIsNone(SC.as_if(loaded, again))
        SC._adaptive_rows(trainer)[0]['adaptive_geography']['as_if_terrain'] = 'cave'
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('shaped')
        self.assertEqual(SC.as_if(engine, trainer), row)
        self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
