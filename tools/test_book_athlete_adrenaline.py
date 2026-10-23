"""Athlete Adrenaline Rush: actual HP crossing trigger, triggered Free Action, trained-stat stages, two cures, a Tick of temporary HP,
three daily uses and once per Scene.

Reuses the acquisition scene helpers without inheriting any test method.
"""
import unittest

import test_book_athlete_acquisition as fixture
from engine import Rules
import action_points as AP
import athlete as AT
import frequency as FREQ


class AthleteAdrenalineTests(fixture.AthleteScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    def ready(self, *, exercise=True):
        self.whole()
        if exercise:
            self.exercise()
        return self.t.base_max_hp   # the printed maximum is the true maximum, before injury penalties

    def drop(self, value, loss, *, source='actual hazard'):
        self.e.gm.set_temp_hp(self.t, 0, reason='observed no temporary HP before the actual loss')
        self.e.gm.set_hp(self.t, value=value, reason='observed current HP')
        self.e.lose_hp(self.t, loss, source=source)

    def rush(self, *cure):
        return AT.adrenaline_rush(self.e, self.t, cure=list(cure))

    def test_trigger_is_recorded_only_on_an_actual_crossing_to_half_or_below_by_an_acquirer(self):
        self.acquire()
        self.drop(100, 50)
        self.assertIsNone(AT.adrenaline_trigger(self.t))
        maximum = self.ready()
        half = maximum // 2
        self.drop(half + 2, 1)
        self.assertIsNone(AT.adrenaline_trigger(self.t))
        self.drop(half + 1, 1)
        row = AT.adrenaline_trigger(self.t)
        self.assertEqual((row['before_hp'], row['hp'], row['max_hp'], row['round'], row['at']), (half + 1, half, maximum, self.e.round_no, self.e.elapsed_seconds))
        # Staying at or below half is not a new crossing; a foe's actual attack damage is a producer too.
        self.e.gm.set_hp(self.t, value=half, reason='observed current HP')
        self.e.lose_hp(self.t, 5, source='actual hazard')
        self.assertEqual(AT.adrenaline_trigger(self.t)['before_hp'], half + 1)
        self.t.spec.pop(AT.ADRENALINE_TRIGGER)
        self.e.gm.set_hp(self.t, value=half + 1, reason='observed current HP')
        self.combat(self.q, count=15)
        self.use(self.q, self.t, 'move/몸통박치기')
        self.assertLessEqual(self.t.hp * 2, maximum)
        self.assertEqual(AT.adrenaline_trigger(self.t)['before_hp'], half + 1)
        self.restore()
        self.valid()
        self.assertIsNotNone(AT.adrenaline_trigger(self.t))
        # The Pokemon's own crossing never records a Trainer trigger.
        self.e.lose_hp(self.p, self.p.max_hp - 1, source='actual hazard')
        self.assertNotIn(AT.ADRENALINE_TRIGGER, self.p.spec)

    def test_rush_adds_one_stage_per_trained_stat_cures_up_to_two_afflictions_and_grants_a_tick(self):
        maximum = self.ready()
        self.rejected(lambda:self.rush(), 'printed trigger')
        for status in ('화상', '마비', '혼란'):
            self.e.apply_status(self.t, status)
        self.drop(maximum // 2 + 1, 1)
        ap = AP.available(self.t)
        self.rejected(lambda:self.rush('화상', '마비', '혼란'), 'up to two')
        self.rejected(lambda:self.rush('화상', '화상'), 'up to two')
        self.rejected(lambda:self.rush('독'), 'up to two')
        self.rejected(lambda:self.rush('기절'), 'up to two')
        self.rejected(lambda:self.rush(''), 'cure choices')
        self.rejected(lambda:AT.adrenaline_rush(self.e, self.p), 'actual acquired Athlete')
        receipt = self.rush('화상', '마비')
        tick = self.e.tick(self.t)
        self.assertEqual((receipt['cured'], receipt['stats'], receipt['tick'], receipt['temp_gained']), (['화상', '마비'], ['atk', 'spe'], tick, tick))
        self.assertEqual((self.t.stages['atk'], self.t.stages['spe'], self.t.stages['def']), (2, 2, 0))
        self.assertEqual((self.t.temp_hp, self.t.conditions & {'화상', '마비', '혼란'}), (tick, {'혼란'}))
        self.assertEqual((AP.available(self.t), self.t._action_history[-1]), (ap, 'free'))
        self.assertIsNone(AT.adrenaline_trigger(self.t))
        self.assertEqual(self.activations(self.t)[AT.ADRENALINE]['used'], 1)
        self.assertEqual(self.activations(self.t)[AT.ADRENALINE + ':scene']['used'], 1)
        self.restore()
        self.valid()
        self.assertEqual(len(self.t.spec[AT.ADRENALINE_HISTORY]), 1)
        # Without trained stats only the cure and the non-stacking Tick apply.
        self.setup()
        self.ready(exercise=False)
        self.drop(maximum // 2 + 1, 1)
        receipt = self.rush()
        self.assertEqual((receipt['stats'], receipt['cured'], self.t.temp_hp), ([], [], self.e.tick(self.t)))
        self.assertEqual(self.t.stages, dict.fromkeys(self.t.stages, 0))

    def test_once_per_scene_three_per_day_and_the_trigger_lapses_with_the_round(self):
        maximum = self.ready()
        half = maximum // 2
        self.drop(half + 1, 1)
        self.rush()
        self.drop(half + 1, 1)
        self.rejected(lambda:self.rush(), 'already used this Scene')
        for use in (2, 3):
            self.e.end_scene()
            self.drop(half + 1, 1)
            self.assertEqual(self.rush()['id'], AT.ADRENALINE + ':' + self.t.entity_id + ':' + str(use))
        self.e.end_scene()
        self.drop(half + 1, 1)
        self.rejected(lambda:self.rush(), 'daily uses exhausted')
        FREQ.new_day(self.t)
        self.assertEqual(self.rush()['id'], AT.ADRENALINE + ':' + self.t.entity_id + ':4')
        self.e.end_scene()
        # The triggered Free Action answers the crossing when it happens: a later round is too late.
        self.e.gm.set_injuries(self.t, value=0, reason='observed recovered injuries before the actual fight')
        self.e.gm.set_temp_hp(self.t, 0, reason='observed expired temporary HP')
        self.e.gm.set_hp(self.t, value=half + 1, reason='observed current HP')
        self.combat(self.q, count=15)
        self.use(self.q, self.t, 'move/몸통박치기')
        self.assertIsNotNone(AT.adrenaline_trigger(self.t))
        self.next_turn(self.q, count=15)
        self.rejected(lambda:self.rush(), 'lapsed')
        self.restore()
        self.valid()
        self.assertEqual(len(self.t.spec[AT.ADRENALINE_HISTORY]), 4)
        # A trigger without its acquisition is detected.
        self.t.spec[AT.ADRENALINE_TRIGGER]['before_hp'] = 1
        self.invalid()


if __name__ == '__main__':
    unittest.main()
