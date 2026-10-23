"""Source-valid equipped weather readers and the CSV267 actual hit consumer."""
import unittest
import test_category2_class_actor_state_reactions as FIX
import class_actor_state_reactions as REACTIONS
import csv_item_physical_contracts as PHYSICAL
import items as ITEMS
import weather_state as WEATHER
import world_entities as WORLD


class WeatherBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.ClassActorStateReactionTests.setUpClass()

    def fixture(self):
        helper = FIX.ClassActorStateReactionTests()
        return (helper, *helper.fixture(feats=[REACTIONS.ENDURING_BLOOM]))

    def equip(self, engine, actor, item, instance):
        WORLD.register_object(engine, instance, location={'kind': 'unknown'},
                              reason='actual source-valid weather item', kind='item_instance',
                              item_rule_id=item, owner_id=actor.entity_id)
        return ITEMS.register_item(engine, actor, item, source_instance_id=instance, as_held=False)

    def test_umbrella_blocks_global_sunny_actual_enduring_bloom_second_choice(self):
        helper, engine, trainer, partner, enemy = self.fixture()
        self.equip(engine, partner, 'item/만능우산', 'main113/weather/umbrella')
        engine.gm.set_weather('sunny', rounds=None, reason='actual sunny battlefield')
        helper.start(engine, enemy)
        helper.hit(engine, enemy, partner, '화염방사')
        event = helper.pending_one(engine, trainer, REACTIONS.ENDURING_BLOOM)
        self.assertFalse(event['sunny'])
        with self.assertRaisesRegex(ValueError, 'one stat'):
            engine.resolve_class_actor_state_reaction(trainer, event['id'], use=True, stats=('def', 'spd'))
        engine.resolve_class_actor_state_reaction(trainer, event['id'], use=True, stats=('def',))
        self.assertEqual((partner.stages['def'], partner.stages['spd']), (1, 0))
        self.assertEqual(engine.weather, 'sunny')

    def test_umbrella_shared_weather_reader_suppresses_rain_sunny_only(self):
        helper, engine, trainer, partner, enemy = self.fixture()
        self.equip(engine, partner, 'item/만능우산', 'main113/weather/umbrella-reader')
        for actual in ('sunny', 'rain', 'sandstorm', 'hail'):
            with self.subTest(actual=actual):
                engine.gm.set_weather(actual, rounds=None, reason='source weather boundary')
                active = WEATHER.effective_state(engine, partner)['active']
                self.assertEqual(None if active is None else active['weather'],
                                 None if actual in ('sunny', 'rain') else actual)
                self.assertEqual(WEATHER.effective_state(engine, trainer)['active']['weather'], actual)
                self.assertEqual(engine.weather, actual)

    def test_trainer_booster_local_weather_is_canonical_and_preserves_global(self):
        helper, engine, trainer, partner, enemy = self.fixture()
        self.equip(engine, trainer, 'item/부스트에너지', 'main113/weather/booster')
        PHYSICAL.activate_booster(engine, trainer, '쾌청')
        local = WEATHER.effective_state(engine, trainer)['active']
        self.assertEqual(local['weather'], 'sunny')
        self.assertTrue(local['local_to_actor'])
        self.assertEqual(local['source_id'], 'item/부스트에너지')
        self.assertIsNone(WEATHER.effective_state(engine, partner)['active'])
        self.assertIsNone(engine.weather)

