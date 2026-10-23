"""Independent native review of scoped multi-target activation authority."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import test_range_sources as _fixture_test_range_sources
import move_activation as MA
import action_lifecycle as ACTION

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_range_sources.RangeSourceTests.setUpClass()
 def setUp(self):
  self.e,self.a,self.b,self.c,self.mid=_fixture_test_range_sources.RangeSourceTests().area()
  self._original_versions=deepcopy(self.e.r.ruleset.unit_versions)
  self.e.start_round([self.a,self.b,self.c]);self.e.start_of_turn(self.a,initiative_count=20)
 def tearDown(self):
  self.e.r.ruleset.unit_versions=self._original_versions
 def state(self):return deepcopy((self.a.budget,self.a.move_uses,self.b.injuries,self.c.injuries,self.e.rng.getstate()))
 def verify(self,activation,accuracy,actor=None,target=None,move=None,**kw):return MA.verify(self.e,actor or self.a,target or self.b,move or self.mid,activation,accuracy,count_use=kw.get('count_use',True),free_action=kw.get('free_action',False))
 def test_direct_activation_or_shared_roll_dicts_cannot_authorize_native_move(self):
  for flags in ({'_activation':{}},{'_shared_accuracy':{}},{'_shared_accuracy':{'targets':(self.b,),'rolls':[20]}}):
   before=self.state()
   with self.assertRaises(ValueError):self.e.use_move(self.a,self.b,self.mid,**flags)
   self.assertEqual(self.state(),before)
 def test_native_shared_area_one_roll_one_standard_one_frequency(self):
  rolls=[];self.e.d20=lambda:(rolls.append(True) or 2)
  self.e.use_move_on(self.a,self.b,self.mid,[self.a,self.b,self.c]);self.assertEqual(len(rolls),1);self.assertEqual((self.b.injuries,self.c.injuries),(1,0));self.assertEqual(self.a.move_uses[self.mid],1);self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a._action_history,['standard']);self.assertEqual(getattr(self.e,'_move_activation_scopes',[]),[])
 def test_refused_first_target_cannot_leak_free_secondary_activation(self):
  self.a.budget={'standard':0};before=self.state()
  with patch.object(self.e,'d20',side_effect=AssertionError('no accuracy on refused action')):
   self.e.use_move_on(self.a,self.b,self.mid,[self.a,self.b,self.c])
  self.assertEqual(self.state(),before);self.assertEqual(getattr(self.e,'_move_activation_scopes',[]),[])
 def test_shared_first_miss_keeps_the_same_natural_one_for_every_target(self):
  calls=[];self.e.d20=lambda:(calls.append(True) or 1)
  self.e.use_move_on(self.a,self.b,self.mid,[self.a,self.b,self.c]);self.assertEqual(calls,[True]);self.assertEqual((self.b.injuries,self.c.injuries),(0,0));self.assertEqual(self.a.move_uses[self.mid],1)
 def test_native_nonarea_multi_target_continuation_keeps_individual_accuracy(self):
  self.e.r.moves[self.mid]['range']='원거리';self.e.r.moves_mech[self.mid]['header']['range']={'origin':5,'targets':2}
  calls=[]
  def check(a,t,*args,**kw):calls.append(t);return (t is self.c,10,False)
  self.e.accuracy_check=check
  self.e.use_move_on(self.a,self.b,self.mid,[self.a,self.b,self.c]);self.assertEqual(calls,[self.b,self.c]);self.assertEqual((self.b.injuries,self.c.injuries),(0,1));self.assertEqual(self.a.move_uses[self.mid],1)
 def test_scope_actor_move_target_order_and_profile_are_bound(self):
  for change in ('actor','target','move','profile'):
   self.setUp()
   with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):
    kw={'actor':self.c} if change=='actor' else {'target':self.c} if change=='target' else {'move':'struggle'} if change=='move' else {}
    if change=='profile':self.e.r.ruleset.unit_versions=dict(self.e.r.ruleset.unit_versions,**{'maneuver/밀기':'changed'})
    with self.assertRaises(ValueError):self.verify(activation,accuracy,**kw)
 def test_scope_forbids_prefilled_observations_or_changed_target_set(self):
  for key in ('activation','rolls','targets'):
   self.setUp()
   with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):
    if key=='activation':activation['started']=True
    elif key=='rolls':accuracy['rolls']=[20]
    else:accuracy['targets']=(self.b,)
    with self.assertRaises(ValueError):self.verify(activation,accuracy)
 def test_cost_frequency_boundary_cannot_be_skipped_or_recharged(self):
  for count,free in ((False,False),(True,True),(False,True)):
   with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):
    with self.assertRaises(ValueError):self.verify(activation,accuracy,count_use=count,free_action=free)
  with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):
   self.verify(activation,accuracy)
   with self.assertRaises(ValueError):self.verify(activation,accuracy,target=self.c,count_use=True)
 def test_live_scope_observation_cannot_be_replayed_after_scope_closed(self):
  with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):self.verify(activation,accuracy)
  with self.assertRaises(ValueError):self.verify(activation,accuracy,target=self.c,count_use=False)
  self.assertEqual(getattr(self.e,'_move_activation_scopes',[]),[])
 def test_scope_always_revokes_on_native_exception(self):
  with patch.object(self.e,'accuracy_check',side_effect=ValueError('invalid native observation')):
   with self.assertRaises(ValueError):self.e.use_move_on(self.a,self.b,self.mid,[self.a,self.b,self.c])
  self.assertEqual(getattr(self.e,'_move_activation_scopes',[]),[]);self.assertEqual(self.a.move_uses[self.mid],1)
 def test_duplicate_actual_target_is_not_a_second_cost_free_occurrence(self):
  with self.assertRaises(ValueError):
   with MA.open_scope(self.e,self.a,self.mid,(self.b,self.b),shared=True):pass

 def test_restore_cannot_keep_ephemeral_scope_while_rewinding_first_target_cost(self):
  self.e.gm.snapshot('before-parent')
  with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):
   self.e.d20=lambda:20
   self.e.use_move(self.a,self.b,self.mid,_activation=activation,_shared_accuracy=accuracy)
   self.assertEqual(self.a.budget['standard'],0)
   self.e.gm.restore('before-parent','rewind parent action');self.assertEqual(self.a.budget['standard'],1);before=self.state()
   with ACTION.move_grant(self.e,self.a,self.c,self.mid,source='same_move_activation') as token:
    with self.assertRaises(ValueError):self.e.use_move(self.a,self.c,self.mid,count_use=False,_activation=activation,_shared_accuracy=accuracy,_action_grant=token)
   self.assertEqual(self.state(),before)
 def test_active_scope_cannot_cross_turn_or_encounter_lifetime(self):
  for boundary in ('round','turn','encounter'):
   self.setUp()
   with MA.open_scope(self.e,self.a,self.mid,(self.b,self.c),shared=True) as (activation,accuracy):
    self.verify(activation,accuracy)
    if boundary=='round':self.e.round_no+=1
    elif boundary=='turn':self.e._active_turn_actor=self.c
    else:self.e.encounter_active=False
    with self.assertRaises(ValueError):self.verify(activation,accuracy,target=self.c,count_use=False)

 def test_arbitrary_action_token_cannot_turn_ordinary_activation_into_exception(self):
  before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.a,self.b,self.mid,_action_grant=object())
  self.assertEqual(self.state(),before)
 def test_direct_chain_without_actual_native_group_is_rejected_before_cost(self):
  self.e.r.moves_mech[self.mid]['effects'].append({'type':'multi_target_chain','max':3,'shift_between':2})
  before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.a,self.b,self.mid)
  self.assertEqual(self.state(),before)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/move_activation.py','engine/engine.py','engine/action_lifecycle.py','tools/test_upper_move_activation.py','tools/test_range_sources.py','tools/test_frequencies.py','tools/synthetic_rule_fixture.py']
 (ROOT/'output/upper-move-activation-tests.json').write_text(json.dumps({'successful':result.wasSuccessful(),'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
