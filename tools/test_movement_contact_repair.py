"""F10/F36/F38/F39: commit contact before actual cell-entry consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANON = Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools'), str(CANON/'engine'), str(CANON/'tools')]
from engine import Engine
from grid import Grid
import test_category2_hazard_state as HAZARD_FIXTURE
import test_category2_vision_impairment as VISION_FIXTURE
import test_core_ice_lake as ICE_FIXTURE
import test_category2_core_g041_g045_g050 as NICOLETTE_FIXTURE
import effects_ext as EXT
import forced_movement as FORCED
import map_terrain as MAP
import movement_actions as MOVE
import nicolette_gym as NICOLETTE
import survivalist_features as SURVIVAL
import skill_feature_actions as SKILL
import turn as TURN
import world_entities as WORLD


class MovementContactRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for fixture in (HAZARD_FIXTURE.HazardStateTests, VISION_FIXTURE.VisionImpairmentTests,
                        ICE_FIXTURE.IceLakeTests, NICOLETTE_FIXTURE.NicoletteTerrainTests):
            fixture.setUpClass()

    def river(self, *, weight=5, identity='contact', position=(0, 1)):
        case = NICOLETTE_FIXTURE.NicoletteTerrainTests('runTest')
        return case._ice_engine(weight=weight, position=position, identity=identity)

    def paid(self, e, actor, path, *, mode='land', progress=None):
        e.start_round([actor]); e.start_of_turn(actor)
        self.assertTrue(TURN.spend(e, actor, 'shift', 'actual contact test route', movement=True))
        return MOVE.follow_paid_path(e, actor, path, mode=mode, maximum_distance=6, progress=progress)

    def ice(self):
        case = ICE_FIXTURE.IceLakeTests('runTest'); case.setUp()
        flyer = case.pokemon(weight=6, pos=(0, 1))
        goal = case.trainer('contact goal', pos=(2, 1))
        case.adopt(shallow_cells=[(1, 1)], thick_cells=[])
        case.e.grid.blocking.update({(1, 0), (1, 2)})
        return case.e, flyer, goal

    def options(self, identity='blind-contact', faces=(6, 6)):
        return {'movement_id': identity, 'frequency': 'once_per_shift',
                'reason': 'actual observed rough route and one DC10 check',
                'check_options': [{'skill': '곡예', 'fixed': list(faces)}]}

    def test_paid_sky_then_land_spikes_uses_actual_entry_surface(self):
        case = HAZARD_FIXTURE.HazardStateTests('runTest')
        e, setter, flyer = case.install('move/압정뿌리기', target_species='피죤')
        e.gm.set_position(flyer, (3, 0), reason='actual sky entry origin')
        e.gm.set_position(setter, (4, 2), reason='actual approach target')
        e.end_of_turn(setter); e.start_of_turn(flyer, initiative_count=10)
        hp = flyer.hp
        result = e.approach(flyer, setter, movement_mode='sky')
        self.assertEqual(result['position'], (3, 1)); self.assertTrue(flyer.airborne)
        self.assertEqual(flyer.hp, hp); self.assertNotIn('둔화', flyer.conditions)
        e.end_of_turn(flyer)
        landed = self.paid(e, flyer, [(3, 2)], mode='육상')
        self.assertEqual(landed['steps'], 1); self.assertFalse(flyer.airborne)
        self.assertEqual(flyer.hp, hp-max(1, flyer.max_hp//10)); self.assertIn('둔화', flyer.conditions)
        self.assertTrue(e.validate_state()['valid'])

    def test_public_sky_shallow_ice_and_blinded_sky_share_noncontact(self):
        for blinded in (False, True):
            with self.subTest(blinded=blinded):
                e, flyer, goal = self.ice()
                if blinded:
                    flyer.conditions.add('실명'); e.grid.rough.add((1, 1))
                e.start_round([flyer, goal]); e.start_of_turn(flyer)
                e.approach(flyer, goal, movement_mode='sky',
                           blindness_options=self.options() if blinded else None)
                self.assertEqual(flyer.pos, (1, 1)); self.assertTrue(flyer.airborne)
                self.assertEqual(MAP.base_at(e.grid, (1, 1)), 'regular')
                if blinded:
                    row = flyer.spec['_survivalist_shift']
                    self.assertEqual(row['mode'], '공중/부유'); self.assertEqual(len(row['checks']), 1)
                    self.assertTrue(row['checks'][0]['result'].passed)
                self.assertTrue(e.validate_state()['valid'])

    def test_same_rough_sky_profile_with_and_without_blindness_stays_airborne(self):
        for blinded in (False, True):
            with self.subTest(blinded=blinded):
                case = VISION_FIXTURE.VisionImpairmentTests('runTest')
                e, actor, target = case.fresh(grid=Grid(6, 1, rough={(1, 0)}))
                actor.pos=(0, 0); target.pos=(4, 0); actor.spec['movement']['sky']=8
                if blinded: actor.conditions.add('실명')
                TURN.reset_budget(e, actor)
                e.approach(actor, target, movement_mode='sky',
                           blindness_options=self.options(faces=(3, 3, 3, 3)) if blinded else None)
                self.assertEqual(actor.pos, (3, 0)); self.assertTrue(actor.airborne)
                self.assertEqual(actor._action_history, ['shift'])
                if blinded:
                    row=actor.spec['_survivalist_shift']
                    self.assertEqual((row['spent'], row['moved']), (3, 3))
                    self.assertEqual(row['checks'][0]['result'].total, 12)
                self.assertTrue(e.validate_state()['valid'])

    def test_public_sky_over_river_is_not_a_walk(self):
        e, actor = self.river(identity='public-river-flight')
        actor.spec['movement']['sky']=6
        goal=NICOLETTE_FIXTURE.trainer(e.r, 'river goal')
        e.gm.add_combatant(goal, pos=(2, 1), side='wild', reason='actual river goal')
        e.grid.blocking.update({(1, 0), (1, 2)})
        e.start_round([actor, goal]); e.start_of_turn(actor)
        result=e.approach(actor, goal, movement_mode='sky')
        self.assertEqual(result['position'], (1, 1)); self.assertTrue(actor.airborne)
        self.assertEqual(NICOLETTE.state(e)['broken_ice'], [])
        self.assertTrue(e.validate_state()['valid'])

    def test_aerial_altitude_one_preserves_river_then_actual_landing_breaks_once(self):
        e, actor = self.river(identity='aerial-river-flight'); actor.spec['movement']['sky']=6
        progress={}
        path=[{'position': (1, 1), 'altitude': 1, 'gm_distance': 2},
              {'position': (1, 1), 'altitude': 0, 'gm_distance': 1}]
        native=EXT.on_enter_cell; observations=[]
        def enter(engine, subject, cell):
            self.assertEqual(NICOLETTE.state(engine)['broken_ice'], [])
            observations.append((subject.airborne, subject.spec['_movement_altitude']))
            return native(engine, subject, cell)
        with patch.object(EXT, 'on_enter_cell', side_effect=enter):
            result=self.paid(e, actor, path, mode='sky', progress=progress)
        self.assertEqual((result['steps'], result['altitude']), (2, 0))
        self.assertEqual(observations, [(False, 0)])
        self.assertEqual(NICOLETTE.state(e)['broken_ice'], [[1, 1]])
        self.assertEqual(len(actor.spec['_nicolette_ice_entries']), 1)
        before=deepcopy((actor.spec, e.grid.base_terrain, actor.budget))
        MOVE.follow_paid_path(e, actor, path, mode='sky', maximum_distance=6, progress=progress)
        self.assertEqual((actor.spec, e.grid.base_terrain, actor.budget), before)
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_forced_river_entry_preserves_weight_and_airborne_boundaries(self):
        for weight, flying in ((4, False), (5, False), (6, False), (5, True)):
            with self.subTest(weight=weight, flying=flying):
                e, actor = self.river(weight=weight, identity='forced-'+str(weight)+str(flying))
                owner=next(other for other in e.everyone if other is not actor)
                if flying:
                    actor.spec['movement']['sky']=6
                    self.paid(e, actor, [{'position': (0, 1), 'altitude': 1, 'gm_distance': 1}], mode='sky')
                else:
                    e.start_round([actor]); e.start_of_turn(actor)
                before=deepcopy(actor.budget)
                result=FORCED.along_path(e, owner, actor, points=[(0, 1), (1, 1)], source='actual horizontal displacement')
                self.assertEqual((result['moved'], actor.pos), (1, (1, 1)))
                self.assertEqual([1, 1] in NICOLETTE.state(e)['broken_ice'], weight>=5 and not flying)
                self.assertEqual(actor.budget, before)
                if flying:self.assertEqual(actor.spec['_movement_altitude'], 1); self.assertTrue(actor.airborne)
                self.assertTrue(e.validate_state()['valid'])

    def test_cold_water_checks_current_contact_after_departure_flight_restore_and_landing(self):
        e, actor = self.river(identity='current-cold-contact'); actor.spec['movement'].update(sky=6, swim=6)
        self.paid(e, actor, [(1, 1)])
        before=actor.stages['spe']; e.end_of_turn(actor)
        self.assertEqual(actor.stages['spe'], before-1)
        self.paid(e, actor, [(0, 1)]); before=actor.stages['spe']; e.end_of_turn(actor)
        self.assertEqual(actor.stages['spe'], before)
        self.paid(e, actor, [{'position': (1, 1), 'altitude': 1, 'gm_distance': 2}], mode='sky')
        saved=json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        e=Engine.import_state(e.r, saved); actor=WORLD.actor_index(e)[actor.entity_id]
        before=actor.stages['spe']; e.end_of_turn(actor)
        self.assertEqual(actor.stages['spe'], before)
        self.paid(e, actor, [{'position': (0, 1), 'altitude': 0, 'gm_distance': 2}], mode='sky')
        e.end_of_turn(actor)
        self.paid(e, actor, [(1, 1)], mode='swim')
        before=actor.stages['spe']; e.end_of_turn(actor)
        self.assertEqual(actor.stages['spe'], before-1)
        self.assertTrue(e.validate_state()['valid'])

    def test_departure_relocation_or_incapacitation_never_consumes_unreached_river_cell(self):
        for blinded, stop in ((False, 'relocate'), (False, 'faint'), (True, 'relocate'), (True, 'faint')):
            with self.subTest(blinded=blinded, stop=stop):
                e, actor=self.river(identity='stop-'+str(blinded)+stop)
                actor.spec['movement']['sky']=6
                goal=NICOLETTE_FIXTURE.trainer(e.r, 'stopped river goal')
                e.gm.add_combatant(goal, pos=(2, 1), side='wild', reason='actual stopped goal')
                e.grid.blocking.update({(1, 0), (1, 2)})
                if blinded:actor.conditions.add('실명'); e.grid.rough.add((1, 1))
                e.start_round([actor, goal]); e.start_of_turn(actor)
                native=MOVE.departure
                def depart(engine, subject, destination, height, **kwargs):
                    allowed=native(engine, subject, destination, height, **kwargs)
                    if stop=='relocate':subject.pos=(0, 2)
                    else:subject.hp=0
                    return allowed and TURN.can_act(engine, subject)
                with patch.object(MOVE, 'departure', side_effect=depart):
                    e.approach(actor, goal, movement_mode='sky',
                               blindness_options=self.options() if blinded else None)
                self.assertNotEqual(actor.pos, (1, 1))
                self.assertEqual(NICOLETTE.state(e)['broken_ice'], [])
                self.assertNotIn('_nicolette_ice_entries', actor.spec)
                self.assertEqual(actor._action_history, ['shift'])

    def test_entry_relocation_stops_paid_prefix_and_forced_vector_before_next_ice(self):
        for forced in (False, True):
            with self.subTest(forced=forced):
                e, actor=self.river(identity='entry-relocate-'+str(forced))
                owner=next(other for other in e.everyone if other is not actor)
                native=EXT.on_enter_cell
                def relocate(engine, subject, cell):
                    result=native(engine, subject, cell)
                    subject.pos=(0, 2)
                    return result
                with patch.object(EXT, 'on_enter_cell', side_effect=relocate):
                    if forced:
                        result=FORCED.along_path(e, owner, actor, points=[(0, 1), (1, 1), (1, 2)], source='actual river relocation')
                        self.assertEqual(result['stopped_by'], 'relocated'); self.assertEqual(result['moved'], 1)
                    else:
                        result=self.paid(e, actor, [(1, 1), (1, 2)])
                        self.assertEqual(result['steps'], 1)
                self.assertEqual(actor.pos, (0, 2))
                self.assertEqual(NICOLETTE.state(e)['broken_ice'], [[1, 1]])
                self.assertEqual(len(actor.spec['_nicolette_ice_entries']), 1)

    def test_blinded_failed_dc10_stops_on_actual_airborne_cell_without_breaking_ice(self):
        e, actor, goal=self.ice(); actor.conditions.add('실명'); e.grid.rough.add((1, 1))
        e.start_round([actor, goal]); e.start_of_turn(actor)
        e.approach(actor, goal, movement_mode='sky', blindness_options=self.options(faces=(1, 1)))
        row=actor.spec['_survivalist_shift']
        self.assertEqual((actor.pos, row['moved'], row['spent']), ((1, 1), 1, 1))
        self.assertFalse(row['checks'][0]['result'].passed)
        self.assertIn('넘어짐', actor.conditions); self.assertTrue(actor.airborne)
        self.assertEqual(MAP.base_at(e.grid, (1, 1)), 'regular')
        self.assertEqual(actor._action_history, ['shift'])
        self.assertTrue(e.validate_state()['valid'])

    def test_blinded_later_choice_failure_json_resume_keeps_airborne_prefix_and_one_shift(self):
        case=VISION_FIXTURE.VisionImpairmentTests('runTest')
        e, actor, goal=case.fresh(grid=Grid(6, 1, rough={(1, 0), (2, 0)}))
        actor.pos=(0, 0); goal.pos=(4, 0)
        actor.spec['movement']['sky']=8; actor.spec['weight_class']=5
        actor.spec['skills']['집중']=4; actor.spec.setdefault('feats', []).append(SKILL.MONKEY)
        actor.conditions.add('실명')
        NICOLETTE.configure(e, heights={(0, 0):0, (1, 0):0, (2, 0):0}, ladder_links=[],
            snow_cells=[(5, 0)], brush_cells=[(5, 0)], ice_cells=[(1, 0), (2, 0)],
            pc_deploy_cells=[(0, 0)], gym_deploy_cells=[(4, 0)], nicolette_cell=(3, 0),
            reason='GM adopts narrow river for actual blinded continuation')
        TURN.reset_budget(e, actor)
        options=self.options('blind-river-resume', faces=(3, 3, 3, 3))
        options['frequency']='each_hazard_cell'
        options['check_options'][0].update(roll_id='river-one', feature=SKILL.MONKEY,
            feature_options={'decision':lambda first:False})
        options['check_options'].append(dict(skill='곡예', fixed=[1]*4,
            roll_id='river-two', feature=SKILL.MONKEY, feature_options={'decision':lambda first:'invalid'}))
        with self.assertRaisesRegex(ValueError, 'boolean'):
            e.approach(actor, goal, movement_mode='sky', blindness_options=options)
        self.assertEqual(actor.pos, (1, 0)); self.assertTrue(actor.airborne)
        self.assertEqual(NICOLETTE.state(e)['broken_ice'], [])
        first=SKILL.event(e, actor, 'river-two').first
        saved=json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        e=Engine.import_state(e.r, saved); index=WORLD.actor_index(e)
        actor=index[actor.entity_id]; goal=index[goal.entity_id]
        options['check_options'][1]['feature_options']={'decision':lambda first:True, 'reroll_faces':[3]*4}
        e.approach(actor, goal, movement_mode='sky', blindness_options=options)
        self.assertEqual(actor.pos, (3, 0)); self.assertTrue(actor.airborne)
        self.assertEqual(SKILL.event(e, actor, 'river-two').first, first)
        self.assertEqual((actor._action_history.count('shift'), actor._action_history.count('free')), (1, 1))
        self.assertEqual(NICOLETTE.state(e)['broken_ice'], [])
        row=actor.spec['_survivalist_shift']
        self.assertEqual((row['moved'], len(row['checks'])), (3, 2))
        before=e.export_state()
        e.approach(actor, goal, movement_mode='sky', blindness_options=options)
        self.assertEqual(e.export_state(), before)
        self.assertTrue(e.validate_state()['valid'])

    def test_native_teleport_entry_reuses_contact_hook_without_affecting_aerial_transfer(self):
        for surface in (False, True):
            with self.subTest(surface=surface):
                e, actor=self.river(identity='teleport-contact-'+str(surface))
                actor.spec['movement'].update(teleport=6, sky=6)
                e.start_round([actor]); e.start_of_turn(actor)
                result=MOVE.teleport(e, actor, (1, 1), surface_contact=surface,
                    altitude=0 if surface else 1, gm_distance=1,
                    reason_text='actual river transfer plane', sky_air_policy='sky_unlimited')
                self.assertEqual(result['position'], (1, 1))
                self.assertEqual([1, 1] in NICOLETTE.state(e)['broken_ice'], surface)
                self.assertEqual(actor.airborne, not surface)
                self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':
    unittest.main()
