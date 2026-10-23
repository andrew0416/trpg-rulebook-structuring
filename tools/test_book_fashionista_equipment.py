"""Fashionista equipment Features: Dashing Makeover, Accessorize and Style is Eternal on the existing item owners.

Reuse acquisition fixture helpers without inheriting or collecting its tests.
"""
from copy import deepcopy
import unittest

import test_book_fashionista_acquisition as fixture
from engine import Rules
import action_points as AP
import equipment_protection as PROTECTION
import fashionista as FA
import frequency as FREQ
import held_equipment as HELD
import items as I


class FashionistaEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    # Only fixture methods are borrowed: no inherited test methods or load_tests.
    setUp = fixture.FashionistaAcquisitionTests.setUp
    setup = fixture.FashionistaAcquisitionTests.setup
    add = fixture.FashionistaAcquisitionTests.add
    acquire = fixture.FashionistaAcquisitionTests.acquire
    whole = fixture.FashionistaAcquisitionTests.whole
    rejected = fixture.FashionistaAcquisitionTests.rejected
    valid = fixture.FashionistaAcquisitionTests.valid
    restore = fixture.FashionistaAcquisitionTests.restore
    skills = fixture.FashionistaAcquisitionTests.skills
    item = fixture.FashionistaAcquisitionTests.item
    hold = fixture.FashionistaAcquisitionTests.hold
    wear = fixture.FashionistaAcquisitionTests.wear
    combat = fixture.FashionistaAcquisitionTests.combat
    next_turn = fixture.FashionistaAcquisitionTests.next_turn
    use = fixture.FashionistaAcquisitionTests.use
    craft = fixture.FashionistaAcquisitionTests.craft
    incense = fixture.FashionistaAcquisitionTests.incense

    def makeover(self, target, item_id='item/겨울망토', recipe='fashionista/practical-winter-cloak', **options):
        values = dict(recipe_id=recipe, seconds=600, reason='actual completed Dashing Makeover')
        values.update(options)
        return FA.makeover(self.e, self.t, target, item_id, **values)

    def steal(self, *, face=10):
        return self.use(self.q, self.p, 'move/도둑질', face=face)

    def disarm(self):
        return self.e.disarm(self.q, self.p, attacker_skill='전투', defender_skill='은신', fixed_accuracy=20,
            challenger_options={'fixed':[6, 6, 6]}, defender_options={'fixed':[1, 1, 1]})

    # ---------------------------------------------------------------- Dashing Makeover
    def test_dashing_makeover_binds_two_ap_for_a_craftable_item_the_target_could_wear_without_a_slot(self):
        self.whole()
        ap = AP.available(self.t)
        self.rejected(lambda:self.makeover(self.p, 'item/불꽃깁스', 'fashionista/practical-winter-cloak'), 'currently craft')
        self.rejected(lambda:self.makeover(self.p, 'item/불꽃깁스', 'fashionista/unknown'), 'printed Fashionista recipe')
        self.rejected(lambda:self.makeover(self.t, 'item/무사태평향로', 'fashionista/incense-lax'), 'could not normally equip')
        self.rejected(lambda:self.makeover(self.p, seconds=0), 'seconds')
        self.t.spec['ap_spent'] = AP.maximum(self.t) - 1
        self.rejected(lambda:self.makeover(self.p), 'two available AP')
        self.t.spec['ap_spent'] = 0
        record = self.makeover(self.p)
        self.assertEqual((record['item_id'], record['ap'], record['effects'], AP.available(self.t)), ('item/겨울망토', 2, 1, ap - 2))
        self.assertIn('싸라기눈', self.p.weather_immune)
        self.assertEqual(HELD.entries(self.p), [])                 # no held slot is used
        self.assertEqual(I.equipment_options(self.p), [])          # nothing physical to steal or drop
        self.assertEqual(self.t.spec['ap_bound'], {record['source_id']:2})
        self.assertEqual(self.t._action_history, ['extended'])
        self.rejected(lambda:self.makeover(self.p, 'item/고고고글', 'fashionista/practical-go-goggles'), 'only one Dashing Makeover')
        self.rejected(lambda:self.makeover(self.p), 'only one Dashing Makeover')
        # A second target of the same Trainer and the Trainer themself are independent targets.
        self.makeover(self.t, 'item/고고고글', 'fashionista/practical-go-goggles')
        self.assertIn('모래바람', self.t.weather_immune)
        self.assertEqual(AP.available(self.t), ap - 4)
        self.valid()
        self.restore()
        self.valid()
        self.assertIn('싸라기눈', self.p.weather_immune)
        self.assertEqual(AP.available(self.t), ap - 4)
        # A target already wearing the item keeps the physical item's own registration instead.
        self.hold(self.q, 'cloak:q', 'item/겨울망토')
        self.rejected(lambda:self.makeover(self.q), 'already benefits')
        # Inside an encounter the Extended action cannot start; ending is the owner's own-turn Free Action.
        self.combat(self.q)
        self.rejected(lambda:self.makeover(self.q, 'item/고고고글', 'fashionista/practical-go-goggles'), 'encounter')
        self.rejected(lambda:FA.end_makeover(self.e, self.t, self.p, event_id='end:1'), 'own-turn')
        self.next_turn(self.t)
        ended = FA.end_makeover(self.e, self.t, self.p, event_id='end:1')
        self.assertEqual((ended['cause'], ended['event_id']), ('released:end:1', 'end:1'))
        self.assertNotIn('싸라기눈', self.p.weather_immune)
        self.assertEqual(AP.available(self.t), ap - 2)
        self.assertIn('free', self.t._action_history)
        self.rejected(lambda:FA.end_makeover(self.e, self.t, self.p, event_id='end:2'), 'live Dashing Makeover')
        self.rejected(lambda:FA.end_makeover(self.e, self.t, self.t, event_id='end:1'), 'already used')
        self.rejected(lambda:FA.end_makeover(self.e, self.t, self.q, event_id='end:3'), 'live Dashing Makeover')
        self.e.end_encounter()
        self.valid()
        self.restore()
        self.valid()
        # A reservation without its live projection, or a projection without its reservation, is detected.
        self.t.spec['ap_bound']['fashionista-makeover:' + self.t.entity_id + ':' + self.q.entity_id] = 2
        self.assertFalse(self.e.validate_state()['valid'])

    # ---------------------------------------------------------------- Accessorize
    def test_accessorize_admits_a_second_distinct_accessory_that_shares_no_effect(self):
        self.acquire()
        self.acquire(FA.MAKEOVER)
        self.wear(self.t, 'brace:fire', 'item/불꽃깁스')
        self.assertEqual(self.t._item_reg['item/불꽃깁스']['slots'], ['장신구'])
        self.assertEqual(self.wear(self.t, 'brace:ice', 'item/얼음깁스'), 0)      # one accessory slot without Accessorize
        self.assertEqual(len(FA._accessory_registrations(self.t)), 1)
        self.acquire(FA.ACCESSORIZE)
        self.assertEqual(self.wear(self.t, 'brace:fire2', 'item/불꽃깁스'), 0)    # same type of item
        self.assertEqual(self.wear(self.t, 'brace:ice2', 'item/얼음깁스'), 1)
        self.assertEqual([row['item_id'] for _, row in FA._accessory_registrations(self.t)], ['item/불꽃깁스', 'item/얼음깁스'])
        self.assertEqual(self.wear(self.t, 'claw:1', 'item/선제공격손톱'), 0)     # the printed pair is exactly two
        fire = dict(self.e.r.move('move/화염방사'))
        ice = dict(self.e.r.move('move/냉동빔'))
        self.assertEqual((I.item_damage_reduction(self.t, fire, engine=self.e), I.item_damage_reduction(self.t, ice, engine=self.e)), (15, 15))
        self.assertTrue(FA.shares_effects(self.e, 'item/불꽃깁스', 'item/불꽃깁스'))
        self.assertFalse(FA.shares_effects(self.e, 'item/불꽃깁스', 'item/얼음깁스'))
        self.valid()
        self.restore()
        self.valid()
        self.assertEqual(I.item_damage_reduction(self.t, ice, engine=self.e), 15)
        I.unregister_item(self.e, self.t, registration_key='item/불꽃깁스')
        self.assertEqual(self.wear(self.t, 'claw:2', 'item/선제공격손톱'), 1)
        self.assertEqual([row['item_id'] for _, row in FA._accessory_registrations(self.t)], ['item/얼음깁스', 'item/선제공격손톱'])
        self.assertEqual(self.t.initiative_bonus, 10)
        self.valid()
        # Two worn accessories require the live Feature; a tampered extra registration is detected.
        self.t._item_reg['item/선제공격손톱']['slots'] = ['장신구']
        self.wear(self.t, 'brace:fire3', 'item/불꽃깁스')
        self.t._item_reg['item/불꽃깁스'] = dict(self.t._item_reg['item/얼음깁스'], item_id='item/불꽃깁스', name='item/불꽃깁스')
        self.assertFalse(self.e.validate_state()['valid'])

    # ---------------------------------------------------------------- Style is Eternal
    def test_style_is_eternal_keeps_the_held_item_against_actual_theft_once_per_scene_per_pokemon_for_one_ap(self):
        self.acquire()
        self.rejected(lambda:FA.arm_style(self.e, self.t, self.p), 'Fashionista Feature required')
        self.acquire(FA.STYLE)
        self.rejected(lambda:FA.arm_style(self.e, self.t, self.q), 'owned Pokemon')
        self.hold(self.p, 'claw:p', 'item/선제공격손톱')
        self.combat(self.q)
        self.steal()
        self.assertEqual((HELD.entries(self.p), HELD.entries(self.q)[0]['instance_id']), ([], 'claw:p'))   # unarmed: stolen
        self.setup()
        self.acquire()
        self.acquire(FA.STYLE)
        self.hold(self.p, 'claw:p', 'item/선제공격손톱')
        FA.arm_style(self.e, self.t, self.p)
        self.assertEqual(FA.armed(self.p)['trainer_id'], self.t.entity_id)
        self.rejected(lambda:FA.disarm_style(self.e, self.t, self.q), 'armed Style')
        self.combat(self.q)
        ap = AP.available(self.t)
        self.steal()
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'claw:p')
        self.assertEqual(HELD.entries(self.q), [])
        self.assertEqual((AP.available(self.t), self.t._action_history), (ap - 1, ['free']))
        self.assertIsNone(FA.armed(self.p))
        receipt = self.t.spec['fashionista_style_history'][-1]
        self.assertEqual((receipt['pokemon_id'], receipt['operation'], receipt['source']), (self.p.entity_id, 'transfer', 'move/도둑질'))
        self.assertFalse(FREQ.activation_allowed(self.t, FA.STYLE + ':' + self.p.entity_id, {'kind':'scene', 'uses':1}))
        self.valid()
        # Once per Scene per Pokemon: arming again in the same Scene cannot answer a second theft.
        FA.arm_style(self.e, self.t, self.p)
        self.assertIsNone(FA.style_ready(self.e, self.p))
        self.next_turn(self.q)
        self.steal()
        self.assertEqual((HELD.entries(self.p), HELD.entries(self.q)[0]['instance_id']), ([], 'claw:p'))
        self.assertEqual(AP.available(self.t), ap - 1)
        self.e.end_scene()
        I.transfer_equipment(self.e, self.q, self.p, 'claw:p', consent_by=(self.q,))
        FA.arm_style(self.e, self.t, self.p)
        self.restore()
        self.valid()
        self.assertEqual(FA.armed(self.p)['trainer_id'], self.t.entity_id)
        # Without an available AP the armed Feature cannot answer.
        self.t.spec['ap_spent'] = AP.maximum(self.t)
        self.combat(self.q)
        self.assertIsNone(FA.style_ready(self.e, self.p))
        self.steal()
        self.assertEqual(HELD.entries(self.q)[0]['instance_id'], 'claw:p')
        self.assertIsNotNone(FA.armed(self.p))   # the arming stays until it is used or cancelled
        self.e.end_encounter()
        FA.disarm_style(self.e, self.t, self.p)
        self.assertIsNone(FA.armed(self.p))
        self.valid()

    def test_style_is_eternal_answers_disarm_knock_off_and_switcheroo_but_never_a_voluntary_drop(self):
        self.acquire()
        self.acquire(FA.STYLE)
        self.hold(self.p, 'claw:p', 'item/선제공격손톱')
        self.hold(self.q, 'band:q', 'item/기합의머리띠')
        self.p.pos, self.q.pos = (2, 2), (3, 2)
        # Disarm: the maneuver is actually attempted and won, and the armed Feature keeps the item.
        FA.arm_style(self.e, self.t, self.p)
        self.combat(self.q)
        ap = AP.available(self.t)
        self.assertTrue(self.disarm())
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'claw:p')
        self.assertEqual((AP.available(self.t), self.t.spec['fashionista_style_history'][-1]['operation']), (ap - 1, 'disarm'))
        self.assertFalse(getattr(self.e, 'ground_items', []))
        self.e.end_scene()                                   # spent AP returns at the Scene end
        # Switcheroo (exchange): the Trainer answers and neither holder changes.
        FA.arm_style(self.e, self.t, self.p)
        self.combat(self.q)
        ap = AP.available(self.t)
        self.use(self.q, self.p, 'move/바꿔치기')
        self.assertEqual((HELD.entries(self.p)[0]['instance_id'], HELD.entries(self.q)[0]['instance_id']), ('claw:p', 'band:q'))
        self.assertEqual((AP.available(self.t), self.t.spec['fashionista_style_history'][-1]['operation']), (ap - 1, 'exchange'))
        self.e.end_scene()
        # Knock Off (enemy drop effect) is answered; the holder's own voluntary drop is not a trigger.
        FA.arm_style(self.e, self.t, self.p)
        self.combat(self.q)
        ap = AP.available(self.t)
        self.use(self.q, self.p, 'move/탁쳐서떨구기')
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'claw:p')
        self.assertEqual((AP.available(self.t), self.t.spec['fashionista_style_history'][-1]['operation']), (ap - 1, 'effect_drop'))
        self.e.end_scene()
        FA.arm_style(self.e, self.t, self.p)
        self.combat(self.p)
        ap = AP.available(self.t)
        I.drop_item(self.e, self.p, consent_by=(self.p,))
        self.assertEqual(HELD.entries(self.p), [])
        self.assertEqual(AP.available(self.t), ap)
        self.assertIsNotNone(FA.armed(self.p))
        self.valid()
        self.restore()
        self.valid()
        self.assertEqual(len(self.t.spec['fashionista_style_history']), 3)
        # An unarmed Pokemon is disarmed normally.
        I.transfer_equipment(self.e, self.q, self.p, 'band:q', consent_by=(self.q,))
        self.e.end_encounter()
        FA.disarm_style(self.e, self.t, self.p)
        self.combat(self.q)
        self.assertTrue(self.disarm())
        self.assertEqual(HELD.entries(self.p), [])
        self.assertEqual(self.e.ground_items[-1]['instance_id'], 'band:q')
        self.valid()


if __name__ == '__main__':
    unittest.main()
