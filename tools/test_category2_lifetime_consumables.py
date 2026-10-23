"""Native lifetime limits, permanent growth and both persistence boundaries."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock
from builder import build_trainer
import lifetime_consumables as L,downtime as D,common_checks as C
import state_codec as CODEC,pokemon_party as PARTY,move_state as M

class LifetimeConsumableTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
    add=_fixture_test_category2_progression_state.ProgressionStateTests.add
    pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
    restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
    held=_fixture_test_category2_medicine_stock.MedicineStockTests.held
    def setUp(self):
        _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon(4)
        self.a.spec['items']={'item/이상한사탕':3,'item/이상한사탕-1':3}
    def snap(self):
        return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone],getattr(self.e,'_physical_objects',{}),self.e.log_lines),{id(self.r):self.r})
    def quota(self,actor=None):return (actor or self.p).spec[L.KEY]['quotas']['rare_candy']
    def use(self,uid='item/이상한사탕-1',**kw):return self.e.use_item(self.a,uid,self.p,**kw)

    def test_both_source_ids_share_five_lifetime_uses_and_preserve_vitamin_capacity(self):
        self.p.spec['exp']=39
        self.p.spec['vitamins']=['item/타우린']*5
        occupied=M.vitamin_state(self.r,self.p.spec)['occupied']
        for i,uid in enumerate(['item/이상한사탕','item/이상한사탕-1']*2+['item/이상한사탕'],1):
            self.assertEqual(self.use(uid),(1,0))
            self.assertEqual((self.p.level,self.p.spec['exp']),(4+i,D.exp_for_level(self.r,4+i)))
            self.assertEqual(self.quota()['receipts'][-1]['ordinal'],i)
            self.assertEqual(M.vitamin_state(self.r,self.p.spec)['occupied'],occupied)
        self.assertEqual(self.quota()['receipts'][0]['before']['exp'],39)
        self.assertEqual(self.p.spec['tutor_points'],2)
        before=self.snap();self.assertEqual(self.use(),(0,0));self.assertEqual(self.snap(),before)
        self.assertEqual(self.a.spec['items']['item/이상한사탕-1'],1)
        self.assertEqual(L.definition(self.r,'item/이상한사탕')[1]['catalog']['price'],9800)
        self.assertEqual(self.r.item_effects('item/이상한사탕-1')[1]['price'],9800)

    def test_unknown_import_requires_observed_history_and_cannot_reset_known_uses(self):
        self.p.spec.pop(L.KEY);before=self.snap()
        self.assertIsInstance(self.use(),C.PendingDecision);self.assertEqual(before,self.snap())
        for bad in (-1,True,1.5,6):
            with self.assertRaises(ValueError):self.e.gm.observe_lifetime_consumption(self.p,item='item/이상한사탕-1',count=bad,reason='actual history')
            self.assertEqual(before,self.snap())
        self.e.gm.observe_lifetime_consumption(self.p,item='item/이상한사탕-1',count=4,reason='GM checked original character history')
        self.assertEqual(self.use(),(1,0));self.assertEqual(self.quota()['receipts'][0]['ordinal'],5)
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'cannot be reset'):self.e.gm.observe_lifetime_consumption(self.p,item='item/이상한사탕-1',count=0,reason='new owner')
        self.assertEqual(before,self.snap());self.assertEqual(self.use(),(0,0))

    def test_used_quota_follows_evolution_trade_day_and_both_restored_continuations(self):
        self.p=self.pokemon(19)
        self.assertEqual(self.use(),(1,0));self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스'))
        other=self.add(build_trainer(self.r,'new owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'items':{'item/이상한사탕-1':10}}))
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual party',roster=[c for c in self.e.gm.everyone if c.spec.get('trainer_id')==self.a.entity_id])
        PARTY.configure(self.e,other,mode='unlimited',reason='actual party',roster=[])
        PARTY.transfer(self.e,self.a,target=self.p,new_owner=other,reason='actual trade',request_id='lifetime-trade')
        self.e.advance_time(86400);D.new_day(self.p)
        saved=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(saved)
        for e in (self.e,loaded):
            actors={c.entity_id:c for c in e.gm.everyone};p=actors[self.p.entity_id];u=actors[other.entity_id]
            for i in range(4):self.assertEqual(e.use_item(u,'item/이상한사탕-1',p),(1,0))
            self.assertEqual((p.level,len(p.spec[L.KEY]['quotas']['rare_candy']['receipts'])),(24,5))
            stock=u.spec['items']['item/이상한사탕-1'];self.assertEqual(e.use_item(u,'item/이상한사탕-1',p),(0,0));self.assertEqual(u.spec['items']['item/이상한사탕-1'],stock)
            self.assertTrue(e.validate_state()['valid'])

    def test_post_growth_failure_rolls_back_physical_quantity_action_and_permanent_changes(self):
        native=D._gain_exp_combatant
        def fail_after_growth(*args,**kw):
            native(*args,**kw);raise ValueError('injected after native growth')
        for physical in (False,True):
            self.setUp();options={}
            if physical:self.held(self.a,'item/이상한사탕-1','candy');options['held_selection']='candy'
            self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a);before=self.snap()
            with patch.object(D,'_gain_exp_combatant',side_effect=fail_after_growth):
                with self.assertRaisesRegex(ValueError,'after native growth'):self.use(**options)
            self.assertEqual(before,self.snap());self.assertEqual(self.use(**options),(1,0))
            self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.p.level,5)
            self.assertEqual(self.a.spec['items']['item/이상한사탕-1'],3 if physical else 2)
            if physical:self.assertIn('consumed',self.e._physical_objects['candy'])
            if not physical:
                before=self.snap();self.assertEqual(self.use(),(0,0));self.assertEqual(before[:-1],self.snap()[:-1])

    def test_invalid_receipts_reject_before_consumption_and_in_real_save_load_paths(self):
        self.use();valid=deepcopy(self.p.spec[L.KEY])
        variants=[]
        for field,value in [('ordinal',True),('actor_id','another-pokemon'),('source','item/타우린')]:
            bad=deepcopy(valid);bad['quotas']['rare_candy']['receipts'][0][field]=value;variants.append(bad)
        bad=deepcopy(valid);bad['quotas']['rare_candy']['receipts'][0]['after']['exp']+=1;variants.append(bad)
        bad=deepcopy(valid);bad['quotas']['rare_candy']['initial_count']=True;variants.append(bad)
        bad=deepcopy(valid);bad['actor_id']='another-pokemon';variants.append(bad)
        for bad in variants:
            self.p.spec[L.KEY]=bad;before=self.snap()
            with self.assertRaises(ValueError):self.use()
            self.assertEqual(before,self.snap())
            with self.assertRaises(ValueError):self.e.gm.snapshot()
            with patch.object(L,'validate',return_value=True):invalid_snapshot=self.e.gm.snapshot()
            self.p.spec[L.KEY]=deepcopy(valid);good=self.snap()
            with self.assertRaises(ValueError):self.e.gm.restore(invalid_snapshot)
            self.assertEqual(good,self.snap())
            self.p.spec[L.KEY]=bad
            with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        with patch.object(L,'validate',return_value=True):payload=json.loads(json.dumps(CODEC.dump_engine(self.e)))
        with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
        self.p.spec[L.KEY]=valid
        self.assertTrue(self.e.validate_state()['valid'])

    def test_unknown_xp_refusal_wrong_kind_max_level_and_unreviewed_options_never_spend(self):
        before=self.snap();self.assertEqual(self.use(accepted=False),(0,0))
        # Refusal is logged, but no actor/item state changes.
        self.assertEqual(before[:-1],self.snap()[:-1])
        for opts in ({'count':2},{'duration_minutes':1},{'selected_move':'move/몸통'}):
            before=self.snap()
            with self.assertRaises(ValueError):self.use(**opts)
            self.assertEqual(before,self.snap())
        before=self.snap()
        with self.assertRaises(ValueError):self.e.use_item(self.a,'item/이상한사탕-1',self.a)
        self.assertEqual(before,self.snap())
        self.p.spec.pop('exp');before=self.snap()
        with self.assertRaises(ValueError):self.use()
        self.assertEqual(before,self.snap())
        self.p=self.pokemon(100);before=self.snap()
        self.assertIsInstance(self.use(),C.PendingDecision);self.assertEqual(before,self.snap())
        self.assertFalse(self.quota()['receipts'])
        import items as I
        with self.assertRaisesRegex(ValueError,'sourced consumption adapter'):I._use_immediate_item(self.e,self.a,'item/이상한사탕-1',self.p)
        self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
