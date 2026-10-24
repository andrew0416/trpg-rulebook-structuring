"""Fashionista: Versatile Wardrobe (Chic storage, Swift swap, Choice-item suppression, Mega) and Dress to Impress.

Reuse acquisition fixture helpers without inheriting or collecting its tests.
"""
from copy import deepcopy
import unittest

import test_book_fashionista_acquisition as fixture
from engine import Rules, Combatant
from builder import build_pokemon
from native_scenario_fixture import prepare_body
import combat_timing as TIMING
import condition_instances as CONDITIONS
import fashionista as FA
import frequency as FREQ
import held_equipment as HELD
import items as I


class FashionistaWardrobeTests(unittest.TestCase):
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
    item = fixture.FashionistaAcquisitionTests.item
    hold = fixture.FashionistaAcquisitionTests.hold
    wear = fixture.FashionistaAcquisitionTests.wear
    combat = fixture.FashionistaAcquisitionTests.combat
    next_turn = fixture.FashionistaAcquisitionTests.next_turn
    use = fixture.FashionistaAcquisitionTests.use

    def chic(self, pokemon=None, **options):
        values = dict(seconds=600, reason='actual completed wardrobe fitting')
        values.update(options)
        return FA.make_chic(self.e, self.t, pokemon or self.p, **values)

    def store(self, uid, slot, pokemon=None):
        return FA.store(self.e, pokemon or self.p, uid, slot, reason='actual stored held item')

    def stocked(self):
        """A Chic model with a Quick Claw stored in slot 1 and a Choice Band stored in slot 2."""
        self.whole()
        self.chic()
        self.item('claw:1', 'item/선제공격손톱', self.p)
        self.item('band:1', 'item/구애머리띠', self.p)
        self.store('claw:1', 'wardrobe:1')
        self.store('band:1', 'wardrobe:2')

    def allowed(self, move):
        return CONDITIONS.move_allowed(self.e, self.p, self.e.r.move(move))[0]

    # ---------------------------------------------------------------- Versatile Wardrobe
    def test_versatile_wardrobe_makes_an_owned_pokemon_chic_for_two_tutor_points_as_an_extended_action(self):
        self.acquire()
        self.rejected(self.chic, 'Fashionista Feature required')
        self.whole()
        self.rejected(lambda:self.chic(self.q), 'owned Pokemon')
        self.rejected(lambda:self.chic(seconds=0), 'seconds')
        self.p.spec['tutor_points'] = 1
        self.rejected(self.chic, 'two actual Tutor Points')
        self.p.spec['tutor_points'] = 8
        self.combat(self.p)
        self.rejected(self.chic, 'encounter')
        self.e.end_encounter()
        elapsed = self.e.elapsed_seconds
        record = self.chic()
        self.assertEqual((record['point_cost'], self.p.spec['tutor_points'], self.e.elapsed_seconds), (2, 6, elapsed + 600))
        self.assertEqual(record['slots'], {'wardrobe:1':None, 'wardrobe:2':None})
        self.assertEqual(self.t._action_history, ['extended'])
        self.assertTrue(self.t.spec['state_grants']['sources']['feature:' + self.t.entity_id + ':' + FA.WARDROBE].get('irreversible_trainer_feature'))
        self.rejected(self.chic, 'already Chic')
        self.restore()
        self.valid()
        self.assertEqual(FA.chic(self.p)['owner_id'], self.t.entity_id)
        self.p.spec[FA.CHIC]['slots']['wardrobe:3'] = None
        self.assertFalse(self.e.validate_state()['valid'])

    def test_chic_storage_holds_two_held_items_without_effect_and_refuses_same_type_or_repeated_effects(self):
        self.whole()
        self.item('claw:1', 'item/선제공격손톱', self.p)
        self.rejected(lambda:self.store('claw:1', 'wardrobe:1'), 'Chic Pokemon required')
        self.chic()
        self.item('claw:2', 'item/선제공격손톱', self.p)
        self.item('claw:q', 'item/선제공격손톱', self.q)
        self.item('clothes:1', 'item/멋진-옷', self.p)
        self.rejected(lambda:self.store('claw:1', 'wardrobe:3'), 'printed Chic wardrobe slot')
        self.rejected(lambda:self.store('claw:q', 'wardrobe:1'), 'actually possess')
        self.rejected(lambda:self.store('clothes:1', 'wardrobe:1'), 'Held Items only')
        self.store('claw:1', 'wardrobe:1')
        self.assertEqual((self.p.initiative_bonus, HELD.entries(self.p), I.equipment_options(self.p)), (0, [], []))   # no effect, not equipped
        self.assertEqual(self.e._physical_objects['claw:1'][FA.WARDROBE_HOLDER], self.p.entity_id)
        self.rejected(lambda:self.store('claw:2', 'wardrobe:2'), 'same type')
        self.rejected(lambda:self.store('claw:1', 'wardrobe:2'), 'already stored')
        self.item('band:1', 'item/구애머리띠', self.p)
        self.store('band:1', 'wardrobe:2')
        self.assertEqual(self.p.conditions, set())   # a stored Choice item suppresses nothing
        self.rejected(lambda:self.store('claw:2', 'wardrobe:1'), 'occupied')
        self.valid()
        self.restore()
        self.valid()
        FA.release(self.e, self.p, 'wardrobe:2', reason='actual removal from the wardrobe')
        self.assertNotIn(FA.WARDROBE_HOLDER, self.e._physical_objects['band:1'])
        # The active held item can be moved into storage outside combat; it stops being equipped.
        self.hold(self.p, 'scope:1', 'item/달인의띠')
        self.assertEqual(HELD.entries(self.p)[0]['instance_id'], 'scope:1')
        self.store('scope:1', 'wardrobe:2')
        self.assertEqual((HELD.entries(self.p), self.p.spec[FA.CHIC]['slots']['wardrobe:2']['item_id']), ([], 'item/달인의띠'))
        self.combat(self.p)
        self.rejected(lambda:FA.release(self.e, self.p, 'wardrobe:2', reason='x'), 'encounter')
        self.rejected(lambda:self.store('claw:2', 'wardrobe:1'), 'encounter')
        self.valid()
        self.restore()
        self.valid()
        self.e._physical_objects['scope:1'].pop(FA.WARDROBE_HOLDER)
        self.assertFalse(self.e.validate_state()['valid'])

    def test_chic_swift_swap_exchanges_the_active_item_and_a_choice_item_suppresses_for_the_rest_of_combat(self):
        self.stocked()
        self.rejected(lambda:FA.swap(self.e, self.p, 'wardrobe:1'), 'own turn')
        self.combat(self.t)
        self.rejected(lambda:FA.swap(self.e, self.p, 'wardrobe:1'), 'own turn')
        self.next_turn(self.p)
        swift = self.p.budget['swift']
        result = FA.swap(self.e, self.p, 'wardrobe:1')
        self.assertEqual((result['in'], result['out'], self.p.budget['swift']), ('claw:1', None, swift - 1))
        self.assertEqual((HELD.entries(self.p)[0]['instance_id'], self.p.initiative_bonus), ('claw:1', 10))
        self.assertIsNone(self.p.spec[FA.CHIC]['slots']['wardrobe:1'])
        self.assertEqual(self.p.conditions, set())
        self.valid()
        # The existing action economy lets the unused Standard fund a second Swift; a third swap has no action left.
        self.next_turn(self.p)
        FA.swap(self.e, self.p, 'wardrobe:1')
        self.assertEqual(self.p.initiative_bonus, 0)
        FA.swap(self.e, self.p, 'wardrobe:1')
        self.assertEqual((self.p.initiative_bonus, self.p.budget['swift'], self.p.budget['standard']), (10, 0, 0))
        self.rejected(lambda:FA.swap(self.e, self.p, 'wardrobe:2'), 'Swift action unavailable')
        self.next_turn(self.p)
        result = FA.swap(self.e, self.p, 'wardrobe:2')
        self.assertEqual((result['in'], result['out']), ('band:1', 'claw:1'))
        self.assertEqual((HELD.entries(self.p)[0]['instance_id'], self.p.initiative_bonus, self.p.stages['atk']), ('band:1', 0, 2))
        self.assertEqual(self.p.spec[FA.CHIC]['slots']['wardrobe:2']['instance_id'], 'claw:1')
        self.assertIn('억압', self.p.conditions)
        self.assertEqual(self.p.spec[FA.CHIC]['suppression']['instance_id'], 'band:1')
        self.assertTrue(self.allowed('move/전광석화'))          # At-Will Moves remain usable
        self.assertFalse(self.allowed('move/10만볼트'))         # EOT-frequency Move is suppressed
        self.assertFalse(self.e.cure_status(self.p, '억압'))     # cannot be cured before the encounter ends
        self.assertIn('억압', self.p.conditions)
        self.assertEqual(self.e.gm_prompts, [])                 # the Choice condition was resolved by the actual swap, not a prompt
        self.valid()
        self.restore()
        self.valid()
        self.next_turn(self.p)
        result = FA.swap(self.e, self.p, 'wardrobe:2')
        self.assertEqual((result['in'], result['out']), ('claw:1', 'band:1'))
        self.assertEqual((HELD.entries(self.p)[0]['instance_id'], self.p.stages['atk'], self.p.initiative_bonus), ('claw:1', 0, 10))
        self.assertIn('억압', self.p.conditions)                 # the suppression outlives the Choice item
        self.assertFalse(self.allowed('move/10만볼트'))
        self.assertEqual(len(self.p.spec[FA.CHIC]['swaps']), 5)
        self.valid()
        self.e.end_encounter()
        self.assertNotIn('억압', self.p.conditions)
        self.assertIsNone(self.p.spec[FA.CHIC]['suppression'])
        self.assertTrue(self.allowed('move/10만볼트'))
        self.valid()
        self.restore()
        self.valid()
        self.p.spec[FA.CHIC]['suppression'] = {'item_id':'item/구애머리띠', 'instance_id':'band:1', 'round':1, 'at':0, 'source':FA.WARDROBE, 'clause_id':FA.clause(FA.WARDROBE)}
        self.assertFalse(self.e.validate_state()['valid'])

    def test_mega_evolved_chic_pokemon_keeps_its_form_when_the_stone_is_swapped_into_the_wardrobe(self):
        self.whole()
        self.c = Combatant(self.rules, build_pokemon(self.rules, '리자몽', 40, moves=['몸통박치기'], abilities=[],
            extra={'trainer_id':self.t.entity_id, 'tutor_points':8, 'size':'중형'}, pos=(2, 4)))
        self.e.gm.add_combatant(self.c, pos=(2, 4), side='party', reason='actual owned Charizard')
        prepare_body(self.e, self.c, size='중형', offsets=[(0, 0)], reason='observed complete body')
        self.wear(self.t, 'ring', 'item/메가링')
        self.hold(self.c, 'stone', 'item/리자몽나이트x')
        self.chic(self.c)
        self.item('claw:1', 'item/선제공격손톱', self.c)
        self.store('claw:1', 'wardrobe:1', self.c)
        self.combat(self.t)
        form = self.e.mega_evolve(self.t, self.c, 'mega/리자몽-x', ring='ring', stone='stone')
        self.assertEqual((self.c.form, form['stone_instance']), ('mega/리자몽-x', 'stone'))
        self.assertEqual(PROTECTION_status(self.e, self.c)['status'], 'blocked')   # the active Stone stays locked for removal effects
        self.next_turn(self.c)
        result = FA.swap(self.e, self.c, 'wardrobe:1')
        self.assertEqual((result['in'], result['out']), ('claw:1', 'stone'))
        self.assertEqual((self.c.form, HELD.entries(self.c)[0]['instance_id'], self.c.initiative_bonus), ('mega/리자몽-x', 'claw:1', 10))
        self.assertIn('단단한발톱', self.c.abilities)
        self.assertEqual(self.e._physical_objects['stone'][FA.WARDROBE_HOLDER], self.c.entity_id)
        self.valid()
        self.restore()
        self.valid()
        self.assertEqual(self.c.form, 'mega/리자몽-x')
        self.next_turn(self.c)
        FA.swap(self.e, self.c, 'wardrobe:1')
        self.assertEqual(HELD.entries(self.c)[0]['instance_id'], 'stone')
        self.valid()
        self.e.end_scene()
        self.assertFalse(self.c.form)
        self.valid()
        # The wardrobe waiver belongs to an actual Chic Pokemon only.
        self.hold(self.p, 'claw:p', 'item/선제공격손톱')
        self.rejected(lambda:I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'], wardrobe=True), 'Chic Pokemon')

    # ---------------------------------------------------------------- Dress to Impress
    def test_dress_to_impress_projects_every_stored_item_for_one_round_twice_per_scene_once_per_pokemon(self):
        self.stocked()
        self.v = self.add('second model', 'pokemon', (2, 5), trainer_id=self.t.entity_id, tutor_points=8,
            species='피카츄', types=['전기'], moves=['move/전광석화'], speed=22)
        self.e.gm.observe_loyalty(self.v, 6, reason='actual willing Pokemon')
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.p), 'active encounter')
        self.combat(self.p, count=25)
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.p), 'between turns')
        self.next_turn(self.t, count=20)
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.q), 'owned Pokemon')
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.v), 'Chic Pokemon')
        record = FA.dress_to_impress(self.e, self.t, self.p)
        self.assertEqual([row['item_id'] for row in record['items']], ['item/선제공격손톱', 'item/구애머리띠'])
        self.assertEqual((self.p.initiative_bonus, self.p.stages['atk'], self.p.conditions), (10, 0, set()))   # no swap: no suppression, no conditional boost
        self.assertEqual(self.e.gm_prompts, [])
        self.assertEqual((HELD.entries(self.p), I.equipment_options(self.p)), ([], []))
        self.assertTrue(self.t.took_standard)
        self.assertEqual(TIMING.records(self.p)[-1]['count_deadline'], (self.e.round_no + 1, 20))
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.p), 'already active')
        self.valid()
        self.restore()
        self.valid()
        self.assertEqual(self.p.initiative_bonus, 10)
        # Same count one round later: the projections end with their record.
        self.next_turn(self.t, count=20)
        self.assertEqual((self.p.initiative_bonus, getattr(self.p, '_item_reg', {})), (0, {}))
        self.assertIsNone(FA.dress_record(self.p))
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.p), 'once per Scene')
        self.e.end_encounter()
        self.chic(self.v)
        self.item('claw:v', 'item/선제공격손톱', self.v)
        self.store('claw:v', 'wardrobe:1', self.v)
        self.combat(self.t, count=20)
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.p), 'once per Scene')
        FA.dress_to_impress(self.e, self.t, self.v)
        self.assertEqual(self.v.initiative_bonus, 10)
        self.e.end_scene()
        self.combat(self.t, count=20)
        FA.dress_to_impress(self.e, self.t, self.p)
        self.next_turn(self.t, count=20)
        FA.dress_to_impress(self.e, self.t, self.v)
        self.next_turn(self.t, count=20)
        self.rejected(lambda:FA.dress_to_impress(self.e, self.t, self.p), 'Scene frequency exhausted')
        self.e.end_encounter()
        self.valid()
        self.restore()
        self.valid()
        self.assertEqual(self.p.initiative_bonus, 0)


def PROTECTION_status(engine, pokemon):
    import equipment_protection as PROTECTION
    row = I.equipment_options(pokemon, ('held',))[0]
    return PROTECTION.status(engine, pokemon, row, 'transfer')


if __name__ == '__main__':
    unittest.main()
