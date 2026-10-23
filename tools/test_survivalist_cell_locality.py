"""F48: actual cell observations, committed relocation and overnight evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import movement_actions as MOVEMENT
import survivalist_features as V
import state_codec as CODEC
import state_grants as GRANTS
import common_checks as C
from native_scenario_fixture import assert_rejected_unchanged, assert_rejections_unchanged
import test_category2_survivalist_csv as CSV
import test_category3_movement as NATIVE_TELEPORT
from test_completed1255_survivalist_obligations import CompletedSurvivalistObligations


class SurvivalistCellLocalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CompletedSurvivalistObligations.setUpClass()
        cls.r = CSV.SurvivalistCSVTests.r

    def fixture(self, *, mastered=True):
        if mastered:
            e, a, b = CompletedSurvivalistObligations().markdown()
        else:
            f = CSV.SurvivalistCSVTests(); f.r = self.r
            e, a, b = f.fixture()
        e.grid.slow.clear(); e.grid.rough.clear()
        MOVEMENT.observe_cell_terrain(e, [(0, 0), (0, 1)], ['forest'], 'actual forest cells')
        MOVEMENT.observe_cell_terrain(e, [(0, 2), (0, 3), (0, 4), (0, 5)], ['desert'], 'actual desert cells')
        return e, a, b

    def begin(self, e, a, name='night', terrain='forest'):
        return e.survivalist_activity(a, 'begin_night', night_id=name, terrain_name=terrain, reason='actual overnight begins')

    def finish(self, e, a, name='night'):
        return e.survivalist_activity(a, 'finish_night', night_id=name, reason='actual overnight ends')

    def test_native_shift_drops_bonus_and_records_first_departure(self):
        e, a, b = self.fixture()
        self.assertEqual(e.skill_roll(a, '생존', fixed=[1]*6).total, 8)
        self.begin(e, a)
        e.begin_encounter(e.everyone); e.start_round(e.everyone); e.start_of_turn(a)
        e.approach(a, b)
        self.assertEqual(a.pos, (0, 3))
        self.assertEqual(e.skill_roll(a, '생존', fixed=[1]*6).total, 6)
        departure = deepcopy(a.spec['_survivalist_open_night']['departure'])
        self.assertEqual(departure['event'], 'native movement entry')
        self.assertEqual(departure['environment']['position'], [0, 2])
        e.gm.set_position(a, (0, 1), reason='returns to forest')
        self.assertEqual(a.spec['_survivalist_open_night']['departure'], departure)
        assert_rejected_unchanged(e, lambda: self.finish(e, a), reason_pattern='interrupted')

    def test_gm_position_rejects_wrong_night_and_return_does_not_restore_it(self):
        e, a, _ = self.fixture()
        e.gm.set_position(a, (0, 3), reason='actual desert arrival')
        assert_rejected_unchanged(e, lambda: self.begin(e, a), reason_pattern='match current environment')
        e.gm.set_position(a, (0, 0), reason='actual forest arrival')
        self.begin(e, a)
        e.gm.set_position(a, (0, 3), reason='leaves forest during night')
        self.assertEqual(a.spec['_survivalist_open_night']['departure']['event'], 'GM set_position')
        e.gm.set_position(a, (0, 1), reason='returns during same night')
        e.advance_time(60, [a])
        assert_rejected_unchanged(e, lambda: self.finish(e, a), reason_pattern='interrupted')

    def test_noncombat_native_teleport_out_and_back_keeps_interruption(self):
        e, a, _ = self.fixture()
        before=CODEC.dump_engine(e)
        pending=e.teleport(a,(0,3),surface_contact=True,reason_text='trainer Teleporter source remains unspecified')
        self.assertIsInstance(pending,C.PendingDecision)
        self.assertEqual(CODEC.dump_engine(e),before)
        # Trainer Teleporter authority is unresolved; use its existing native Pokemon owner.
        f=NATIVE_TELEPORT.MovementTests(); f.r=self.r; f.setUp()
        e,a=f.e,f.a
        f.base(); e.gm.set_move(a,'move/순간이동',reason='actual learned Pokemon Teleport')
        MOVEMENT.observe_cell_terrain(e,[(1,1)],['forest'],'actual forest origin')
        MOVEMENT.observe_cell_terrain(e,[(3,1)],['desert'],'actual desert destination')
        self.begin(e, a)
        result=e.teleport(a, (3, 1), surface_contact=True, reason_text='observed desert destination')
        self.assertEqual((result['position'],a.pos),((3,1),(3,1)))
        self.assertEqual(V.current_environment(e,a)['terrains'],('desert',))
        self.assertTrue(a.spec['_survivalist_open_night']['left_terrain'])
        e.teleport(a, (1, 1), surface_contact=True, reason_text='observed forest return')
        e.advance_time(60, [a])
        assert_rejected_unchanged(e, lambda: self.finish(e, a), reason_pattern='interrupted')

    def test_cell_reobservation_interrupts_without_movement_and_outranks_scene(self):
        e, a, _ = self.fixture()
        self.begin(e, a)
        MOVEMENT.observe_cell_terrain(e, [(0, 0)], ['desert'], 'actual current cell reclassified')
        self.assertEqual(a.spec['_survivalist_open_night']['departure']['event'], 'GM cell terrain observation')
        e.survivalist_activity(a, 'observe_environment', terrains=['forest'], light='normal', reason='old scene description repeated')
        self.assertEqual(e.skill_roll(a, '생존', fixed=[1]*6).total, 6)
        MOVEMENT.observe_cell_terrain(e, [(0, 0)], ['forest'], 'forest restored later')
        e.advance_time(60, [a])
        assert_rejected_unchanged(e, lambda: self.finish(e, a), reason_pattern='interrupted')

    def test_current_cell_allows_true_night_despite_old_different_scene(self):
        e, a, _ = self.fixture()
        e.survivalist_activity(a, 'observe_environment', terrains=['desert'], light='normal', reason='stale scene-wide desert')
        self.assertEqual(e.skill_roll(a, '생존', fixed=[1]*6).total, 8)
        self.begin(e, a); e.advance_time(60, [a]); row = self.finish(e, a)
        self.assertEqual(row['start_environment']['source'], 'observed_cell')
        self.assertTrue(V.verified_night(e, a, row))

    def test_unobserved_grid_and_mapless_scenes_keep_explicit_gm_fallback(self):
        f = CSV.SurvivalistCSVTests(); f.r = self.r
        for mapless in (False, True):
            with self.subTest(mapless=mapless):
                e, a, _ = f.fixture()
                if mapless: e.grid = None
                f.env(e, a, 'forest')
                for index in range(3):
                    self.begin(e, a, str(index)); e.advance_time(60, [a]); row = self.finish(e, a, str(index))
                    self.assertEqual(row['start_environment']['source'], 'explicit_gm_environment')
                e.survivalist_activity(a, 'select_terrain', terrain_name='forest', minutes=1, reason='three actual GM witnessed nights')
                self.assertEqual(e.skill_roll(a, '생존', fixed=[1]*6).total, 8)

    def test_json_and_gm_restore_preserve_valid_proof_and_interrupted_history(self):
        e, a, _ = self.fixture()
        self.begin(e, a)
        payload = CODEC.dump_engine(e); e.gm.snapshot('valid open night')
        e.gm.set_position(a, (0, 3), reason='temporary departure')
        e.gm.restore('valid open night')
        for world in (e, CODEC.load_engine(self.r, json.loads(json.dumps(payload)))):
            owner = world.everyone[0]
            self.assertEqual(V.selected(world, owner), ('forest',))
            world.advance_time(60, [owner]); self.finish(world, owner)
            self.begin(world, owner, 'interrupted')
            world.gm.set_position(owner, (0, 3), reason='actual departure')
            world.gm.set_position(owner, (0, 1), reason='actual return')
            interrupted = CODEC.dump_engine(world)
            restored = CODEC.load_engine(self.r, json.loads(json.dumps(interrupted)))
            actor = restored.everyone[0]
            self.assertEqual(actor.spec['_survivalist_open_night'], owner.spec['_survivalist_open_night'])
            restored.advance_time(60, [actor])
            assert_rejected_unchanged(restored, lambda: self.finish(restored, actor, 'interrupted'), reason_pattern='interrupted')

    def test_both_csv_paid_sources_use_cell_without_importing_book_nights(self):
        f = CSV.SurvivalistCSVTests(); f.r = self.r
        for clause in V.CSV_CLAUSES:
            with self.subTest(clause=clause):
                e, a, _ = self.fixture(mastered=False)
                row = f.select(e, a, clause=clause)
                f.env(e, a, 'forest')
                self.assertEqual((row['clause_id'], e.elapsed_seconds, a._action_history), (clause,120,['extended']))
                self.assertNotIn('_survivalist_nights', a.spec)
                e.gm.set_position(a, (0, 3), reason='actual observed desert')
                self.assertEqual(e.skill_roll(a, '생존', fixed=[1]*6).total, 6)
                self.assertIn('forest', MOVEMENT.naturewalk_terrains(e,a))
                assert_rejected_unchanged(e, lambda: f.select(e,a,clause=clause), reason_pattern='daily selection exhausted')
                restored = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(e))))
                owner = restored.everyone[0]
                self.assertEqual(restored.skill_roll(owner, '생존', fixed=[1]*6).total, 6)
                self.assertEqual(owner.spec[V.CSV_STATE]['history'][-1]['clause_id'], clause)

    def test_unverified_legacy_nights_stay_stored_but_cannot_create_mastery(self):
        e, a, _ = self.fixture()
        a.spec.pop('_survivalist_terrains')
        for row in a.spec['_survivalist_nights'].values():
            for key in ('source','provenance','owner_id','start_environment','end_environment'): row.pop(key)
        legacy = deepcopy(a.spec['_survivalist_nights'])
        assert_rejected_unchanged(e, lambda: e.survivalist_activity(a, 'select_terrain', terrain_name='forest', minutes=1, reason='legacy unsupported claim'), reason_pattern='three actual completed nights')
        restored = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(e))))
        self.assertEqual(restored.everyone[0].spec['_survivalist_nights'], legacy)

    def test_legacy_selected_talents_restore_without_deletion_but_fail_qualification(self):
        e, a, _ = self.fixture(mastered=False)
        a.spec['feats'].append('feat/내추럴-파이터')
        for terrain, cell in (('forest',(0,0)),('desert',(0,3))):
            e.gm.set_position(a,cell,reason='actual terrain for complete nights')
            for index in range(3):
                name=terrain+str(index); self.begin(e,a,name,terrain); e.advance_time(60,[a]); self.finish(e,a,name)
            e.survivalist_activity(a,'select_terrain',terrain_name=terrain,minutes=1,reason='actual mastered terrain')
        a.spec['feats'].append(V.TALENT); a.spec['feat_ranks']={V.TALENT:1}
        e.survivalist_activity(a,'choose_talents',terrains=['forest','desert'])
        for row in a.spec['_survivalist_nights'].values(): row.pop('provenance')
        saved = deepcopy(a.spec)
        restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(e)))); owner=restored.everyone[0]
        self.assertEqual(owner.spec,saved)
        assert_rejections_unchanged(restored, [lambda: V.selected(restored,owner),lambda: V.talents(restored,owner),lambda: restored.survivalist_activity(owner,'choose_talents',terrains=['forest','desert'])], reason_pattern='legacy history needs explicit historical correction')

    def test_verified_talents_work_outside_habitat_and_independent_naturewalk_survives(self):
        e,a,_=self.fixture(mastered=False)
        a.spec['feats'].append('feat/내추럴-파이터')
        for terrain in ('grassland','mountain'):
            MOVEMENT.observe_cell_terrain(e,[(0,0)],[terrain],'actual mastery terrain')
            for index in range(3):
                name=terrain+str(index); self.begin(e,a,name,terrain);e.advance_time(60,[a]);self.finish(e,a,name)
            e.survivalist_activity(a,'select_terrain',terrain_name=terrain,minutes=1,reason='actual mastered terrain')
        a.spec['feats'].append(V.TALENT);a.spec['feat_ranks']={V.TALENT:1}
        e.survivalist_activity(a,'choose_talents',terrains=['grassland','mountain'])
        GRANTS.grant(a,'capabilities','Naturewalk(cave)','independent:cave','fixture')
        e.gm.set_position(a,(0,3),reason='actual unrelated desert')
        self.assertEqual(e.skill_roll(a,'통찰',fixed=[1]*3,skill_context={'purpose':'distant_object','reason':'distant object in desert'}).total,5)
        self.assertEqual(e.skill_roll(a,'육상',fixed=[1]*4,skill_context={'purpose':'climb','reason':'climbing in desert'}).total,6)
        self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,6)
        a.spec['classes']=[]
        self.assertEqual(MOVEMENT.naturewalk_terrains(e,a),frozenset({'cave'}))


if __name__ == '__main__': unittest.main()
