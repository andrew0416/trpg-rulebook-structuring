"""Actual acquired HB Guide against passive weather consumers; source-only candidate."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import ability_transitions as ABILITIES
import book_survivalist_fixture as FIX
import frequency as FREQ
import movement_actions as MOVEMENT
import state_grants as GRANTS
import survivalist_class as SC
import temporary_hp as TEMP
import test_csv_survivalist_hb as HB
import weather_passive_benefits as WEATHER


class WeatherPassiveGuideLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def scene(self, *sources, weather):
        fixture = HB.SurvivalistHBTests()
        fixture.rules = self.rules
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        world = fixture.world(terrains=('desert',))
        engine, foe = world['engine'], world['foe']
        if WEATHER.PROTO in sources:
            engine.gm.set_stat(foe, 'atk', value=40, reason='actual unique highest non-HP Stat')
        for source in sources:
            GRANTS.grant(foe, 'abilities', source, 'gm/passive-guide/' + source,
                         'gm', rule_id=source)
        GRANTS.reconcile(engine, foe)
        engine.gm.set_weather(weather, rounds=None, reason='actual persistent weather before Guide')
        return fixture, engine, world['trainer'], foe

    def guide(self, fixture, engine, trainer, foe):
        FIX.audible_order(engine, trainer)
        receipt = fixture.guide(engine, trainer)
        self.assertEqual(SC.edition(trainer, SC.GUIDE), 'csv_hb')
        self.assertEqual(receipt['edition'], 'csv_hb')
        self.assertIn(foe.entity_id, receipt['weather_targets'])
        self.assertEqual((trainer.budget['standard'],
                          FREQ.state(trainer)['activations'][SC.GUIDE]['used']), (0, 1))
        return receipt

    def cold_restore(self, engine, trainer, foe):
        fresh_rules = Rules(ROOT, ruleset='all')
        loaded, index = FIX.restore(fresh_rules, engine)
        self.assertIsNot(loaded.r, engine.r)
        return loaded, index[trainer.entity_id], index[foe.entity_id]

    def valid(self, engine):
        result = engine.validate_state()
        self.assertTrue(result['valid'], result)

    def test_thermosensitive_actual_guide_preserves_independent_stage_and_hail_harm_until_exact_expiry(self):
        fixture, e, trainer, foe = self.scene(WEATHER.THERMO, weather='sunny')
        e.gm.set_stage(foe, 'atk', delta=1, reason='actual independent combat-stage increase')
        learned = list(foe.abilities)
        land = MOVEMENT.capabilities(e, foe)['land']
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (3, 2))
        FIX.battle(e, trainer, count=20)
        self.guide(fixture, e, trainer, foe)
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (1, 0))
        self.assertTrue(ABILITIES.active(foe, WEATHER.THERMO))
        e.gm.set_weather('hail', rounds=None, reason='actual harmful weather while Guide is active')
        self.assertTrue(SC.weather_ability_suppressed(e, foe, WEATHER.THERMO))
        self.assertEqual(MOVEMENT.capabilities(e, foe)['land'], land // 2)
        e, trainer, foe = self.cold_restore(e, trainer, foe)
        self.assertEqual(e.weather, 'hail')
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (1, 0))
        self.assertEqual(MOVEMENT.capabilities(e, foe)['land'], land // 2)
        e.gm.set_weather('sunny', rounds=None, reason='actual sun returns before Guide expires')
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (1, 0))
        e.end_of_turn(trainer)
        e.end_round()
        e.start_round(e.everyone)
        e.at_initiative_count(21)
        self.assertTrue(SC.weather_ability_suppressed(e, foe, WEATHER.THERMO))
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (1, 0))
        e.at_initiative_count(20)
        self.assertFalse(SC.weather_ability_suppressed(e, foe, WEATHER.THERMO))
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (3, 2))
        self.assertEqual((MOVEMENT.capabilities(e, foe)['land'], foe.abilities), (land, learned))
        e.gm.set_weather(None, reason='actual sun ends after the restored benefit')
        self.assertEqual((foe.stages['atk'], foe.stages['spa']), (1, 0))
        self.valid(e)

    def test_protosynthesis_actual_guide_keeps_strict_low_hp_route_across_cold_restore_and_count_expiry(self):
        fixture, e, trainer, foe = self.scene(WEATHER.PROTO, weather='sunny')
        self.assertEqual(WEATHER.highest_stats(foe), ['atk'])
        self.assertEqual(foe.stages['atk'], 1)
        FIX.battle(e, trainer, count=20)
        self.guide(fixture, e, trainer, foe)
        self.assertEqual(foe.stages['atk'], 0)
        e, trainer, foe = self.cold_restore(e, trainer, foe)
        self.assertTrue(ABILITIES.active(foe, WEATHER.PROTO))
        self.assertEqual(foe.stages['atk'], 0)
        e.gm.set_hp(foe, (foe.base_max_hp - 1) // 2, reason='actual strictly below-half HP')
        self.assertEqual(foe.stages['atk'], 1)
        e.gm.set_hp(foe, (foe.base_max_hp + 1) // 2, reason='actual half-or-higher HP boundary')
        self.assertEqual(foe.stages['atk'], 0)
        e.end_of_turn(trainer)
        e.end_round()
        e.start_round(e.everyone)
        e.at_initiative_count(21)
        self.assertTrue(SC.weather_ability_suppressed(e, foe, WEATHER.PROTO))
        self.assertEqual(foe.stages['atk'], 0)
        e.at_initiative_count(20)
        self.assertFalse(SC.weather_ability_suppressed(e, foe, WEATHER.PROTO))
        self.assertEqual(foe.stages['atk'], 1)
        e.gm.set_hp(foe, (foe.base_max_hp - 1) // 2, reason='both independent low HP and sun are now true')
        self.assertEqual(foe.stages['atk'], 1)
        e.gm.set_weather(None, reason='actual sun ends while independent low HP remains')
        self.assertEqual(foe.stages['atk'], 1)
        e.gm.set_hp(foe, (foe.base_max_hp + 1) // 2, reason='actual low-HP route ends too')
        self.assertEqual(foe.stages['atk'], 0)
        self.valid(e)

    def test_actual_guide_blocks_new_rain_healing_and_temp_hp_without_erasing_prior_grants(self):
        fixture, e, trainer, foe = self.scene(WEATHER.DRY, WEATHER.DESERT, weather='rain')
        e.gm.set_hp(foe, foe.base_max_hp // 2, reason='actual damage before prior rain healing')
        FIX.battle(e, foe, count=10)
        before, tick = foe.hp, e.tick(foe)
        e.end_of_turn(foe)
        self.assertEqual((foe.hp, foe.temp_hp), (before + tick, tick))
        paid_hp, barrier = foe.hp, foe.temp_hp
        prior_grants = deepcopy(foe.custom_conditions[TEMP.STATE]['grant_events'])
        self.assertEqual(prior_grants[-1]['provenance']['source'], WEATHER.DESERT)
        e.end_round()
        FIX.battle(e, trainer, count=20)
        self.guide(fixture, e, trainer, foe)
        self.assertEqual((foe.hp, foe.temp_hp), (paid_hp, barrier))
        e, trainer, foe = self.cold_restore(e, trainer, foe)
        self.assertEqual((foe.hp, foe.temp_hp), (paid_hp, barrier))
        FIX.next_turn(e, trainer, foe, count=10)
        e.end_of_turn(foe)
        self.assertEqual((foe.hp, foe.temp_hp), (paid_hp, barrier))
        self.assertEqual(foe.custom_conditions[TEMP.STATE]['grant_events'], prior_grants)
        # Spend the retained barrier through real HP loss so a resumed grant is observable.
        e.lose_hp(foe, barrier, source='gm/actual independent barrier-consuming hazard')
        self.assertEqual((foe.hp, foe.temp_hp), (paid_hp, 0))
        e.end_round()
        e.start_round(e.everyone)
        e.at_initiative_count(21)
        for source in (WEATHER.DRY, WEATHER.DESERT):
            self.assertTrue(SC.weather_ability_suppressed(e, foe, source))
            self.assertTrue(ABILITIES.active(foe, source))
        e.at_initiative_count(20)
        for source in (WEATHER.DRY, WEATHER.DESERT):
            self.assertFalse(SC.weather_ability_suppressed(e, foe, source))
        e.start_of_turn(foe, initiative_count=10)
        e.end_of_turn(foe)
        self.assertEqual((foe.hp, foe.temp_hp), (paid_hp + tick, tick))
        grant = foe.custom_conditions[TEMP.STATE]['grant_events'][-1]
        self.assertEqual(grant['provenance'], {'source': WEATHER.DESERT, 'event': 'owner_turn_end',
                                              'turn_serial': foe.custom_conditions['combat_turn_serial']})
        self.assertEqual(e.weather, 'rain')
        self.assertEqual(FREQ.state(trainer)['activations'][SC.GUIDE]['used'], 1)
        self.valid(e)


if __name__ == '__main__':
    unittest.main()
