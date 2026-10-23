"""Native held identity -> shell juice -> Candy and interruption/restore edges."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock
from builder import build_pokemon
import item_maturation as M,items as I,item_stock as STOCK,held_equipment as H,state_codec as CODEC,common_checks as C

class ItemMaturationTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
    add=_fixture_test_category2_progression_state.ProgressionStateTests.add
    held=_fixture_test_category2_medicine_stock.MedicineStockTests.held
    restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
    def setUp(self):
        _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
        self.p=self.add(build_pokemon(self.r,'단단지',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'items':{'오랭열매':2}}))
        self.held(self.p,'오랭열매','berry')
        self.key=next(iter(self.p.spec[M.KEY]))
    def row(self):return self.p.spec[M.KEY][self.key]
    def snap(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone],getattr(self.e,'_physical_objects',{}),self.e.log_lines),{id(self.r):self.r})
    def collect(self):return self.e.pokemon_activity(self.a,'collect_matured_item',target=self.p,batch_id=self.key,reason='actual Candy removed from shell')

    def test_exact_two_boundaries_actual_material_and_native_candy_consumption(self):
        self.e.advance_time(86399);self.assertEqual(self.row()['stage'],'held');self.assertTrue(H.entries(self.p))
        self.e.advance_time(1);r=self.row();self.assertEqual((r['stage'],r['juice_at'],r['product']['location']),('juice',86400,'shell'))
        self.assertEqual(self.p.spec['items']['오랭열매'],2);self.assertFalse(H.entries(self.p))
        self.assertEqual(self.e._physical_objects['berry']['consumed']['at'],86400)
        before=self.snap();self.assertIsInstance(self.collect(),C.PendingDecision);self.assertEqual(before,self.snap())
        self.e.advance_time(1209599);self.assertEqual(self.row()['stage'],'juice')
        self.e.advance_time(1);self.assertEqual((self.row()['stage'],self.row()['candy_at']),('candy',1296000))
        self.assertNotIn('item/이상한사탕-1',self.a.spec['items']);self.collect()
        self.assertEqual(self.a.spec['items']['item/이상한사탕-1'],1)
        self.assertEqual(self.e.use_item(self.a,'item/이상한사탕-1',self.p),(1,0));self.assertEqual(self.p.level,21)
        before=self.snap()
        with self.assertRaises(ValueError):self.collect()
        self.assertEqual(before,self.snap());self.assertTrue(self.e.validate_state()['valid'])

    def test_whole_interval_and_both_restore_paths_preserve_original_phase_times(self):
        self.e.advance_time(86399)
        saved=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(saved)
        for e in (self.e,loaded):
            p=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
            e.advance_time(1209601)
            r=p.spec[M.KEY][self.key]
            self.assertEqual((r['stage'],r['juice_at'],r['candy_at']),('candy',86400,1296000))
            before=deepcopy(r);e.advance_time(0);self.assertEqual(r,before)
            self.assertEqual(len(p.spec[M.KEY]),1);self.assertTrue(e.validate_state()['valid'])

    def test_actual_release_interrupts_and_reholding_starts_a_distinct_continuity(self):
        self.e.advance_time(86000)
        I.unregister_item(self.e,self.p,'오랭열매')
        self.assertEqual(self.row()['stage'],'cancelled')
        self.e.advance_time(400)
        I.equip_held(self.e,self.p,'오랭열매',source_instance_id='berry')
        rows=list(self.p.spec[M.KEY].values());self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1]['started_at'],86400)
        I.equip_held(self.e,self.p,'오랭열매',source_instance_id='berry');self.assertEqual(len(self.p.spec[M.KEY]),2)
        self.e.advance_time(86399);self.assertEqual(rows[-1]['stage'],'held')
        self.e.advance_time(1);self.assertEqual(self.p.spec[M.KEY][rows[-1]['id']]['stage'],'juice')
        self.assertTrue(self.e.validate_state()['valid'])

    def test_real_food_intake_interrupts_before_the_maturation_deadline(self):
        self.e.advance_time(86370)
        out=self.e.use_item(self.p,'오랭열매',held_selection='berry',duration_minutes=1,duration_reason='actual Berry intake')
        self.assertEqual(out['status'],'digestion_buff_gained');self.assertEqual(self.row()['stage'],'cancelled')
        self.assertEqual(self.row()['cancel_reason'],'intake_started');self.assertNotIn('product',self.row())
        self.assertEqual(self.e.elapsed_seconds,86430);self.assertEqual(len(self.p.buffs),1)
        self.e.advance_time(1296000);self.assertEqual(self.row()['stage'],'cancelled')
        self.assertTrue(self.e.validate_state()['valid'])

    def test_missing_historical_start_unknown_clock_or_lost_capability_never_invents_product(self):
        self.p.spec.pop(M.KEY)
        self.e.advance_time(86400);self.assertNotIn(M.KEY,self.p.spec)
        key=self.e.gm.observe_maturation_start(self.p,held_selection='berry',started_at=0,reason='GM confirmed this actual continuous holding interval')
        self.e.advance_time(0);self.assertEqual(self.p.spec[M.KEY][key]['stage'],'juice')
        self.setUp();self.e.unresolved_time_intervals.append({'kind':'unobserved-test-interval'})
        self.e.advance_time(1296000);self.assertEqual((self.row()['stage'],self.row()['pending']),('held','unknown_elapsed_interval'))
        self.assertNotIn('consumed',self.e._physical_objects['berry'])
        self.setUp();self.p.spec['capabilities']=[]
        self.e.advance_time(86400);self.assertEqual((self.row()['stage'],self.row()['pending']),('held','capability_continuity_unknown'))

    def test_late_conversion_failure_rolls_back_interval_and_material_then_retry_succeeds(self):
        native=STOCK.debit
        def fail_after_material(*args,**kw):native(*args,**kw);raise ValueError('injected after material debit')
        before=self.snap()
        with patch.object(STOCK,'debit',side_effect=fail_after_material):
            with self.assertRaisesRegex(ValueError,'after material debit'):self.e.advance_time(86400)
        # The default clock commits the entire interval atomically.
        self.assertEqual(self.e.elapsed_seconds,0)
        self.assertEqual(before,self.snap())
        self.assertEqual(self.row()['stage'],'held');self.assertNotIn('consumed',self.e._physical_objects['berry'])
        self.assertTrue(H.entries(self.p));self.assertEqual(self.p.spec['items']['오랭열매'],2)
        self.e.advance_time(86400);self.assertEqual(self.row()['stage'],'juice');self.assertEqual(self.row()['juice_at'],86400)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_two_actual_held_inputs_keep_independent_start_times_and_products(self):
        import state_grants as G
        G.replace_baseline(self.e,self.p,'abilities',['배달부'])
        self.e.advance_time(600);self.held(self.p,'복슝열매','second-berry')
        self.assertEqual(len(self.p.spec[M.KEY]),2)
        self.e.advance_time(85800)
        rows=list(self.p.spec[M.KEY].values())
        self.assertEqual([r['stage'] for r in rows],['juice','held'])
        self.assertEqual([r['instance_id'] for r in rows],['berry','second-berry'])
        self.e.advance_time(600);rows=list(self.p.spec[M.KEY].values())
        self.assertEqual([r['juice_at'] for r in rows],[86400,87000])
        self.assertEqual(len({r['product']['id'] for r in rows}),2)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_bad_product_provenance_rejects_before_time_and_in_both_restore_paths(self):
        self.e.advance_time(86400);valid=deepcopy(self.row())
        for field,value in [('juice_at',True),('actor_id','foreign'),('input_item','item/타우린')]:
            self.p.spec[M.KEY][self.key]=deepcopy(valid);self.row()[field]=value;before=self.snap()
            with self.assertRaises(ValueError):self.e.advance_time(1)
            self.assertEqual(before,self.snap())
            with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
            with self.assertRaises(ValueError):self.e.gm.snapshot()
        with patch.object(M,'validate',return_value=True),patch.object(M,'validate_world',return_value=True):
            payload=json.loads(json.dumps(CODEC.dump_engine(self.e)));bad=self.e.gm.snapshot('bad-maturation')
        self.p.spec[M.KEY][self.key]=valid;before=self.snap()
        with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
        with self.assertRaises(ValueError):self.e.gm.restore(bad)
        self.assertEqual(before,self.snap())
        self.e._physical_objects['berry']['consumed']['at']=1
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

if __name__=='__main__':unittest.main()
