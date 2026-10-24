"""Actual paid producers, whole occurrences, partial clearing and current restore."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
sys.path.insert(0,str(ROOT/'tools'))
from engine import Engine
import effects as FX
import smoke_regions as SMOKE
import world_entities as WORLD
import test_category2_smoke_regions as BASE


class SmokescreenRegionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):BASE.SmokeTests.setUpClass()

    def fixture(self):
        e,a,b=BASE.SmokeTests().fixture()
        b.pos=(15,15)
        return e,a,b

    def begin(self,e,a):
        # Two actual own turns preserve the ordinary EOT/Scene interval.
        for _ in range(2):
            if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
            e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)

    def smoke(self,e,a,b,aim):
        self.begin(e,a);before=a.move_uses.get('move/연막',0)
        e.use_move_on(a,b,'move/연막',e.everyone,aim=aim)
        self.assertEqual(a.move_uses['move/연막'],before+1)
        identity=next(reversed(e._smoke_regions['regions']))
        cells=e.grid.ranged_blast(aim,3)
        self.assertEqual(e._smoke_regions['regions'][identity]['cells'],cells)
        return identity,cells

    def whirlwind(self,e,a,b,aim=(5,5)):
        self.begin(e,a);before=a.move_uses.get('move/날려버리기',0)
        e.use_move_on(a,b,'move/날려버리기',e.everyone,aim=aim)
        self.assertEqual(a.move_uses['move/날려버리기'],before+1)
        self.assertEqual(a.budget['standard'],0)

    def legacy(self,e):
        # The actual producer ran above; this represents its old flat-only save.
        del e._smoke_regions
        del e._smoke_region_sequence

    def observed(self,e,a):
        return deepcopy((a.budget,a.move_uses,e.zone_cells,e.zones,
            getattr(e,'_smoke_regions',None),getattr(e,'_smoke_region_sequence',None),
            e.rng.getstate(),len(getattr(e,'_move_completions',{}))))

    def test_paid_line_disperses_whole_occurrence_and_retains_disjoint_source(self):
        e,a,b=self.fixture()
        first,cells=self.smoke(e,a,b,(5,5));other,outside=self.smoke(e,a,b,(5,8))
        self.assertTrue(cells-e.grid.line(a.pos,(1,0),6))
        self.whirlwind(e,a,b)
        self.assertEqual(set(e.zone_cells),outside)
        self.assertEqual(set(e._smoke_regions['regions']),{other})
        self.assertNotIn(first,e._smoke_regions['regions'])
        row=list(e._move_completions.values())[-1]
        self.assertEqual((row['activation'],row['targets'],row['results']),('empty_area_field',[],{}))
        self.assertFalse(e.gm_prompts)

    def test_overlapping_survivor_is_not_flooded_but_every_line_intersection_disperses(self):
        e,a,b=self.fixture()
        first,cells=self.smoke(e,a,b,(5,5));survivor,remaining=self.smoke(e,a,b,(5,7))
        a.pos=(4,5);third,far=self.smoke(e,a,b,(8,5));a.pos=(1,5)
        line=e.grid.line(a.pos,(1,0),6)
        self.assertTrue(cells&remaining);self.assertFalse(remaining&line);self.assertTrue(far&line)
        self.whirlwind(e,a,b)
        self.assertEqual(set(e.zone_cells),remaining)
        self.assertEqual(set(e._smoke_regions['regions']),{survivor})
        self.assertNotIn(first,e._smoke_regions['regions']);self.assertNotIn(third,e._smoke_regions['regions'])
        a.pos,b.pos=(1,7),(5,7)
        self.assertEqual(e._prepare_accuracy_context(a,b,e.r.move('struggle'))['zone_pen'],-3)

    def test_actual_razor_wind_removes_only_adjacent_cells_for_current_and_legacy_smoke(self):
        for historical in (False,True):
            with self.subTest(historical=historical):
                e,a,b=self.fixture();identity,cells=self.smoke(e,a,b,(5,5))
                if historical:self.legacy(e)
                a.pos,b.pos=(3,5),(9,5)
                e.gm.set_move(a,'move/칼바람',reason='actual learned Razor Wind partial smoke clearing')
                self.begin(e,a)
                e.use_move(a,b,'move/칼바람')
                adjacent=set(e.grid.burst(a.pos,1))|{a.pos};remaining=cells-adjacent
                self.assertTrue(cells&adjacent);self.assertTrue(remaining)
                self.assertEqual(set(e.zone_cells),remaining)
                if historical:
                    self.assertEqual(e._smoke_regions['regions'],{})
                    self.assertEqual(set(e._smoke_regions['legacy_cells']),remaining)
                else:self.assertEqual(e._smoke_regions['regions'][identity]['cells'],remaining)
                loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
                self.assertEqual(loaded._smoke_regions,e._smoke_regions)
                self.assertEqual(set(loaded.zone_cells),remaining)

    def test_legacy_source_gap_refuses_before_cost_then_explicit_current_adoption_enables_native_line(self):
        e,a,b=self.fixture();_,cells=self.smoke(e,a,b,(5,5));_,outside=self.smoke(e,a,b,(5,8))
        self.legacy(e)
        e=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        index=WORLD.actor_index(e);a,b=index[a.entity_id],index[b.entity_id];b.pos=(5,5)
        self.begin(e,a)
        before=self.observed(e,a)
        for direct in (False,True):
            with self.assertRaisesRegex(ValueError,'legacy smoke without observed region membership'):
                if direct:e.use_move(a,b,'move/날려버리기')
                else:e.use_move_on(a,b,'move/날려버리기',e.everyone,aim=(5,5))
            self.assertEqual(self.observed(e,a),before)
        with self.assertRaisesRegex(ValueError,'existing legacy smoke cells'):
            e.gm.observe_smoke_region([*cells,(19,19)],reason='not actually smoke')
        with self.assertRaisesRegex(ValueError,'reason required'):
            e.gm.observe_smoke_region(cells,reason='')
        self.assertEqual(self.observed(e,a),before)
        identity=e.gm.observe_smoke_region(cells,reason='GM observes this one current original smoke occurrence')
        observed=e._smoke_regions['regions'][identity]
        self.assertEqual((observed['source'],observed['observation_reason']),
                         ('gm/observed-current-smoke','GM observes this one current original smoke occurrence'))
        adoption=next(row for row in reversed(e.rulings.log) if row['what']=='현재 연막 영역 관측')
        self.assertEqual(adoption['after'],observed)
        self.assertEqual(adoption['reason'],observed['observation_reason'])
        self.assertEqual(set(e._smoke_regions['legacy_cells']),outside)
        adopted=self.observed(e,a)
        with self.assertRaisesRegex(ValueError,'existing legacy smoke cells'):
            e.gm.observe_smoke_region(cells,reason='duplicate current membership is not a new legacy observation')
        self.assertEqual(self.observed(e,a),adopted)
        self.whirlwind(e,a,b)
        self.assertEqual(set(e.zone_cells),outside)
        self.assertNotIn(identity,e._smoke_regions['regions'])

    def test_new_overlapping_producer_does_not_fabricate_membership_for_older_opaque_cells(self):
        e,a,b=self.fixture();_,cells=self.smoke(e,a,b,(5,5));self.legacy(e)
        current,_=self.smoke(e,a,b,(5,5))
        current_only,outside=self.smoke(e,a,b,(5,8))
        self.assertEqual(set(e._smoke_regions['legacy_cells']),cells)
        self.begin(e,a);before=self.observed(e,a)
        with self.assertRaisesRegex(ValueError,'existing legacy smoke cells'):
            e.gm.observe_smoke_region(outside,reason='native current-only cells have no unbound legacy membership')
        self.assertEqual(self.observed(e,a),before)
        with self.assertRaisesRegex(ValueError,'legacy smoke without observed region membership'):
            e.use_move_on(a,b,'move/날려버리기',e.everyone,aim=(5,5))
        self.assertEqual(self.observed(e,a),before)
        old=e.gm.observe_smoke_region(cells,reason='actual old occurrence still overlaps the later paid move')
        self.assertEqual(set(e._smoke_regions['regions']),{current,current_only,old})
        self.whirlwind(e,a,b)
        self.assertEqual(set(e.zone_cells),outside)
        self.assertEqual(set(e._smoke_regions['regions']),{current_only})

    def test_gm_and_json_restore_keep_current_membership_and_never_recreate_a_dispersed_source(self):
        e,a,b=self.fixture();first,_=self.smoke(e,a,b,(5,5));second,cells=self.smoke(e,a,b,(5,8))
        e.gm.snapshot('two-real-smoke-regions')
        self.whirlwind(e,a,b)
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        self.assertEqual(set(loaded._smoke_regions['regions']),{second})
        self.assertEqual(set(loaded.zone_cells),cells)
        self.assertNotIn(first,loaded._smoke_regions['regions'])
        e.gm.restore('two-real-smoke-regions')
        self.assertIs(WORLD.actor_index(e)[a.entity_id],a)
        self.assertEqual(set(e._smoke_regions['regions']),{first,second})
        self.whirlwind(e,a,b)
        self.assertEqual(set(e._smoke_regions['regions']),{second})

    def test_defog_encounter_and_mapless_anchor_clear_metadata_with_the_actual_field(self):
        e,a,b=self.fixture();first,_=self.smoke(e,a,b,(5,5))
        self.begin(e,a);e.use_move_on(a,b,'move/안개제거',e.everyone)
        self.assertFalse(e.zone_cells);self.assertEqual(e._smoke_regions,{})
        second,_=self.smoke(e,a,b,(5,5));self.assertNotEqual(first,second)
        e.end_encounter();self.assertFalse(e.zone_cells);self.assertEqual(e._smoke_regions,{})
        e.grid=None;self.begin(e,a);e.use_move(a,b,'move/연막')
        identity=next(iter(e._smoke_regions['regions']))
        self.assertEqual(e._smoke_regions['regions'][identity]['target_id'],b.entity_id)
        self.assertEqual(e.zones,{b.entity_id:-3})
        self.assertEqual(e._prepare_accuracy_context(a,b,e.r.move('struggle'))['zone_pen'],-3)
        e.end_encounter();self.assertEqual((e.zones,e._smoke_regions),({},{}))

    def test_actual_empty_field_failure_rolls_back_region_identity_and_projection_together(self):
        e,a,b=self.fixture();self.smoke(e,a,b,(5,5));self.begin(e,a)
        before=self.observed(e,a);native=FX.HANDLERS['clear_field']
        def fail_after_clear(*args):
            native(*args)
            raise RuntimeError('forced failure after actual region dispersal')
        with patch.dict(FX.HANDLERS,{'clear_field':fail_after_clear}):
            with self.assertRaisesRegex(ValueError,'target-free field effects did not complete'):
                e.use_move_on(a,b,'move/날려버리기',e.everyone,aim=(5,5))
        self.assertEqual(self.observed(e,a),before)


if __name__=='__main__':unittest.main()
