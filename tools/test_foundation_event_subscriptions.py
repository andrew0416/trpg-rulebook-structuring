"""External declarations react only to native move completion observations."""
from pathlib import Path
from hashlib import sha256
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_passive_event_runtime as FIX
import passive_events as PE
from state_codec import dump_engine,load_engine

class Subscriptions(unittest.TestCase):
 @classmethod
 def setUpClass(cls):FIX.Cases.setUpClass()
 def fixture(self,seed=0):
  e,a,b=FIX.Cases().fixture(seed=seed,register=False)
  source=e.r.selection.units['combat/struggle']['source']['file']
  row={'rule_id':'combat/struggle','source':{'file':'input/'+source,'sha256':sha256((ROOT/'input'/source).read_bytes()).hexdigest()},
       'inputs':{'hit':{'authority':'context','type':'boolean','question':'Native hit'}},
       'when':{'op':'eq','left':{'$input':'hit'},'right':True},
       'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}
  doc={'schema':1,'id':'event/subscription','variants':[row]}
  key=e.subscribe_source_policy(a,'on-hit',doc,inputs={'hit':'hit'})
  return e,a,b,doc,key
 def test_native_hit_delivery_and_save_redelivery_are_exactly_once(self):
  e,a,b,doc,key=self.fixture()
  self.assertFalse(e._passive_events);self.assertEqual(a.stages['atk'],0)
  e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.stages['atk'],1);self.assertEqual(a._action_history,['standard'])
  ev=list(e._passive_events.values())[-1]
  self.assertEqual(ev['outcomes'][key]['status'],'applied')
  loaded=load_engine(e.r,dump_engine(e));before=dump_engine(loaded)
  self.assertEqual(loaded.deliver_passive_event(ev['id']),'already_delivered')
  self.assertEqual(dump_engine(loaded),before)
 def test_miss_and_nonmove_hp_loss_cannot_assert_hit(self):
  e,a,b,doc,key=self.fixture(seed=31)
  e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.stages['atk'],0)
  ev=list(e._passive_events.values())[-1]
  self.assertEqual(ev['outcomes'][key]['status'],'inapplicable')
  before=len(e._passive_events);e.lose_hp(b,1)
  self.assertEqual(len(e._passive_events),before)
  with self.assertRaises(ValueError):e.deliver_passive_event('fabricated')
 def test_pending_listener_preserves_completed_prefix_and_rechecks_eligibility(self):
  e,a,b,doc,key=self.fixture()
  import copy
  pending=copy.deepcopy(doc);pending['id']='event/pending'
  pending['variants'][0]['inputs']['choice']={'type':'boolean','authority':'gm','question':'Explicit choice'}
  e.subscribe_source_policy(a,'pending',pending,inputs={'hit':'hit'})
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.stages['atk'],1)
  eid=e._passive_pending
  with self.assertRaises(PE.PassiveEventPending):e.deliver_passive_event(eid)
  self.assertEqual(a.stages['atk'],1)
  a.hp=0;a.conditions.add('기절')
  e.deliver_passive_event(eid)
  self.assertEqual(a.stages['atk'],1);self.assertIsNone(e._passive_pending)
 def test_explicit_choice_resumes_same_event_without_repeating_completed_listener(self):
  e,a,b,doc,key=self.fixture()
  import copy
  pending=copy.deepcopy(doc);pending['id']='event/choice'
  pending['variants'][0]['inputs']['choice']={'type':'boolean','authority':'gm','question':'Explicit choice'}
  second=e.subscribe_source_policy(a,'choice',pending,inputs={'hit':'hit'})
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,b,'struggle',set_damage=True)
  eid=e._passive_pending
  e=load_engine(e.r,dump_engine(e));a=e.everyone[0]
  self.assertEqual(a.stages['atk'],1)
  with self.assertRaises(ValueError):e.choose_passive_event(eid,a,second,{'hit':True})
  e.choose_passive_event(eid,a,second,{'decisions':{'choice':{'value':True,'reason':'explicit test choice'}}})
  self.assertEqual(a.stages['atk'],2);self.assertIsNone(e._passive_pending)
  self.assertEqual(e.deliver_passive_event(eid),'already_delivered')
  self.assertEqual(a.stages['atk'],2)

 def test_actual_stage_order_and_damage_request_precedes_resource_change(self):
  from unittest.mock import patch
  import heavy_injury_adapter as HEAVY
  e,a,b,doc,key=self.fixture();b.damage_cap={'value':0}
  original=HEAVY.apply_attack_damage
  observed=[]
  def apply(*args,**kwargs):
   event=list(e._passive_events.values())[-1]
   rows=PE.observations(e,event['id'])
   observed.append((rows[-1]['stage'],b.hp,a.stages['atk']))
   return original(*args,**kwargs)
  with patch.object(HEAVY,'apply_attack_damage',side_effect=apply):
   e.use_move(a,b,'struggle',set_damage=True)
  event=list(e._passive_events.values())[-1]
  rows=PE.observations(e,event['id'])
  self.assertEqual([r['stage'] for r in rows],['attempt','accuracy','damage_request','hp_loss','resolved'])
  self.assertEqual(observed,[('damage_request',8,0)])
  self.assertGreater(rows[2]['facts']['amount'],0)
  self.assertEqual(rows[3]['facts']['real_hp_loss'],0)
  self.assertEqual(a.stages['atk'],1)
  rows[1]['facts']['hit']=False
  self.assertTrue(PE.observations(e,event['id'])[1]['facts']['hit'])
  restored=load_engine(e.r,dump_engine(e))
  self.assertEqual(PE.observations(restored,event['id']),PE.observations(e,event['id']))
 def test_miss_has_no_damage_stages_and_changed_history_is_rejected(self):
  e,a,b,doc,key=self.fixture(seed=31);e.use_move(a,b,'struggle',set_damage=True)
  event=list(e._passive_events.values())[-1]
  self.assertEqual([r['stage'] for r in PE.observations(e,event['id'])],['attempt','accuracy','resolved'])
  event['observations'][1]['facts']['hit']=True
  with self.assertRaisesRegex(ValueError,'observation changed'):PE.observations(e,event['id'])
  with self.assertRaises(ValueError):e.deliver_passive_event(event['id'])

 def test_accuracy_wait_save_resume_does_not_repeat_cost_roll_or_damage(self):
  import copy
  e,a,b,doc,key=self.fixture()
  pending=copy.deepcopy(doc);pending['id']='event/pre-damage'
  pending['variants'][0]['inputs']['choice']={'type':'boolean','authority':'gm','question':'Reaction choice'}
  # Zero stage change keeps expected native damage comparable.
  pending['variants'][0]['values']['effects'][0]['delta']=0
  middle=e.subscribe_source_policy(a,'before-damage',pending,event='accuracy_resolved',inputs={'hit':'hit'})
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,b,'struggle',set_damage=True)
  eid=e._passive_pending
  self.assertEqual(b.hp,8);self.assertEqual(a.stages['atk'],0)
  self.assertEqual(a.move_uses['struggle'],1);self.assertEqual(a._action_history,['standard'])
  self.assertEqual([r['stage'] for r in PE.observations(e,eid)],['attempt','accuracy'])
  rng=e.rng.getstate()
  restored=load_engine(e.r,dump_engine(e));a,b=restored.everyone
  restored.choose_passive_event(eid,a,middle,{'decisions':{'choice':{'value':True,'reason':'explicit reaction'}}})
  self.assertLess(b.hp,8);self.assertEqual(a.stages['atk'],1)
  self.assertEqual(a.move_uses['struggle'],1);self.assertEqual(a._action_history,['standard'])
  self.assertEqual(restored.rng.getstate(),rng)
  before=dump_engine(restored);self.assertEqual(restored.deliver_passive_event(eid),'already_delivered')
  self.assertEqual(dump_engine(restored),before)
 def test_accuracy_listener_cannot_read_future_damage_observation(self):
  e,a,b,doc,key=self.fixture()
  with self.assertRaisesRegex(ValueError,'do not exist'):
   e.subscribe_source_policy(a,'future',doc,event='accuracy_resolved',inputs={'hit':'real_hp_loss'})

 def accuracy_listener(self,e,a,doc):
  import copy
  pending=copy.deepcopy(doc);pending['id']='event/wait'
  pending['variants'][0]['inputs']['decision']={'authority':'gm','type':'boolean','question':'Wait'}
  return e.subscribe_source_policy(a,'wait',pending,event='accuracy_resolved',inputs={'hit':'hit'})
 def test_changed_continuation_is_rejected_and_time_cannot_advance_while_waiting(self):
  e,a,b,doc,key=self.fixture();self.accuracy_listener(e,a,doc)
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,b,'struggle',set_damage=True)
  eid=e._passive_pending
  before=dump_engine(e)
  with self.assertRaises(PE.PassiveEventPending):e.advance_time(1)
  self.assertEqual(dump_engine(e),before)
  e._passive_events[eid]['continuation']['args']['nat']=2
  before=dump_engine(e)
  with self.assertRaisesRegex(ValueError,'continuation changed'):e.deliver_passive_event(eid)
  self.assertEqual(dump_engine(e),before);self.assertEqual(b.hp,8)
 def test_faint_during_wait_cancels_remaining_attack_without_refunding_or_repaying(self):
  e,a,b,doc,key=self.fixture();self.accuracy_listener(e,a,doc)
  with self.assertRaises(PE.PassiveEventPending):e.use_move(a,b,'struggle',set_damage=True)
  eid=e._passive_pending;a.hp=0;a.conditions.add('\uae30\uc808')
  e.deliver_passive_event(eid)
  self.assertEqual(b.hp,8);self.assertEqual(a.move_uses['struggle'],1)
  self.assertEqual(a._action_history,['standard']);self.assertIsNone(e._passive_pending)
  self.assertEqual(e._passive_events[eid]['continuation_cancelled'],'actor_no_longer_eligible')
 def test_nonordinary_intermediate_scope_rejects_before_cost(self):
  e,a,b,doc,key=self.fixture();self.accuracy_listener(e,a,doc)
  before=dump_engine(e)
  with self.assertRaisesRegex(ValueError,'standalone native'):
   e.use_move(a,b,'struggle',count_use=False,set_damage=True)
  self.assertEqual(dump_engine(e),before)

 def test_no_arbitrary_producer_or_context_field_and_no_redefinition(self):
  e,a,b,doc,key=self.fixture()
  for args in [{'event':'assert_hit','inputs':{'hit':'hit'}},{'inputs':{'hit':'fake_hit'}}]:
   with self.assertRaises(ValueError):e.subscribe_source_policy(a,'bad',doc,**args)
  doc['variants'][0]['values']['effects'][0]['delta']=2
  with self.assertRaises(ValueError):e.subscribe_source_policy(a,'on-hit',doc,inputs={'hit':'hit'})

if __name__=='__main__':unittest.main()
