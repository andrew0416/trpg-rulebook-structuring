"""Native Far Reading uses actual Telepathy through the existing common owners."""
from copy import copy,deepcopy
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import json,unittest
import test_category2_progression_state as _fixture_test_category2_progression_state
from grid import Grid
from builder import build_trainer
import telepathy as T,perception_observe as O,perception_communicate as M
import state_grants as G,state_codec as CODEC,skill_modifiers as S,roll_context as R
import capability_parameter_edges as P,activity_jobs as JOBS,acquisition_qualification as Q
import acquisition_receipts as RECEIPTS,aura_pulse as A

class FarReadingTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon(20,tutor_points=8);self.t=self.pokemon(20)
  G.replace_baseline(self.e,self.p,'capabilities',['텔레파시'])
  self.e.gm.set_skill(self.p,'집중','3d6+2',reason='observed actual Focus pool')
  self.e.gm.set_skill(self.t,'집중','3d6',reason='observed actual receiver Focus pool')
  self.e.grid=Grid(24,8);self.a.pos=(3,2);self.p.pos=(2,1);self.t.pos=(8,1)
 def snap(self):return CODEC.dump_engine(self.e)
 def teach(self,edge=T.EDGE):return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=edge,safe=True)
 def allow(self,target=None,allowed=True):
  return self.e.set_communication_consent(target or self.t,self.p,T.SOURCE,allowed,reason='actual target willingness')
 def thought(self,target=None,text='current thought'):
  return self.e.gm.observe_surface_thought(target or self.t,text,reason='observed current thought, not memory')
 def read(self,key='telepathy/read',target=None,**options):
  return self.e.read_telepathic_thought(self.p,self.t if target is None else target,request_id=key,**options)
 def fixed(self,win=False,target=None):
  target=target or self.t
  return {label:{'fixed':[6 if (label=='sender')==win else 1]*R.plan(self.e,actor,'집중',purpose='telepathy',target=other)['dice_count']}
          for label,actor,other in (('sender',self.p,target),('recipient',target,self.p))}
 def telepath(self,target=None):
  G.grant(target or self.t,'capabilities','Telepath','fixture:receiver-telepath','fixture')
 def test_selected_csv_acquisition_reuses_actual_tp_job_qualification_and_receipt(self):
  with patch.object(Q,'require',wraps=Q.require) as qualification,patch.object(JOBS,'run_fixed',wraps=JOBS.run_fixed) as job:
   out=self.teach('C2CSV/input/db/poke-edges.csv:R53:main')
  self.assertGreater(qualification.call_count,0);self.assertEqual(job.call_count,1)
  self.assertEqual((out['point_cost'],out['definition_origin']['record'],self.p.spec['tutor_points'],self.e.elapsed_seconds),(1,53,7,3600))
  receipt=next(x for x in RECEIPTS.read(self.e,self.p) if x['source_id']==T.EDGE)
  self.assertEqual((receipt['basis'],receipt['provider_id'],receipt['debit']['amount']),('native_learned_edge',self.a.entity_id,1))
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_far_reading_changes_only_actual_range_and_the_real_entrypoint_uses_common_owners(self):
  self.allow();self.thought()
  self.assertEqual(self.read()['message']['surface_thought'],'current thought')
  self.t.pos=(9,1);self.assertEqual(self.read('base-outside')['reason'],'out_of_range')
  skills=deepcopy(self.p.spec['skills']);pool=S.rank(self.r,self.p,'집중')
  self.teach('Far Reading');self.t.pos=(12,1)
  with patch.object(M,'send',wraps=M.send) as communication,patch.object(O,'route',wraps=O.route) as route:
   result=self.read('far-boundary')
  self.assertEqual((communication.call_count,route.call_count),(1,1))
  self.assertEqual(result['status'],'delivered');self.assertEqual((self.p.spec['skills'],S.rank(self.r,self.p,'집중')),(skills,pool))
  self.assertEqual(T.projection_maximum(self.p),1)
  self.t.pos=(13,1);self.assertEqual(self.read('far-outside')['reason'],'out_of_range')
 def test_live_focus_rank_and_range_edge_do_not_change_registered_policy_or_check_pool(self):
  self.allow();self.thought();self.read();body=deepcopy(M._state(self.e)['policies'][T.SOURCE])
  self.teach();self.e.gm.set_skill(self.p,'집중','4d6-2',reason='actual changed Focus pool')
  self.t.pos=(14,1);self.assertEqual(self.read('live-rank')['status'],'delivered')
  self.assertEqual(M._state(self.e)['policies'][T.SOURCE],body)
  self.allow(allowed=False);result=self.read('unwilling-live',roll_options=self.fixed(True))
  self.assertEqual((result['check']['plans'][0]['dice_count'],result['check']['plans'][0]['modifier']),(4,-2))
  self.assertEqual(S.rank(self.r,self.p,'집중')[2],4)
 def test_unwilling_reading_automatically_opposes_and_preserves_private_information_on_failure(self):
  self.thought();self.t.spec['hidden_memory']='never disclose memory'
  with patch.object(R,'resolve',wraps=R.resolve) as opposed:
   result=self.read(roll_options=self.fixed(False))
  self.assertEqual(opposed.call_count,1);self.assertEqual((result['status'],result['reason']),('failed','opposed_failed'))
  self.assertIsNone(result['message']);self.assertTrue(result['event']['supernatural_trace'])
  self.assertNotIn('never disclose',str(result));self.assertEqual(self.e.communication_messages(self.t),[])
  result=self.read('read-wins',roll_options=self.fixed(True));self.assertEqual(result['message']['surface_thought'],'current thought')
  self.assertTrue(result['event']['supernatural_trace']);self.assertEqual(self.e.communication_messages(self.p),[])
 def test_equal_focus_totals_preserve_the_unwilling_targets_status_quo(self):
  options={}
  for label,actor,target in (('sender',self.p,self.t),('recipient',self.t,self.p)):
   plan=R.plan(self.e,actor,'집중',purpose='telepathy',target=target)
   options[label]={'fixed':[1]*plan['dice_count'],'mods':10-plan['dice_count']-plan['modifier']}
  result=self.read(roll_options=options)
  self.assertEqual(result['reason'],'opposed_failed');self.assertEqual(result['check']['rolls'][0]['total'],result['check']['rolls'][1]['total'])
 def test_failed_pair_retry_penalty_is_minus_three_once_and_expires_at_exact_24_hours(self):
  self.thought();self.read('failed',roll_options=self.fixed(False));base=R.plan(self.e,self.p,'집중',purpose='telepathy',target=self.t)
  result=self.read('retry',roll_options=self.fixed(True));self.assertEqual(result['retry_modifier'],-3)
  self.assertEqual(result['check']['rolls'][0]['total'],6*base['dice_count']+base['modifier']-3)
  self.assertEqual(R.plan(self.e,self.p,'집중',purpose='ordinary')['modifier'],base['modifier'])
  other=self.pokemon(20);other.pos=(7,2);self.thought(other)
  self.assertEqual(self.read('other-pair',other,roll_options=self.fixed(True,other))['retry_modifier'],0)
  self.e.advance_time(86399);self.assertEqual(self.read('last-second',roll_options=self.fixed(True))['retry_modifier'],-3)
  loaded=self.restored();ids={x.entity_id:x for x in loaded.everyone};loaded.advance_time(1)
  out=loaded.read_telepathic_thought(ids[self.p.entity_id],ids[self.t.entity_id],request_id='expired',roll_options=self.fixed(True))
  self.assertEqual(out['retry_modifier'],0)
 def test_willingness_is_pair_specific_and_suppresses_opposition_and_unwilling_trace(self):
  self.allow();self.thought();rng=self.e.rng.getstate();result=self.read()
  self.assertIsNone(result['check']);self.assertFalse(result['event']['supernatural_trace']);self.assertEqual(self.e.rng.getstate(),rng)
  self.allow(allowed=False);self.assertIsNotNone(self.read('revoked',roll_options=self.fixed(True))['check'])
  self.assertEqual(len(self.e.telepathy_attempts(self.p)),2)
 def test_projection_count_uses_focus_divided_by_two_without_far_reading_bonus(self):
  self.teach();self.telepath();other=self.pokemon(20);other.pos=(6,2);self.telepath(other);self.allow();self.allow(other)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'recipient count'):self.e.project_telepathic_thought(self.p,[self.t,other],'group',request_id='too-many')
  self.assertEqual(self.snap(),before)
  self.e.gm.set_skill(self.p,'집중','4d6+7',reason='actual Focus rank four, independent constant')
  out=self.e.project_telepathic_thought(self.p,[self.t,other],'group',request_id='two-recipients')
  self.assertEqual([x['status'] for x in out['results']],['delivered','delivered'])
  self.assertEqual([x['text'] for x in self.e.communication_messages(other)],['group'])
  before=self.snap();self.assertTrue(self.e.project_telepathic_thought(self.p,[self.t,other],'group',request_id='two-recipients')['replayed'])
  self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.e.project_telepathic_thought(self.p,[self.t],'group',request_id='two-recipients')
  self.assertEqual(self.snap(),before)
 def test_projection_requires_recipient_telepathy_and_unwilling_recipients_still_resist(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'actual telepath'):self.e.project_telepathic_thought(self.p,[self.t],'offered',request_id='projection')
  self.assertEqual(self.snap(),before);self.telepath()
  out=self.e.project_telepathic_thought(self.p,[self.t],'offered',request_id='projection',roll_options=self.fixed(True))
  self.assertEqual(out['results'][0]['status'],'delivered');self.assertTrue(out['results'][0]['event']['supernatural_trace'])
 def test_trainer_can_offer_without_gaining_telepathy_and_actual_receiver_range_is_used(self):
  self.a.pos=(9,1);self.e.gm.set_skill(self.a,'집중',6,reason='trainer Focus does not own this ability')
  before=self.snap();result=self.e.offer_telepathic_thought(self.a,self.p,'trainer thought',request_id='trainer-offer')
  self.assertEqual(result['reason'],'out_of_range');self.assertFalse(T.owns(self.a))
  self.teach();result=self.e.offer_telepathic_thought(self.a,self.p,'trainer thought',request_id='far-offer')
  self.assertEqual(result['status'],'delivered');self.assertEqual(result['message']['sender_id'],self.a.entity_id)
  self.assertIsNone(result['check']);self.assertEqual(self.e.communication_messages(self.p),[result['message']]);self.assertFalse(T.owns(self.a))
  before=self.snap()
  with self.assertRaises(ValueError):self.e.offer_telepathic_thought(self.t,self.p,'Pokemon offer',request_id='invalid-offer')
  self.assertEqual(self.snap(),before)
 def test_mindlock_blocks_reading_but_not_projection_and_isolation_blocks_actual_receiving(self):
  self.thought();self.telepath();G.grant(self.t,'capabilities','Mindlock','fixture:mindlock','fixture')
  result=self.read();self.assertEqual(result['reason'],'receiver_blocked');self.assertTrue(result['event']['supernatural_trace'])
  self.allow();out=self.e.project_telepathic_thought(self.p,[self.t],'projection',request_id='mindlock-project')
  self.assertEqual(out['results'][0]['status'],'delivered')
  self.t.spec.setdefault('feats',[]).append('Utter Isolation')
  self.assertEqual(self.e.project_telepathic_thought(self.p,[self.t],'blocked',request_id='isolation')['results'][0]['reason'],'receiver_blocked')
  self.p.spec.setdefault('feats',[]).append('Utter Isolation')
  self.assertEqual(self.e.offer_telepathic_thought(self.a,self.p,'blocked offer',request_id='offer-isolation')['reason'],'receiver_blocked')
 def test_unknown_current_thought_stays_unknown_and_observed_fact_is_identity_bound(self):
  self.allow();self.t.spec['hidden_memory']='not a surface thought';result=self.read()
  self.assertEqual((result['message']['status'],result['message']['surface_thought']),('unknown',None))
  self.thought();self.t.spec[O.THOUGHT]['text']='forged'
  with self.assertRaises(ValueError):self.snap()
 def test_thought_observation_is_shared_with_aura_without_sharing_read_permission(self):
  self.thought();self.assertNotIn(A.KEY,self.t.spec)
  G.grant(self.a,'capabilities','Aura Pulse','fixture:aura','fixture')
  self.e.set_aura_openness(self.t,self.a,True,reason='only this aura reader is willing')
  self.assertEqual(self.e.read_aura_thought(self.a,self.t)['surface_thought'],'current thought')
  self.assertEqual(self.read(roll_options=self.fixed(False))['reason'],'opposed_failed')
  self.allow();self.thought(text='new observation')
  self.assertEqual(self.read('fresh')['message']['thought_revision'],2)
  self.assertEqual(self.e.read_aura_thought(self.a,self.t)['surface_thought'],'new observation')
 def test_out_of_range_or_unknown_distance_does_not_create_attempt_traces_or_notices(self):
  self.t.pos=(9,1);self.assertEqual(self.read()['reason'],'out_of_range')
  self.assertEqual(self.e.telepathy_attempts(),[])
  self.t.location={'kind':'unknown'}
  self.assertEqual(self.read('unknown-distance')['reason'],'distance_unknown');self.assertEqual(self.e.telepathy_attempts(),[])
 def test_actual_iron_mind_notices_each_in_range_read_attempt_including_failure_and_immunity(self):
  self.e.gm.set_skill(self.a,'집중',3,reason='actual Novice Focus prerequisite')
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append('강철의 정신'))
  self.thought(self.a);first=self.read('iron-failure',self.a,roll_options=self.fixed(False,self.a))
  self.assertEqual(first['reason'],'opposed_failed')
  G.grant(self.a,'capabilities','Mindlock','fixture:iron-block','fixture')
  self.assertEqual(self.read('iron-immunity',self.a)['reason'],'receiver_blocked')
  notices=self.e.telepathy_attempts(self.a,notices_only=True)
  self.assertEqual(len(notices),2);self.assertTrue(all(x['kind']=='telepathy_read_attempt' for x in notices))
  self.a.pos=(20,2);self.read('iron-outside',self.a);self.assertEqual(len(self.e.telepathy_attempts(self.a,notices_only=True)),2)
 def test_actual_single_read_target_and_distinct_projection_roster_are_enforced_atomically(self):
  before=self.snap()
  for other in (copy(self.t),self.p,[self.t]):
   with self.assertRaises(ValueError):self.read('invalid-target',other)
   self.assertEqual(self.snap(),before)
  self.telepath();before=self.snap()
  with self.assertRaises(ValueError):self.e.project_telepathic_thought(self.p,[self.t,self.t],'duplicate',request_id='duplicate')
  self.assertEqual(self.snap(),before)
 def test_group_late_failure_rolls_back_prior_recipient_messages_attempts_and_rng(self):
  self.telepath();other=self.pokemon(20);other.pos=(6,1);self.telepath(other);self.allow();self.allow(other)
  self.e.gm.set_skill(self.p,'집중','4d6',reason='two actual recipients')
  real=T.deliver;calls=[]
  def broken(*args,**options):
   calls.append(1)
   if len(calls)==2:raise ValueError('late recipient failure')
   return real(*args,**options)
  before=self.snap()
  with patch.object(T,'deliver',side_effect=broken):
   with self.assertRaisesRegex(ValueError,'late recipient'):self.e.project_telepathic_thought(self.p,[self.t,other],'atomic group',request_id='atomic')
  self.assertEqual(self.snap(),before)
 def test_capability_or_level_loss_refunds_actual_tp_once_and_preserves_base_telepathy_sources(self):
  self.teach();G.grant(self.p,'capabilities','Telepath','independent-telepath','feature')
  G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual((self.p.spec['tutor_points'],P.records(self.p,T.EDGE)[0]['status']),(7,'active'))
  G.transition(self.e,self.p,lambda e,c:G.revoke(c,'independent-telepath'))
  self.assertEqual((self.p.spec['tutor_points'],P.records(self.p,T.EDGE)[0]['status']),(8,'refunded'))
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],8)
  G.replace_baseline(self.e,self.p,'capabilities',['텔레파시']);self.teach()
  self.e.gm.set_level(self.p,19,reason='actual prerequisite loss');self.assertEqual(self.p.spec['tutor_points'],8)
 def test_json_and_gm_restores_preserve_thought_retry_events_receipt_and_durable_replay(self):
  self.teach();self.thought();failed=self.read('stored-read',roll_options=self.fixed(False));self.telepath();self.allow()
  projected=self.e.project_telepathic_thought(self.p,[self.t],'stored projection',request_id='stored-group')
  saved=self.e.gm.snapshot();loaded=self.restored();idx={x.entity_id:x for x in loaded.everyone};before=CODEC.dump_engine(loaded)
  out=loaded.read_telepathic_thought(idx[self.p.entity_id],idx[self.t.entity_id],request_id='stored-read',roll_options=self.fixed(False))
  self.assertTrue(out['replayed']);self.assertEqual(out['event'],failed['event']);self.assertEqual(CODEC.dump_engine(loaded),before)
  self.e.gm.set_level(self.p,19,reason='temporary correction');self.e.gm.restore(saved)
  self.assertEqual(self.p.spec['tutor_points'],7)
  self.assertTrue(self.e.project_telepathic_thought(self.p,[self.t],'stored projection',request_id='stored-group')['replayed'])
 def test_acquisition_prerequisite_tp_and_late_job_failures_are_atomic(self):
  for kind in ('level','capability','owner','points'):
   self.setUp()
   if kind=='level':self.e.gm.set_level(self.p,19,reason='actual too low level')
   if kind=='capability':G.replace_baseline(self.e,self.p,'capabilities',[])
   if kind=='owner':
    another=self.add(build_trainer(self.r,'other owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
    self.p.spec['trainer_id']=another.entity_id
   if kind=='points':self.p.spec['tutor_points']=0
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before,kind)
  self.setUp();before=self.snap();real=JOBS.run_fixed
  def broken(*args,**options):real(*args,**options);raise ValueError('late job refusal')
  with patch.object(JOBS,'run_fixed',side_effect=broken):
   with self.assertRaisesRegex(ValueError,'late job'):self.teach()
  self.assertEqual(self.snap(),before)
 def test_native_source_policy_information_and_request_identity_cannot_be_relabelled(self):
  self.allow();self.thought();self.read();before=self.snap();value=T.policy(self.r)['declaration']
  for altered in ('range','retry','capabilities'):
   changed=deepcopy(value)
   if altered=='range':changed['range']['maximum']=999
   if altered=='retry':changed['retry']=None
   if altered=='capabilities':changed['capabilities']=[]
   with self.assertRaises(ValueError):self.e.communicate(self.p,self.t,changed,'forged',request_id='forged')
   self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.e.communicate(self.p,self.t,value,'changed operation',request_id='telepathy/read')
  self.assertEqual(self.snap(),before)
  selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/different' if uid==T.SOURCE else selected(uid)):
   with self.assertRaises(ValueError):self.read('wrong-source')
  self.assertEqual(self.snap(),before)
 def test_external_json_teaching_replays_after_restore_without_double_payment(self):
  source='input/'+self.r.selection.units[T.EDGE]['source']['file']
  document={'schema':1,'id':'far-reading-author','variants':[{'rule_id':T.EDGE,
   'source':{'file':source,'sha256':sha256((Path(self.r.root)/source).read_bytes()).hexdigest()},
   'inputs':{},'values':{'teaching_operation':{'kind':'edge','edge':T.EDGE,'safe':True}}}]}
  result=self.e.execute_source_policy_teaching(self.a,self.p,document,request_id='far-reading/native')
  self.assertEqual(result['status'],'PolicyTeachingCompleted');loaded=self.restored();idx={x.entity_id:x for x in loaded.everyone};before=CODEC.dump_engine(loaded)
  self.assertTrue(loaded.execute_source_policy_teaching(idx[self.a.entity_id],idx[self.p.entity_id],document,request_id='far-reading/native')['replayed'])
  self.assertEqual(CODEC.dump_engine(loaded),before)

 def test_retry_penalty_does_not_coerce_boolean_skill_modifiers_into_valid_numbers(self):
  self.read('first-failure',roll_options=self.fixed(False));options=self.fixed(True);options['sender']['mods']=True;before=self.snap()
  with self.assertRaises(ValueError):self.read('boolean-modifier',roll_options=options)
  self.assertEqual(self.snap(),before)

 def test_unowned_iron_mind_source_is_not_a_dependency_of_ordinary_telepathy(self):
  self.allow(self.a);self.thought(self.a);selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**options:uid+'/different' if uid=='edge/강철의-정신' else selected(uid,**options)):
   result=self.read('no-iron-source',self.a)
  self.assertEqual(result['status'],'delivered');self.assertIsNone(result['event']['notice'])
  self.e.gm.set_skill(self.a,'집중',3,reason='actual Novice Focus prerequisite')
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append('강철의 정신'));before=self.snap()
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**options:uid+'/different' if uid=='edge/강철의-정신' else selected(uid,**options)):
   with self.assertRaises(ValueError):self.read('owned-wrong-iron-source',self.a)
  self.assertEqual(self.snap(),before)

if __name__=='__main__':unittest.main()

