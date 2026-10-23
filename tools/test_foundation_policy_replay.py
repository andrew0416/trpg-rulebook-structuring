"""Completed external policy requests survive redelivery without new costs."""
from pathlib import Path
from hashlib import sha256
from copy import copy,deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine
import world_entities as W

class PolicyReplayTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.r=copy(self.rules);self.r.ruleset=deepcopy(self.rules.ruleset)
  self.r.selection=copy(self.rules.selection);self.r.selection.filter=self.r.ruleset
  self.e=Engine(self.r,16)
  self.c=Combatant(self.r,build_trainer(self.r,'replay',10,
   {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c]
  source=self.r.selection.units['combat/struggle']['source']['file']
  self.row={'rule_id':'combat/struggle','source':{'file':'input/'+source,'sha256':sha256((ROOT/'input'/source).read_bytes()).hexdigest()},
   'inputs':{},'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}
  self.doc={'schema':1,'id':'replay-policy','variants':[self.row]}
 def run_policy(self,request_id='event/one',**kw):
  return self.e.execute_source_policy_effects(self.c,self.c,self.doc,request_id=request_id,**kw)
 def test_replay_preserves_rng_effects_evidence_and_detached_result(self):
  from unittest.mock import patch
  import effects
  original=effects.HANDLERS['stage_change']
  def apply(e,a,t,effect,ctx):e.rng.random();return original(e,a,t,effect,ctx)
  with patch.dict(effects.HANDLERS,{'stage_change':apply}):
   first=self.run_policy();before=dump_engine(self.e);second=self.run_policy()
  self.assertFalse(first['replayed']);self.assertTrue(second['replayed'])
  self.assertEqual(first['execution_id'],second['execution_id']);self.assertEqual(dump_engine(self.e),before)
  self.assertNotIn('receipt',second['outcomes'][0])
  second['values']['effects'].clear();self.assertEqual(self.run_policy()['values'],first['values'])
  self.run_policy('event/two');self.assertEqual(self.c.stages['atk'],2)
 def bound_action(self,request='binding/one'):
  return self.e.execute_source_policy_action(self.c,self.c,self.doc,request_id=request)
 def prepare_binding(self):
  self.e.start_round([self.c]);self.e.start_of_turn(self.c)
  self.row['values']={'action':'swift','ap':{'amount':2,'mode':'bind',
      'instance_id':'effect/bound','ending_method':'none_specified'},
      'effects':[{'type':'damage_roll_mod','value':3}]}
 def test_authored_binding_activates_restores_and_releases_exact_effect(self):
  import action_points as AP
  self.prepare_binding();first=self.bound_action()
  self.assertEqual(first['status'],'PolicyActionCompleted')
  self.assertEqual(self.c.spec['ap_bound'],{'effect/bound':2})
  self.assertEqual(self.c.modifiers[-1],{'type':'damage_roll_mod','value':3})
  self.assertEqual(self.c.budget['swift'],0)
  loaded=load_engine(self.r,dump_engine(self.e))
  owner=loaded.everyone[0]
  replay=loaded.execute_source_policy_action(owner,owner,self.doc,request_id='binding/one')
  self.assertTrue(replay['replayed'])
  available=AP.available(owner)
  ended=loaded.release_bound_ap(owner,'effect/bound',event_id='binding/end')
  self.assertEqual(ended.status,'released');self.assertEqual(AP.available(owner),available+2)
  self.assertFalse(owner.modifiers)
  replay=loaded.execute_source_policy_action(owner,owner,self.doc,request_id='binding/one')
  self.assertTrue(replay['replayed']);self.assertFalse(owner.modifiers)
 def test_binding_failure_rolls_back_action_and_reservation(self):
  self.prepare_binding();self.row['values']['ap']['ending_method']='invalid'
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.bound_action()
  self.assertEqual(dump_engine(self.e),before)
 def test_distinct_request_cannot_reuse_a_live_binding_identity(self):
  self.prepare_binding();self.row['values']['action']='free';self.bound_action()
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'already reserved'):self.bound_action('binding/two')
  self.assertEqual(dump_engine(self.e),before)

 def test_recipient_debt_commits_once_and_next_budget_settles_without_action(self):
  import turn as TURN
  self.prepare_binding()
  self.row['values']={'action':'free','ap':{'amount':0,'mode':'spend'},
      'recipient_debt':{'standard':1,'swift':1},
      'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  first=self.bound_action('debt/one')
  self.assertEqual(self.c.pending_action_loss,{'standard':1,'swift':1})
  history=list(self.c._action_history)
  TURN.reset_budget(self.e,self.c)
  self.assertEqual(self.c.budget,{'standard':0,'shift':1,'swift':0})
  self.assertEqual(self.c._action_history,history)
  self.assertIsNone(self.c.pending_action_loss)
  self.assertTrue(self.bound_action('debt/one')['replayed'])
  self.assertIsNone(self.c.pending_action_loss)
  TURN.reset_budget(self.e,self.c)
  self.assertEqual(self.c.budget,{'standard':1,'shift':1,'swift':1})
 def test_conflicting_debts_reject_before_changing_budget_or_effects(self):
  import turn as TURN
  self.prepare_binding();self.c.pending_action_loss={'standard':1}
  self.c.spec['_burrow']={'standard_debt':True}
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'conjunction'):TURN.reset_budget(self.e,self.c)
  self.assertEqual(dump_engine(self.e),before)
  self.c.spec.pop('_burrow')
  self.row['values']={'action':'swift','ap':{'amount':1,'mode':'spend'},
      'recipient_debt':{'standard':1,'swift':1},
      'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'conjunction'):self.bound_action('debt/conflict')
  self.assertEqual(dump_engine(self.e),before)

 def prepare_frequency(self,kind='scene',scope=None):
  self.prepare_binding()
  self.row['values']={'action':'free','ap':{'amount':1,'mode':'spend'},
      'frequency':{'kind':kind,'uses':1,'scope':scope or []},
      'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
 def test_authored_frequency_shares_native_source_and_replay_never_spends_twice(self):
  import frequency as FREQ
  from source_policy import PolicyExecutionPending
  self.prepare_frequency();self.bound_action('frequency/one')
  self.assertFalse(FREQ.activation_allowed(self.c,'combat/struggle',{'kind':'scene','uses':1}))
  before=dump_engine(self.e)
  self.assertTrue(self.bound_action('frequency/one')['replayed'])
  with self.assertRaises(PolicyExecutionPending):self.bound_action('frequency/two')
  self.assertEqual(dump_engine(self.e),before)
  FREQ.new_day(self.c)
  with self.assertRaises(PolicyExecutionPending):self.bound_action('frequency/two')
  FREQ.end_scene(self.e,self.c)
  self.bound_action('frequency/two');self.assertEqual(self.c.stages['atk'],2)
 def test_declared_turn_owner_controls_refresh_not_other_turns_or_extra_actions(self):
  import frequency as FREQ
  import turn as TURN
  from source_policy import PolicyExecutionPending
  self.prepare_frequency(kind='turn')
  owner=Combatant(self.r,dict(deepcopy(self.c.spec),id='turn/owner',name='owner'))
  self.e.everyone.append(owner)
  quota=self.row['values']['frequency'];quota['turn_owner_id']=owner.entity_id
  self.bound_action('turn/one');before=dump_engine(self.e)
  with self.assertRaises(PolicyExecutionPending):self.bound_action('turn/two')
  self.assertEqual(dump_engine(self.e),before)
  TURN.reset_budget(self.e,self.c);FREQ.start_turn(self.c)
  with self.assertRaises(PolicyExecutionPending):self.bound_action('turn/two')
  restored=load_engine(self.r,dump_engine(self.e));actor=restored.everyone[0]
  with self.assertRaises(PolicyExecutionPending):restored.execute_source_policy_action(actor,actor,self.doc,request_id='turn/two')
  FREQ.start_turn(owner)
  self.bound_action('turn/two');self.assertEqual(self.c.stages['atk'],2)
  self.assertTrue(self.bound_action('turn/one')['replayed'])
  with self.assertRaises(PolicyExecutionPending):self.bound_action('turn/three')
  quota['turn_owner_id']='missing';before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'turn owner'):self.bound_action('turn/invalid')
  self.assertEqual(dump_engine(self.e),before)

 def test_scoped_frequency_distinguishes_actual_targets(self):
  from source_policy import PolicyExecutionPending
  self.prepare_frequency(scope=['target'])
  other=Combatant(self.r,dict(self.c.spec,id='other',name='other'))
  self.e.everyone.append(other)
  self.bound_action('target/self')
  result=self.e.execute_source_policy_action(self.c,other,self.doc,request_id='target/other')
  self.assertEqual(result['status'],'PolicyActionCompleted')
  with self.assertRaises(PolicyExecutionPending):
   self.e.execute_source_policy_action(self.c,other,self.doc,request_id='target/other-again')
 def test_lifetime_frequency_receipt_survives_temporary_kind_change(self):
  import frequency as FREQ
  from source_policy import PolicyExecutionPending
  self.prepare_frequency('one_time');self.bound_action('once/one')
  self.row['values']['frequency']['kind']='scene';self.bound_action('once/scene')
  FREQ.new_day(self.c);FREQ.end_scene(self.e,self.c)
  self.row['values']['frequency']['kind']='one_time'
  before=dump_engine(self.e)
  with self.assertRaises(PolicyExecutionPending):self.bound_action('once/two')
  self.assertEqual(dump_engine(self.e),before)
 def test_frequency_invalid_provider_and_late_effect_failure_do_not_debit(self):
  import frequency as FREQ
  self.prepare_frequency(scope=['provider']);self.row['values']['frequency']['provider_id']='missing'
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.bound_action('frequency/invalid')
  self.assertEqual(dump_engine(self.e),before)
  self.row['values']['frequency']={'kind':'scene','uses':1,'scope':[]}
  self.row['values']['recipient_debt']={'standard':1,'swift':1}
  self.c.pending_action_loss={'standard':1}
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.bound_action('frequency/late-failure')
  self.assertEqual(dump_engine(self.e),before)
  self.assertTrue(FREQ.activation_allowed(self.c,'combat/struggle',{'kind':'scene','uses':1}))

 def test_provider_action_dimensions_and_compound_order_share_only_intended_pool(self):
  import frequency as FREQ
  from action_metadata import ActionCost
  self.prepare_frequency(scope=['provider','action'])
  quota=self.row['values']['frequency'];quota['provider_id']=self.c.entity_id
  key=FREQ.declaration_key(self.e,self.c,self.c,'combat/struggle','free',quota)
  FREQ.consume_activation(self.c,key,quota,engine=self.e)
  self.assertFalse(FREQ.activation_allowed(self.c,key,quota))
  second=FREQ.declaration_key(self.e,self.c,self.c,'combat/struggle','swift',quota)
  self.assertTrue(FREQ.activation_allowed(self.c,second,quota))
  other=Combatant(self.r,dict(self.c.spec,id='provider/other',name='provider'))
  self.e.everyone.append(other);quota['provider_id']=other.entity_id
  third=FREQ.declaration_key(self.e,self.c,self.c,'combat/struggle','free',quota)
  self.assertTrue(FREQ.activation_allowed(self.c,third,quota))
  ordered=FREQ.declaration_key(self.e,self.c,self.c,'combat/struggle',ActionCost(('standard','swift')),quota)
  reversed_key=FREQ.declaration_key(self.e,self.c,self.c,'combat/struggle',ActionCost(('swift','standard')),quota)
  self.assertEqual(ordered,reversed_key)
  quota['uses']=None
  with self.assertRaises(ValueError):FREQ.declaration_key(self.e,self.c,self.c,'combat/struggle','free',quota)

 def test_action_replay_after_save_needs_no_fresh_action_or_ap(self):
  self.e.encounter_active=True;self.e._active_turn_actor=self.c;self.e.round_start_seconds=0
  self.c.budget={'standard':1,'shift':1,'swift':1};self.c._turn_start_decisions_pending=False
  self.row['values'].update(action=['standard','swift'],ap={'amount':2,'mode':'drain'})
  first=self.e.execute_source_policy_action(self.c,self.c,self.doc,request_id='action/one')
  self.assertEqual(self.c.spec['ap_removed'],2)
  restored=load_engine(self.r,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  before=dump_engine(restored)
  result=restored.execute_source_policy_action(c,c,self.doc,request_id='action/one')
  self.assertTrue(result['replayed']);self.assertEqual(result['execution_id'],first['execution_id'])
  self.assertEqual(dump_engine(restored),before)
 def test_changed_intent_mode_and_invalid_identity_are_rejected(self):
  self.run_policy();before=dump_engine(self.e)
  self.row['values']['effects'][0]['delta']=2
  with self.assertRaisesRegex(ValueError,'changed input'):self.run_policy()
  self.row['values']['effects'][0]['delta']=1
  with self.assertRaisesRegex(ValueError,'changed input'):
   self.e.execute_source_policy_action(self.c,self.c,self.doc,request_id='event/one')
  for uid in ['',False,1]:
   with self.assertRaises(ValueError):self.run_policy(uid)
  self.assertEqual(dump_engine(self.e),before)
 def test_pending_and_failed_attempts_do_not_mark_a_request_completed(self):
  self.row['inputs']={'delta':{'type':'integer','authority':'gm','question':'Delta?'}}
  self.row['values']['effects'][0]['delta']={'$input':'delta'}
  before=dump_engine(self.e);self.assertEqual(self.run_policy()['status'],'PolicyInputsRequired')
  self.assertEqual(dump_engine(self.e),before)
  args={'decisions':{'delta':{'value':1,'reason':'explicit'}}}
  self.row['values']['effects'].append({'type':'not_implemented'})
  with self.assertRaises(ValueError):self.run_policy(**args)
  self.assertEqual(dump_engine(self.e),before)
  self.row['values']['effects'].pop()
  self.assertFalse(self.run_policy(**args)['replayed']);self.assertTrue(self.run_policy(**args)['replayed'])
 def test_completed_request_still_checks_current_source_and_actual_actor(self):
  self.run_policy();before=dump_engine(self.e)
  good=self.row['source']['sha256'];self.row['source']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'source changed'):self.run_policy()
  self.row['source']['sha256']=good
  with self.assertRaises(ValueError):
   self.e.execute_source_policy_effects(copy(self.c),self.c,self.doc,request_id='event/one')
  self.r.ruleset.exclude_units.add('combat/struggle')
  with self.assertRaises(ValueError):self.run_policy()
  self.r.ruleset.exclude_units.remove('combat/struggle')
  self.assertEqual(dump_engine(self.e),before)

 def test_replay_reads_original_evidence_after_state_condition_changes(self):
  self.row['inputs']={'level':{'type':'integer','authority':'state','question':'Actual level',
    'binding':{'subject':'actor','field':'level'}}}
  self.row['when']={'op':'ge','left':{'$input':'level'},'right':10}
  first=self.run_policy();self.c.spec['level']=9
  replay=self.run_policy();self.assertTrue(replay['replayed'])
  self.assertEqual(replay['input_values'],first['input_values']);self.assertEqual(self.c.stages['atk'],1)
  self.assertEqual(self.run_policy('event/new')['status'],'PolicyNotApplicable')
 def test_rebuilt_changed_profile_cannot_reuse_completed_identity(self):
  from ruleset import RuleSelection
  self.run_policy();before=dump_engine(self.e)
  self.r.ruleset.exclude_units.add('combat/tick-of-hit-points')
  self.r.selection=RuleSelection(self.r.ruleset,list(self.rules.selection.units.values()))
  with self.assertRaisesRegex(ValueError,'changed input'):self.run_policy()
  self.r.ruleset.exclude_units.remove('combat/tick-of-hit-points')
  self.r.selection=RuleSelection(self.r.ruleset,list(self.rules.selection.units.values()))
  self.assertEqual(dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
