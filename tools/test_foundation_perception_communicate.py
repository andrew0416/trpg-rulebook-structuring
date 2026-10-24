"""Common communication through actual sender, receiver, budgets and clocks."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_body_modes as _fixture_test_category2_body_modes
from state_codec import dump_engine,load_engine,StateCodecError
import perception_communicate as M,state_grants as G,world_entities as W,roll_context as R,aura_pulse as P


class CommunicateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 def setUp(self):
  _fixture_test_category2_body_modes.Tests.setUp(self);G.grant(self.a,'capabilities','Aura Pulse','fixture:message','fixture')
  self.e.pokemon_activity(self.a,'configure_intelligence',
      portrayal='Pokemon use assigned communication opposition skills',discussed_with=['communication participants'],
      social=True,education=True,reason='explicit campaign permission retained by communication restores')
 def policy(self,index=0):return json.loads((ROOT/'data/examples/perception-communicate.json').read_text(encoding='utf8'))[index]
 def send(self,request='message/1',*,value=None,target=None,options=None):
  return self.e.communicate(self.a,target or self.t,value or self.policy(),'specified message',request_id=request,roll_options=options)
 def allow(self,target=None,allowed=True):
  return self.e.set_communication_consent(target or self.t,self.a,self.policy()['source'],allowed,reason='actual receiver consent')
 def snap(self):return dump_engine(self.e)
 def connections(self):return getattr(self.e,M.KEY)['connections']
 def fixed(self,value,win=False):
  return {label:{'fixed':[6 if (label=='sender')==win else 1]*R.plan(self.e,actor,value['consent'][label+'_skill'],purpose=value['consent']['purpose'],target=other)['dice_count']}
          for label,actor,other in (('sender',self.a,self.t),('recipient',self.t,self.a))}
 def test_willing_actual_delivery_replay_is_single_and_does_not_open_surface_reading(self):
  self.allow();self.t.spec['hidden_memory']='private';out=self.send();self.assertEqual(out['status'],'delivered')
  self.assertEqual(self.e.communication_messages(self.t),[out['message']]);before=self.snap()
  self.assertTrue(self.send()['replayed']);self.assertEqual(before,self.snap());self.assertNotIn('private',str(out))
  self.assertNotIn(P.KEY,self.t.spec)
  with self.assertRaises(ValueError):self.e.read_aura_thought(self.a,self.t)
  with self.assertRaises(ValueError):self.e.communicate(self.a,self.t,self.policy(),'changed text',request_id='message/1')
  self.assertEqual(before,self.snap())
 def test_consent_is_directional_and_revocation_closes_only_the_actual_pair(self):
  self.allow(self.p);self.assertEqual(self.send()['reason'],'mind_not_open')
  self.allow();self.assertEqual(self.send('message/2')['status'],'delivered');self.allow(allowed=False)
  self.assertEqual(next(iter(self.connections().values()))['ending'],'consent_revoked')
  self.assertEqual(self.send('message/3')['reason'],'mind_not_open');self.assertEqual(len(self.e.communication_messages(self.t)),1)
 def test_source_capability_qualification_actual_identity_and_selected_rule_are_required(self):
  self.allow();before=self.snap()
  for a,t in ((copy(self.a),self.t),(self.a,copy(self.t)),(self.a,self.a)):
   with self.assertRaises(ValueError):self.e.communicate(a,t,self.policy(),'text',request_id='bad')
   self.assertEqual(before,self.snap())
  value=self.policy();value['requirements']=[{'kind':'skill','skill':'명령','rank':6,'effective':False}]
  with self.assertRaisesRegex(ValueError,'qualification'):self.send(value=value)
  self.assertEqual(before,self.snap());G.revoke(self.a,'fixture:message');before=self.snap()
  with self.assertRaisesRegex(ValueError,'capability'):self.send()
  self.assertEqual(before,self.snap())
 def test_native_pulse_respects_isolation_without_inventing_mindlock_immunity(self):
  G.grant(self.t,'capabilities','Mindlock','fixture:mindlock','fixture')
  out=self.e.project_aura_thought(self.a,self.t,'native allowed projection');self.assertEqual(out['text'],'native allowed projection')
  self.t.spec.setdefault('feats',[]).append('Utter Isolation')
  with self.assertRaisesRegex(ValueError,'receiving blocked'):self.e.project_aura_thought(self.a,self.t,'blocked projection')
  self.assertEqual(len(P.state(self.t)['received']),1);self.assertEqual(getattr(self.e,M.KEY)['attempts'][-1]['reason'],'receiver_blocked')
 def test_declared_receiver_blocker_is_live_even_after_link_has_been_opened(self):
  value=self.policy(1);options=self.fixed(value,True);self.assertEqual(self.send(value=value,options=options)['status'],'delivered')
  G.grant(self.t,'capabilities','Mindlock','fixture:mindlock','fixture')
  out=self.send('message/2',value=value);self.assertEqual((out['status'],out['reason']),('failed','receiver_blocked'))
  self.assertEqual(len(self.e.communication_messages(self.t)),1)
 def test_native_opposition_tie_fails_and_new_request_id_cannot_reset_retry_budget(self):
  value=self.policy(1);options=self.fixed(value,False);out=self.send(value=value,options=options)
  self.assertEqual((out['status'],out['reason']),('failed','opposed_failed'));self.assertEqual(out['check']['result']['winner_id'],self.t.entity_id)
  self.assertEqual(self.send('another/request',value=value,options=self.fixed(value,True))['reason'],'retry_exhausted')
  renamed=deepcopy(value);renamed['id']='changed declaration name'
  self.assertEqual(self.send('third/request',value=renamed)['reason'],'retry_exhausted')
  self.assertFalse(self.connections());self.assertEqual(len(getattr(self.e,M.KEY)['attempts']),1)
 def test_successful_opposition_reuses_link_and_never_grants_voluntary_reading(self):
  value=self.policy(1);out=self.send(value=value,options=self.fixed(value,True));self.assertEqual(out['status'],'delivered')
  self.assertEqual(out['check']['result']['winner_id'],self.a.entity_id);self.assertEqual(self.send('message/2',value=value)['status'],'delivered')
  self.assertIsNone(self.send('message/3',value=value)['check'])
  with self.assertRaises(ValueError):self.e.read_aura_thought(self.a,self.t)
  self.assertEqual(self.send('message/4',value=value)['reason'],'frequency_exhausted')
 def test_changed_source_policy_cannot_redefine_frequency_limits_or_retry_unit(self):
  self.allow();self.send();before=self.snap()
  for field,changed in (('frequency',{'kind':'scene','uses':999}),('retry',None),('connection',{'maximum':99,'lifetime':{}}),('consent',{'kind':'none'})):
   value=self.policy();value['id']='renamed';value[field]=changed
   with self.assertRaisesRegex(ValueError,'source policy'):self.send('new/request',value=value)
   self.assertEqual(before,self.snap())
 def test_connection_capacity_uses_actual_sender_and_releases_at_native_seconds_boundary(self):
  self.allow();self.allow(self.p);self.send();out=self.send('message/2',target=self.p)
  self.assertEqual(out['reason'],'connection_limit');self.e.advance_time(9);self.assertTrue(M.has_connections(self.e))
  self.e.advance_time(1);self.assertFalse(M.has_connections(self.e))
  self.assertEqual(self.send('message/3',target=self.p)['status'],'delivered');self.assertEqual(len(self.e.communication_messages(self.p)),1)
 def test_explicit_disconnect_and_scene_end_do_not_reset_failure_history(self):
  value=self.policy(1);self.send(value=value,options=self.fixed(value,True))
  self.assertTrue(self.e.disconnect_communication(self.a,self.t,value['source'],reason='actual sender ended channel'))
  self.assertFalse(self.e.disconnect_communication(self.a,self.t,value['source'],reason='already ended'))
  self.assertEqual(self.send('message/2',value=value,options=self.fixed(value,False))['reason'],'opposed_failed')
  self.assertEqual(self.send('message/3',value=value)['reason'],'retry_exhausted');self.e.end_scene(self.e.everyone)
  self.assertEqual(self.send('message/4',value=value,options=self.fixed(value,True))['status'],'delivered')
  self.e.end_scene(self.e.everyone);self.assertFalse(M.has_connections(self.e))
 def test_same_pair_retry_delay_uses_actual_elapsed_time(self):
  value=self.policy();value['retry'].update(delay_seconds=5,maximum_failures=None)
  self.assertEqual(self.send(value=value)['reason'],'mind_not_open');self.allow();self.assertEqual(self.send('message/2',value=value)['reason'],'retry_wait')
  self.e.advance_time(5);self.assertEqual(self.send('message/3',value=value)['status'],'delivered')
 def test_sender_scope_failure_limit_cannot_move_to_another_recipient(self):
  value=self.policy();value['retry'].update(scope='sender',maximum_failures=1)
  self.assertEqual(self.send(value=value)['reason'],'mind_not_open');self.allow(self.p)
  self.assertEqual(self.send('new/recipient',value=value,target=self.p)['reason'],'retry_exhausted')
 def test_relationship_exception_checks_actual_owner_and_never_infers_two_unknown_owners(self):
  self.allow();self.t.pos=(19,3);self.assertEqual(self.send()['distance_exemption'],'owned_pokemon')
  self.t.spec.pop('trainer_id');self.assertEqual(self.send('message/2')['reason'],'out_of_range')
  self.a.spec.pop('trainer_id',None);self.assertEqual(self.send('message/3')['reason'],'out_of_range')
 def test_named_pair_distance_exemption_is_current_and_does_not_apply_to_other_target(self):
  value=self.policy(1);self.t.pos=(19,3);self.assertEqual(self.send(value=value)['reason'],'out_of_range')
  # A different period allows a fresh attempt, but does not create the relationship.
  self.e.end_scene(self.e.everyone);self.e.gm.observe_communication_relationship(self.a,self.t,'authored/twin_soul',value['source'],True,reason='GM observed exact relationship')
  out=self.send('message/2',value=value,options=self.fixed(value,True));self.assertEqual(out['distance_exemption'],'authored/twin_soul')
  self.p.pos=(18,3);self.assertEqual(self.send('message/3',value=value,target=self.p)['reason'],'out_of_range')
  self.e.gm.observe_communication_relationship(self.a,self.t,'authored/twin_soul',value['source'],False,reason='relationship ended')
  self.assertEqual(self.send('message/4',value=value)['reason'],'out_of_range')
 def test_unknown_distance_and_observed_blocked_path_do_not_deliver_messages(self):
  value=self.policy();value.update(distance_exceptions=[],retry=None);self.t.location={'kind':'unknown'}
  self.assertEqual(self.send(value=value)['reason'],'distance_unknown');self.t.pos=(7,3)
  value['id']='different';value['path']='mental'
  # Fresh engine because this is a different source policy.
  self.setUp();self.e.gm.observe_sensory_environment(self.a,self.t,paths={'mental':False},present=True,reason='actual blocking')
  self.allow();self.assertEqual(self.send(value=value)['reason'],'path_blocked');self.assertEqual(self.e.communication_messages(self.t),[])
 def test_actual_condition_lifetime_and_source_revocation_release_links(self):
  value=self.policy();value['connection']['lifetime']={'while':{'owner':'user','condition':'마비'}}
  self.e.apply_status(self.a,'마비');self.allow();self.send(value=value);self.assertTrue(M.has_connections(self.e))
  self.e.cure_status(self.a,'마비');self.assertFalse(M.has_connections(self.e))
  self.e.apply_status(self.a,'마비');self.send('message/2',value=value);G.revoke(self.a,'fixture:message')
  import effect_lifetime_policy as L
  L.reconcile(self.e);self.assertFalse(M.has_connections(self.e))
 def test_false_initial_lifetime_condition_never_opens_or_delivers(self):
  value=self.policy();value['connection']['lifetime']={'while':{'owner':'user','condition':'마비'}}
  self.allow();out=self.send(value=value);self.assertEqual(out['reason'],'connection_condition_unavailable')
  self.assertFalse(M.has_connections(self.e));self.assertEqual(self.e.communication_messages(self.t),[])
 def test_large_time_interval_ends_link_at_its_actual_deadline(self):
  self.allow();self.send();self.e.advance_time(100)
  row=next(iter(self.connections().values()));self.assertEqual((row['ended_at'],self.e.elapsed_seconds),(10,100))
  self.assertEqual(row['status'],'closed');self.assertEqual(len(self.e.communication_messages(self.t)),1)
 def test_connection_turn_expiry_uses_actual_recipient_not_an_unrelated_turn(self):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  value=self.policy();value['connection']['lifetime']={'until':{'event':'turn_end','owner':'target'}}
  self.allow();self.send(value=value);self.e.end_of_turn(self.a);self.assertTrue(M.has_connections(self.e))
  self.e.start_of_turn(self.t,initiative_count=10);self.e.end_of_turn(self.t);self.assertFalse(M.has_connections(self.e))
 def test_opposed_equal_totals_preserve_actual_receiver_status_quo(self):
  value=self.policy(1);options={}
  for label,actor,target in (('sender',self.a,self.t),('recipient',self.t,self.a)):
   plan=R.plan(self.e,actor,'명령',purpose=value['consent']['purpose'],target=target)
   options[label]={'fixed':[1]*plan['dice_count'],'mods':10-plan['dice_count']-plan['modifier']}
  out=self.send(value=value,options=options);self.assertEqual(out['check']['rolls'][0]['total'],out['check']['rolls'][1]['total'])
  self.assertEqual(out['reason'],'opposed_failed');self.assertEqual(self.e.communication_messages(self.t),[])
 def test_recipient_retry_scope_shares_failure_limit_across_actual_senders(self):
  value=self.policy();value['retry'].update(scope='recipient',maximum_failures=1)
  self.assertEqual(self.send(value=value)['reason'],'mind_not_open');G.grant(self.p,'capabilities','Aura Pulse','fixture:second-sender','fixture')
  self.e.set_communication_consent(self.t,self.p,value['source'],True,reason='actual second sender consent')
  out=self.e.communicate(self.p,self.t,value,'second sender message',request_id='another/sender')
  self.assertEqual(out['reason'],'retry_exhausted');self.assertEqual(self.e.communication_messages(self.t),[])
 def test_current_source_change_and_tampered_time_record_reject_without_advancing_world(self):
  self.allow();before=self.snap();selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/other' if uid==self.policy()['source'] else selected(uid)):
   with self.assertRaises(ValueError):self.send()
  self.assertEqual(before,self.snap());self.send();row=next(iter(self.connections().values()));row['lifetime']['end_at']=1
  before=deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),getattr(self.e,M.KEY)))
  with self.assertRaises(ValueError):self.e.advance_time(5)
  self.assertEqual(before,(self.e.elapsed_seconds,self.e.rng.getstate(),getattr(self.e,M.KEY)))
 def test_late_delivery_failure_rolls_back_checks_rng_frequency_links_and_messages(self):
  value=self.policy(1);before=self.snap()
  with patch.object(M,'_deliver',side_effect=ValueError('late message failure')):
   with self.assertRaisesRegex(ValueError,'late message failure'):self.send(value=value,options=self.fixed(value,True))
  self.assertEqual(before,self.snap())
 def test_json_and_gm_restore_keep_permissions_links_receipts_and_failure_budget(self):
  value=self.policy(1);self.send(value=value,options=self.fixed(value,False));saved=self.snap()
  loaded=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));actors=W.actor_index(loaded)
  out=loaded.communicate(actors[self.a.entity_id],actors[self.t.entity_id],value,'specified message',request_id='changed/request')
  self.assertEqual(out['reason'],'retry_exhausted');self.assertEqual(loaded.communication_messages(actors[self.t.entity_id]),[])
  # Successful channel and consent restored separately from failed attempts.
  self.setUp();self.allow();self.send();snapshot=self.e.gm.snapshot();self.e.advance_time(10);self.e.gm.restore(snapshot)
  self.assertTrue(M.has_connections(self.e));self.assertTrue(self.send()['replayed']);self.assertEqual(len(self.e.communication_messages(self.t)),1)
  loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)));actors=W.actor_index(loaded)
  loaded.advance_time(10);self.assertFalse(M.has_connections(loaded));self.assertEqual(len(loaded.communication_messages(actors[self.t.entity_id])),1)
 def test_corrupt_saved_histories_dangling_endpoints_and_policy_changes_are_rejected(self):
  self.allow();self.send();saved=self.snap();state=getattr(self.e,M.KEY)
  state['attempts'][0]['status']='failed';self.assertFalse(self.e.validate_state()['valid'])
  with self.assertRaises(ValueError):self.e.communication_messages(self.t)
  loaded=load_engine(self.r,saved);getattr(loaded,M.KEY)['policies'][self.policy()['source']]['declaration']['retry']=None
  self.assertFalse(loaded.validate_state()['valid'])
 def test_malformed_policy_and_non_opposed_roll_inputs_are_atomic(self):
  before=self.snap()
  for mutate in (lambda d:d.update(extra=True),lambda d:d['connection'].update(maximum=True),lambda d:d['retry'].update(period='invented'),lambda d:d.update(blockers=[{'field':'hidden_memory','names':['anything'],'source':P.SOURCE}]),lambda d:d['frequency'].update(uses=False)):
   value=self.policy();mutate(value)
   with self.assertRaises(ValueError):self.send(value=value)
   self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):self.send(options={'sender':{'fixed':[6]}})
  self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
