"""C11-080/081: source-selected adoption and actual native consumer boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
from state_codec import StateCodecError
import ice_lake as ICE, body_state as BODY, map_terrain as MAP
import movement_actions as MOVE, turn as TURN, combat_damage as DAMAGE


class IceLakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(ROOT, ruleset='core')
    def setUp(self):
        self.e = Engine(self.r, 1180)
        self.e.grid = Grid(10, 10)
    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        BODY.observe(self.e, actor, [(0, 0)], reason='actual mapped one-cell body')
        return actor
    def trainer(self, name='attacker', pos=(0, 1)):
        return self.add(build_trainer(self.r, name, 10,
            dict(hp=10, atk=10, **{'def': 10}, spa=10, spd=10, spe=10),
            pos=pos, moves=['move/몸통박치기', 'move/지진', 'move/불꽃세례'],
            skills={'곡예': 2}, abilities=[], extra={'movement': {'land': 6, 'swim': 6}}))
    def pokemon(self, weight=5, pos=(0, 1), **extra):
        return self.add(build_pokemon(self.r, '브케인', 10, wild=True,
            moves=['move/몸통박치기'], abilities=[], pos=pos,
            extra=dict(weight_class=weight, movement={'land': 6, 'swim': 6, 'sky': 6},
                       movement_basis='current', skills={'곡예': 2}, **extra)))
    def adopt(self, **options):
        base = dict(shallow_cells=[(1, 1), (2, 1)], thick_cells=[(3, 1)],
                    water_air_available=False, gm_id='actual-gm', reason='GM adopts this printed ice lake')
        base.update(options)
        return ICE.adopt(self.e, **base)
    def shift(self, actor, path, mode='land'):
        self.e.start_round([actor]); self.e.start_of_turn(actor)
        self.assertTrue(TURN.spend(self.e, actor, 'shift', 'actual paid ice path', movement=True))
        return MOVE.follow_paid_path(self.e, actor, path, mode=mode, maximum_distance=6)
    def attack(self, actor, target, *, mid='move/몸통박치기', damage=40, faces=(6, 6), natural=18, aim=None):
        self.e.start_round([actor, target]); self.e.start_of_turn(actor)
        roll = Engine.skill_roll
        def actual_roll(engine, subject, skill, **kw):
            self.assertEqual(skill, '곡예')
            return roll(engine, subject, skill, fixed=faces, **kw)
        with patch.object(Engine, 'd20', return_value=natural), patch.object(DAMAGE, 'scale', return_value=damage), patch.object(Engine, 'skill_roll', new=actual_roll):
            if aim is None: return self.e.use_move(actor, target, mid)
            return self.e.use_move_on(actor, target, mid, self.e.everyone, aim=aim)
    def proof(self): return next(reversed(self.e._move_completions.values()))[ICE.KEY]

    def test_weight_four_five_six_and_actual_pokemon_only(self):
        for weight in (4, 5, 6):
            with self.subTest(weight=weight):
                self.setUp(); p = self.pokemon(weight=weight); self.adopt()
                out = self.shift(p, [(1, 1)])
                self.assertEqual(out['steps'], 1)
                self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'underwater' if weight >= 5 else 'regular')
                self.assertNotIn('넘어짐', p.conditions)
        self.setUp(); trainer = self.trainer(); self.adopt()
        self.shift(trainer, [(1, 1)])
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'regular')

    def test_thick_ice_airborne_and_ordinary_map_do_not_break(self):
        p = self.pokemon(weight=6); self.adopt(shallow_cells=[], thick_cells=[(1, 1)])
        self.shift(p, [(1, 1)])
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'regular')
        self.setUp(); p = self.pokemon(weight=6)
        p.airborne = True; p.spec['_movement_altitude'] = 2
        self.adopt()
        self.shift(p, [{'position': (1, 1), 'altitude': 2}], mode='sky')
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'regular')
        self.setUp(); p = self.pokemon(weight=6)
        self.shift(p, [(1, 1)])
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'regular')

    def test_actual_full_body_contacts_break_only_shallow_cells(self):
        p = self.pokemon(weight=5)
        BODY.observe(self.e, p, [(0, 0), (0, 1)], reason='actual two-cell Pokemon body')
        self.adopt(shallow_cells=[(1, 1), (1, 2), (2, 1)], thick_cells=[])
        self.shift(p, [(1, 1)])
        self.assertEqual([MAP.base_at(self.e.grid, p) for p in [(1, 1), (1, 2), (2, 1)]],
                         ['underwater', 'underwater', 'regular'])

    def test_actual_fall_and_entry_into_existing_hole_share_native_water(self):
        p = self.pokemon(weight=5, pos=(1, 1)); p.airborne = True
        p.spec['_movement_altitude'] = 2; self.adopt()
        self.e.falling_damage(p, action_id='actual-lake-fall', meters=1,
            intentional=False, reason='actual fall lands on adopted shallow ice', fixed_damage=[1])
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'underwater')
        self.assertFalse(p.airborne); self.assertNotIn('넘어짐', p.conditions)
        self.assertEqual((p.spec['_respiration']['medium'], p.spec['_respiration']['breathing']), ('water', False))
        p.on_field = False
        q = self.pokemon(weight=1, pos=(0, 1))
        self.shift(q, [(1, 1)], mode='swim')
        self.assertEqual(q.pos, (1, 1)); self.assertNotIn('넘어짐', q.conditions)

    def test_optional_slow_terrain_uses_actual_paid_movement_cost(self):
        for slow, expected in ((False, 1), (True, 2)):
            with self.subTest(slow=slow):
                self.setUp(); p = self.pokemon(weight=4); self.adopt(slow=slow)
                self.assertEqual(self.shift(p, [(1, 1)])['distance'], expected)

    def test_existing_hole_allows_first_surface_fall_without_granting_swimming(self):
        p = self.pokemon(weight=5, pos=(1, 1)); self.adopt()
        p.on_field = False
        q = self.trainer('walker', pos=(0, 1))
        q.spec['movement']['swim'] = 0
        MAP.observe(self.e, [(2, 1)], base='underwater', reason='second actual adopted ice hole')
        out = self.shift(q, [(1, 1), (2, 1)])
        self.assertEqual((q.pos, out['steps']), ((1, 1), 1))
        self.assertEqual(q.spec['_respiration']['medium'], 'water')
        self.assertFalse(MAP.can_travel(self.e, q, (2, 1), 'land'))
        self.assertFalse(MAP.can_travel(self.e, q, (2, 1), 'swim'))
        q.pos = (6, 1)
        MAP.observe(self.e, [(7, 1)], base='underwater', reason='ordinary water outside adopted ice')
        self.assertFalse(MAP.can_travel(self.e, q, (7, 1), 'land'))

    def test_ground_move_breaks_frozen_actual_effect_area_once_including_empty_cells(self):
        actor = self.trainer(pos=(4, 4)); target = self.trainer('target', pos=(5, 4))
        self.adopt(shallow_cells=[(5, 4), (4, 5), (9, 9)], thick_cells=[(5, 5)],
                   breaking_moves=['move/지진'])
        self.attack(actor, target, mid='move/지진', damage=1, aim=(4, 4))
        for cell in ((5, 4), (4, 5), (5, 5)):
            self.assertEqual(MAP.base_at(self.e.grid, cell), 'underwater')
        self.assertEqual(MAP.base_at(self.e.grid, (9, 9)), 'regular')
        self.assertEqual(self.proof()['phase'], 'resolved')
        frozen = deepcopy(self.e.grid.base_terrain)
        import move_completion as COMPLETE
        COMPLETE.refresh(self.e)
        self.assertEqual(self.e.grid.base_terrain, frozen)
        self.assertNotIn('넘어짐', target.conditions)

    def test_other_gm_selected_move_breaks_its_actual_target_cell_only(self):
        actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(breaking_moves=['move/불꽃세례'])
        self.attack(actor, target, mid='move/불꽃세례', damage=1)
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'underwater')
        self.assertEqual(MAP.base_at(self.e.grid, (2, 1)), 'regular')
        self.setUp(); actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(); self.attack(actor, target, damage=1)
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'regular')

    def test_multi_target_injury_checks_resolve_once_before_the_same_area_breaks(self):
        actor = self.trainer(pos=(4, 4)); first = self.trainer('first', pos=(5, 4))
        second = self.trainer('second', pos=(4, 5))
        self.adopt(shallow_cells=[(5, 4), (4, 5)], thick_cells=[],
            breaking_moves=['move/지진'], injury_check={'dc': 99, 'reason': 'GM area ice DC'})
        self.attack(actor, first, mid='move/지진', faces=(1, 1), aim=(4, 4))
        self.assertEqual(set(self.proof()['injury_checks']), {first.entity_id, second.entity_id})
        for target in (first, second):
            self.assertIn('넘어짐', target.conditions)
            self.assertEqual(target.spec['_respiration']['medium'], 'water')
        import move_completion as COMPLETE
        with patch.object(Engine, 'skill_roll', side_effect=AssertionError('one check per real recipient')):
            COMPLETE.refresh(self.e)

    def test_missed_actual_area_still_breaks_ice_without_an_injury_check(self):
        actor = self.trainer(pos=(4, 4)); target = self.trainer('target', pos=(5, 4))
        self.adopt(shallow_cells=[(5, 4), (4, 5)], thick_cells=[],
            breaking_moves=['move/지진'], injury_check={'dc': 99, 'reason': 'GM area ice DC'})
        self.attack(actor, target, mid='move/지진', natural=1, aim=(4, 4))
        self.assertEqual(self.proof()['injury_checks'], {})
        self.assertEqual(MAP.base_at(self.e.grid, (5, 4)), 'underwater')

    def test_empty_selected_area_pays_one_native_activation_without_accuracy_or_damage(self):
        actor = self.trainer(pos=(4, 4))
        self.adopt(shallow_cells=[(5, 4), (4, 5)], thick_cells=[], breaking_moves=['move/지진'])
        self.e.start_round([actor]); self.e.start_of_turn(actor)
        with patch.object(Engine, 'd20', side_effect=AssertionError('empty area has no accuracy')), patch.object(Engine, 'roll_damage', side_effect=AssertionError('empty area has no damage')):
            self.e.use_move_on(actor, actor, 'move/지진', [actor], aim=(4, 4))
        self.assertEqual(MAP.base_at(self.e.grid, (5, 4)), 'underwater')
        completion = next(iter(self.e._move_completions.values()))
        self.assertEqual((completion['activation'], completion['targets'], completion['phase']),
                         ('empty_area_field', [], 'complete'))
        self.assertEqual(actor.move_uses['move/지진'], 1)
        self.assertEqual(actor.budget['standard'], 0)

    def test_unadopted_empty_scope_and_fabricated_completion_cannot_break_ice(self):
        actor = self.trainer(pos=(4, 4))
        import move_activation as ACTIVATION
        with self.assertRaises(ValueError):
            with ACTIVATION.open_empty_field_scope(self.e, actor, 'move/지진', [(5, 4)], []): pass
        self.adopt(shallow_cells=[(5, 4)], thick_cells=[], breaking_moves=['move/지진'])
        fake = {'id': 'fake', 'actor': actor, 'move_id': 'move/지진',
                'move': dict(self.r.move('move/지진'), _area_aim=(4, 4)),
                'targets': [], 'phase': 'completion_effects', 'results': {}, 'sealed': True}
        ICE.bind_move(self.e, fake)
        with self.assertRaisesRegex(ValueError, 'actual native'):
            ICE.observe_completion(self.e, fake)
        self.assertEqual(MAP.base_at(self.e.grid, (5, 4)), 'regular')

    def test_injury_attack_uses_explicit_gm_dc_and_native_check_pass_fail(self):
        for faces, passed in (((6, 6), True), ((1, 1), False)):
            with self.subTest(faces=faces):
                self.setUp(); actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
                self.adopt(injury_check={'dc': 8, 'reason': 'GM sets the unsupplied ice DC'})
                self.attack(actor, target, faces=faces)
                self.assertGreater(target.injuries, 0)
                proof = self.proof()['injury_checks'][target.entity_id]
                self.assertEqual((proof['dc'], proof['passed']), (8, passed))
                self.assertEqual('넘어짐' in target.conditions, not passed)
                self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'regular')

    def test_miss_noninjuring_attack_passive_loss_and_unadopted_check_are_excluded(self):
        for mode in ('miss', 'small', 'disabled', 'airborne'):
            with self.subTest(mode=mode):
                self.setUp(); actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
                if mode == 'airborne': target.airborne = True; target.spec['_movement_altitude'] = 2
                self.adopt(injury_check=None if mode == 'disabled' else {'dc': 99, 'reason': 'GM severe ice'})
                self.attack(actor, target, damage=1 if mode == 'small' else 40, natural=1 if mode == 'miss' else 18)
                self.assertEqual(self.proof()['injury_checks'], {})
                self.assertNotIn('넘어짐', target.conditions)
        self.setUp(); target = self.trainer('target', pos=(1, 1))
        self.adopt(injury_check={'dc': 99, 'reason': 'GM severe ice'})
        self.e.take_damage(target, 40)
        self.assertNotIn('넘어짐', target.conditions)
        self.assertFalse(getattr(self.e, '_move_completions', {}))

    def test_explicit_native_move_injury_effect_uses_actual_recipient_completion(self):
        actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(injury_check={'dc': 99, 'reason': 'GM adopts explicit injury check'})
        self.e.rule_effect('move/몸통박치기', 'add',
            effect={'type': 'injury', 'value': 1, 'target': 'target'}, reason='actual GM Move injury effect')
        self.attack(actor, target, damage=1, faces=(1, 1))
        self.assertEqual(target.injuries, 1)
        self.assertEqual(self.proof()['injury_checks'][target.entity_id]['injuries'], 1)
        self.assertIn('넘어짐', target.conditions)

    def test_actual_injury_contact_survives_subsequent_native_push_off_ice(self):
        actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(shallow_cells=[(1, 1)], thick_cells=[],
            injury_check={'dc': 99, 'reason': 'GM adopts ice injury check'})
        self.e.rule_effect('move/몸통박치기', 'add',
            effect={'type': 'push', 'meters': 1, 'target': 'target'}, reason='actual same-Move push')
        self.attack(actor, target, faces=(1, 1))
        self.assertEqual(target.pos, (2, 1))
        self.assertIn('넘어짐', target.conditions)
        self.assertGreater(self.proof()['injury_checks'][target.entity_id]['injuries'], 0)

    def test_adoption_missing_policy_invalid_identity_and_source_reject_before_mutation(self):
        before = deepcopy(vars(self.e.grid))
        for options in ({'injury_check': {}}, {'injury_check': {'dc': True, 'reason': 'invalid'}},
                        {'shallow_cells': [(1, 1), (1, 1)]}, {'gm_id': ''},
                        {'breaking_moves': ['move/not-a-real-move']}):
            with self.subTest(options=options), self.assertRaises((ValueError, KeyError)):
                self.adopt(**options)
            self.assertEqual(vars(self.e.grid), before)
        with patch.object(self.r, 'select_source_definition', return_value={'selected_id': 'different-source'}):
            with self.assertRaises(ValueError): self.adopt()
        self.assertEqual(vars(self.e.grid), before)

    def test_gm_snapshot_and_fresh_json_restore_preserve_water_and_completed_check(self):
        actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(injury_check={'dc': 99, 'reason': 'GM explicit sample DC'}, breaking_moves=['move/몸통박치기'])
        self.attack(actor, target, faces=(1, 1))
        self.e.gm.snapshot('actual-ice')
        self.e.grid.base_terrain['1,1'] = 'regular'
        self.e.gm.restore('actual-ice')
        self.assertEqual(MAP.base_at(self.e.grid, (1, 1)), 'underwater')
        loaded = Engine.import_state(Rules(ROOT, ruleset='core'), json.loads(json.dumps(self.e.export_state())))
        self.assertEqual(ICE.state(loaded), ICE.state(self.e))
        self.assertEqual(loaded.grid.base_terrain, self.e.grid.base_terrain)
        restored = next(a for a in loaded.everyone if a.entity_id == target.entity_id)
        self.assertIn('넘어짐', restored.conditions)
        import move_completion as COMPLETE
        old = (restored.hp, restored.injuries, deepcopy(loaded.grid.base_terrain))
        COMPLETE.refresh(loaded)
        self.assertEqual((restored.hp, restored.injuries, loaded.grid.base_terrain), old)

    def test_adoption_and_native_check_proof_tampering_reject_on_save(self):
        actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(injury_check={'dc': 8, 'reason': 'GM sample policy'})
        self.attack(actor, target)
        actual = ICE.state(self.e)
        actual['injury_check']['dc'] = 0
        with self.assertRaises(StateCodecError): self.e.export_state()
        actual['injury_check']['dc'] = 8
        self.proof()['injury_checks'][target.entity_id]['passed'] = False
        with self.assertRaises(StateCodecError): self.e.export_state()

    def test_late_native_slip_failure_rolls_back_damage_action_roll_and_terrain(self):
        actor = self.trainer(); target = self.trainer('target', pos=(1, 1))
        self.adopt(injury_check={'dc': 99, 'reason': 'GM adopted sample policy'}, breaking_moves=['move/몸통박치기'])
        self.e.start_round([actor, target]); self.e.start_of_turn(actor)
        before = (target.hp, target.injuries, deepcopy(vars(self.e.grid)), deepcopy(actor.budget), self.e.rng.getstate())
        with patch.object(Engine, 'd20', return_value=18), patch.object(DAMAGE, 'scale', return_value=40), patch.object(Engine, 'apply_status', side_effect=ValueError('late native ice failure')):
            with self.assertRaisesRegex(ValueError, 'late native ice failure'):
                self.e.use_move(actor, target, 'move/몸통박치기')
        self.assertEqual((target.hp, target.injuries, vars(self.e.grid), actor.budget, self.e.rng.getstate()), before)
        self.assertFalse(getattr(self.e, '_move_completions', {}))
