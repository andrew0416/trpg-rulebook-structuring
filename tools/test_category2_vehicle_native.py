"""Five vehicle clauses through concrete bodies, damage, repair and control."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine, Rules, Combatant
from builder import build_pokemon
from grid import Grid
from state_codec import dump_engine, load_engine, StateCodecError
import test_category2_special_entities as FIXTURES
import vehicle_native as N
import special_entities as S
import world_entities as W
import state_grants as G
import repair_breach as B
import repair_restore as REPAIR
import control_remote as REMOTE


class NativeVehicleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.poly = Rules(str(ROOT), ruleset='polygon')

    trainer = FIXTURES.SpecialTests.trainer

    def setUp(self):
        self.e = Engine(self.poly, 39); self.e.grid = Grid(24, 12)
        self.a = self.trainer(self.poly, 'actual-vehicle-owner')
        self.a.spec.update(money=100000, crafting_scrap={'차량': 0})
        self.a.spec['skills'].update({'기술학': 4, '집중': 4})
        self.e.everyone = self.e.gm.everyone = [self.a]

    def snap(self):
        return dump_engine(self.e)

    def register(self, identity='car', template='basic', occupied=True, modifications=()):
        N.register_template(self.e, self.a, identity, template, maximum_occupants=3,
                            location={'kind': 'grid', 'cell': [1, 1]}, modifications=modifications,
                            reason='actual selected vehicle template')
        row = self.e._physical_objects[identity]
        if occupied:
            proposed = deepcopy(row); proposed.update(driver_id=self.a.entity_id, passenger_ids=[self.a.entity_id])
            S.observe(self.e, proposed, reason='actual driver and passenger relation')
        return row

    def policy(self):
        value = json.loads((ROOT / 'data/examples/control-vehicle.json').read_text(encoding='utf-8'))[0]
        value['movement']['override'] = None
        return value

    def breach(self):
        return json.loads((ROOT / 'data/examples/repair-breach.json').read_text(encoding='utf-8'))[0]

    def start(self, actor=None):
        self.e.begin_encounter(self.e.everyone); self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor or self.a)

    def move(self, identity='car', actor=None, value=None, path=None, request='drive', **options):
        return self.e.operate_machine(actor or self.a, identity, value or self.policy(), command='move',
            request_id=request, body_eligible=options.pop('body_eligible', True), reason='actual native vehicle movement',
            path=path or [[1, 1], [2, 1], [3, 1]], **options)

    def hit(self, base, *, kind='노말', passengers=None, event='hit', identity='car'):
        return N.hit(self.e, self.a, identity, move_type=kind, after_defense=base,
            passenger_after_defense={} if passengers is None else passengers, event_id=event,
            reason='actual typed attack resolved against vehicle', breach_policy=self.breach())

    def pokemon(self):
        p = Combatant(self.poly, build_pokemon(self.poly, '폴리곤', 5, name='actual-driver',
                      extra={'trainer_id': self.a.entity_id, 'tutor_points': 2}))
        p.pos = (1, 1); self.e.everyone.append(p)
        return p

    def test_ranked_upgrade_purchases_use_all_three_source_columns_and_actual_consumers(self):
        for template, expected in [('personal', (80, 5, 9, 2000, 20)), ('basic', (120, 10, 7, 3000, 40)), ('large', (250, 15, 6, 4000, 60))]:
            row = self.register(template, template, occupied=False); hp, defense, speed, cost, amount = expected
            before = self.a.spec['money']
            for n in range(3):
                result = N.acquire_upgrade(self.e, self.a, template, 'structural_integrity', request_id='structure/' + str(n), reason='actual ranked purchase')
                self.assertEqual(result['cost'], cost)
            self.assertEqual((row['hp'], row['max_hp']), (hp + 3 * amount, hp + 3 * amount))
            for n in range(2): N.acquire_upgrade(self.e, self.a, template, 'armored_plating', request_id='armor/' + str(n), reason='actual armor purchase')
            bonus = {'personal': 4, 'basic': 6, 'large': 8}[template]
            self.assertEqual((row['stats']['def'], row['stats']['spd']), (defense + 2 * bonus,) * 2)
            N.acquire_upgrade(self.e, self.a, template, 'vehicle_speed', request_id='speed', reason='actual movement upgrade')
            self.assertEqual(row['overland'], speed + 1); self.assertLess(self.a.spec['money'], before)
            defended = N.defend(self.e, template, damage_class='물리', total=40)
            self.hit(defended, identity=template, event='actual-defense-consumer')
            self.assertEqual(row['hp'], row['max_hp'] - max(1, 40 - defense - 2 * bonus))
            saved = self.snap()
            for upgrade in ('structural_integrity', 'armored_plating'):
                with self.assertRaisesRegex(ValueError, 'rank'): N.acquire_upgrade(self.e, self.a, template, upgrade, request_id='overflow/' + upgrade, reason='rank cannot be exceeded')
                self.assertEqual(saved, self.snap())
            self.assertEqual(result, N.acquire_upgrade(self.e, self.a, template, 'structural_integrity', request_id='structure/2', reason='actual ranked purchase'))

    def test_combat_mobility_and_added_replaced_modes_keep_designed_occupancy_without_power(self):
        quote = lambda uid, operation, mode, cost: dict(id=uid, kind='movement', operation=operation, mode=mode, cost=cost, reason='explicit GM adoption of optional customization guidance')
        row = self.register(modifications=[quote('added-swim', 'add', 'swim', 8250)])
        derived = N.validate_record(self.e, row); self.assertEqual(derived['movement'], {'land': 7, 'swim': 7})
        self.assertEqual(derived['total_cost'], 18250); self.assertNotIn('power', row['stats'])
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'combat maneuverability'): self.move()
        self.assertEqual(before, self.snap())
        N.acquire_upgrade(self.e, self.a, 'car', 'vehicle_speed', request_id='speed-for-movement', reason='actual upgraded maneuverability')
        self.start(); result = self.move()
        self.assertEqual((result['remaining'], row['location']['cell']), (6, (3, 1)))
        self.assertEqual((self.a.pos, self.a.budget['standard']), ((3, 1), 0))
        self.e.end_encounter(); replaced = self.register('hover', 'personal', occupied=False, modifications=[quote('replacement', 'replace', 'levitate', 7500)])
        self.assertEqual(N.validate_record(self.e, replaced)['movement'], {'levitate': 9}); self.assertEqual(replaced['overland'], 0)
        result = self.hit(40, kind='땅', identity='hover', event='ground-immunity')
        self.assertEqual((result['type_multiplier'], replaced['hp']), ([0, 1], 80))
        self.assertEqual(N.policy(self.e)['mobility_guidance']['within_designed_occupancy_penalty'], 0)

    def test_unranked_upgrade_columns_feed_actual_breach_typing_and_scene_shield_consumers(self):
        row = self.register(template='personal', occupied=False)
        for upgrade, cost in [('breach_resistance', 1500), ('reinforced_alloys', 5000), ('shield_generator', 3000)]:
            result = N.acquire_upgrade(self.e, self.a, 'car', upgrade, request_id=upgrade, reason='actual sourced vehicle upgrade')
            self.assertEqual(result['cost'], cost)
        self.assertEqual((row['breach_security'], row['breach_capacity']), (2, 5))
        self.assertEqual(self.hit(40, kind='독', event='immune-poison')['type_multiplier'], [0, 1])
        first = self.hit(40, event='shield'); self.assertEqual((first['type_multiplier'], first['shield_absorbed'], row['hp']), ([1, 2], 20, 80))
        second = self.hit(40, event='shield-used'); self.assertEqual((second['shield_absorbed'], row['hp']), (0, 60))
        self.assertEqual(N.begin_scene(self.e, self.a, 'car')['temporary_hp'], 0)
        self.e.end_scene(); self.assertEqual(N.begin_scene(self.e, self.a, 'car')['temporary_hp'], 20)
        self.a.spec['money'] = 0; saved = self.snap()
        with self.assertRaises(ValueError): N.acquire_upgrade(self.e, self.a, 'car', 'vehicle_speed', request_id='unpaid', reason='missing real payment')
        self.assertEqual(saved, self.snap())

    def test_typed_damage_breach_exposure_and_environment_affect_actual_crew_separately(self):
        row = self.register(); hp = self.a.hp
        for kind in ('condition', 'injury', 'vacuum', 'hazardous_environment'):
            result = N.hazard(self.e, self.a, 'car', kind=kind, event_id='immune/' + kind, reason='actual hostile exposure', hp_loss=4, status='화상')
            self.assertTrue(result['vehicle_immune']); self.assertEqual(result['passengers'], [])
        self.assertEqual((self.a.hp, row['hp']), (hp, 120)); self.assertNotIn('injuries', row)
        self.hit(10, event='before-marker')
        result = self.hit(20, kind='불꽃', passengers={self.a.entity_id: 20}, event='opens-hull')
        self.assertEqual((row['hp'], row['breaches']), (80, 1)); self.assertEqual(result['type_multiplier'], [3, 2])
        self.assertEqual((result['passengers'][0]['requested'], self.a.hp), (10, hp - 10))
        self.assertEqual(row['max_hp'], 120)
        result = N.hazard(self.e, self.a, 'car', kind='vacuum', event_id='exposed-vacuum', reason='hull no longer protects crew', hp_loss=3)
        self.assertEqual((result['passengers'][0]['id'], self.a.hp, row['hp']), (self.a.entity_id, hp - 13, 80))
        before = self.snap(); self.assertEqual(result, N.hazard(self.e, self.a, 'car', kind='vacuum', event_id='exposed-vacuum', reason='hull no longer protects crew', hp_loss=3)); self.assertEqual(before, self.snap())
        self.a.spec['feats'] = ['feat/긴급-수리']; self.start()
        self.e.emergency_repair_vehicle(self.a, 'car', source='feat/긴급-수리', request_id='actual-patch', reason='actual patch repair', roll_options={'fixed': [6] * 4})
        self.assertEqual((row['breaches'], row['patched_breaches']), (1, 1)); self.assertTrue(B.exposure(self.e, 'car')['protected'])
        protected = self.a.hp
        N.hazard(self.e, self.a, 'car', kind='hazardous_environment', event_id='patched-protection', reason='real patch restores protection', hp_loss=3)
        self.assertEqual(self.a.hp, protected)

    def test_zero_hp_capacity_and_actual_extended_hp_structure_repairs_have_distinct_costs(self):
        row = self.register(); self.hit(120, passengers={self.a.entity_id: 0})
        self.assertEqual(row['hp'], 0); self.assertFalse(S.vehicle_view(row)['operable']); self.assertFalse(row['destroyed'])
        self.start(); before = self.snap()
        with self.assertRaisesRegex(ValueError, 'cannot act'): self.move()
        self.assertEqual(before, self.snap()); self.e.end_encounter()
        organic = REPAIR.vehicle_policy(1, 60); organic['method'] = 'organic'; before = self.snap()
        with self.assertRaisesRegex(ValueError, 'organic'): self.e.restore_object(self.a, 'car', organic, request_id='organic', accessible=True, reason='ordinary healing cannot repair a vehicle')
        self.assertEqual(before, self.snap()); money = self.a.spec['money']; elapsed = self.e.elapsed_seconds
        self.e.repair_vehicle(self.a, 'car', cost=4, seconds=60, request_id='hp-repair', accessible=True, reason='two HP per paid cost')
        self.assertEqual((row['hp'], self.a.spec['money'], self.e.elapsed_seconds), (8, money - 4, elapsed + 60))
        count = row['breaches']; money = self.a.spec['money']
        self.e.repair_breaches(self.a, 'car', count=count, seconds=60, subset='unpatched_first', request_id='structure-repair', accessible=True, reason='one hundred per actual breach')
        self.assertEqual((row['breaches'], row['patched_breaches'], self.a.spec['money']), (0, 0, money - 100 * count)); self.assertTrue(S.vehicle_view(row)['operable'])

    def test_destroyed_vehicle_produces_exact_third_value_salvage_and_late_failure_is_atomic(self):
        row = self.register(template='personal', occupied=False); before = self.snap()
        with patch.object(W, 'register_object', side_effect=RuntimeError('late salvage registration')):
            with self.assertRaisesRegex(RuntimeError, 'late salvage'): self.hit(240)
        self.assertEqual(before, self.snap()); result = self.hit(240)
        self.assertTrue(row['destroyed']); salvage = self.e._physical_objects[result['salvage_id']]['vehicle_salvage']
        self.assertEqual((row['hp'], salvage['cost'], salvage['value_fraction']), (-160, 7500, [7500, 3]))
        before = self.snap(); self.assertEqual(result, self.hit(240)); self.assertEqual(before, self.snap())
        with self.assertRaisesRegex(ValueError, 'destroyed'): self.e.repair_vehicle(self.a, 'car', cost=1, seconds=60, request_id='revive', accessible=True, reason='salvage cannot silently revive original')
        self.assertEqual(before, self.snap())

    def test_actual_training_spends_one_tp_and_revocation_stops_standard_action_driving(self):
        p = self.pokemon(); row = self.register(occupied=False); proposed = deepcopy(row)
        proposed.update(driver_id=p.entity_id, passenger_ids=[p.entity_id]); S.observe(self.e, proposed, reason='actual Pokemon driver')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'body'): N.teach_training(self.e, self.a, p, body_eligible=False, safe=True)
        self.assertEqual(before, self.snap())
        result = N.teach_training(self.e, self.a, p, body_eligible=True, safe=True)
        self.assertEqual((result['point_cost'], p.spec['tutor_points']), (1, 1)); self.start(p)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'body'): self.move(actor=p, body_eligible=False)
        self.assertEqual(before, self.snap()); result = self.move(actor=p)
        self.assertEqual((result['action'], p.budget['standard'], p.pos), ('standard', 0, (3, 1)))
        G.revoke(p, N.TRAINING, engine=self.e); self.e.end_of_turn(p); self.e.start_round(self.e.everyone); self.e.start_of_turn(p); before = self.snap()
        with self.assertRaisesRegex(ValueError, 'Vehicle Training'): self.move(actor=p, request='after-withdrawal', path=[[3, 1], [4, 1]])
        self.assertEqual(before, self.snap())

    def test_datajack_requires_adoption_actual_installation_and_closes_on_uninstall(self):
        p = self.pokemon(); row = self.register(occupied=False); proposed = deepcopy(row); proposed['driver_id'] = p.entity_id
        S.observe(self.e, proposed, reason='actual electronic driver relation')
        for identity in ('datajack', 'electronics'):
            W.register_object(self.e, identity, location={'kind': 'unknown'}, reason='actual interface hardware')
        augment = dict(id='implants', kind='augmentation_set', location={'kind': 'unknown'}, actor_id=p.entity_id,
            body_slots=[], installations=[{'instance_id': 'datajack', 'augmentation_id': 'datajack'}], allow_added_parts=False, essence_enabled=False)
        S.observe(self.e, augment, reason='actual Pokemon Datajack installation')
        self.e.gm.observe_control_device('electronics', 'car', N.SOURCE, True, reason='actual installed electronic vehicle port')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'adoption'): N.connect_datajack_vehicle(self.e, p, 'car', 'datajack', 'electronics', enabled=False, route_id='jack', connected=True, reason='not adopted')
        self.assertEqual(before, self.snap()); N.connect_datajack_vehicle(self.e, p, 'car', 'datajack', 'electronics', enabled=True, route_id='jack', connected=True, reason='explicitly adopted direct Datajack control')
        self.start(p); result = self.move(actor=p, body_eligible=False, remote_route='jack')
        self.assertTrue(result['passed']); self.assertEqual((p.pos, row['location']['cell']), ((1, 1), (3, 1)))
        augment['installations'] = []; S.observe(self.e, augment, reason='actual Datajack removed')
        self.assertEqual(self.e.remote_control_routes(p)['jack']['status'], 'closed'); before = self.snap()
        with self.assertRaisesRegex(ValueError, 'closed'): self.move(actor=p, body_eligible=False, remote_route='jack', request='after-removal', path=[[3, 1], [4, 1]])
        self.assertEqual(before, self.snap())

    def test_json_gm_restore_keep_vehicle_receipts_aliases_and_late_passenger_failure_atomic(self):
        row = self.register(); self.a.custom_conditions['actual_vehicle'] = row
        self.hit(20, kind='불꽃', passengers={self.a.entity_id: 12}, event='saved-hit'); saved = self.snap()
        self.e.gm.snapshot('vehicle-native'); self.e.gm.set_hp(self.a, value=1, reason='later change'); self.e.gm.restore('vehicle-native')
        for e in (self.e, load_engine(self.poly, json.loads(json.dumps(saved, ensure_ascii=False)))):
            actor = W.actor_index(e)[self.a.entity_id]; car = e._physical_objects['car']
            self.assertIs(actor.custom_conditions['actual_vehicle'], car); self.assertTrue(W.validate_world(e)['valid'])
            self.assertIn('saved-hit', car['native_vehicle']['events']); self.assertEqual(car['hp'], 90)
        before = self.snap()
        with patch.object(Engine, '_take_damage', side_effect=RuntimeError('late passenger damage')):
            with self.assertRaisesRegex(RuntimeError, 'late passenger'): self.hit(5, passengers={self.a.entity_id: 12}, event='late-failure')
        self.assertEqual(before, self.snap())
        with self.assertRaisesRegex(ValueError, 'one resolved defense'): self.hit(5, event='missing-passenger')
        self.assertEqual(before, self.snap())
        row = self.e._physical_objects['car']; native = row['native_vehicle']; native['config']['upgrades']['vehicle_speed'] = 1
        config = {k: v for k, v in native['config'].items() if k != 'sha256'}; native['config'] = N._sign(config); row['overland'] += 1
        self.assertFalse(W.validate_world(self.e)['valid'])
        with self.assertRaises(StateCodecError): self.snap()


if __name__ == '__main__':
    unittest.main()
