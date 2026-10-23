"""Terrain Talents table (C04-094): the printed effects of Forest Ranger, Marsh Stomper, Deep Diver,
Arctic Pilgrim, Cave Dweller (Stealth Rock), Traceur and Dune Walker on their real consumers; Plains Runner,
Surefooted and Cave Dweller sight keep their existing survivalist_features owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import environmental_effects as ENVFX
import jump_actions as JUMP
import movement_actions as M
import sound_state as SOUND
import state_grants as G
import survivalist_class as SC
import survivalist_features as V
import trainer_capabilities as TRAINER

ROCKS = ((6, 1), (6, 3), (8, 0), (8, 4))


class TerrainTalentTableTests(unittest.TestCase):
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

    def world(self, *terrains, talents=True, foe_moves=None, env='urban'):
        world = FIX.scene(self.rules, foe_moves=foe_moves)
        engine, trainer = world['engine'], world['trainer']
        for terrain in terrains:
            FIX.master(engine, trainer, terrain)
        if talents:
            FIX.talents(engine, trainer, *terrains[:2])
        FIX.env(engine, trainer, env)
        return world

    def standard(self, engine, actor, target):
        with patch.object(engine, 'd20', return_value=18):
            engine.use_move(actor, target, 'struggle', set_damage=True)

    def test_forest_ranger_grants_the_stealth_capability_everywhere_only_to_the_actual_choice(self):
        world = self.world('forest', 'cave')
        engine, trainer = world['engine'], world['trainer']
        self.assertEqual(V.talents(engine, trainer), ('forest', 'cave'))
        self.assertIn('은밀', G.effective_capabilities(trainer))
        self.assertEqual(SOUND.sources(trainer).get('stealth'), 'capability/은밀')
        self.assertEqual(SC.capability_contributions(trainer), ['은밀'])
        other = self.world('cave', 'mountain')
        self.assertNotIn('은밀', G.effective_capabilities(other['trainer']))
        self.assertNotIn('은밀', G.effective_capabilities(world['partner']))
        self.assertTrue(engine.validate_state()['valid'])

    def test_marsh_stomper_keeps_the_poison_without_hit_point_loss_and_loses_one_stage(self):
        for talent in (True, False):
            with self.subTest(talent=talent):
                world = self.world('wetland', 'cave', talents=talent, foe_moves=['move/독가루'])
                engine, trainer, foe = world['engine'], world['trainer'], world['foe']
                engine.gm.set_position(foe, (2, 3), reason='adjacent foe')
                FIX.battle(engine, foe)
                with patch.object(engine, 'd20', return_value=20):
                    engine.use_move(foe, trainer, 'move/독가루')
                self.assertIn('독', trainer.conditions)
                self.assertEqual(trainer.stages['spd'], -1 if talent else -2)
                FIX.next_turn(engine, foe, trainer, count=10)
                hp = trainer.hp
                self.standard(engine, trainer, foe)
                with patch.object(engine, 'd20', return_value=1):
                    engine.end_of_turn(trainer)
                self.assertEqual(trainer.hp, hp if talent else hp - engine.tick(trainer))
                self.assertIn('독', trainer.conditions)
                engine.cure_status(trainer, '독')
                self.assertEqual(trainer.stages['spd'], 0)
                self.assertTrue(engine.validate_state()['valid'])

    def test_deep_diver_swim_equals_overland_and_breath_lasts_survival_rank_minutes(self):
        world = self.world('ocean', 'cave')
        engine, trainer = world['engine'], world['trainer']
        values = M.capabilities(engine, trainer)
        self.assertEqual(values['swim'], values['land'])
        self.assertEqual(TRAINER.breath_grace(trainer, 'water', engine=engine), 360)
        self.assertEqual(TRAINER.breath_grace(trainer, 'air', engine=engine), 60)
        state = engine.observe_breathing(trainer, air_available=False, medium='water', reason='GM observed the dive')
        self.assertEqual(trainer.spec['_respiration']['grace_seconds'], 360)
        engine.advance_time(300, [trainer])
        self.assertEqual(trainer.injuries, 0)
        other = self.world('cave', 'mountain')
        values = M.capabilities(other['engine'], other['trainer'])
        self.assertEqual(values['swim'], TRAINER.swimming(other['trainer'], values['land']))
        self.assertLess(values['swim'], values['land'])
        self.assertEqual(TRAINER.breath_grace(other['trainer'], 'water', engine=other['engine']), 60)

    def test_arctic_pilgrim_ignores_hail_and_frozen_and_reduces_ice_damage_by_five(self):
        move, fire = self.rules.move('move/냉동빔'), self.rules.move('move/화염방사')
        baseline = self.world('cave', 'mountain', foe_moves=['move/냉동빔'])
        plain = baseline['engine'].roll_damage(baseline['foe'], baseline['trainer'], move, set_damage=True)
        plain_fire = baseline['engine'].roll_damage(baseline['foe'], baseline['trainer'], fire, set_damage=True)
        world = self.world('tundra', 'cave', foe_moves=['move/냉동빔'])
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        self.assertEqual(engine.roll_damage(foe, trainer, move, set_damage=True), plain - 5)
        self.assertEqual(engine.roll_damage(foe, trainer, fire, set_damage=True), plain_fire)
        self.assertFalse(engine.apply_status(trainer, '얼음'))
        self.assertNotIn('얼음', trainer.conditions)
        self.assertTrue(engine.apply_status(partner, '얼음'))
        FIX.battle(engine, foe)
        engine.gm.set_weather('hail', rounds=5, reason='GM observed the hail')
        FIX.next_turn(engine, foe, trainer, count=15)
        hp = trainer.hp
        engine.end_of_turn(trainer)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=15)
        self.assertEqual(trainer.hp, hp)
        self.assertTrue(any('싸라기눈 피해 면역 (생존가)' in line for line in engine.log_lines))
        engine.end_of_turn(trainer)
        hp = foe.hp
        engine.start_of_turn(foe, initiative_count=10)
        self.assertEqual(foe.hp, hp - engine.tick_loss(foe))
        self.assertTrue(engine.validate_state()['valid'])

    def test_cave_dweller_is_immune_to_stealth_rock_hazards(self):
        for talent in (True, False):
            with self.subTest(talent=talent):
                world = self.world('cave', 'mountain', talents=talent, foe_moves=['move/스텔스록'])
                engine, trainer, foe = world['engine'], world['trainer'], world['foe']
                FIX.battle(engine, foe)
                engine.use_move_on(foe, foe, 'move/스텔스록', engine.everyone, aim=ROCKS)
                self.assertEqual(sum(len(x['instances']) for x in engine.hazards.values()), 4)
                FIX.next_turn(engine, foe, trainer, count=10)
                hp = trainer.hp
                engine.approach(trainer, foe)
                self.assertGreaterEqual(trainer.pos[0], 5)
                if talent:
                    self.assertEqual(trainer.hp, hp)
                    self.assertEqual(sum(len(x['instances']) for x in engine.hazards.values()), 4)
                    self.assertTrue(any('동굴 거주자로 스텔스록 함정 면역' in line for line in engine.log_lines))
                else:
                    self.assertLess(trainer.hp, hp)
                    self.assertLess(sum(len(x['instances']) for x in engine.hazards.values()), 4)
                self.assertTrue(engine.validate_state()['valid'])

    def test_traceur_adds_one_jump_and_half_survival_rank_evasion_against_push_trip_and_opportunity_attacks(self):
        results = {}
        for talent in (True, False):
            world = self.world('urban', 'cave', talents=talent)
            engine, trainer, foe = world['engine'], world['trainer'], world['foe']
            results[talent] = JUMP.limits(trainer)
            bandit = Combatant(self.rules, FIX.trainer_spec(self.rules, 'bandit', survival=3, movement={'land': 6, 'power': 4}))
            engine.gm.add_combatant(bandit, pos=(1, 2), side='wild', reason='adjacent opposing trainer')
            engine.gm.set_position(world['partner'], (3, 5), reason='own Pokemon clears the push lane')
            bandit.spec['weight_kg'] = 30
            trainer.spec['weight_kg'] = 30
            FIX.battle(engine, bandit)
            need = 4 + trainer.evasion('변화', engine=engine)
            options = dict(challenger_skill='전투', defender_skill='전투', fixed_accuracy=need + 1, challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [2] * 4})
            self.assertEqual(SC.evasion_bonus(engine, trainer, bandit, {'id': 'maneuver/밀기'}), 3 if talent else 0)
            self.assertEqual(SC.evasion_bonus(engine, trainer, bandit, {'id': 'move/몸통박치기'}), 0)
            pushed = engine.push(bandit, trainer, **options)
            self.assertEqual(bool(pushed), not talent, pushed)
            self.assertEqual(trainer.pos, (2, 2) if talent else (3, 2) if pushed else (2, 2))
            engine.end_of_turn(bandit)
            engine.start_of_turn(trainer, initiative_count=10)
            engine.gm.set_position(trainer, (2, 2), reason='GM returns the Survivalist next to the bandit before it leaves')
            hp = trainer.hp
            need = 4 + trainer.evasion('물리', engine=engine)
            with patch.object(engine, 'd20', return_value=need + 1):
                engine.approach(trainer, foe)
            self.assertTrue(bandit.aoo_used)
            self.assertEqual(trainer.hp == hp, talent)
            self.assertTrue(engine.validate_state()['valid'])
        self.assertEqual({key: results[True][key] - results[False][key] for key in results[True]}, {'high_jump': 1, 'long_jump': 1})

    def test_dune_walker_ignores_sandstorm_sand_attack_and_sand_tomb_and_reduces_fire_damage_by_five(self):
        move, ice = self.rules.move('move/화염방사'), self.rules.move('move/냉동빔')
        baseline = self.world('cave', 'mountain', foe_moves=['move/화염방사'])
        plain = baseline['engine'].roll_damage(baseline['foe'], baseline['trainer'], move, set_damage=True)
        plain_ice = baseline['engine'].roll_damage(baseline['foe'], baseline['trainer'], ice, set_damage=True)
        world = self.world('desert', 'cave', foe_moves=['move/모래뿌리기', 'move/모래지옥', 'move/화염방사'])
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        self.assertEqual(engine.roll_damage(foe, trainer, move, set_damage=True), plain - 5)
        self.assertEqual(engine.roll_damage(foe, trainer, ice, set_damage=True), plain_ice)
        engine.gm.set_position(foe, (2, 3), reason='adjacent foe')
        FIX.battle(engine, foe)
        with patch.object(engine, 'd20', return_value=20):
            engine.use_move(foe, trainer, 'move/모래뿌리기')
        self.assertNotIn('실명', trainer.conditions)
        self.assertTrue(any('실명에 면역 (지형 재능)' in line for line in engine.log_lines))
        engine.end_of_turn(foe)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(foe, initiative_count=20)
        hp = trainer.hp
        with patch.object(engine, 'd20', return_value=18):
            engine.use_move(foe, trainer, 'move/모래지옥', set_damage=True)
        self.assertLess(trainer.hp, hp)
        self.assertNotIn('조이기', trainer.conditions)
        engine.end_of_turn(foe)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(foe, initiative_count=20)
        with patch.object(engine, 'd20', return_value=18):
            engine.use_move(foe, partner, 'move/모래뿌리기')
        self.assertIn('실명', partner.conditions)
        engine.gm.set_weather('sandstorm', rounds=5, reason='GM observed the sandstorm')
        FIX.next_turn(engine, foe, trainer, count=15)
        engine.end_of_turn(trainer)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(foe, initiative_count=20)
        engine.end_of_turn(foe)
        hp = trainer.hp
        engine.start_of_turn(trainer, initiative_count=15)
        self.assertEqual(trainer.hp, hp)
        self.assertTrue(any('모래바람 피해 면역 (생존가)' in line for line in engine.log_lines))
        self.assertTrue(engine.validate_state()['valid'])

    def test_talent_effects_survive_both_restores_and_need_the_actual_choice(self):
        world = self.world('forest', 'tundra')
        engine, trainer = world['engine'], world['trainer']
        self.assertEqual(SC.talent_projection(trainer), ('forest', 'tundra'))
        engine.gm.snapshot('chosen')
        loaded, index = FIX.restore(self.rules, engine)
        again = index[trainer.entity_id]
        self.assertEqual(SC.talent_set(loaded, again), ('forest', 'tundra'))
        self.assertIn('은밀', G.effective_capabilities(again))
        self.assertFalse(loaded.apply_status(again, '얼음'))
        self.assertTrue(loaded.validate_state()['valid'])
        trainer.spec['_survivalist_talents']['terrains'] = ('forest', 'cave')
        self.assertEqual(SC.talent_projection(trainer), ('forest', 'cave'))
        with self.assertRaises(ValueError):
            SC.talent_set(engine, trainer)
        engine.gm.restore('chosen')
        self.assertEqual(SC.talent_set(engine, trainer), ('forest', 'tundra'))
        unchosen = FIX.scene(self.rules)
        FIX.master(unchosen['engine'], unchosen['trainer'], 'forest')
        FIX.master(unchosen['engine'], unchosen['trainer'], 'cave')
        FIX.acquire(unchosen['engine'], unchosen['trainer'], SC.TALENT, rank=1)
        self.assertEqual(SC.talent_projection(unchosen['trainer']), ())
        self.assertNotIn('은밀', G.effective_capabilities(unchosen['trainer']))
        self.assertEqual(SC.jump_bonus(unchosen['trainer']), {'high_jump': 0, 'long_jump': 0})
        with self.assertRaises(ValueError):
            SC.talent_set(unchosen['engine'], unchosen['trainer'])


if __name__ == '__main__':
    unittest.main()
