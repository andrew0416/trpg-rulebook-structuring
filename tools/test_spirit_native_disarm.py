"""F-29: Spirit of Justice is consumed by actual native Disarm checks."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_category2_blessing_skill_rules_ten as fixture
from grid import Grid
import items
import state_grants as grants


class SpiritNativeDisarmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.BlessingSkillRuleTests.setUpClass()

    def setUp(self):
        self.fixture = fixture.BlessingSkillRuleTests()
        self.fixture.setUp()
        self.e, self.a, self.b = self.fixture.e, self.fixture.a, self.fixture.b
        self.a.spec['size'] = self.b.spec['size'] = '중형'
        self.e.grid = Grid(5, 5)
        self.a.pos, self.b.pos = (1, 1), (2, 1)
        self.a.side, self.b.side = 'party', 'wild'
        self.e.everyone = self.e.gm.everyone = [self.a, self.b]
        self.b.item = '소형 방패'
        items.register_item(self.e, self.b)
        self.e.start_round([self.a, self.b])
        self.e.start_of_turn(self.a)

    def own(self, actor):
        self.fixture.own(fixture.B.SPIRIT_OF_JUSTICE, actor=actor)

    def disarm(self, **changes):
        options = dict(attacker_skill='전투', defender_skill='전투', fixed_accuracy=20,
                       challenger_options={'fixed': [3, 3, 3, 3]},
                       defender_options={'fixed': [3, 3, 3, 3]})
        options.update(changes)
        return self.e.disarm(self.a, self.b, **options)

    def observe(self, action, engine=None):
        observed = {}
        owner = type(self.e if engine is None else engine)
        original = owner.skill_roll

        def record(current, actor, skill, **options):
            result = original(current, actor, skill, **options)
            observed[actor.entity_id] = (result, deepcopy(options))
            return result

        with patch.object(owner, 'skill_roll', record):
            outcome = action()
        return outcome, observed

    def remote_ready(self):
        for actor in (self.a, self.b):
            actor.spec['skills']['집중'] = '숙련'
            grants.grant(actor, 'capabilities', 'Telekinetic', 'fixture:telekinetic', 'fixture')
        self.b.pos = (4, 1)
        self.b.spec['weight_kg'] = 10

    def remote(self, kind='disarm', **changes):
        options = dict(defender_skill='집중', fixed_accuracy=20,
                       challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [3] * 4})
        options.update(changes)
        return self.e.telekinetic_maneuver(self.a, self.b, kind, **options)

    def snapshot(self):
        return deepcopy((self.a.spec, self.b.spec, self.a.budget, getattr(self.b, 'budget', None),
                         self.a.custom_conditions, self.b.custom_conditions,
                         self.b._item_reg, self.b.evasion_mod,
                         getattr(self.e, 'ground_items', []),
                         getattr(self.a, '_action_history', []),
                         self.e.rng.getstate(), self.e.log_lines))

    def test_attack_bonus_reverses_actual_loss_and_drops_registered_item(self):
        self.own(self.a)
        result, rolls = self.observe(lambda: self.disarm(defender_options={'fixed': [3, 3, 3, 4]}))
        self.assertTrue(result)
        attack, defense = rolls[self.a.entity_id], rolls[self.b.entity_id]
        self.assertEqual((attack[0].modifier, attack[0].total, defense[0].total), (2, 14, 13))
        self.assertEqual(attack[1]['skill_context']['purpose'], 'disarm')
        self.assertEqual(defense[1]['skill_context']['purpose'], 'resist_disarm')
        self.assertFalse(self.b._item_reg)
        self.assertEqual(self.b.evasion_mod, 0)
        self.assertEqual(self.e.ground_items[-1]['item'], '소형 방패')
        self.assertEqual(self.a.budget['standard'], 0)

    def test_defense_bonus_reverses_actual_win_and_retains_registered_item(self):
        self.own(self.b)
        held = deepcopy(self.b._item_reg)
        result, rolls = self.observe(lambda: self.disarm(challenger_options={'fixed': [3, 3, 3, 4]}))
        self.assertFalse(result)
        attack, defense = rolls[self.a.entity_id], rolls[self.b.entity_id]
        self.assertEqual((attack[0].total, defense[0].modifier, defense[0].total), (13, 2, 14))
        self.assertEqual(defense[1]['skill_context']['purpose'], 'resist_disarm')
        self.assertEqual(self.b._item_reg, held)
        self.assertEqual(self.b.evasion_mod, 1)
        self.assertFalse(getattr(self.e, 'ground_items', []))
        self.assertEqual(self.a.budget['standard'], 0)

    def test_existing_context_and_explicit_mind_selection_survive_on_both_sides(self):
        self.own(self.a)
        self.own(self.b)
        options = [dict(fixed=[3] * 4, mods=2, skill_context={
            'purpose': purpose, 'reason': 'player selected actual mental modifier',
            'modifier_basis': {'body': 2, 'mind': 5, 'selected': 'mind'}})
            for purpose in ('disarm', 'resist_disarm')]
        original = deepcopy(options)
        result, rolls = self.observe(lambda: self.disarm(challenger_options=options[0], defender_options=options[1]))
        self.assertFalse(result)
        for actor, supplied in zip((self.a, self.b), original):
            roll, received = rolls[actor.entity_id]
            self.assertEqual((roll.modifier, roll.total), (7, 19))
            self.assertEqual(received['skill_context'], supplied['skill_context'])
            self.assertEqual(received['mods'], 2)
        self.assertEqual(options, original)
        self.assertTrue(self.b._item_reg)

    def test_conflicting_or_malformed_purpose_rejects_before_cost_rng_or_equipment(self):
        self.own(self.a)
        self.own(self.b)
        for side, wrong in (('challenger_options', 'resist_disarm'), ('defender_options', 'disarm')):
            for context in ({'purpose': wrong, 'reason': 'conflicting actual action'}, 'disarm'):
                with self.subTest(side=side, context=context):
                    supplied = {'fixed': [3] * 4, 'skill_context': context}
                    original, before = deepcopy(supplied), self.snapshot()
                    with self.assertRaisesRegex(ValueError, 'actual maneuver skill context cannot be replaced'):
                        self.disarm(**{side: supplied})
                    self.assertEqual(supplied, original)
                    self.assertEqual(self.snapshot(), before)

    def test_mind_selection_without_purpose_receives_native_context_without_losing_input(self):
        self.own(self.a)
        self.own(self.b)
        options = [dict(fixed=[3] * 4, mods=2, skill_context={
            'modifier_basis': {'body': 2, 'mind': 5, 'selected': 'mind'}})
            for _ in range(2)]
        options[1]['skill_context']['reason'] = 'player supplied actual choice reason'
        original = deepcopy(options)
        result, rolls = self.observe(lambda: self.disarm(challenger_options=options[0], defender_options=options[1]))
        self.assertFalse(result)
        for actor, supplied, purpose in zip((self.a, self.b), original, ('disarm', 'resist_disarm')):
            roll, received = rolls[actor.entity_id]
            self.assertEqual((roll.modifier, roll.total), (7, 19))
            self.assertEqual(received['skill_context']['purpose'], purpose)
            self.assertEqual(received['skill_context']['modifier_basis'], supplied['skill_context']['modifier_basis'])
            self.assertTrue(received['skill_context']['reason'])
        self.assertEqual(rolls[self.b.entity_id][1]['skill_context']['reason'], original[1]['skill_context']['reason'])
        self.assertEqual(options, original)
        self.assertTrue(self.b._item_reg)

    def test_invalid_explicit_mind_basis_is_not_replaced_by_automatic_context(self):
        self.own(self.a)
        self.own(self.b)
        for side, purpose in (('challenger_options', 'disarm'), ('defender_options', 'resist_disarm')):
            with self.subTest(side=side):
                supplied = {'fixed': [3] * 4, 'mods': 1, 'skill_context': {
                    'purpose': purpose, 'reason': 'declared body does not match actual modifier',
                    'modifier_basis': {'body': 2, 'mind': 5, 'selected': 'mind'}}}
                original, before = deepcopy(supplied), self.snapshot()
                with self.assertRaisesRegex(ValueError, 'ordinary skill modifier must equal'):
                    self.disarm(**{side: supplied})
                self.assertEqual(supplied, original)
                self.assertEqual(self.snapshot(), before)

    def test_unowned_combat_stealth_and_remote_focus_disarm_receive_no_bonus(self):
        for skill in ('전투', '은신', '집중'):
            with self.subTest(skill=skill):
                self.setUp()
                self.a.spec['skills'][skill] = self.b.spec['skills'][skill] = '숙련'
                if skill == '집중':
                    self.remote_ready()
                    action = self.remote
                else:
                    action = lambda: self.disarm(attacker_skill=skill, defender_skill=skill)
                result, rolls = self.observe(action)
                self.assertFalse(result)
                self.assertEqual([rolls[a.entity_id][0].modifier for a in (self.a, self.b)], [0, 0])
                self.assertTrue(self.b._item_reg)
                self.assertEqual(self.a.budget['standard'], 0)

    def test_stealth_attack_and_resistance_bonus_reverses_actual_native_result(self):
        for attacking in (True, False):
            with self.subTest(attacking=attacking):
                self.setUp()
                self.own(self.a if attacking else self.b)
                self.a.spec['skills']['은신'] = self.b.spec['skills']['은신'] = '숙련'
                options = {'challenger_options': {'fixed': [3, 3, 3, 3 if attacking else 4]},
                           'defender_options': {'fixed': [3, 3, 3, 4 if attacking else 3]}}
                result, rolls = self.observe(lambda: self.disarm(attacker_skill='은신', defender_skill='은신', **options))
                self.assertEqual(result, attacking)
                self.assertEqual([rolls[a.entity_id][0].modifier for a in (self.a, self.b)], [2, 0] if attacking else [0, 2])
                self.assertEqual([rolls[a.entity_id][0].total for a in (self.a, self.b)], [14, 13] if attacking else [13, 14])
                self.assertEqual(bool(self.b._item_reg), not attacking)
                self.assertEqual(bool(getattr(self.e, 'ground_items', [])), attacking)
                self.assertEqual(self.a.budget['standard'], 0)

    def test_equipped_weapon_focus_athletics_and_occult_resistance_gets_bonus(self):
        import test_category2_optional_weapon_framework as weapons
        weapons.OptionalWeaponFrameworkTests.setUpClass()
        helper = weapons.OptionalWeaponFrameworkTests()
        for family, skill in (('steelheart', '집중'), ('steelheart', '육상'), ('arcane', '오컬트학')):
            with self.subTest(family=family, skill=skill):
                e, holder, attacker, _ = helper.fixture(family=family, focus=4, athletics=4, occult=4, combat=4)
                attacker.spec['skills']['전투'] = 4
                uid = helper.weapon(e, holder, 'spirit/' + family + '/' + skill, arcane=family == 'arcane', metal=family == 'steelheart')
                key = weapons.FW.equip(e, holder, uid)
                approval = fixture.BlessingSkillRuleTests()
                approval.e = e
                approval.own(fixture.B.SPIRIT_OF_JUSTICE, actor=holder)
                helper.start(e, attacker)
                result, rolls = self.observe(lambda: e.disarm(attacker, holder,
                    attacker_skill='전투', defender_skill=skill, item_name=key, fixed_accuracy=20,
                    challenger_options={'fixed': [3, 3, 3, 4]}, defender_options={'fixed': [3] * 4}), engine=e)
                self.assertFalse(result)
                self.assertEqual((rolls[attacker.entity_id][0].total, rolls[holder.entity_id][0].modifier,
                                  rolls[holder.entity_id][0].total), (13, 2, 14))
                self.assertEqual(rolls[holder.entity_id][1]['skill_context']['purpose'], 'resist_disarm')
                self.assertEqual(e._physical_objects[uid]['equipped_by'], holder.entity_id)
                self.assertIn(key, holder.custom_conditions['equipped_weapons'])
                self.assertEqual(attacker.budget['standard'], 0)

    def test_remote_focus_attack_and_resistance_bonus_reverses_actual_native_result(self):
        for attacking in (True, False):
            with self.subTest(attacking=attacking):
                self.setUp()
                self.remote_ready()
                self.own(self.a if attacking else self.b)
                options = {'challenger_options': {'fixed': [3, 3, 3, 3 if attacking else 4]},
                           'defender_options': {'fixed': [3, 3, 3, 4 if attacking else 3]}}
                result, rolls = self.observe(lambda: self.remote(**options))
                self.assertEqual(result, attacking)
                for actor, counterpart in ((self.a, self.b), (self.b, self.a)):
                    context = rolls[actor.entity_id][1]['skill_context']
                    self.assertEqual((context['purpose'], context['maneuver'], context['target_id']),
                                     ('telekinetic_maneuver', 'maneuver/무장해제', counterpart.entity_id))
                self.assertEqual([rolls[a.entity_id][0].modifier for a in (self.a, self.b)], [2, 0] if attacking else [0, 2])
                self.assertEqual([rolls[a.entity_id][0].total for a in (self.a, self.b)], [14, 13] if attacking else [13, 14])
                self.assertEqual(bool(self.b._item_reg), not attacking)
                self.assertEqual(bool(getattr(self.e, 'ground_items', [])), attacking)
                self.assertEqual(self.a.budget['standard'], 0)

    def test_remote_push_and_trip_do_not_receive_disarm_bonus(self):
        for kind in ('push', 'trip'):
            with self.subTest(kind=kind):
                self.setUp()
                self.remote_ready()
                self.own(self.a)
                self.own(self.b)
                before = (self.b.pos, deepcopy(self.b._item_reg))
                result, rolls = self.observe(lambda: self.remote(kind))
                self.assertFalse(result)
                self.assertEqual([rolls[a.entity_id][0].modifier for a in (self.a, self.b)], [0, 0])
                self.assertEqual((self.b.pos, self.b._item_reg), before)
                self.assertNotIn('넘어짐', self.b.conditions)
                self.assertEqual(self.a.budget['standard'], 0)


if __name__ == '__main__':
    unittest.main()
