from pathlib import Path
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_event_subscriptions as FIX
import source_context as SC
from state_codec import dump_engine,load_engine

class TraceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):FIX.Subscriptions.setUpClass()
 def test_execution_resources_detached_saved_and_replay(self):
  e,a,b,doc,key=FIX.Subscriptions().fixture()
  e.use_move(a,b,'struggle',set_damage=True)
  eid=list(e._passive_events)[-1];row=e.event_trace(eid)
  execution=row['listeners'][0]['execution']
  delta=execution['trace']['resource_changes']
  self.assertTrue(any(x['resource']=='stages' and x['after']['atk']==1 for x in delta))
  self.assertEqual(execution['trace']['state'],'completed')
  self.assertEqual([x['stage'] for x in row['observations']],['attempt','accuracy','damage_request','hp_loss','resolved'])
  json.dumps(row)
  restored=load_engine(e.r,dump_engine(e));self.assertEqual(restored.event_trace(eid),row)
  restored.deliver_passive_event(eid);self.assertEqual(restored.event_trace(eid),row)
  row['listeners'].clear();self.assertTrue(e.event_trace(eid)['listeners'])
 def test_rejected_listener_retains_resolution_without_execution(self):
  e,a,b,doc,key=FIX.Subscriptions().fixture(seed=31)
  with self.assertRaises(KeyError):e.event_trace('invented')
  e.use_move(a,b,'struggle',set_damage=True)
  row=e.event_trace(list(e._passive_events)[-1])['listeners'][0]
  self.assertEqual(row['status'],'inapplicable');self.assertNotIn('execution',row)
  self.assertEqual(row['resolution']['status'],'PolicyNotApplicable')
 def test_native_calculation_provenance_and_hp_paths_survive_restore(self):
  e,a,b,doc,key=FIX.Subscriptions().fixture();e.enable_execution_trace()
  e.use_move(attacker=a,target=b,move_id='struggle',set_damage=True)
  rows=e.execution_traces();json.dumps(rows)
  calc=next(x for x in rows if x['kind']=='damage_calculation')
  self.assertEqual(calc['state'],'returned');self.assertTrue(calc['calculations'])
  self.assertEqual(calc['calculations'][0]['result'],calc['result'])
  self.assertTrue(any(x.get('selected_id')=='combat/damage-formula' for x in calc['source_reads']))
  move=next(x for x in rows if x['kind']=='move_attempt')
  application=next(x for x in rows if x['kind']=='attack_damage_application')
  self.assertEqual(calc['parent_id'],application['trace_id'])
  self.assertEqual(application['parent_id'],move['trace_id'])
  receipt=next(x['damage_application'] for x in application['calculations'] if 'damage_application' in x)
  self.assertEqual(receipt['requested'],application['result'])
  self.assertEqual(receipt['net_hp_loss'],receipt['before']['hp']-receipt['after']['hp'])
  damage=next(x for x in rows if x['kind']=='damage_application')
  self.assertIn('amount',damage['inputs'])
  restored=load_engine(e.r,dump_engine(e));self.assertEqual(restored.execution_traces(),rows)
  rows.clear();self.assertTrue(e.execution_traces())
  e.lose_hp(a,1);e.heal(a,1)
  self.assertEqual(e.execution_traces()[-2]['kind'],'non_attack_hp_loss')
  self.assertEqual(e.execution_traces()[-1]['kind'],'healing')
  self.assertEqual(e.execution_traces()[-2]['resource_changes'][0]['classification'],'resource_change')
 def test_policy_trace_reads_actual_ap_spec_and_action_budget(self):
  import test_foundation_policy_replay as REPLAY
  REPLAY.PolicyReplayTests.setUpClass()
  fixture=REPLAY.PolicyReplayTests();fixture.setUp();fixture.prepare_binding()
  record=fixture.bound_action()
  changes=record['trace']['resource_changes']
  ap=next(x for x in changes if x['resource']=='ap_bound')
  self.assertEqual(ap['after'],{'effect/bound':2})
  budget=next(x for x in changes if x['resource']=='budget')
  self.assertEqual(budget['before']['swift'],1);self.assertEqual(budget['after']['swift'],0)
 def test_trace_disabled_and_invalid_operation_do_not_claim_execution(self):
  e,a,b,doc,key=FIX.Subscriptions().fixture()
  e.lose_hp(a,0);self.assertEqual(e.execution_traces(),[])
  e.enable_execution_trace()
  with self.assertRaises(ValueError):e.lose_hp(a,-1)
  row=e.execution_traces()[-1]
  self.assertEqual(row['state'],'raised');self.assertEqual(row['resource_changes'],[])
  e.enable_execution_trace(False);e.lose_hp(a,0)
  self.assertEqual(len(e.execution_traces()),1)
 def test_named_damage_arguments_preserve_native_contract_and_strict_rejection_in_both_trace_modes(self):
  for enabled in (False,True):
   for mixed in (False,True):
    with self.subTest(trace=enabled,mixed=mixed):
     e,a,b,doc,key=FIX.Subscriptions().fixture();e.enable_execution_trace(enabled)
     move=e.r.move('struggle')
     public=dict(attacker=a,target=b,move=move,set_damage=True)
     missing=dict(public);missing.pop('move')
     before=dump_engine(e)
     for args,kwargs in (((),dict(public,unreviewed_option=True)),((a,),public),((),missing)):
      with self.assertRaises(TypeError):e.resolve_attack_damage(*args,**kwargs)
      self.assertEqual(dump_engine(e),before)
      self.assertEqual(e.execution_traces(),[])
     hp=b.hp
     result=(e.resolve_attack_damage(a,target=b,move=move,set_damage=True) if mixed else
             e.resolve_attack_damage(**public))
     self.assertGreater(result,0);self.assertLess(b.hp,hp)
     rows=e.execution_traces()
     if enabled:
      application=next(row for row in rows if row['kind']=='attack_damage_application')
      calc=next(row for row in rows if row['kind']=='damage_calculation')
      self.assertEqual((application['state'],application['result']),('returned',result))
      self.assertIsNone(application['parent_id']);self.assertEqual(calc['parent_id'],application['trace_id'])
      self.assertIs(application['inputs']['crit'],False)
      self.assertTrue(any(row.get('selected_id')=='combat/damage-formula' for row in calc['source_reads']))
      self.assertTrue(any(row['entity_id']==b.entity_id and row['resource']=='hp' and row['after']==b.hp
                          for row in application['resource_changes']))
     else:self.assertEqual(rows,[])
     restored=load_engine(e.r,dump_engine(e));self.assertEqual(restored.execution_traces(),rows)
 def test_pending_declaration_is_not_reported_as_execution(self):
  import copy,passive_events as PE
  e,a,b,doc,key=FIX.Subscriptions().fixture()
  pending=copy.deepcopy(doc);pending['id']='trace/pending'
  pending['variants'][0]['inputs']['choice']={'type':'boolean','authority':'gm','question':'Choose'}
  second=e.subscribe_source_policy(a,'pending-trace',pending,inputs={'hit':'hit'})
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,b,'struggle',set_damage=True)
  row=e.event_trace(e._passive_pending)
  listener=next(x for x in row['listeners'] if x['listener_id']==second)
  self.assertEqual(listener['status'],'pending');self.assertNotIn('execution',listener)
  self.assertNotIn('trace',listener['resolution'])
  self.assertEqual(sum('execution' in x for x in row['listeners']),1)
 def test_pending_native_trace_restores_and_resume_never_repeats_damage(self):
  import passive_events as PE
  fixture=FIX.Subscriptions();e,a,b,doc,key=fixture.fixture()
  middle=fixture.accuracy_listener(e,a,doc);e.enable_execution_trace()
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,target=b,move_id='struggle',set_damage=True)
  eid=e._passive_pending;first=e.execution_traces()
  self.assertEqual(first[-1]['state'],'pending')
  self.assertFalse(any(x['kind']=='damage_application' for x in first))
  restored=load_engine(e.r,dump_engine(e));a,b=restored.everyone
  restored.choose_passive_event(eid,a,middle,{'decisions':{'decision':{'value':True,'reason':'test'}}})
  self.assertEqual(sum(x['kind']=='damage_application' for x in restored.execution_traces()),1)
  before=restored.execution_traces();restored.deliver_passive_event(eid)
  self.assertEqual(restored.execution_traces(),before)
  self.assertEqual(restored.execution_traces(first[-1]['trace_id']),first[-1])
 def test_transaction_discards_resource_and_trace_changes_on_failure(self):
  import state_grants as G
  e,a,b,doc,key=FIX.Subscriptions().fixture();e.enable_execution_trace()
  before=dump_engine(e)
  def fail(staged,actor):
   staged.lose_hp(actor,1)
   self.assertEqual(len(staged.execution_traces()),1)
   raise ValueError('rollback')
  with self.assertRaisesRegex(ValueError,'rollback'):G.transition(e,a,fail)
  self.assertEqual(dump_engine(e),before)
  G.transition(e,a,lambda staged,actor:staged.lose_hp(actor,1))
  self.assertEqual(len(e.execution_traces()),1)
 def test_shared_rules_do_not_merge_separate_engine_trace_parents(self):
  import event_trace as T,state_grants as G
  e,a,b,doc,key=FIX.Subscriptions().fixture();other=load_engine(e.r,dump_engine(e))
  e.enable_execution_trace();other.enable_execution_trace()
  @T.operation('test_outer')
  def outer(engine):
   other.lose_hp(other.everyone[0],0)
   G.transition(engine,a,lambda staged,actor:staged.lose_hp(actor,0))
  outer(e)
  self.assertIsNone(other.execution_traces()[0]['parent_id'])
  rows=e.execution_traces();parent=next(x for x in rows if x['kind']=='test_outer')
  child=next(x for x in rows if x['kind']=='non_attack_hp_loss')
  self.assertEqual(child['parent_id'],parent['trace_id'])
 def test_outer_trace_includes_registered_off_roster_actor_once(self):
  import event_trace as T
  e,a,b,doc,key=FIX.Subscriptions().fixture();e.enable_execution_trace()
  e.everyone=e.gm.everyone=[a]
  self.assertIn(b,e._time_actors)
  e._time_actors.append(b)
  @T.operation('off_roster_effect')
  def apply(engine):engine.lose_hp(b,1)
  apply(e)
  outer=next(row for row in e.execution_traces() if row['kind']=='off_roster_effect')
  changes=[row for row in outer['resource_changes'] if row['entity_id']==b.entity_id and row['resource']=='hp']
  self.assertEqual(len(changes),1);self.assertEqual(changes[0]['delta'],-1)
  self.assertEqual(changes[0]['classification'],'resource_change')
  restored=load_engine(e.r,dump_engine(e))
  self.assertEqual(restored.execution_traces(outer['trace_id']),outer)

 def test_read_capture_is_scoped_nested_and_exception_safe(self):
  e,a,b,doc,key=FIX.Subscriptions().fixture()
  with SC.capture_reads(e.r) as outer:
   e.r.mech('combat/struggle')
   with SC.capture_reads(e.r) as inner:e.r.mech('combat/struggle')
  self.assertEqual(len(outer),2);self.assertEqual(len(inner),1)
  try:
   with SC.capture_reads(e.r) as failed:
    e.r.mech('combat/struggle');raise RuntimeError('test')
  except RuntimeError:pass
  e.r.mech('combat/struggle')
  self.assertEqual(len(outer),2);self.assertEqual(len(failed),1)
  self.assertEqual(inner[0]['selected_id'],'combat/struggle')

if __name__=='__main__':unittest.main()
