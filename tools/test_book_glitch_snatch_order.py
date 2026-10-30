"""Ordered same-trigger Snatch: real responses, real defenses and retained choices."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_book_glitch_bender_full as _fixture
from engine import Engine
import glitch_bender as B,combat_move_reactions as R,passive_events as P
import snatch_dispatch as S,move_defense_reactions as D,move_completion as MC
import state_grants as G

class OrderedSnatchTests(unittest.TestCase):
 setUpClass=classmethod(_fixture.GlitchBenderFullTests.setUpClass.__func__)
 setUp=_fixture.GlitchBenderFullTests.setUp
 scene=_fixture.GlitchBenderFullTests.scene
 acquire=_fixture.GlitchBenderFullTests.acquire
 family=_fixture.GlitchBenderFullTests.family
 begin=_fixture.GlitchBenderFullTests.begin
 native=_fixture.GlitchBenderFullTests.native
 restore=_fixture.GlitchBenderFullTests.restore
 valid=_fixture.GlitchBenderFullTests.valid
 reject=_fixture.GlitchBenderFullTests.reject
 snatch_checkpoint=_fixture.GlitchBenderFullTests.snatch_checkpoint

 def setup_responders(self,*,two=True,ordered=True):
  self.family(B.NULL)
  if two:
   self.family(B.NULL,actor=self.c)
   self.e.gm.set_position(self.c,(4,4),reason='actual second responder within range')
  self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b)
  if two:
   B.arm_snatch(self.e,self.c,target=self.b)
   if ordered:B.order_snatch(self.e,self.b,[self.a,self.c],reason='explicit order for the same original Self trigger')

 def parent(self):
  return next(r for r in self.e._move_completions.values() if r['actor'] is self.b and r['move_id']=='move/칼춤')

 def paid(self):
  return deepcopy([(a.move_uses,a._action_history) for a in self.people])

 def test_multiple_offers_require_exact_explicit_order_without_fabricated_winner(self):
  self.setup_responders(ordered=False)
  self.reject(lambda:self.native(self.b,self.b,'move/칼춤'),reason='explicit simultaneous Snatch order')
  self.assertNotIn(B.SNATCH,self.a.move_uses);self.assertNotIn(B.SNATCH,self.c.move_uses)
  self.reject(lambda:B.order_snatch(self.e,self.b,[self.a,self.a],reason='invalid repeated responder'),reason='exact explicit')
  B.order_snatch(self.e,self.b,[self.c,self.a],reason='actual declared opposite order')
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  plan,window,native=S._record(self.e,self.parent())
  self.assertEqual([a.entity_id for a,_,_ in native],[self.c.entity_id,self.a.entity_id])
  self.assertTrue(all(r['status']=='complete' and req['status']=='completed' for _,r,req in native))
  self.assertEqual((self.a.stages['atk'],self.b.stages['atk'],self.c.stages['atk']),(0,0,0))
  self.assertEqual(self.e._passive_events[self.e._passive_pending]['reason'],'actual_simultaneous_snatch_recipient')
  self.assertIsNone(plan['selection']);self.valid()

 def test_multiple_success_restore_explicit_occurrence_choice_never_replays_or_snatches_snatch(self):
  self.setup_responders()
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  pending=self.e._passive_pending;paid=self.paid()
  self.assertEqual(self.b.move_uses['move/칼춤'],1)
  self.assertEqual((self.a.move_uses[B.SNATCH],self.c.move_uses[B.SNATCH]),(1,1))
  self.restore();self.valid()
  self.reject(lambda:B.choose_snatch_recipient(self.e,pending,self.b,reason='original actor did not succeed at Snatch'),reason='successful Snatch recipient')
  with patch.object(Engine,'d20',side_effect=AssertionError('completed responses must not reroll')):
   B.choose_snatch_recipient(self.e,pending,self.a,reason='GM resolves this observed simultaneous conflict in favor of the first responder')
  self.assertEqual(self.paid(),paid)
  self.assertEqual((self.a.stages['atk'],self.b.stages['atk'],self.c.stages['atk']),(2,0,0))
  plan,window,native=S._record(self.e,self.parent())
  self.assertTrue(all(r['trigger_move']=='move/칼춤' and r['completion_id']==self.parent()['id'] for _,r,_ in native))
  self.assertEqual(len(native),2);self.assertEqual(window['cursor'],2)
  self.reject(lambda:B.choose_snatch_recipient(self.e,pending,self.c,reason='cannot replace an already applied decision'),reason='actual simultaneous')
  self.restore();self.valid()

 def test_first_response_pending_restore_finishes_in_order_without_repaying(self):
  self.setup_responders()
  key=self.snatch_checkpoint(self.a,'accuracy_resolved')
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  pending=self.e._passive_pending
  self.assertEqual(self.e._passive_events[pending]['move_id'],B.SNATCH)
  self.assertNotIn(B.SNATCH,self.c.move_uses)
  self.restore()
  with self.assertRaises(P.PassiveEventPending):
   P.choose(self.e,pending,self.a,key,{'decisions':{'continue_fixture':{'value':False,'reason':'return the first actual paid response'}}})
  self.assertEqual(self.e._passive_events[self.e._passive_pending]['reason'],'actual_simultaneous_snatch_recipient')
  self.assertEqual((self.a.move_uses[B.SNATCH],self.c.move_uses[B.SNATCH]),(1,1))
  paid=self.paid();self.restore()
  B.choose_snatch_recipient(self.e,self.e._passive_pending,self.c,reason='GM resolves this occurrence for the second actual success')
  self.assertEqual(self.paid(),paid);self.assertEqual((self.a.stages['atk'],self.c.stages['atk']),(0,2))
  self.restore();self.valid()

 def test_actual_detect_success_against_snatch_preserves_zero_or_one_success_semantics(self):
  for two in (False,True):
   with self.subTest(two_responders=two):
    self.scene();self.e.gm.set_move(self.b,D.DETECT,reason='actual owned native Detect')
    self.setup_responders(two=two)
    native_run=R._run;armed=[]
    def observe_response(e,owner,target,event,**kwargs):
     # Fixture supplies a real optional watch at the actual incoming response
     # boundary; native Detect still owns payment, hit prevention and receipt.
     if event['source']==R.SNATCH and owner.entity_id==self.a.entity_id and not armed:
      D.watch(e,target,[{'actor_id':target.entity_id,'source':D.DETECT}],reason='GM observes incoming Snatch and arms actual Detect')
      armed.append(event['id'])
     return native_run(e,owner,target,event,**kwargs)
    with patch.object(R,'_run',side_effect=observe_response):
     with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
    pending=self.e._passive_pending
    self.assertEqual(self.e._passive_events[pending]['move_id'],B.SNATCH)
    self.restore()
    D.choose(self.e,pending,self.b,use=True,reason='actual user elects its native Detect Interrupt')
    self.assertIsNone(self.e._passive_pending)
    self.assertEqual(self.b.move_uses['move/칼춤'],1);self.assertEqual(self.b.move_uses[D.DETECT],1)
    self.assertEqual(self.a.move_uses[B.SNATCH],1)
    plan,window,native=S._record(self.e,self.parent())
    successful=S._successful(self.e,native)
    self.assertEqual(len(successful),int(two));self.assertIsNone(plan['selection'])
    failed=next(r for owner,r,_ in native if owner is self.a)
    received=MC.recipient_result(self.e._move_completions[failed['result_completion']],self.b)
    self.assertFalse(received['hit'])
    self.assertEqual((self.a.stages['atk'],self.b.stages['atk'],self.c.stages['atk']),(0,0,2) if two else (0,2,0))
    self.restore();self.valid()

 def test_forged_selected_response_cannot_save_or_replace_real_window(self):
  self.setup_responders()
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  self.restore()
  def corrupt(staged,owner):
   parent=next(r for r in staged._move_completions.values() if r['actor'] is owner and r['move_id']=='move/칼춤')
   parent[S.PLAN]['selection']={'reaction_id':'invented-native-success','reason':'forged recipient'}
  self.reject(lambda:G.transition(self.e,self.b,corrupt),reason='multiple completed successes')
  self.assertIsNone(self.parent()[S.PLAN]['selection']);self.valid()


 def test_defense_curl_uses_producer_edition_and_actual_recipient_conditions_and_end(self):
  import defense_curl as CURL,effect_instances as E
  for variant in ('core','september_playtest'):
   with self.subTest(variant=variant):
    self.scene();self.family(B.NULL)
    self.e.gm.set_move(self.b,CURL.MOVE,reason='actual known Defense Curl')
    self.e.gm.set_move(self.b,'move/구르기',reason='original actor knows Rollout; recipient does not')
    if variant!='core':self.e.choose_defense_curl_source(self.b,variant,reason='original producer selected complete September source')
    self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b)
    self.native(self.b,self.b,CURL.MOVE)
    received=CURL.live(self.a)
    self.assertIsNotNone(received);self.assertIsNone(CURL.live(self.b))
    self.assertEqual(received['effect']['variant'],variant)
    self.assertEqual(received[E.KEY]['applied_by_actor_id'],self.b.entity_id)
    self.assertEqual(self.b.move_uses[CURL.MOVE],1);self.assertEqual(self.a.move_uses[B.SNATCH],1)
    if variant=='core':
     self.assertTrue(CURL.slowed(self.a));self.assertEqual(CURL.reduction(self.a),10)
     self.assertTrue(CURL.critical_immune(self.a));self.assertEqual(self.b.stages['def'],0)
    else:self.assertEqual((self.a.stages['def'],self.b.stages['def']),(1,0))
    self.restore();self.valid()
    if variant=='core':
     self.e.end_of_turn(self.b);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=40)
     self.assertTrue(self.e.stop_defense_curl(self.a));self.assertIsNone(CURL.live(self.a))
    else:
     self.e.end_of_turn(self.b);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
     self.assertIsNone(CURL.live(self.a))
    self.valid()

if __name__=='__main__':unittest.main()

