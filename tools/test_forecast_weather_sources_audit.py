"""Separate source facts can describe the same active weather."""
import test_category2_ability_state_projection as _fixture_test_category2_ability_state_projection
from engine import Engine


class ForecastWeatherSourcesAuditTests(_fixture_test_category2_ability_state_projection.AbilityStateProjectionTests):
    def test_independent_same_weather_fact_survives_primary_end_and_round_trip(self):
        e = self.engine()
        c = self.actor(e, 'ability/기분파')
        e.gm.set_weather('sunny', reason='actual primary sunlight')
        e.activate_ability_state(c, 'ability/기분파', choice='불꽃', observation={
            'weather_effects': [
                {'weather': 'sunny', 'source': 'gm/primary', 'reason': 'primary sunlight'},
                {'weather': 'sunny', 'source': 'gm/local', 'reason': 'independent local sunlight'},
            ],
        }, reason='choose sunlight while both sources remain active')
        e.gm.set_weather(None, reason='only primary sunlight ends')
        self.assertEqual(c.types, ['불꽃'])
        e.gm.set_weather('sunny', reason='new primary matches independent local weather')
        e.gm.set_weather(None, reason='new primary ends while local sunlight remains')
        self.assertEqual(c.types, ['불꽃'])
        n = Engine.import_state(self.r, e.export_state())
        self.assertEqual(n.everyone[0].types, ['불꽃'])
