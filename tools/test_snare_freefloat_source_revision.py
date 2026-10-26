"""S-poly-2/3: actual reflected damage and source-owned zero-gravity movement."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

import test_category2_digital_programs as DIGITAL
import test_category2_optional_physical_equipment as EQUIPMENT
from engine import Rules
from state_codec import dump_engine, load_engine, StateCodecError
from native_scenario_fixture import assert_rejected_unchanged
import digital_programs as PROGRAMS
import environment_derive as ENVIRONMENT
import movement_actions as MOVEMENT
import network_integrity as INTEGRITY
import network_connection as CONNECTION
import optional_physical_equipment as OPTIONAL
import items as ITEMS
import special_entities as SPECIAL
import state_grants as GRANTS
import world_entities as WORLD


class SnareReflectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.poly = Rules(str(ROOT), ruleset='all')

    trainer = DIGITAL.DigitalProgramTests.trainer
    setUp = DIGITAL.DigitalProgramTests.setUp
    next_turn = DIGITAL.DigitalProgramTests.next_turn
    run_effect = DIGITAL.DigitalProgramTests.run_effect
    node = DIGITAL.DigitalProgramTests.node
    policy = DIGITAL.DigitalProgramTests.policy
    snap = DIGITAL.DigitalProgramTests.snap
    snare = DIGITAL.DigitalProgramTests.snare
    shield = DIGITAL.DigitalProgramTests.shield
    use_shield = DIGITAL.DigitalProgramTests.use_shield
    intrude = DIGITAL.DigitalProgramTests.intrude

    def test_extraction_and_modification_return_the_roll_once_to_the_attacker(self):
        for outcome in ('extracted', 'modified'):
            with self.subTest(outcome=outcome):
                if outcome == 'modified':
                    self.setUp()
                snare = self.snare()
                untouched = deepcopy(snare)
                physical = (self.a.hp, self.t.hp, self.a.pos, self.t.pos)
                value = self.policy()
                # A false core returns the roll, not an authored target-damage multiplier.
                value['effect'].update(data_outcome=outcome, multiplier=[2, 1], minimum=99)
                result = self.run_effect(value, target='snare', request='reflect/' + outcome)
                avatar = self.e._physical_objects['avatar']
                self.assertEqual((result['check']['total'], result['requested']), (24, 24))
                self.assertEqual(result['damage_target_id'], 'avatar')
                self.assertEqual((avatar['integrity'], self.a.budget['standard']), (16, 0))
                self.assertEqual(snare, untouched)
                self.assertEqual(physical, (self.a.hp, self.t.hp, self.a.pos, self.t.pos))
                self.assertNotIn('snare', getattr(self.e, INTEGRITY.FIELD)['data_permissions'])
                before = self.snap()
                self.assertEqual(self.run_effect(value, target='snare', request='reflect/' + outcome), result)
                self.assertEqual(before, self.snap())

    def test_reflection_consumes_actual_net_shield_before_integrity_and_restores_recognition(self):
        self.snare()
        self.shield()
        self.use_shield()
        self.next_turn()
        self.a.temp_hp = 9
        physical = (self.a.hp, self.a.temp_hp)
        result = self.intrude()
        avatar = self.e._physical_objects['avatar']
        self.assertEqual(result['before'], {'integrity': 40, 'temporary_integrity': 20})
        self.assertEqual((avatar['integrity'], avatar['temp_integrity']), (36, 0))
        self.assertNotIn('avatar', getattr(self.e, INTEGRITY.FIELD)['temporary'])
        self.assertEqual(physical, (self.a.hp, self.a.temp_hp))
        saved = self.snap()
        loaded = load_engine(self.poly, json.loads(json.dumps(saved, ensure_ascii=False)))
        actor = WORLD.actor_index(loaded)[self.a.entity_id]
        self.assertEqual(PROGRAMS.known_data_snares(loaded, actor, 'avatar'), {'snare': 'snare/intrude'})
        self.assertEqual(loaded._physical_objects['avatar']['integrity'], 36)
        self.assertEqual(loaded._physical_objects['snare']['integrity'], 50)
        self.next_turn()
        assert_rejected_unchanged(self.e, lambda: self.intrude(request='recognized/retry'),
                                  reason_pattern='recognized false core')

    def test_reflection_uses_the_attacking_avatars_actual_defensive_hacking(self):
        self.snare()
        self.a.spec['skills']['집중'] = 3
        self.a.spec['edges'] = [INTEGRITY.DEFENSIVE_HACKING]
        WORLD.register_object(self.e, 'snare/datajack', location={'kind': 'unknown'},
                              reason='actual attacker Datajack instance')
        SPECIAL.observe(self.e, dict(id='snare/augmentations', kind='augmentation_set',
            location={'kind': 'unknown'}, actor_id=self.a.entity_id, body_slots=[],
            installations=[{'instance_id': 'snare/datajack', 'augmentation_id': 'datajack'}],
            allow_added_parts=False, essence_enabled=False), reason='actual attacker installed Datajack')
        result = self.intrude()
        self.assertEqual((result['requested'], result['derivation']['defense'],
                          result['derivation']['reduction']), (21, 0, 3))
        self.assertEqual(self.e._physical_objects['avatar']['integrity'], 19)
        self.assertEqual(self.e._physical_objects['snare']['integrity'], 50)
        self.assertEqual(self.e._physical_objects['target-avatar']['integrity'], 40)

    def test_zero_reflection_ejects_attacker_and_reuses_actual_recovery_clock(self):
        self.snare()
        self.e._physical_objects['avatar']['integrity'] = 10
        value = self.policy()
        value['effect']['data_outcome'] = 'modified'
        seconds = value['effect']['recovery']['seconds']
        result = self.run_effect(value, target='snare', request='snare/ejection')
        avatar = self.e._physical_objects['avatar']
        self.assertEqual((avatar['integrity'], avatar['status']), (0, 'ejected'))
        self.assertEqual(result['ejected'], ['avatar'])
        self.assertEqual(self.e._physical_objects['snare']['integrity'], 50)
        recovery = getattr(self.e, INTEGRITY.FIELD)['recovery']['avatar']
        self.assertEqual(recovery['ready_at'], recovery['started_at'] + seconds)
        saved = self.snap()
        self.assertEqual(self.run_effect(value, target='snare', request='snare/ejection'), result)
        self.assertEqual(saved, self.snap())
        self.e.end_of_turn(self.a)
        self.e.start_round(self.e.everyone)
        # Starting the successor round may already advance the previous round's clock.
        remaining = recovery['ready_at'] - self.e.elapsed_seconds
        self.assertGreater(remaining, 1)
        self.e.advance_time(remaining - 1)
        self.assertEqual(avatar['integrity'], 0)
        self.e.advance_time(1)
        self.assertEqual((avatar['integrity'], avatar['status']), (1, 'ejected'))
        self.e.start_of_turn(self.a)
        self.e.enter_network(self.a, 'network', avatar_id='avatar', request_id='snare/reentry',
                             access_established=True, reason='completed actual reflection recovery')
        self.assertEqual(avatar['status'], 'connected')
        self.assertEqual(PROGRAMS.known_data_snares(self.e, self.a, 'avatar'), {'snare': 'snare/ejection'})

    def test_late_reflection_ejection_rolls_back_cost_rng_damage_and_recognition(self):
        self.snare()
        self.e._physical_objects['avatar']['integrity'] = 10
        before = self.snap()
        with patch.object(CONNECTION, '_end', side_effect=RuntimeError('late reflected ejection')):
            with self.assertRaisesRegex(RuntimeError, 'late reflected ejection'):
                self.intrude()
        self.assertEqual(before, self.snap())
        self.assertEqual(PROGRAMS.known_data_snares(self.e, self.a, 'avatar'), {})

    def test_nonintrusion_technology_damages_snare_and_saved_reflection_target_is_checked(self):
        self.snare()
        self.run_effect(target='snare')
        self.assertEqual(self.e._physical_objects['snare']['integrity'], 26)
        self.assertEqual(self.e._physical_objects['avatar']['integrity'], 40)
        self.assertEqual(PROGRAMS.known_data_snares(self.e, self.a, 'avatar'), {})
        self.next_turn()
        self.intrude()
        state = getattr(self.e, INTEGRITY.FIELD)
        receipt = state['requests']['snare/intrude']
        receipt.pop('sha256')
        receipt['result']['damage_target_id'] = 'snare'
        state['requests']['snare/intrude'] = INTEGRITY._sign(receipt)
        self.assertFalse(WORLD.validate_world(self.e)['valid'])
        with self.assertRaises(StateCodecError):
            self.snap()

    def test_legacy_paid_snare_damage_history_loads_unchanged_and_new_intrusions_reflect(self):
        self.snare()
        result = self.intrude()
        # Preserve the exact old receipt shape and its already-paid historical result.
        legacy = deepcopy(result)
        legacy.pop('damage_target_id')
        legacy['before'] = {'integrity': 50, 'temporary_integrity': 0}
        legacy['after'] = {'integrity': 26, 'temporary_integrity': 0}
        self.e._physical_objects['avatar']['integrity'] = 40
        self.e._physical_objects['snare']['integrity'] = 26
        state = getattr(self.e, INTEGRITY.FIELD)
        row = state['requests']['snare/intrude']
        row.pop('sha256')
        row['result'] = legacy
        state['requests']['snare/intrude'] = INTEGRITY._sign(row)
        saved = self.snap()
        loaded = load_engine(self.poly, json.loads(json.dumps(saved, ensure_ascii=False)))
        self.assertEqual(getattr(loaded, INTEGRITY.FIELD)['requests']['snare/intrude'],
                         state['requests']['snare/intrude'])
        actors = WORLD.actor_index(loaded)
        attacker, other = actors[self.a.entity_id], actors[self.t.entity_id]
        self.assertEqual(attacker.budget['standard'], 0)
        self.assertEqual(loaded._physical_objects['avatar']['integrity'], 40)
        self.assertEqual(loaded._physical_objects['snare']['integrity'], 26)
        self.assertEqual(PROGRAMS.known_data_snares(loaded, attacker, 'avatar'), {'snare': 'snare/intrude'})
        loaded.end_of_turn(attacker)
        loaded.start_of_turn(other)
        value = self.policy()
        value['effect']['data_outcome'] = 'extracted'
        fresh = loaded.digital_operation(other, 'target-avatar', 'snare', value,
            request_id='post-legacy/intrusion', reason='new actual intrusion after historical restore',
            roll_options={'fixed': [6, 6, 6, 6]})
        self.assertEqual(fresh['damage_target_id'], 'target-avatar')
        self.assertEqual(loaded._physical_objects['target-avatar']['integrity'], 16)
        self.assertEqual(loaded._physical_objects['snare']['integrity'], 26)


class FreeFloatingTests(unittest.TestCase):
    setUpClass = classmethod(EQUIPMENT.OptionalPhysicalEquipmentTests.setUpClass.__func__)
    actor = EQUIPMENT.OptionalPhysicalEquipmentTests.actor
    fixture = EQUIPMENT.OptionalPhysicalEquipmentTests.fixture
    equip = EQUIPMENT.OptionalPhysicalEquipmentTests.equip
    restored = EQUIPMENT.OptionalPhysicalEquipmentTests.restored

    def region(self, engine, *, gravity, airless=False):
        source = json.loads((ROOT / 'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
        engine.observe_environment('float-region', dict(gravity=gravity,
            pressure=0 if airless else 1, air_available=not airless,
            medium='airless' if airless else 'air'), source=source,
            reason='observed actual gravity and atmosphere for Free Floating')
        return source

    def test_suit_does_not_grant_levitate_or_flight_at_normal_unknown_or_unobserved_gravity(self):
        for observed, gravity in ((False, None), (True, None), (True, 1), (True, 2)):
            with self.subTest(observed=observed, gravity=gravity):
                engine, actor, _, _ = self.fixture()
                self.equip(engine, actor, 'item/우주복', 'no-float')
                if observed:
                    self.region(engine, gravity=gravity)
                raw = MOVEMENT.capabilities(engine, actor, environment=False)
                self.assertEqual(raw['free_float'], 4)
                self.assertEqual(raw.get('levitate', 0), 0)
                usable = MOVEMENT.capabilities(engine, actor)
                self.assertEqual((usable['free_float'], usable.get('sky', 0)), (0, 0))
                engine.start_round(engine.everyone)
                engine.start_of_turn(actor)
                assert_rejected_unchanged(engine, lambda: engine.aerial_move(actor, actor.pos,
                    mode='sky', altitude=3, reason_text='not actual zero gravity'),
                    reason_pattern='not possessed')

    def test_zero_gravity_air_and_vacuum_use_native_sky_motion_above_levitate_height(self):
        for airless in (False, True):
            with self.subTest(airless=airless):
                engine, actor, _, _ = self.fixture()
                self.equip(engine, actor, 'item/우주복', 'native-flight')
                self.region(engine, gravity=0, airless=airless)
                # Region ownership suffices; no unrelated numeric home-gravity policy is required.
                self.assertFalse(ENVIRONMENT.bound(engine, actor))
                self.assertEqual(MOVEMENT.capabilities(engine, actor)['sky'], 4)
                engine.start_round(engine.everyone)
                engine.start_of_turn(actor)
                before = actor.pos
                result = engine.aerial_move(actor, before, mode='sky', altitude=3,
                    reason_text='sourced Free Floating through native Sky traversal')
                self.assertEqual((result['altitude'], actor.spec['_movement_altitude'], actor.budget['shift']), (3, 3, 0))
                self.assertTrue(actor.airborne)
                self.assertEqual(actor.pos, before)
                self.assertNotIn('sky', actor.spec['movement'])
                self.assertIn('자유평형 4', GRANTS.effective_capabilities(actor))

    def test_unrelated_observed_region_disables_only_float_and_bad_local_evidence_still_rejects(self):
        engine, actor, _, _ = self.fixture()
        self.equip(engine, actor, 'item/우주복', 'unrelated-region')
        source = json.loads((ROOT / 'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
        engine.observe_environment('elsewhere', dict(gravity=0, pressure=1,
            air_available=True, medium='air'), cells=[[20, 10]], source=source,
            reason='zero gravity is observed elsewhere, not at this actor')
        values = MOVEMENT.capabilities(engine, actor)
        self.assertEqual((values['land'], values['free_float'], values.get('sky', 0)), (6, 0, 0))
        self.assertEqual(engine.move_profile(actor, movement_mode='land'), (6, '육상'))
        self.region(engine, gravity=0)
        row = getattr(engine, ENVIRONMENT.FIELD)['regions']['float-region']
        row['facts']['gravity'] = 1  # Its unchanged signed observation must reject.
        with self.assertRaisesRegex(ValueError, 'observation or binding changed'):
            MOVEMENT.capabilities(engine, actor)

    def test_float_only_sky_cannot_cross_to_normal_or_unobserved_gravity_before_cost(self):
        for destination_observed in (False, True):
            with self.subTest(destination_observed=destination_observed):
                engine, actor, _, _ = self.fixture()
                self.equip(engine, actor, 'item/우주복', 'gravity-boundary')
                source = json.loads((ROOT / 'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
                facts = dict(gravity=0, pressure=1, air_available=True, medium='air')
                engine.observe_environment('origin', facts, cells=[list(actor.pos)], source=source,
                    reason='only the actual departure cell has zero gravity')
                if destination_observed:
                    engine.observe_environment('destination', dict(facts, gravity=1), cells=[[3, 2]],
                        source=source, reason='actual normal-gravity destination')
                engine.start_round(engine.everyone)
                engine.start_of_turn(actor)
                assert_rejected_unchanged(engine, lambda: engine.aerial_move(actor, (3, 2),
                    mode='sky', altitude=1, gm_distance=2, reason_text='float-only boundary crossing'),
                    reason_pattern='Free Floating destination requires observed zero gravity')
                engine.gm.set_movement_capabilities(actor, {'land': 6, 'sky': 4}, basis='current',
                    reason='independent native Sky supports the destination')
                result = engine.aerial_move(actor, (3, 2), mode='sky', altitude=1, gm_distance=2,
                    reason_text='ordinary Sky remains usable across this gravity boundary')
                self.assertEqual((result['position'], actor.budget['shift']), ((3, 2), 0))

    def test_approach_planning_uses_actual_owner_and_stays_inside_the_zero_gravity_route(self):
        for complete_route in (False, True):
            with self.subTest(complete_route=complete_route):
                engine, actor, ally, enemy = self.fixture()
                ally.pos = (10, 2)
                self.equip(engine, actor, 'item/우주복', 'approach-route')
                engine.gm.set_movement_capabilities(actor, {'land': 6, 'levitate': 8}, basis='current',
                    reason='independent Levitate must not authorize explicitly selected Sky')
                source = json.loads((ROOT / 'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
                cells = [[x, 2] for x in range(2, 6 if complete_route else 4)]
                engine.observe_environment('route', dict(gravity=0, pressure=1,
                    air_available=True, medium='air'), cells=cells, source=source,
                    reason='actual continuous zero-gravity corridor')
                engine.start_round(engine.everyone)
                engine.start_of_turn(actor)
                engine.approach(actor, enemy, movement_mode='sky')
                # Native Approach pays its attempted Shift even when no valid route exists.
                self.assertEqual((actor.pos, actor.budget['shift']),
                                 ((5, 2) if complete_route else (2, 2), 0))

    def test_disengage_checks_float_destination_before_spending_its_native_action(self):
        engine, actor, _, _ = self.fixture()
        self.equip(engine, actor, 'item/우주복', 'disengage-boundary')
        source = json.loads((ROOT / 'data/examples/environment-derive.json').read_text(encoding='utf-8'))['source']
        engine.observe_environment('origin', dict(gravity=0, pressure=1,
            air_available=True, medium='air'), cells=[list(actor.pos)], source=source,
            reason='actual zero-gravity departure with unknown neighboring gravity')
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor)
        assert_rejected_unchanged(engine,
            lambda: engine.disengage(actor, (3, 2), movement_mode='sky'),
            reason_pattern='Free Floating destination requires observed zero gravity')
        engine.gm.set_movement_capabilities(actor, {'land': 6, 'levitate': 4}, basis='current',
            reason='independent native Levitate supports the same display mode')
        assert_rejected_unchanged(engine,
            lambda: engine.disengage(actor, (3, 2), movement_mode='sky'),
            reason_pattern='Free Floating destination requires observed zero gravity')
        self.assertTrue(engine.disengage(actor, (3, 2), movement_mode='levitate'))
        self.assertEqual((actor.pos, actor.budget['shift']), ((3, 2), 0))

    def test_live_gravity_change_restore_and_unequip_preserve_stronger_native_movement(self):
        engine, actor, _, _ = self.fixture()
        engine.gm.set_movement_capabilities(actor, {'land': 6, 'sky': 7, 'levitate': 8, 'swim': 3},
            basis='current', reason='actual independent stronger movement')
        uid = self.equip(engine, actor, 'item/우주복', 'preserve-native')
        source = self.region(engine, gravity=0)
        expected = MOVEMENT.capabilities(engine, actor)
        self.assertEqual((expected['sky'], expected['levitate'], expected['swim'], expected['free_float']), (7, 8, 3, 4))
        engine.gm.snapshot('float-origin')
        engine.change_environment('float-region', {'gravity': 1}, source=source,
            request_id='float/normal', reason='actual return to normal gravity')
        current = MOVEMENT.capabilities(engine, actor)
        self.assertEqual((current['sky'], current['levitate'], current['free_float']), (7, 8, 0))
        engine.gm.restore('float-origin', reason='restore actual zero-gravity region and suit')
        loaded = self.restored(engine)
        restored = WORLD.actor_index(loaded)[actor.entity_id]
        self.assertEqual(MOVEMENT.capabilities(loaded, restored), expected)
        key = next(k for k, v in restored._item_reg.items() if v.get('instance_id') == uid)
        ITEMS.unregister_item(loaded, restored, registration_key=key)
        current = MOVEMENT.capabilities(loaded, restored)
        self.assertEqual((current['sky'], current['levitate'], current['swim'], current.get('free_float', 0)), (7, 8, 3, 0))
        self.assertNotIn('진공면역', GRANTS.effective_capabilities(restored))

    def test_distinct_larger_free_float_and_sky_environment_rule_do_not_erase_vacuum_motion(self):
        engine, actor, _, _ = self.fixture()
        source = self.region(engine, gravity=0, airless=True)
        engine.gm.set_movement_capabilities(actor, {'land': 6, 'free_float': 8, 'levitate': 2},
            basis='current', reason='observed independent Free Floating score')
        self.equip(engine, actor, 'item/우주복', 'larger-native-float')
        declaration = dict(id='actual-sky-vacuum-rule', source=source, home_gravity=1, rules=[
            dict(id='sky-vacuum', family='pressure', target='movement', selector='sky',
                when=[dict(fact='pressure', op='eq', value=0)], law='multiply', value=0,
                priority=0, exemption='none')])
        engine.bind_environment(actor, declaration, reason='authored ordinary Sky vacuum restriction')
        result = MOVEMENT.capabilities(engine, actor)
        self.assertEqual((result['free_float'], result['sky'], result['levitate']), (8, 8, 2))
        self.assertEqual(actor.spec['movement']['free_float'], 8)
        self.assertNotIn('sky', actor.spec['movement'])

    def test_tampered_saved_suit_speed_cannot_replace_the_selected_source(self):
        engine, actor, _, _ = self.fixture()
        uid = self.equip(engine, actor, 'item/우주복', 'source-bound-speed')
        row = next(row for row in actor.registry if row.get('instance_id') == uid
                   and row.get('type') == 'optional_physical_equipment')
        row['free_float'] = 99
        self.assertFalse(WORLD.validate_world(engine)['valid'])
        with self.assertRaises(StateCodecError):
            dump_engine(engine)


    def test_weaker_native_sky_does_not_spend_free_float_speed_in_normal_gravity(self):
        for restored in (False,True):
            with self.subTest(restored=restored):
                engine,actor,_,_=self.fixture()
                self.equip(engine,actor,'item/우주복','weak-sky')
                engine.gm.set_movement_capabilities(actor,{'land':6,'sky':1},basis='current',reason='actual independent Sky1')
                source=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))['source']
                for name,gravity,cells in [('origin',0,[[2,2]]),('corridor',1,[[2,y] for y in range(3,7)])]:
                    engine.observe_environment(name,dict(gravity=gravity,pressure=1,air_available=True,medium='air'),cells=cells,source=source,reason='actual gravity along the whole selected Sky path')
                if restored:
                    engine=self.restored(engine);actor=WORLD.actor_index(engine)[actor.entity_id]
                engine.start_round(engine.everyone);engine.start_of_turn(actor)
                assert_rejected_unchanged(engine,lambda:engine.aerial_move(actor,(2,6),mode='sky',altitude=0,reason_text='four metre normal-gravity flight'),reason_pattern='independent native Sky allowance')
                result=engine.aerial_move(actor,(2,3),mode='sky',altitude=0,reason_text='one metre actual native Sky')
                self.assertEqual((result['distance'],actor.pos,actor.budget['shift']),(1,(2,3),0))
                self.assertEqual(MOVEMENT.capabilities(engine,actor)['sky'],1)

        # Existing aerial geometry accepts an explicitly measured fractional path.
        engine,actor,_,_=self.fixture();self.equip(engine,actor,'item/우주복','fractional-native-sky')
        engine.gm.set_movement_capabilities(actor,{'land':6,'sky':2},basis='current',reason='actual independent Sky2')
        source=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))['source']
        for name,gravity,cells in [('origin',0,[[2,2]]),('destination',1,[[2,3]])]:
            engine.observe_environment(name,dict(gravity=gravity,pressure=1,air_available=True,medium='air'),cells=cells,source=source,reason='actual fractional aerial path gravity')
        engine.start_round(engine.everyone);engine.start_of_turn(actor)
        result=engine.aerial_move(actor,(2,3),mode='sky',altitude=0.5,gm_distance=1.5,reason_text='observed native Sky2 path')
        self.assertEqual((result['distance'],actor.pos,actor.spec['_movement_altitude'],actor.budget['shift']),(1.5,(2,3),0.5,0))

    def test_free_float_paid_path_cannot_reset_native_sky_allowance_each_step(self):
        import turn as TURN
        engine,actor,_,_=self.fixture();self.equip(engine,actor,'item/우주복','paid-weak-sky')
        engine.gm.set_movement_capabilities(actor,{'land':6,'sky':1},basis='current',reason='actual native Sky1')
        source=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))['source']
        engine.observe_environment('origin',dict(gravity=0,pressure=1,air_available=True,medium='air'),cells=[[2,2]],source=source,reason='zero-gravity departure')
        engine.observe_environment('corridor',dict(gravity=1,pressure=1,air_available=True,medium='air'),cells=[[2,y] for y in range(3,7)],source=source,reason='normal-gravity native Sky path')
        engine.start_round(engine.everyone);engine.start_of_turn(actor)
        self.assertTrue(TURN.spend(engine,actor,'shift','actual paid Sky movement',movement=True))
        path=[{'position':(2,y),'altitude':0} for y in range(3,7)];progress={}
        result=MOVEMENT.follow_paid_path(engine,actor,path,mode='sky',maximum_distance=4,progress=progress)
        self.assertEqual((result['distance'],result['steps'],actor.pos,actor.budget['shift']),(1,1,(2,3),0))
        before=(actor.pos,progress.copy(),engine.rng.getstate())
        again=MOVEMENT.follow_paid_path(engine,actor,path,mode='sky',maximum_distance=4,progress=progress)
        self.assertEqual((again['distance'],again['steps']),(1,1));self.assertEqual((actor.pos,progress,engine.rng.getstate()),before)

    def test_full_zero_gravity_keeps_four_speed_and_zero_endpoints_do_not_hide_normal_gap(self):
        for gap in (False,True):
            with self.subTest(normal_gap=gap):
                engine,actor,_,_=self.fixture();self.equip(engine,actor,'item/우주복','float-corridor')
                source=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))['source']
                zeros=[[2,y] for y in range(2,7) if not gap or y in (2,6)]
                engine.observe_environment('zero',dict(gravity=0,pressure=1,air_available=True,medium='air'),cells=zeros,source=source,reason='actual complete zero-gravity cells')
                if gap:engine.observe_environment('gap',dict(gravity=1,pressure=1,air_available=True,medium='air'),cells=[[2,y] for y in (3,4,5)],source=source,reason='actual normal-gravity gap')
                engine.start_round(engine.everyone);engine.start_of_turn(actor)
                call=lambda:engine.aerial_move(actor,(2,6),mode='sky',altitude=0,reason_text='four metre Free Floating path')
                if gap:assert_rejected_unchanged(engine,call,reason_pattern='observed zero gravity')
                else:
                    result=call();self.assertEqual((result['distance'],actor.pos,actor.budget['shift']),(4,(2,6),0))



    def test_one_movement_sprint_keeps_paid_rate_across_segments_and_continuation(self):
        import turn as TURN
        for scenario in ('whole','continuation','live_capacity_loss'):
            with self.subTest(scenario=scenario):
                engine,actor,_,_=self.fixture();self.equip(engine,actor,'item/우주복','paid-sprint')
                engine.gm.set_movement_capabilities(actor,{'land':6,'sky':2},basis='current',reason='actual native Sky2 with dormant Free Floating4')
                self.region(engine,gravity=1)
                if scenario!='whole':engine.gm.set_terrain((2,4),'blocking',reason='actual temporary obstacle pauses the paid path')
                engine.start_round(engine.everyone);engine.start_of_turn(actor)
                self.assertTrue(MOVEMENT.sprint(engine,actor,source_policy='ch06_once'))
                allowance=MOVEMENT.distance_budget(engine,actor,'sky');self.assertEqual(allowance,3)
                self.assertTrue(TURN.spend(engine,actor,'shift','actual paid Sprint Sky path',movement=True))
                path=[{'position':(2,y),'altitude':0} for y in range(3,6)];progress={}
                result=MOVEMENT.follow_paid_path(engine,actor,path,mode='sky',maximum_distance=allowance,progress=progress)
                if scenario!='whole':
                    self.assertEqual((result['distance'],result['steps'],actor.pos),(1,1,(2,3)))
                    self.assertNotIn('질주',actor.custom_conditions)
                    engine.gm.set_terrain((2,4),'blocking',on=False,reason='actual obstacle removed before resuming same paid path')
                    if scenario=='live_capacity_loss':engine.gm.set_movement_capabilities(actor,{'land':6,'sky':1},basis='current',reason='actual reduced native Sky before continuation')
                    result=MOVEMENT.follow_paid_path(engine,actor,path,mode='sky',maximum_distance=allowance,progress=progress)
                expected=1 if scenario=='live_capacity_loss' else 3
                self.assertEqual((result['distance'],result['steps'],actor.pos),(expected,expected,(2,2+expected)))
                self.assertEqual((actor.budget['standard'],actor.budget['shift']),(0,0));self.assertNotIn('질주',actor.custom_conditions)
                if scenario=='whole':
                    engine.end_of_turn(actor);engine.end_round();engine.start_round(engine.everyone);engine.start_of_turn(actor)
                    self.assertEqual(MOVEMENT.distance_budget(engine,actor,'sky'),2)
                    self.assertTrue(TURN.spend(engine,actor,'shift','distinct later Sky movement',movement=True))
                    fresh=[{'position':(2,y),'altitude':0} for y in range(6,9)]
                    later=MOVEMENT.follow_paid_path(engine,actor,fresh,mode='sky',maximum_distance=2,progress={})
                    self.assertEqual((later['distance'],later['steps'],actor.pos),(2,2,(2,7)))



if __name__ == '__main__':
    unittest.main()
