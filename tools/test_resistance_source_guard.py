"""Red audit regression for non-ability resistance under public effect suppression.

Run in this folder:
python -B -X utf8 -W ignore::ResourceWarning -m unittest test_resistance_source_guard
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_class_passive_combat_bulk as CLASS_FIXTURE
import test_category2_optional_catalog_nine as ITEM_FIXTURE
import class_passive_combat as C
import optional_physical_equipment as OPTIONAL


class ResistanceSourceGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CLASS_FIXTURE.ClassPassiveCombatBulkTests.setUpClass()
        ITEM_FIXTURE.OptionalCatalogNineTests.setUpClass()

    def test_blessed_resilience_remains_when_unrelated_ability_is_suppressed(self):
        case = CLASS_FIXTURE.ClassPassiveCombatBulkTests(
            'test_blessed_resilience_roles_selection_failure_atomicity_and_scene_end')
        choice = {C.BLESSED_RESILIENCE: {
            'role': 'messiah', 'eligible_types': ['불꽃', '물', '풀'],
            'selected_types': ['불꽃', '물'],
        }}
        engine, owner, _, enemy = case.fixture(gifts=[C.BLESSED_RESILIENCE], choices=choice)
        engine.gm.set_ability(owner, '정전기', reason='audit: suppressible ability')
        move = case.rules.move('move/화염방사')
        before = {}
        engine.roll_damage(enemy, owner, move, set_damage=True, _reaction_event=before)
        engine.apply_effect(enemy, owner, {'type': 'suppress_ability'}, None, True, 0,
                            'audit/ability-suppression')
        after = {}
        engine.roll_damage(enemy, owner, move, set_damage=True, _reaction_event=after)
        self.assertTrue(owner.abilities_suppressed)
        self.assertEqual(C.resistance_steps(engine, owner, '불꽃'), 1)
        self.assertEqual(before['damage_formula']['multiplier'], 0.5)
        self.assertEqual(after['damage_formula']['multiplier'], 0.5)

    def test_svalinn_ally_resistance_remains_when_ally_ability_is_suppressed(self):
        case = ITEM_FIXTURE.OptionalCatalogNineTests(
            'test_candy_daily_heal_svalinn_fire_protection_and_release')
        engine, wearer, ally, enemy = case.fixture()
        engine.gm.set_ability(ally, '정전기', reason='audit: suppressible ability')
        case.equip(engine, wearer, 'crafted_item/스-발린', 'audit-svalinn')
        engine.time_actors(engine.everyone)
        move = case.r.move('move/불꽃세례')
        before = {}
        engine.roll_damage(enemy, ally, move, set_damage=True, _reaction_event=before)
        engine.apply_effect(enemy, ally, {'type': 'suppress_ability'}, None, True, 0,
                            'audit/ability-suppression')
        after = {}
        engine.roll_damage(enemy, ally, move, set_damage=True, _reaction_event=after)
        self.assertTrue(ally.abilities_suppressed)
        self.assertEqual(OPTIONAL.resistance_steps(engine, ally, '불꽃'), 1)
        self.assertEqual(before['damage_formula']['multiplier'], 0.5)
        self.assertEqual(after['damage_formula']['multiplier'], 0.5)


if __name__ == '__main__':
    unittest.main()
