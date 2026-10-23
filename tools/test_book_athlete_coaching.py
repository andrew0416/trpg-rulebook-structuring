"""Athlete Coaching: armed 1 AP triggered Free Action answered at the Pokemon's actual combat maneuver attempt.

Reuses the acquisition scene helpers without inheriting any test method.
"""
from unittest.mock import patch
import unittest

import test_book_athlete_acquisition as fixture
from engine import Rules, Engine
from grid import cheb
import action_points as AP
import athlete as AT
import movement_actions as MOVE
import passive_events as PASSIVE
import turn as TURN

MELEE = 'maneuver/근접-가로채기'


class AthleteCoachingTests(fixture.AthleteScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    def ready(self):
        self.whole()
        self.combat(self.p, count=25)
        return AP.available(self.t)

    def push(self, *, face=20, faces=4, defender=(2, 2, 2, 2), skill='육상'):
        return self.e.push(self.p, self.q, challenger_skill=skill, defender_skill='전투', fixed_accuracy=face,
            challenger_options={'fixed':[3] * faces}, defender_options={'fixed':list(defender)})

    def receipt(self, index=-1):
        return self.t.spec[AT.COACHING_HISTORY][index]

    def again(self):
        """A fresh Standard action for the Pokemon and the pushed foe back in reach."""
        TURN.reset_budget(self.e, self.p)
        self.q.pos = (3, 2)

    def attempt(self):
        row = next(row for row in self.e._move_completions.values() if row['actor'] is self.q)
        return row['defense'][self.t.entity_id]['attempts'][0]

    # ---------------------------------------------------------------- arming
    def test_arming_needs_the_feature_an_owned_pokemon_a_branch_and_a_printed_skill_only_for_opposed(self):
        self.acquire()
        self.acquire(AT.REGIME)
        self.rejected(lambda:self.arm('sprint'), 'actual acquired Athlete Feature')
        self.acquire(AT.COACHING)
        self.rejected(lambda:self.arm('sprint', pokemon=self.q), 'owned Pokemon')
        self.rejected(lambda:self.arm('sprint', pokemon=self.t), 'owned Pokemon')
        self.rejected(lambda:self.arm('cheer'), 'opposed, sprint, opportunity or intercept')
        self.rejected(lambda:self.arm('opposed'), 'Acrobatics, Athletics, Combat or Stealth')
        self.rejected(lambda:self.arm('opposed', '집중'), 'Acrobatics, Athletics, Combat or Stealth')
        self.rejected(lambda:self.arm('sprint', '육상'), 'only the opposed')
        row = self.arm('opposed', 'Athletics')
        self.assertEqual((row['branch'], row['skill'], row['trainer_id']), ('opposed', '육상', self.t.entity_id))
        self.assertEqual(AT.armed(self.p), row)
        row = self.arm('intercept')
        self.assertEqual((row['branch'], row['skill']), ('intercept', None))
        self.restore()
        self.valid()
        self.assertEqual(AT.armed(self.p)['branch'], 'intercept')
        self.rejected(lambda:AT.disarm_coaching(self.e, self.t, self.q), 'actual armed Coaching')
        AT.disarm_coaching(self.e, self.t, self.p)
        self.assertIsNone(AT.armed(self.p))
        # An arming without its Athlete owner is detected.
        self.q.spec[AT.COACHING_ARMED] = dict(row, trainer_id=self.t.entity_id)
        self.invalid()

    # ---------------------------------------------------------------- opposed check bonus die
    def test_opposed_maneuver_pays_one_ap_free_action_once_per_pokemon_scene_and_adds_one_bonus_die(self):
        ap = self.ready()
        self.arm('opposed', '육상')
        with patch.object(self.e, 'skill_roll', wraps=self.e.skill_roll) as rolls:
            self.assertTrue(self.push(faces=5))
        self.assertEqual(rolls.call_args_list[0].args[1], '육상')
        self.assertEqual(len(rolls.call_args_list[0].kwargs['fixed']), 5)
        self.assertEqual((AP.available(self.t), self.t._action_history), (ap - 1, ['free']))
        self.assertIsNone(AT.armed(self.p))
        self.assertEqual((self.receipt()['branch'], self.receipt()['skill'], self.receipt()['facts']), ('opposed', '육상', {'source':'maneuver/밀기', 'skill':'육상'}))
        self.assertEqual(self.activations(self.t)[AT.COACHING + ':' + self.p.entity_id]['used'], 1)
        self.assertNotIn(AT.COACHING_PENDING, self.p.custom_conditions)
        self.assertNotIn(AT.COACHING_ACTIVE, self.p.custom_conditions)
        self.assertTrue(any('Coaching bonus die' in line for line in self.e.log_lines))
        self.valid()
        # Once per Pokemon per Scene: a second arming in the same Scene is not ready, so the maneuver runs uncoached and unpaid.
        self.arm('opposed', '육상')
        self.again()
        self.assertIsNone(AT.coaching_ready(self.e, self.p, 'opposed'))
        self.assertTrue(self.push(faces=4))
        self.assertEqual((AP.available(self.t), len(self.t.spec[AT.COACHING_HISTORY])), (ap - 1, 1))
        self.assertIsNotNone(AT.armed(self.p))
        self.e.end_scene()
        self.combat(self.p, count=25)
        self.q.pos = (3, 2)
        ap = AP.available(self.t)   # the Scene boundary refreshed the Trainer's AP
        self.assertIs(AT.coaching_ready(self.e, self.p, 'opposed'), self.t)
        self.assertTrue(self.push(faces=5))
        self.assertEqual((AP.available(self.t), len(self.t.spec[AT.COACHING_HISTORY])), (ap - 1, 2))
        self.restore()
        self.valid()

    def test_skill_mismatch_missing_ap_or_wrong_branch_leaves_the_maneuver_uncoached_and_the_arming_in_place(self):
        ap = self.ready()
        self.arm('opposed', '전투')
        self.assertTrue(self.push(faces=4, skill='육상'))
        self.assertEqual((AP.available(self.t), AT.armed(self.p)['skill']), (ap, '전투'))
        self.assertNotIn(AT.COACHING_HISTORY, self.t.spec)
        self.again()
        self.arm('sprint')
        self.assertTrue(self.push(faces=4))
        self.assertEqual((AP.available(self.t), AT.armed(self.p)['branch']), (ap, 'sprint'))
        self.again()
        self.arm('opposed', '육상')
        AP.charge(self.t, ap)
        self.assertIsNone(AT.coaching_ready(self.e, self.p, 'opposed'))
        self.assertTrue(self.push(faces=4))
        self.assertEqual((AP.available(self.t), AT.armed(self.p)['branch']), (0, 'opposed'))
        # The arming never applies to a plain skill check or to the Trainer's own maneuver.
        self.e.skill_check(self.p, '육상', 5, fixed=[3, 3, 3, 3])
        self.valid()

    def test_accuracy_miss_after_the_paid_attempt_keeps_the_coaching_cost_and_clears_the_markers(self):
        ap = self.ready()
        self.arm('opposed', '육상')
        with patch.object(self.e, 'opposed_check', wraps=self.e.opposed_check) as opposed:
            self.assertFalse(self.push(faces=5, face=1))
            self.assertEqual(opposed.call_count, 0)
        self.assertEqual((AP.available(self.t), self.p.budget['standard']), (ap - 1, 0))
        self.assertNotIn(AT.COACHING_PENDING, self.p.custom_conditions)
        self.assertNotIn(AT.COACHING_ACTIVE, self.p.custom_conditions)
        self.assertEqual(self.receipt()['facts']['source'], 'maneuver/밀기')
        self.valid()

    # ---------------------------------------------------------------- Sprint
    def test_sprint_coaching_doubles_the_actual_sprint_movement_instead_of_half(self):
        ap = self.ready()
        self.assertEqual(MOVE.distance_budget(self.e, self.p, 'land'), 6)
        self.assertTrue(self.e.sprint(self.p, source_policy='ch06_once'))
        self.assertEqual((MOVE.distance_budget(self.e, self.p, 'land'), AP.available(self.t)), (9, ap))
        self.next_turn(self.p, count=25)
        self.arm('sprint')
        self.assertTrue(self.e.sprint(self.p, source_policy='ch06_once'))
        self.assertEqual((MOVE.distance_budget(self.e, self.p, 'land'), AP.available(self.t)), (12, ap - 1))
        self.assertEqual(self.p.custom_conditions['질주']['coaching']['trainer_id'], self.t.entity_id)
        self.assertEqual((self.receipt()['branch'], self.receipt()['facts']['source_policy']), ('sprint', 'ch06_once'))
        self.assertIsNone(AT.armed(self.p))
        self.restore()
        self.valid()
        self.assertEqual(MOVE.distance_budget(self.e, self.p, 'land'), 12)
        self.u = self.add('far marker', 'trainer', (13, 2), classes=[], feats=[], speed=5)
        self.e.approach(self.p, self.u, movement_mode='land')
        self.assertEqual((self.p.pos[0], cheb(self.p.pos, self.u.pos)), (12, 1))   # eleven metres: beyond the ordinary nine
        self.assertNotIn('질주', self.p.custom_conditions)
        self.valid()

    # ---------------------------------------------------------------- Attack of Opportunity
    def test_opportunity_coaching_makes_the_actual_attack_of_opportunity_hit_automatically(self):
        self.whole()
        self.u = self.add('far marker', 'trainer', (12, 2), classes=[], feats=[], side='foe', speed=5)
        self.combat(self.q, count=15)
        ap = AP.available(self.t)
        hp = self.q.hp
        with patch.object(Engine, 'd20', return_value=1):
            self.e.approach(self.q, self.u, movement_mode='land')
        self.assertTrue(self.p.aoo_used)
        self.assertEqual((self.q.hp, AP.available(self.t)), (hp, ap))
        self.setup()
        self.whole()
        self.u = self.add('far marker', 'trainer', (12, 2), classes=[], feats=[], side='foe', speed=5)
        self.combat(self.q, count=15)
        self.arm('opportunity')
        with patch.object(Engine, 'd20', return_value=1):
            self.e.approach(self.q, self.u, movement_mode='land')
        self.assertTrue(self.p.aoo_used)
        self.assertLess(self.q.hp, hp)
        self.assertEqual((AP.available(self.t), self.t._action_history), (ap - 1, ['free']))
        self.assertEqual((self.receipt()['branch'], self.receipt()['facts']), ('opportunity', {'mover_id':self.q.entity_id}))
        self.assertIsNone(AT.armed(self.p))
        self.assertFalse(hasattr(self.e, '_athlete_aoo_scope'))
        self.restore()
        self.valid()

    # ---------------------------------------------------------------- Intercept
    def intercept_scene(self, *, loyalty):
        self.setup(loyalty=loyalty, positions={'t':(3, 2), 'q':(2, 2), 'p':(3, 5)})
        self.whole()
        self.e.watch_move_defense(self.t, [{'actor_id':self.p.entity_id, 'source':MELEE}], reason='actual owner declares the next native hit reaction')
        self.combat(self.q, count=15)
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.q, self.t, 'move/막치기', set_damage=True)
        return self.e._passive_pending

    def choose(self, event, faces=(1, 1, 1, 1)):
        options = {'path':[(3, 5), (3, 4), (3, 3), (3, 2)], 'skill':'육상', 'mode':'land', 'shove_destination':[4, 2], 'roll_options':{'fixed':list(faces)}}
        return self.e.choose_move_defense(event, self.p, use=True, options=options, reason='actual pending defense choice')

    def test_intercept_coaching_permits_a_low_loyalty_pokemon_and_succeeds_without_a_roll(self):
        event = self.intercept_scene(loyalty=2)
        self.rejected(lambda:self.choose(event), 'loyalty')
        ap = AP.available(self.t)
        hp = (self.t.hp, self.p.hp)
        self.arm('intercept')
        rng = self.e.rng.getstate()
        self.choose(event)
        self.assertEqual(self.e.rng.getstate(), rng)   # no skill roll was made for the coached check
        self.assertEqual((self.t.pos, self.p.pos), ((4, 2), (3, 2)))
        self.assertEqual(self.t.hp, hp[0])
        self.assertLess(self.p.hp, hp[1])
        self.assertEqual((AP.available(self.t), self.t._action_history), (ap - 1, ['free']))
        self.assertEqual(self.p._action_history, ['full'])
        attempt = self.attempt()
        self.assertEqual((attempt['outcome'], attempt['check_total'], attempt['dc'], attempt['coaching']['branch']), ('intercepted', 9, 9, 'intercept'))
        self.assertEqual(self.receipt()['facts'], {'source':MELEE, 'protected_id':self.t.entity_id})
        self.assertIsNone(AT.armed(self.p))
        self.valid()
        self.restore()
        self.valid()

    def test_uncoached_loyal_intercept_still_rolls_and_a_spent_scene_use_restores_the_loyalty_rule(self):
        event = self.intercept_scene(loyalty=6)
        ap = AP.available(self.t)
        self.choose(event, faces=(6, 6, 6, 6))
        self.assertEqual((self.p.pos, AP.available(self.t)), ((3, 2), ap))
        attempt = self.attempt()
        self.assertEqual((attempt['outcome'], attempt['check_total'], attempt['dc']), ('intercepted', 24, 9))
        self.assertNotIn('coaching', attempt)
        self.assertNotIn(AT.COACHING_HISTORY, self.t.spec)
        # After the Pokemon's Scene use is spent, an armed intercept Coaching is not ready and loyalty applies again.
        event = self.intercept_scene(loyalty=2)
        self.arm('intercept')
        self.e.gm.observe_loyalty(self.p, 2, reason='observed actual relationship')
        import frequency as FREQ
        FREQ.consume_activation(self.t, AT.COACHING + ':' + self.p.entity_id, AT.COACHING_QUOTA, engine=self.e)
        self.assertIsNone(AT.coaching_ready(self.e, self.p, 'intercept'))
        self.rejected(lambda:self.choose(event), 'loyalty')
        self.assertIsNotNone(AT.armed(self.p))


if __name__ == '__main__':
    unittest.main()
