"""Source-only additions; not executed. Compose the shared CW/effects seams first."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine')]
from engine import Rules, Engine, Combatant
import combat_stage_sources as CS
import movement_actions as MOVEMENT
import weather_passive_benefits as W


class WeatherPassiveBenefitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='playtest')

    def setUp(self):
        self.e = Engine(self.rules, 49)

    def actor(self, abilities=(), *, name=None, side='A', moves=()):
        spec = {'name': name or 'weather-holder-' + str(len(self.e.gm.everyone)),
                'kind': 'pokemon', 'level': 25,
                'stats': {'hp': 25, 'atk': 30, 'def': 15, 'spa': 20, 'spd': 15, 'spe': 15},
                'abilities': list(abilities), 'moves': list(moves), 'types': [],
                'movement': {'land': 8, 'swim': 4}, 'pos': (len(self.e.gm.everyone) + 1, 1),
                'size': 'Medium', 'side': side}
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def weather(self, weather):
        self.e.gm.set_weather(weather, rounds=5, reason='actual weather test fixture')

    def hp(self, actor, amount):
        self.e.gm.set_hp(actor, value=amount, reason='actual HP test fixture')

    def turn(self, actor):
        self.e.start_round(list(self.e.gm.everyone))
        self.e.start_of_turn(actor, initiative_count=12)

    def test_thermosensitive_derived_stages_preserve_other_sources_and_hail_penalty(self):
        actor = self.actor(['감온성'])
        CS.add_base(actor, 'independent', 'atk', 1, source='test/independent', ends='test')
        self.weather('sunny')
        self.assertEqual((actor.stages['atk'], actor.stages['spa']), (3, 2))
        with patch('survivalist_class.weather_ability_suppressed', return_value=True):
            self.assertEqual((actor.stages['atk'], actor.stages['spa']), (1, 0))
            self.assertIn('감온성', actor.abilities)
            self.assertEqual(self.e.weather, 'sunny')
            self.weather('hail')
            self.assertEqual(MOVEMENT.capabilities(self.e, actor)['land'], 4)
        self.weather('sunny')
        self.assertEqual((actor.stages['atk'], actor.stages['spa']), (3, 2))
        for _ in range(2):
            self.e.register_abilities(actor)
            self.assertEqual(actor.stages['atk'], 3)

    def test_protosynthesis_low_hp_is_independent_and_half_hp_is_not_below_half(self):
        actor = self.actor(['고대활성'])
        self.weather('sunny')
        self.assertEqual(actor.stages['atk'], 1)
        with patch('survivalist_class.weather_ability_suppressed', return_value=True):
            self.assertEqual(actor.stages['atk'], 0)
            self.hp(actor, (actor.base_max_hp - 1) // 2)
            self.assertEqual(actor.stages['atk'], 1)
            self.hp(actor, (actor.base_max_hp + 1) // 2)
            self.assertEqual(actor.stages['atk'], 0)
        self.assertEqual(actor.stages['atk'], 1)
        self.weather(None)
        self.assertEqual(actor.stages['atk'], 0)

    def test_conditional_stages_round_trip_without_replaying_or_erasing_combat_changes(self):
        actor = self.actor(['감온성', '고대활성'])
        self.weather('sunny')
        self.e.change_stage(actor, 'atk', 2)
        loaded = Engine.import_state(self.rules, json.loads(json.dumps(self.e.export_state())))
        actual = next(row for row in loaded.everyone if row.entity_id == actor.entity_id)
        self.assertEqual((actual.stages['atk'], actual.stages['spa']), (5, 2))
        loaded.gm.set_weather(None, reason='actual sun ends')
        self.assertEqual((actual.stages['atk'], actual.stages['spa']), (2, 0))

    def test_end_turn_rain_real_healing_and_temp_hp_do_not_retroactively_disappear(self):
        actor = self.actor(['건조피부', '사막날씨 [Playtest]'])
        self.hp(actor, actor.base_max_hp // 2)
        self.weather('rain')
        self.turn(actor)
        hp = actor.hp
        self.e.end_of_turn(actor)
        self.assertEqual(actor.hp, hp + self.e.tick(actor))
        self.assertEqual(actor.temp_hp, self.e.tick(actor))
        barrier = actor.temp_hp
        self.e.end_round()
        self.turn(actor)
        hp = actor.hp
        with patch('survivalist_class.weather_ability_suppressed', return_value=True):
            self.e.end_of_turn(actor)
        self.assertEqual((actor.hp, actor.temp_hp), (hp, barrier))
        self.assertEqual(self.e.weather, 'rain')

    def test_dry_skin_sun_loss_survives_guide_and_forged_turn_end_cannot_heal(self):
        actor = self.actor(['건조피부'])
        self.weather('sunny')
        self.turn(actor)
        hp = actor.hp
        with patch('survivalist_class.weather_ability_suppressed', return_value=True):
            self.e.end_of_turn(actor)
        self.assertEqual(actor.hp, hp - self.e.tick_loss(actor))
        self.weather('rain')
        before = actor.hp
        with self.assertRaises(ValueError):
            W.end_turn(self.e, actor)
        self.assertEqual(actor.hp, before)

    def test_water_absorption_is_native_hit_only_and_survives_guide(self):
        attacker = self.actor(moves=['move/물대포'])
        target = self.actor(['건조피부'], side='B')
        self.hp(target, target.base_max_hp // 2)
        before = target.hp
        with patch('survivalist_class.weather_ability_suppressed', return_value=True):
            self.assertEqual(self.e.roll_damage(attacker, target, self.rules.move('move/물대포'), set_damage=True), 0)
            self.assertEqual(target.hp, before)
            self.turn(attacker)
            with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
                self.e.use_move(attacker, target, 'move/물대포', set_damage=True)
        self.assertEqual(target.hp, before + self.e.tick(target))
        self.assertEqual(attacker.move_uses['move/물대포'], 1)
        completion = list(self.e._move_completions.values())[-1]
        self.assertEqual(completion['results'][target.entity_id]['dealt'], 0)
        self.assertTrue(completion['results'][target.entity_id]['hit_prevented'])

    def test_water_miss_and_forged_hit_cannot_heal(self):
        attacker = self.actor(moves=['move/물대포'])
        target = self.actor(['건조피부'], side='B')
        self.hp(target, target.base_max_hp // 2)
        before = target.hp
        self.turn(attacker)
        with patch.object(Engine, 'accuracy_check', return_value=(False, 1, False)):
            self.e.use_move(attacker, target, 'move/물대포', set_damage=True)
        self.assertEqual(target.hp, before)
        with self.assertRaises(ValueError):
            W.water_hit(self.e, attacker, target, self.rules.move('move/물대포'), {}, 'invented',
                        substitute=None, natural=12, critical=False)
        self.assertEqual(target.hp, before)

    def test_fire_hit_adds_one_tick_and_suppression_removes_whole_ability_only(self):
        attacker = self.actor(moves=['move/불꽃세례'])
        target = self.actor(['건조피부'], side='B')
        self.turn(attacker)
        before = target.hp
        with patch('survivalist_class.weather_ability_suppressed', return_value=True):
            with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
                self.e.use_move(attacker, target, 'move/불꽃세례', set_damage=True)
        completion = list(self.e._move_completions.values())[-1]
        hit = completion['dry_skin_hits'][target.entity_id]
        self.assertEqual(hit['hp_before'] - hit['hp_after'], self.e.tick_loss(target))
        self.assertLess(target.hp, before)
        self.e.end_of_turn(attacker)
        self.e.end_round()
        self.hp(target, target.base_max_hp)
        target.abilities_suppressed = True
        self.turn(attacker)
        with patch.object(Engine, 'accuracy_check', return_value=(True, 12, False)):
            self.e.use_move(attacker, target, 'move/불꽃세례', set_damage=True)
        self.assertNotIn('dry_skin_hits', list(self.e._move_completions.values())[-1])


if __name__ == '__main__':
    unittest.main()
