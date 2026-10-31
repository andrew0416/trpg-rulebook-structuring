"""Source counterexamples for actual child costs, rolls, lifetime and replay."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import common_checks as C
import action_lifecycle as ACTION
import maneuver_grants as MG
import effect_contracts as EFFECTS
import effects_ext as EXT
import effects as FX
import skill_feature_actions as SF

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT)
 def setUp(self):
  self.e=Engine(self.rules,5)
  def actor(name,side,pos):return Combatant(self.rules,dict(id='trainer/'+name,name=name,kind='trainer',size='Medium',side=side,pos=pos,level=50,stats=dict(hp=100,atk=20,**{'def':20},spa=20,spd=20,spe=1),skills={'전투':4,'육상':4,'곡예':4},movement={'land':6,'power':4},weight_kg=30,feats=[],moves=['move/괴력','move/돌진','move/물고버티기']))
  self.a=actor('A','party',(1,1));self.b=actor('B','wild',(2,1));self.e.everyone=[self.a,self.b];self.e.gm.everyone=self.e.everyone;self.e.grid=Grid(8,8)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def grant(self,source='move/괴력',effect=None,options=None):
  effect=deepcopy(effect) if effect is not None else next(x for x in self.rules.move_mech(source)[0]['effects_exec'] if x['type']=='free_maneuver')
  occurrence,receipt=EFFECTS.issue_receipt(self.e,source,self.a,self.b,effect,0)
  ctx=dict(engine=self.e,attacker=self.a,target=self.b,hit=True,source_id=source,effect_occurrence=occurrence,effect_receipt=receipt)
  if options is not None:ctx['maneuver_options']=options
  self.ctx=ctx;self.effect=effect
  return EXT.h_free_maneuver(self.e,self.a,self.b,effect,ctx)
 def opts(self,**changes):
  out=dict(accept=True,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[3]*4},defender_options={'fixed':[2]*4});out.update(changes);return out
 def resolve(self,pending,**changes):return MG.resolve(self.e,self.a,pending.grant_id,**self.opts(**changes))
 def test_strength_auto_accuracy_still_opposed_and_free_cost(self):
  pending=self.grant();self.a.budget['standard']=0
  with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as ac,patch.object(self.e,'opposed_check',wraps=self.e.opposed_check) as opposed:
   result=self.resolve(pending,fixed_accuracy=1)
  self.assertEqual(result.tag,'Completed');self.assertEqual(ac.call_count,0);self.assertEqual(opposed.call_count,1);self.assertEqual(self.b.pos,(3,1));self.assertEqual(self.a._action_history,['free']);self.assertEqual(self.a.budget,dict(standard=0,shift=1,swift=1))
 def test_strength_tie_is_failure_despite_automatic_hit(self):
  result=self.resolve(self.grant(),defender_options={'fixed':[3]*4});self.assertIs(result.result,False);self.assertEqual(self.b.pos,(2,1));self.assertEqual(self.a._action_history,['free'])
 def test_take_down_cost_waiver_does_not_waive_trip_accuracy(self):
  pending=self.grant('move/돌진')
  with patch.object(self.e,'opposed_check',wraps=self.e.opposed_check) as opposed:
   result=self.resolve(pending,fixed_accuracy=1)
  self.assertIs(result.result,False);self.assertNotIn('넘어짐',self.b.conditions);self.assertEqual(opposed.call_count,0);self.assertEqual(self.a.budget['standard'],1)
 def test_take_down_success_uses_trip_six_and_chosen_acrobatics(self):
  result=self.resolve(self.grant('move/돌진'),fixed_accuracy=6,challenger_skill='곡예',defender_skill='곡예');self.assertTrue(result.result);self.assertIn('넘어짐',self.b.conditions)
 def test_each_participant_choice_is_required_before_cost(self):
  pending=self.grant();before=deepcopy(self.a.budget)
  for options in ({},{'accept':True},{'accept':True,'challenger_skill':'전투'}):
   result=MG.resolve(self.e,self.a,pending.grant_id,**options);self.assertEqual(result.tag,'AwaitingInput')
  self.assertEqual(self.a.budget,before);self.assertEqual(self.a._action_history,[])
 def test_optional_decline_consumes_no_child_cost_and_replays(self):
  pending=self.grant();result=MG.resolve(self.e,self.a,pending.grant_id,accept=False)
  self.assertFalse(result.accepted);self.assertEqual(self.a._action_history,[]);self.assertIs(MG.resolve(self.e,self.a,pending.grant_id),result)
  with self.assertRaises(ValueError):self.resolve(pending)
 def test_same_occurrence_and_completed_resolve_do_not_repeat_world_effect(self):
  pending=self.grant();result=self.resolve(pending);before=(self.b.pos,list(self.a._action_history),self.e.rng.getstate())
  self.assertIs(EXT.h_free_maneuver(self.e,self.a,self.b,self.effect,self.ctx),result);self.assertIs(MG.resolve(self.e,self.a,pending.grant_id),result);self.assertEqual((self.b.pos,self.a._action_history,self.e.rng.getstate()),before)
 def test_distinct_occurrences_are_distinct_child_ids(self):
  one=self.grant();two=self.grant();self.assertNotEqual(one.grant_id,two.grant_id)
 def test_forged_or_retargeted_effect_receipt_is_rejected(self):
  pending=self.grant()
  for ctx,target,effect in [(dict(self.ctx,effect_receipt=object()),self.b,self.effect),(self.ctx,self.a,self.effect),(self.ctx,self.b,dict(self.effect,auto_success=True))]:
   with self.assertRaises(ValueError):EXT.h_free_maneuver(self.e,self.a,target,effect,ctx)
 def test_unsourced_auto_success_flags_cannot_skip_trip(self):
  effect={'type':'free_maneuver','maneuver':'걸기','auto_hit':True}
  result=self.grant('move/돌진',effect);self.assertEqual(result.reason,'missing_refinement');self.assertNotIn('넘어짐',self.b.conditions)
 def test_mixed_maneuver_string_never_selects_first_substring(self):
  result=self.grant('move/돌진',{'type':'free_maneuver','maneuver':'무장해제/걸기/밀기 (선택)'});self.assertEqual(result.tag,'Blocked');self.assertEqual(self.b.pos,(2,1));self.assertNotIn('넘어짐',self.b.conditions)

 def test_jaw_lock_free_child_installs_actual_grapple_after_ordinary_hit_and_opposed_win(self):
  import grapple_state as GR
  result=self.grant('move/물고버티기');self.assertEqual(result.basis['authority'],dict(action_cost='free',accuracy='ordinary',opposed='required',success='check'))
  result=self.resolve(result);self.assertEqual(result.tag,'Completed');self.assertEqual(GR.relation(self.e,self.b)['dominant'],self.a.entity_id);self.assertEqual(self.a._action_history,['free'])

 def test_octolock_auto_hit_still_requires_actual_grapple_opposed_win(self):
  import grapple_state as GR
  result=self.grant('move/문어굳히기');self.assertEqual(result.basis['authority'],dict(action_cost='included',accuracy='automatic',opposed='required',success='check'))
  result=self.resolve(result,fixed_accuracy=1,defender_options={'fixed':[3]*4});self.assertIs(result.result,False);self.assertIsNone(GR.relation(self.e,self.b));self.assertEqual(self.a._action_history,[])
 def test_pumpkaboo_source_owned_automatic_dominance_needs_neither_accuracy_nor_skills(self):
  import grapple_state as GR
  source='ability/호박잡기-playtest';pending=self.grant(source,{'type':'free_maneuver','maneuver':'붙잡기','auto_hit':True,'advantage':True})
  before=self.e.rng.getstate()
  with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as ac,patch.object(self.e,'opposed_check',wraps=self.e.opposed_check) as opposed:
   result=MG.resolve(self.e,self.a,pending.grant_id,accept=True)
  self.assertEqual((ac.call_count,opposed.call_count),(0,0));self.assertEqual(self.e.rng.getstate(),before);self.assertEqual(GR.relation(self.e,self.b)['dominant'],self.a.entity_id);self.assertEqual(self.a._action_history,[])
  self.assertEqual(MG.resolve(self.e,self.a,pending.grant_id,accept=True),result)
 def test_missing_source_refinement_is_distinct_from_runtime_gap(self):
  result=self.grant('feat/텔레키네틱-버스트',{'type':'free_maneuver','maneuver':'무장해제/걸기/밀기 (선택)'});self.assertEqual(result.reason,'missing_refinement')
 def test_free_cost_does_not_bypass_status_permission(self):
  pending=self.grant();self.a.conditions.add('얼음');result=self.resolve(pending);self.assertIs(result.result,False);self.assertEqual(self.b.pos,(2,1));self.assertEqual(self.a._action_history,[])
 def test_immediate_choice_expires_at_turn_close(self):
  pending=self.grant();ACTION.check_end(self.e,self.a);ACTION.close_turn(self.e,self.a);result=MG.resolve(self.e,self.a,pending.grant_id);self.assertFalse(result.accepted);self.assertEqual(self.b.pos,(2,1))
 def test_pending_grant_cannot_execute_in_later_round(self):
  pending=self.grant();self.e.round_no+=1;result=self.resolve(pending);self.assertEqual((result.tag,result.reason),('Blocked','invalid_state'));self.assertEqual(self.b.pos,(2,1))
 def test_malformed_skill_can_be_corrected_before_observation(self):
  pending=self.grant()
  with self.assertRaises(ValueError):self.resolve(pending,defender_skill='곡예')
  self.assertEqual(self.a._action_history,[]);self.assertTrue(self.resolve(pending).result)
 def featured(self,bad):
  self.a.spec['feats']=[SF.MONKEY];self.b.spec['feats']=[SF.MONKEY]
  return self.opts(challenger_options={'roll_id':'grant-a','fixed':[1]*4,'feature':SF.MONKEY,'feature_options':{'decision':lambda first:True,'reroll_faces':[4]*4}},defender_options={'roll_id':'grant-b','fixed':[1]*4,'feature':SF.MONKEY,'feature_options':{'decision':(lambda first:'bad') if bad else (lambda first:False)}})
 def test_observed_choice_error_resumes_without_duplicate_free_accuracy_or_first_roll(self):
  pending=self.grant('move/돌진')
  with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as ac:
   with self.assertRaises(ValueError):MG.resolve(self.e,self.a,pending.grant_id,**self.featured(True))
   first=SF.event(self.e,self.a,'grant-a').first;history=list(self.a._action_history);rng=self.e.rng.getstate()
   with self.assertRaises(ValueError):ACTION.check_end(self.e,self.a)
   with self.assertRaises(ValueError):MG.resolve(self.e,self.a,pending.grant_id,accept=False)
   changed=self.featured(False);changed['fixed_accuracy']=19
   with self.assertRaises(ValueError):MG.resolve(self.e,self.a,pending.grant_id,**changed)
   result=MG.resolve(self.e,self.a,pending.grant_id,**self.featured(False))
  self.assertTrue(result.result);self.assertEqual(ac.call_count,1);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.a._action_history,history);self.assertIs(SF.event(self.e,self.a,'grant-a').first,first)
 def test_private_native_grant_cannot_be_invented(self):
  opts=self.opts();opts.pop('accept')
  with self.assertRaises(ValueError):self.e.push(self.a,self.b,_grant=object(),**opts)
 def test_internal_move_tokens_keep_source_specific_cost_and_frequency_scope(self):
  with self.assertRaises(ValueError):
   with ACTION.move_grant(self.e,self.a,self.b,'move/돌진',source='maneuver/기회-공격',kind='free'):pass
  with ACTION.move_grant(self.e,self.a,self.b,'move/돌진',source='same_move_activation') as token:
   with self.assertRaises(ValueError):ACTION.consume_move_grant(self.e,token,self.a,self.b,'move/돌진',count_use=False,free_action=True)
   self.assertEqual(ACTION.consume_move_grant(self.e,token,self.a,self.b,'move/돌진',count_use=False,free_action=False),(True,None))
   self.assertEqual(ACTION.consume_move_grant(self.e,token,self.a,self.b,'move/돌진',count_use=False,free_action=False),(False,None))
 def test_known_unknown_payload_field_is_not_silently_ignored(self):
  effect={'type':'free_maneuver','maneuver':'밀기','auto_hit':True,'bonus':100};result=self.grant('move/괴력',effect);self.assertEqual(result.reason,'missing_refinement')
 def test_inline_actual_choices_supported(self):
  result=self.grant('move/돌진',options=self.opts());self.assertEqual(result.tag,'Completed');self.assertIn('넘어짐',self.b.conditions)

 def test_native_parent_move_damage_frequency_and_standard_are_not_replayed_on_child_resume(self):
  for source in ('move/괴력','move/돌진'):
   self.setUp();damage=self.e.use_move(self.a,self.b,source);self.assertGreater(damage,0)
   row=next(iter(self.a.custom_conditions[MG.RECORDS].values()));self.assertEqual(row['pending'].tag,'AwaitingInput');self.assertEqual(self.a._action_history,['standard']);self.assertEqual(self.b.pos,(2,1));self.assertNotIn('넘어짐',self.b.conditions)
   before=(self.a.hp,self.b.hp,deepcopy(self.a.spec.get('frequency_state')),deepcopy(self.a.move_uses))
   # Printed Recoil (Take Down 1/3) is applied exactly once at move completion, after all
   # recipients and after the granted child; damage, frequency and the standard action are not replayed.
   import arithmetic_policy as M
   recoil=M.ratio(damage,3) if source=='move/돌진' else 0
   after=(before[0]-recoil,*before[1:])
   result=self.e.resolve_maneuver_grant(self.a,row['id'],**self.opts());self.assertEqual(result.tag,'Completed');self.assertEqual(self.a._action_history,['standard','free']);self.assertEqual((self.a.hp,self.b.hp,self.a.spec.get('frequency_state'),self.a.move_uses),after)
   self.assertIs(self.e.resolve_maneuver_grant(self.a,row['id']),result);self.assertEqual((self.a.hp,self.b.hp,self.a.spec.get('frequency_state'),self.a.move_uses),after)
 def test_native_parent_miss_has_no_granted_child(self):
  with patch.object(self.e,'accuracy_check',return_value=(False,1,False)):
   self.assertEqual(self.e.use_move(self.a,self.b,'move/괴력'),0)
  self.assertFalse(self.a.custom_conditions.get(MG.RECORDS));self.assertEqual(self.a._action_history,['standard']);self.assertEqual(self.b.pos,(2,1))

 def test_native_jaw_lock_parent_damage_then_actual_free_grapple_keeps_parent_payment(self):
  import grapple_state as GR
  damage=self.e.use_move(self.a,self.b,'move/물고버티기');self.assertGreater(damage,0);row=next(iter(self.a.custom_conditions[MG.RECORDS].values()));self.assertIsNone(GR.relation(self.e,self.b));self.assertEqual(self.a._action_history,['standard'])
  result=MG.resolve(self.e,self.a,row['id'],**self.opts());self.assertEqual(result.tag,'Completed');self.assertIsNotNone(GR.relation(self.e,self.b));self.assertEqual(self.a._action_history,['standard','free'])
 def test_dispatcher_pending_updates_after_independent_child_continuation(self):
  effect=next(x for x in self.rules.move_mech('move/괴력')[0]['effects_exec'] if x['type']=='free_maneuver')
  batch=FX.run_effects(self.e,self.a,self.b,[effect],{'hit':True},'move/괴력');self.assertEqual(len(batch.pending),1)
  pending=batch.pending[0].reason;self.resolve(pending);self.assertEqual(batch.pending,())
 def test_receipt_removed_after_issue_cannot_authorize_child_world_change(self):
  pending=self.grant();self.e._effect_dispatch_receipts.clear()
  with self.assertRaises(ValueError):self.resolve(pending)
  self.assertEqual(self.b.pos,(2,1));self.assertEqual(self.a._action_history,[])

 def test_immediate_grant_cannot_wait_for_an_intervening_action_or_position_change(self):
  for change in ('action','position','time'):
   self.setUp();pending=self.grant()
   if change=='action':ACTION.record_action(self.e,self.a,'swift')
   elif change=='position':self.a.pos=(2,2)
   else:self.e.elapsed_seconds+=1
   result=self.resolve(pending);self.assertEqual(result.reason,'invalid_state');self.assertEqual(self.b.pos,(2,1))
 def test_observed_pending_child_blocks_unrelated_new_action_and_encounter_end(self):
  pending=self.grant('move/돌진')
  with self.assertRaises(ValueError):MG.resolve(self.e,self.a,pending.grant_id,**self.featured(True))
  before=(self.a.hp,self.b.hp,self.a.pos,self.b.pos,deepcopy(self.a.budget))
  with self.assertRaises(ValueError):self.e.use_move(self.a,self.b,'move/괴력')
  with self.assertRaises(ValueError):self.e.end_encounter()
  self.assertEqual((self.a.hp,self.b.hp,self.a.pos,self.b.pos,self.a.budget),before);self.assertTrue(self.e.encounter_active)

 def test_snapshot_preserves_actual_participants_receipt_aliases_and_parent_cost(self):
  self.e.use_move(self.a,self.b,'move/괴력');row=next(iter(self.a.custom_conditions[MG.RECORDS].values()));identity=row['id'];hp=self.b.hp
  self.e.gm.snapshot('child-pending');self.e.resolve_maneuver_grant(self.a,identity,**self.opts());self.assertEqual(self.b.pos,(3,1))
  self.e.gm.restore('child-pending','test authorized pending child restore');restored=self.a.custom_conditions[MG.RECORDS][identity]
  self.assertIs(restored['actor'],self.a);self.assertIs(restored['target'],self.b);self.assertEqual(self.b.pos,(2,1));self.assertEqual(self.a._action_history,['standard'])
  self.assertTrue(self.e.resolve_maneuver_grant(self.a,identity,**self.opts()).result);self.assertEqual(self.b.hp,hp);self.assertEqual(self.a._action_history,['standard','free']);self.assertEqual(self.b.pos,(3,1))
 def test_automatic_accuracy_still_records_actual_attack_without_d20(self):
  pending=self.grant();before=self.e.rng.getstate();self.resolve(pending)
  events=[r for r in self.e._precision_events if r['source']=='maneuver/밀기'];self.assertEqual(len(events),1);self.assertEqual(events[0]['result'],'accuracy_hit');self.assertEqual(self.e.rng.getstate(),before)

 def suffix_batch(self):
  grant=next(x for x in self.rules.move_mech('move/괴력')[0]['effects_exec'] if x['type']=='free_maneuver')
  return FX.run_effects(self.e,self.a,self.b,[grant,{'type':'stage_change','stat':'def','delta':-1,'target':'target'}],{'hit':True},'move/괴력')
 def test_unresolved_optional_child_holds_suffix_until_resumed_once(self):
  batch=self.suffix_batch();self.assertEqual(self.b.stages['def'],0);pending=batch.pending[0].reason
  result=self.resolve(pending);self.assertEqual(self.b.stages['def'],-1);self.assertEqual(batch.pending,());self.assertTrue(result.following_effects);self.assertIs(MG.resolve(self.e,self.a,pending.grant_id),result);self.assertEqual(self.b.stages['def'],-1)
 def test_declining_optional_child_resumes_unconditional_suffix(self):
  batch=self.suffix_batch();pending=batch.pending[0].reason;self.assertEqual(self.b.stages['def'],0)
  result=MG.resolve(self.e,self.a,pending.grant_id,accept=False);self.assertFalse(result.accepted);self.assertEqual(self.b.stages['def'],-1);self.assertEqual(self.b.pos,(2,1));self.assertEqual(self.a._action_history,[]);self.assertEqual(batch.pending,())
 def test_turn_end_decline_applies_suffix_before_turn_end_ticks(self):
  batch=self.suffix_batch();ACTION.check_end(self.e,self.a);self.assertEqual(self.b.stages['def'],-1);self.assertEqual(batch.pending,());ACTION.close_turn(self.e,self.a);self.assertEqual(self.b.stages['def'],-1)

 def test_observed_native_child_blocks_time_advance_and_same_choice_still_resumes(self):
  self.e.use_move(self.a,self.b,'move/돌진');row=next(iter(self.a.custom_conditions[MG.RECORDS].values()))
  with self.assertRaises(ValueError):MG.resolve(self.e,self.a,row['id'],**self.featured(True))
  before=(self.e.elapsed_seconds,self.a.hp,self.b.hp,self.e.rng.getstate(),list(self.a._action_history))
  with self.assertRaises(ValueError):self.e.advance_time(1)
  self.assertEqual((self.e.elapsed_seconds,self.a.hp,self.b.hp,self.e.rng.getstate(),self.a._action_history),before)
  self.assertTrue(MG.resolve(self.e,self.a,row['id'],**self.featured(False)).result)
 def test_required_suffix_blocks_new_action_time_and_scene_until_current_child_resumes(self):
  import turn as TURN
  batch=self.suffix_batch();pending=batch.pending[0].reason
  before=(deepcopy(self.a.budget),self.e.elapsed_seconds,self.e.encounter_active,self.a.hp,self.b.hp,list(self.a._action_history),self.b.stages['def'])
  for operation in (lambda:TURN.spend(self.e,self.a,'swift','unrelated action'),lambda:self.e.advance_time(1),lambda:self.e.end_scene(),lambda:self.e.use_move(self.a,self.b,'move/돌진')):
   with self.assertRaises(ValueError):operation()
   self.assertEqual((self.a.budget,self.e.elapsed_seconds,self.e.encounter_active,self.a.hp,self.b.hp,self.a._action_history,self.b.stages['def']),before)
  self.assertFalse(MG.resolve(self.e,self.a,pending.grant_id,accept=False).accepted);self.assertEqual(self.b.stages['def'],-1);self.assertEqual(batch.pending,());self.assertTrue(TURN.spend(self.e,self.a,'swift','after suffix completion'))
 def test_stale_suffix_decline_is_rejected_before_child_completion_or_world_change(self):
  batch=self.suffix_batch();pending=batch.pending[0].reason;row=self.a.custom_conditions[MG.RECORDS][pending.grant_id]
  self.e.round_no+=1
  with self.assertRaises(ValueError):MG.resolve(self.e,self.a,pending.grant_id,accept=False)
  self.assertNotEqual(row['status'],'completed');self.assertIsNone(row['accepted']);self.assertEqual(self.b.stages['def'],0);self.assertEqual(self.a._action_history,[]);self.assertTrue(batch.pending)
 def test_stale_optional_without_suffix_cannot_be_declined_as_current_completion(self):
  pending=self.grant();self.e.encounter_active=False
  result=MG.resolve(self.e,self.a,pending.grant_id,accept=False);self.assertIsInstance(result,C.PendingDecision);self.assertEqual(result.reason,'invalid_state');self.assertNotEqual(self.a.custom_conditions[MG.RECORDS][pending.grant_id]['status'],'completed')
 def test_wrong_turn_end_cannot_implicitly_decline_another_actors_pending_suffix(self):
  batch=self.suffix_batch();pending=batch.pending[0].reason;self.e._active_turn_actor=self.b
  with self.assertRaises(ValueError):ACTION.check_end(self.e,self.a)
  self.assertEqual(self.b.stages['def'],0);self.assertNotEqual(self.a.custom_conditions[MG.RECORDS][pending.grant_id]['status'],'completed');self.assertTrue(batch.pending)

 def test_mandatory_or_unknown_child_without_suffix_blocks_world_boundaries(self):
  import turn as TURN
  cases=[('move/문어굳히기',None),('move/튀어오르기',None),('ability/호박잡기-playtest',{'type':'free_maneuver','maneuver':'붙잡기','auto_hit':True,'advantage':True}),('feat/텔레키네틱-버스트',{'type':'free_maneuver','maneuver':'무장해제/걸기/밀기 (선택)'})]
  for source,effect in cases:
   with self.subTest(source=source):
    self.setUp();pending=self.grant(source,effect);row=self.a.custom_conditions[MG.RECORDS][pending.grant_id];self.assertIn(row['status'],('blocked','awaiting_input'));self.assertIsNone(row['accepted'])
    before=(deepcopy(self.a.budget),self.e.elapsed_seconds,self.e.encounter_active,list(self.a._action_history),self.b.pos)
    for operation in (lambda:ACTION.check_end(self.e,self.a),lambda:TURN.spend(self.e,self.a,'swift','unrelated'),lambda:self.e.advance_time(1),lambda:self.e.end_scene()):
     with self.assertRaises(ValueError):operation()
     self.assertEqual((self.a.budget,self.e.elapsed_seconds,self.e.encounter_active,self.a._action_history,self.b.pos),before)
    with self.assertRaises(ValueError):MG.resolve(self.e,self.a,pending.grant_id,accept=False)
 def test_explicit_optional_unsupported_child_may_be_declined_without_fake_success(self):
  pending=self.grant('move/물고버티기');ACTION.check_end(self.e,self.a);result=MG.resolve(self.e,self.a,pending.grant_id);self.assertFalse(result.accepted);self.assertNotIn('붙잡힘',self.b.custom_conditions);self.assertEqual(self.a._action_history,[])

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/maneuver_grants.py','engine/action_lifecycle.py','engine/physics_maneuvers.py','engine/effects_ext.py','engine/effect_contracts.py','engine/effects.py','engine/engine.py','engine/gm_state.py','engine/skill_maneuver_actions.py','engine/skill_feature_actions.py','tools/test_upper_maneuver_grants.py','input/ch07-combat.md','input/db/moves.csv','input/db/abilities.csv']
 (ROOT/'output/upper-maneuver-grants-tests.json').write_text(json.dumps({'successful':result.wasSuccessful(),'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
