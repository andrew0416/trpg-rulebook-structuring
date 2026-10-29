"""Wilderness Guide (ch04:2166-2175): Scene x3 Standard Action, one-full-round ally records by the
actual current terrain, each printed branch on its real consumer, overlap refusal and both restores."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import combat_timing as TIMING
import movement_actions as M
import sound_state as SOUND
import state_grants as G
import survivalist_class as SC
import survivalist_features as V
import vision_impairment as VISION

SPIKES = tuple((5, y) for y in range(8))


class SurvivalistGuideTests(unittest.TestCase):
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

    def guide(self, engine, trainer, terrain, **changes):
        options = dict(terrain_name=terrain, reason='GM observed the order')
        options.update(changes)
        return engine.survivalist_activity(trainer, 'wilderness_guide', **options)

    def world(self, terrain, *, ally=False, foe_moves=None, partner_species='이브이', light='normal'):
        world = FIX.scene(self.rules, ally=ally, foe_moves=foe_moves, partner_species=partner_species)
        for actor in (world['trainer'], world['partner'], *([world['ally']] if ally else [])):
            FIX.env(world['engine'], actor, terrain, light=light)
        return world

    def test_guide_is_a_scene_three_standard_action_on_the_actual_terrain_for_allies_one_full_round(self):
        world = self.world('grassland', ally=True)
        engine, trainer, partner, friend, foe = world['engine'], world['trainer'], world['partner'], world['ally'], world['foe']
        self.rejected(engine, lambda: self.guide(engine, trainer, 'grassland'), 'actual encounter')
        FIX.battle(engine, trainer)
        self.rejected(engine, lambda: self.guide(engine, trainer, 'forest'), 'actual current terrain')
        self.rejected(engine, lambda: self.guide(engine, trainer, 'grassland', reason=''), 'reason')
        receipt = self.guide(engine, trainer, 'grassland')
        self.assertEqual((receipt['branch'], receipt['terrain'], receipt['round'], receipt['count'], sorted(receipt['allies'])),
                         ('grassland_forest', 'grassland', 1, 20, sorted([partner.entity_id, friend.entity_id])))
        self.assertEqual(trainer.budget['standard'], 0)
        self.assertEqual(trainer.spec[SC.GUIDE_HISTORY][-1], receipt)
        for ally in (partner, friend):
            rows = FIX.guide_rows(ally)
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['wilderness_guide']['branch'], rows[0]['count_deadline']), ('grassland_forest', (2, 20)))
        self.assertEqual((FIX.guide_rows(trainer), FIX.guide_rows(foe)), ([], []))
        self.rejected(engine, lambda: self.guide(engine, trainer, 'grassland'), 'Standard Action unavailable|composition policy')
        engine.end_of_turn(trainer)
        engine.start_of_turn(foe, initiative_count=10)
        self.assertTrue(FIX.guide_rows(partner))
        engine.end_of_turn(foe)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.at_initiative_count(21)
        self.assertTrue(FIX.guide_rows(partner))
        engine.start_of_turn(trainer, initiative_count=20)
        self.assertEqual((FIX.guide_rows(partner), FIX.guide_rows(friend)), ([], []))
        second = self.guide(engine, trainer, 'grassland')
        self.assertEqual(second['sequence'], 2)
        self.rejected(engine, lambda: self.guide(engine, trainer, 'grassland'), 'Standard Action unavailable|composition policy')
        for _ in range(2):
            engine.end_of_turn(trainer)
            engine.end_round()
            engine.start_round(engine.everyone)
            engine.start_of_turn(trainer, initiative_count=20)
        third = self.guide(engine, trainer, 'grassland')
        self.assertEqual(third['sequence'], 3)
        engine.end_of_turn(trainer)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.rejected(engine, lambda: self.guide(engine, trainer, 'grassland'), 'Scene frequency exhausted')
        self.assertTrue(engine.validate_state()['valid'])
        world = FIX.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        engine.gm.set_position(world['partner'], (9, 6), reason='own Pokemon away but on the field')
        world['partner'].hp = 0
        FIX.env(engine, trainer, 'grassland')
        FIX.battle(engine, trainer)
        self.rejected(engine, lambda: self.guide(engine, trainer, 'grassland'), 'actual ally on the field')

    def test_grassland_or_forest_grants_the_stealth_capability_and_two_overland_for_one_round(self):
        world = self.world('forest')
        engine, trainer, partner = world['engine'], world['trainer'], world['partner']
        FIX.battle(engine, trainer)
        land = M.capabilities(engine, partner)['land']
        self.assertNotIn('은밀', G.effective_capabilities(partner))
        self.guide(engine, trainer, 'forest')
        self.assertIn('은밀', G.effective_capabilities(partner))
        self.assertEqual(SOUND.sources(partner).get('stealth'), 'capability/은밀')
        self.assertEqual(M.capabilities(engine, partner)['land'], land + 2)
        self.assertEqual(engine.move_profile(partner)[0], land + 2)
        self.assertNotIn('은밀', G.effective_capabilities(trainer))
        engine.end_of_turn(trainer)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.assertNotIn('은밀', G.effective_capabilities(partner))
        self.assertEqual(M.capabilities(engine, partner)['land'], land)
        self.assertTrue(engine.validate_state()['valid'])

    def test_ocean_or_wetland_grants_five_damage_reduction_and_two_swim_for_one_round(self):
        world = self.world('wetland', foe_moves=['move/냉동빔'])
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        FIX.battle(engine, trainer)
        move = self.rules.move('move/냉동빔')
        before = engine.roll_damage(foe, partner, move, set_damage=True)
        swim = M.capabilities(engine, partner)['swim']
        self.assertGreater(swim, 0)
        self.guide(engine, trainer, 'wetland')
        self.assertEqual(engine.roll_damage(foe, partner, move, set_damage=True), before - 5)
        self.assertEqual(M.capabilities(engine, partner)['swim'], swim + 2)
        self.assertEqual(engine.roll_damage(foe, trainer, move, set_damage=True), engine.roll_damage(foe, trainer, move, set_damage=True))
        engine.end_of_turn(trainer)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.assertEqual(engine.roll_damage(foe, partner, move, set_damage=True), before)
        self.assertEqual(M.capabilities(engine, partner)['swim'], swim)

    def test_desert_or_tundra_allies_lose_no_hit_points_to_weather_and_ignore_sand_veil_and_snow_cloak(self):
        world = self.world('desert')
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        FIX.battle(engine, trainer)
        engine.gm.set_weather('sandstorm', rounds=5, reason='GM observed the sandstorm')
        engine.gm.observe_sensory_environment(trainer,partner,paths={'auditory':True},present=True,
            reason='actual contemporaneous Wilderness Guide Order delivery')
        self.guide(engine, trainer, 'desert')
        rows = FIX.guide_rows(partner)
        self.assertEqual(rows[0]['wilderness_guide']['branch'], 'desert_tundra')
        engine.end_of_turn(trainer)
        hp = partner.hp
        engine.start_of_turn(partner, initiative_count=15)
        self.assertEqual(partner.hp, hp)
        self.assertTrue(any('모래바람 피해 면역 (생존가)' in line for line in engine.log_lines))
        engine.end_of_turn(partner)
        hp = foe.hp
        engine.start_of_turn(foe, initiative_count=10)
        self.assertEqual(foe.hp, hp - engine.tick_loss(foe))
        self.assertEqual(SC.ignored_ability_evasion(engine, partner, foe), 0)
        self.assertEqual(SC.BRANCHES['desert_tundra']['ignored_abilities'], ['ability/모래숨기-playtest', 'ability/눈숨기-playtest'])
        engine.end_of_turn(foe)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        engine.end_of_turn(trainer)
        hp = partner.hp
        engine.start_of_turn(partner, initiative_count=15)
        self.assertEqual(partner.hp, hp - engine.tick_loss(partner))
        self.assertTrue(engine.validate_state()['valid'])

    def test_mountain_or_cave_allies_do_not_trigger_hazards_and_are_not_blinded_by_low_light(self):
        world = self.world('cave', foe_moves=['move/몸통박치기', 'move/압정뿌리기'], light='low_light')
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        self.assertEqual(V.vision(engine, partner), ('ordinary', False))
        self.assertEqual(VISION.accuracy_penalty(engine, partner), -6)
        FIX.battle(engine, foe)
        engine.use_move_on(foe, foe, 'move/압정뿌리기', engine.everyone, aim=SPIKES)
        self.assertEqual(sum(len(x['instances']) for x in engine.hazards.values()), 8)
        FIX.next_turn(engine, foe, trainer, count=15)
        self.guide(engine, trainer, 'cave')
        self.assertEqual(V.vision(engine, partner), ('none', False))
        self.assertEqual(VISION.accuracy_penalty(engine, partner), 0)
        self.assertEqual(V.vision(engine, trainer), ('ordinary', False))
        FIX.next_turn(engine, trainer, partner, count=10)
        hp = partner.hp
        engine.approach(partner, foe)
        self.assertGreaterEqual(partner.pos[0], 5)
        self.assertEqual((partner.hp, '둔화' in partner.conditions), (hp, False))
        self.assertEqual(sum(len(x['instances']) for x in engine.hazards.values()), 8)
        self.assertTrue(any('함정을 유발하지 않음 (야생 가이드)' in line for line in engine.log_lines))
        engine.end_of_turn(partner)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(foe, initiative_count=20)
        FIX.next_turn(engine, foe, trainer, count=15)
        FIX.next_turn(engine, trainer, partner, count=10)
        self.assertEqual(V.vision(engine, partner), ('ordinary', False))
        FIX.env(engine, partner, 'cave', light='normal')
        engine.gm.set_position(partner, (3, 2), reason='GM returns the Pokemon west of the spikes')
        hp = partner.hp
        engine.approach(partner, foe)
        self.assertEqual((partner.hp, '둔화' in partner.conditions), (hp - engine.tick(partner), True))
        self.assertTrue(engine.validate_state()['valid'])

    def test_urban_allies_gain_one_evasion_and_two_on_dirty_trick_and_manipulate_rolls_only(self):
        world = self.world('urban', ally=True)
        engine, trainer, partner, friend = world['engine'], world['trainer'], world['partner'], world['ally']
        bandit = Combatant(self.rules, FIX.trainer_spec(self.rules, 'bandit', survival=3))
        engine.gm.add_combatant(bandit, pos=(3, 4), side='wild', reason='opposing trainer adjacent to the ally')
        FIX.battle(engine, trainer)
        evasion = friend.evasion('물리', engine=engine)
        need = 2 + bandit.evasion('변화', engine=engine)
        self.guide(engine, trainer, 'urban')
        self.assertEqual(friend.evasion('물리', engine=engine), evasion + 1)
        self.assertEqual(partner.evasion('특수', engine=engine), partner.evasion('특수', engine=engine))
        self.assertEqual(SC.accuracy_bonus(engine, friend, bandit, {'id': 'maneuver/치사한-짓'}), 2)
        self.assertEqual(SC.accuracy_bonus(engine, friend, bandit, {'id': 'move/몸통박치기'}), 0)
        self.assertEqual(SC.maneuver_skill_options(engine, friend, 'maneuver/술수', {'fixed': [2] * 4})['mods'], 2)
        self.assertNotIn('mods', SC.maneuver_skill_options(engine, friend, 'maneuver/밀기', {'fixed': [2] * 4}))
        FIX.next_turn(engine, trainer, friend, count=15)
        self.assertTrue(engine.dirty_trick(friend, bandit, 'blind', fixed_accuracy=need - 2, challenger_options={'fixed': [3] * 3}, defender_options={'fixed': [3] * 3}))
        self.assertIn('실명', bandit.conditions)
        engine.end_of_turn(friend)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.assertEqual(friend.evasion('물리', engine=engine), evasion)
        engine.end_of_turn(trainer)
        engine.start_of_turn(friend, initiative_count=15)
        self.assertFalse(engine.manipulate(friend, bandit, 'terrorize', defender_skill='집중', fixed_accuracy=need, challenger_options={'fixed': [2] * 4}, defender_options={'fixed': [3] * 3}))
        engine.end_of_turn(friend)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(trainer, initiative_count=20)
        self.guide(engine, trainer, 'urban')
        FIX.next_turn(engine, trainer, friend, count=15)
        self.assertTrue(engine.manipulate(friend, bandit, 'bon_mot', defender_skill='집중', fixed_accuracy=need, challenger_options={'fixed': [2] * 4}, defender_options={'fixed': [3] * 3}))
        self.assertTrue(engine.validate_state()['valid'])

    def test_json_and_gm_restores_keep_the_round_records_and_a_second_guide_cannot_overlap(self):
        world = self.world('forest', ally=True)
        engine, trainer, partner, friend = world['engine'], world['trainer'], world['partner'], world['ally']
        FIX.acquire(engine, friend, SC.CLASS)
        FIX.acquire(engine, friend, SC.GUIDE)
        FIX.battle(engine, trainer)
        receipt = self.guide(engine, trainer, 'forest')
        engine.gm.snapshot('guided')
        loaded, index = FIX.restore(self.rules, engine)
        again, mate = index[partner.entity_id], index[friend.entity_id]
        self.assertEqual(FIX.guide_rows(again)[0]['wilderness_guide'], FIX.guide_rows(partner)[0]['wilderness_guide'])
        self.assertIn('은밀', G.effective_capabilities(again))
        self.assertEqual(index[trainer.entity_id].spec[SC.GUIDE_HISTORY][-1], receipt)
        self.assertTrue(loaded.validate_state()['valid'])
        FIX.next_turn(engine, trainer, friend, count=15)
        self.rejected(engine, lambda: self.guide(engine, friend, 'forest'), 'composition policy')
        partner.custom_conditions[TIMING.KEY][0]['wilderness_guide']['branch'] = 'urban'
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('guided')
        self.assertTrue(engine.validate_state()['valid'])
        self.assertEqual(FIX.guide_rows(partner)[0]['wilderness_guide']['branch'], 'grassland_forest')


if __name__ == '__main__':
    unittest.main()
