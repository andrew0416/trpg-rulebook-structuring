"""R111 activation-only views beside actual sourced Terrain and weather."""
from copy import deepcopy
import json
import unittest

import test_category2_csv_remaining_item_contracts as FIX
import test_localized_grass_field as LOCAL
import csv_item_physical_contracts as P
import field_effects as FIELD
import weather_state as WEATHER
import condition_recovery as RECOVERY
import effects as FX
import turn as TURN
import state_codec as CODEC
import items as ITEMS


class BoosterVirtualEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()

    def setUp(self):
        self.f = FIX.RemainingCsvItemContractTests()
        self.r = self.f.r

    def fixture(self, environment):
        actor = self.f.trainer('booster/owner')
        other = self.f.pokemon('booster/other')
        engine = self.f.fixture(actor, other)
        self.f.equip(engine, actor, 'booster/physical', 'item/부스트에너지', held=False)
        P.activate_booster(engine, actor, environment)
        return engine, actor, other

    def install(self, engine, actor, source):
        return FIELD.install(engine, actor, self.r.move_mech(source)[0]['effects_exec'][0], source)

    def restore(self, engine):
        return CODEC.load_engine(engine.r, json.loads(json.dumps(CODEC.dump_engine(engine))))

    def test_virtual_grass_has_no_native_turn_heal_but_actual_grass_still_heals(self):
        e, a, other = self.fixture('그래스필드')
        e.gm.set_hp(a, value=a.max_hp-50, reason='actual damaged wearer')
        before = a.hp
        e.start_round([a, other]); e.start_of_turn(a, initiative_count=20)
        self.assertEqual(a.hp, before)
        self.assertIsNone(FIELD.terrain_for(e, other))
        self.assertIsNone(e.field)
        self.install(e, other, 'move/그래스필드')
        e.end_of_turn(a); e.start_round([a, other]); e.start_of_turn(a, initiative_count=20)
        self.assertEqual(a.hp, before+a.max_hp//10)

    def test_virtual_mist_confusion_uses_normal_status_without_partial_time_registration(self):
        e, a, _ = self.fixture('미스트필드')
        before = list(e._time_actors)
        self.assertIsNone(FIELD.defer_status(e, a, '혼란', source='condition/혼란'))
        self.assertEqual(e._time_actors, before)
        self.assertTrue(e.apply_status(a, '혼란', source='condition/혼란'))
        self.assertIn('혼란', a.conditions)
        self.assertNotIn(FIELD.DEFERRED, a.custom_conditions)
        control = self.f.trainer('control/normal-status')
        normal = self.f.fixture(control, self.f.pokemon('control/other'))
        self.assertTrue(normal.apply_status(control, '혼란', source='condition/혼란'))
        self.assertEqual(len(e._time_actors), len(normal._time_actors))
        n = self.restore(e); owner = n.gm.everyone[0]
        self.assertIn('혼란', owner.conditions)
        self.assertNotIn(FIELD.DEFERRED, owner.custom_conditions)
        self.assertEqual(FIELD.terrain_for(n, owner)['source_id'], 'item/부스트에너지')

    def test_actual_mist_under_different_virtual_terrain_keeps_receipt_restore_and_delayed_release(self):
        e, a, other = self.fixture('전기지형')
        row = self.install(e, other, 'move/미스트필드')
        self.assertEqual(FIELD.terrain_for(e, a)['name'], '일렉트릭')
        self.assertEqual(FIELD.terrain_for(e, a, include_virtual=False), row)
        self.assertFalse(e.apply_status(a, '독', source='condition/독'))
        self.assertTrue(e.apply_status(a, '혼란', source='condition/혼란', applied_by=other))
        self.assertNotIn('혼란', a.conditions)
        pending = deepcopy(FIELD._pending(a)[0])
        self.assertEqual(pending['terrain_source_id'], 'move/미스트필드')
        self.assertEqual(pending['terrain_source_row_sha256'], row['source_row_sha256'])
        n = self.restore(e); owner = n.gm.everyone[0]
        self.assertEqual(FIELD._pending(owner), [pending])
        n.start_round(n.gm.everyone); n.start_of_turn(owner, initiative_count=20)
        self.assertNotIn('혼란', owner.conditions)
        n.end_of_turn(owner)
        self.assertIn('혼란', owner.conditions)
        self.assertNotIn(FIELD.DEFERRED, owner.custom_conditions)

    def test_actual_mist_pending_can_still_be_cured_after_gm_restore(self):
        e, a, other = self.fixture('미스트필드')
        self.install(e, other, 'move/미스트필드')
        self.assertTrue(e.apply_status(a, '혼란', source='condition/혼란'))
        e.gm.snapshot('actual-mist-pending')
        self.assertTrue(e.cure_status(a, '혼란'))
        self.assertNotIn(FIELD.DEFERRED, a.custom_conditions)
        e.gm.restore('actual-mist-pending')
        owner = e.gm.everyone[0]
        self.assertEqual(FIELD._pending(owner)[0]['terrain_source_id'], 'move/미스트필드')
        self.assertTrue(e.cure_status(owner, '혼란'))
        e.start_round(e.gm.everyone); e.start_of_turn(owner, initiative_count=20); e.end_of_turn(owner)
        self.assertNotIn('혼란', owner.conditions)
        self.assertNotIn(FIELD.DEFERRED, owner.custom_conditions)

    def test_virtual_mist_does_not_shadow_actual_electric_immunity_or_damage(self):
        e, a, other = self.fixture('미스트필드')
        self.install(e, other, 'move/일렉트릭필드')
        self.assertFalse(e.apply_status(a, '잠듦', source='condition/잠듦'))
        self.assertTrue(e.apply_status(a, '독', source='condition/독'))
        electric = self.r.move('move/10만볼트')
        self.assertEqual(FIELD.damage_roll_modifier(e, a, other, electric, '전기'), 10)
        self.assertEqual(FIELD.damage_roll_modifier(e, a, other, self.r.move('move/용의파동'), '드래곤'), 0)
        self.assertEqual(FIELD.terrain_for(e, other)['source_id'], 'move/일렉트릭필드')

    def test_actual_local_grass_survives_virtual_override_and_remains_spatial_after_restore(self):
        LOCAL.LocalGrassTests.setUpClass(); local = LOCAL.LocalGrassTests(); local.setUp()
        e = local.e; self.f.r = e.r
        a = self.f.trainer('local/booster')
        a.spec['footprint'] = {'kind':'observed_cells', 'offsets':[[0,0]], 'reason':'actual trainer body'}
        e.gm.add_combatant(a, pos=(3,3), side='party', reason='actual local recipient')
        self.f.equip(e, a, 'local/booster-object', 'item/부스트에너지', held=False)
        P.activate_booster(e, a, '미스트필드'); receipt = local.activate()
        self.assertEqual(FIELD.terrain_for(e, a)['name'], '미스트')
        self.assertEqual(FIELD.terrain_for(e, a, include_virtual=False)['request_id'], receipt['request_id'])
        e.gm.set_hp(a, value=a.max_hp-50, reason='local Grass recipient damage')
        e.end_of_turn(local.a); e.start_round(e.gm.everyone); before = a.hp
        e.start_of_turn(a, initiative_count=20)
        self.assertEqual(a.hp, before+a.max_hp//10)
        self.assertEqual(FIELD.damage_roll_modifier(e, a, local.o, self.r.move('move/에너지볼'), '풀'), 10)
        n = self.restore(e); owner = next(c for c in n.gm.everyone if c.entity_id==a.entity_id)
        self.assertEqual(FIELD.terrain_for(n, owner, include_virtual=False)['source_id'], FIELD.LOCAL_SOURCE)
        n.gm.set_position(owner, (9,8), reason='actual exit from fixed Grass')
        self.assertIsNone(FIELD.terrain_for(n, owner, include_virtual=False))
        self.assertEqual(FIELD.terrain_for(n, owner)['name'], '미스트')

    def test_weather_activation_and_native_save_use_distinct_views_with_real_hail_and_umbrella(self):
        e, a, other = self.fixture('싸라기눈')
        self.assertTrue(FX.weather_matches(e, 'hail', a))
        self.assertFalse(FX.weather_matches(e, 'hail', other))
        self.assertIsNone(e.weather)
        self.assertEqual(TURN.weather_save_mod(e, '얼음', a), 0)
        self.assertEqual(RECOVERY.saving_check(e, a, '얼음', 10, fixed=10)['dc'], 10)
        # Actual Hail remains visible even under a different selected virtual Sun.
        e.end_scene([a, other]); P.activate_booster(e, a, '쾌청')
        e.gm.set_weather('hail', reason='actual cold weather')
        self.assertTrue(FX.weather_matches(e, 'sunny', a))
        self.assertEqual(WEATHER.effective_weathers(e, a, include_virtual=False), ('hail',))
        self.assertEqual(RECOVERY.saving_check(e, a, '얼음', 10, fixed=10)['dc'], 12)
        ITEMS.unregister_item(e, a, 'item/부스트에너지')
        self.assertTrue(FX.weather_matches(e, 'sunny', a))
        self.f.equip(e, a, 'booster/umbrella', 'item/만능우산', held=False)
        self.assertTrue(P._active(e, a, 'utility_umbrella'))
        self.assertEqual(TURN.weather_save_mod(e, '얼음', a), -2)
        n = self.restore(e); owner = n.gm.everyone[0]
        self.assertEqual(TURN.weather_save_mod(n, '얼음', owner), -2)

    def test_general_weather_damage_uses_actual_rain_sun_and_keeps_independent_umbrella(self):
        e, a, other = self.fixture('쾌청'); fire = self.r.move('move/화염방사')
        self.assertEqual(TURN.weather_damage_mod(e, a, fire, other), 0)
        e.gm.set_weather('rain', reason='actual Rain beside virtual Sun')
        self.assertTrue(FX.weather_matches(e, 'sunny', a))
        self.assertEqual(TURN.weather_damage_mod(e, a, fire, other), -5)
        e.gm.set_weather('sunny', reason='actual Sun')
        self.assertEqual(TURN.weather_damage_mod(e, a, fire, other), 5)
        ITEMS.unregister_item(e, a, 'item/부스트에너지')
        self.assertTrue(FX.weather_matches(e, 'sunny', a))
        self.f.equip(e, a, 'booster/umbrella', 'item/만능우산', held=False)
        self.assertTrue(P._active(e, a, 'utility_umbrella'))
        self.assertEqual(TURN.weather_damage_mod(e, a, fire, other), 0)
        self.assertEqual(TURN.weather_damage_mod(e, other, fire, a), 0)
        ITEMS.unregister_item(e, a, 'item/만능우산')
        self.assertEqual(TURN.weather_damage_mod(e, a, fire, other), 5)


if __name__ == '__main__':
    unittest.main()
