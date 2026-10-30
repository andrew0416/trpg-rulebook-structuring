"""Real native Snatch: exact Minimize/Roost effects, payment and restoration."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_book_glitch_bender_full as _fixture
from engine import Engine
import glitch_bender as B,combat_timing as TIME,effect_lifetimes as LIFE
import state_grants as G,combat_move_reactions as R
import snatch_self_consumers as SELF


class SnatchSelfConsumerTests(unittest.TestCase):
 setUpClass=classmethod(_fixture.GlitchBenderFullTests.setUpClass.__func__)
 setUp=_fixture.GlitchBenderFullTests.setUp
 scene=_fixture.GlitchBenderFullTests.scene
 acquire=_fixture.GlitchBenderFullTests.acquire
 family=_fixture.GlitchBenderFullTests.family
 begin=_fixture.GlitchBenderFullTests.begin
 turn=_fixture.GlitchBenderFullTests.turn
 native=_fixture.GlitchBenderFullTests.native
 restore=_fixture.GlitchBenderFullTests.restore
 valid=_fixture.GlitchBenderFullTests.valid
 reject=_fixture.GlitchBenderFullTests.reject
 snatch_checkpoint=_fixture.GlitchBenderFullTests.snatch_checkpoint

 def prepare(self,source,*,recipient_types=('노말','비행'),user_types=('물',)):
  self.scene()
  self.e.gm.set_move(self.b,source,reason='actual known Self Move')
  self.family(B.NULL)
  self.e.gm.set_types(self.a,list(recipient_types),reason='actual recipient types')
  self.e.gm.set_types(self.b,list(user_types),reason='actual original user types')
  self.e.gm.set_hp(self.a,1,reason='actual damaged recipient')
  self.e.gm.set_hp(self.b,2,reason='actual damaged original user')

 def activate(self,source):
  self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b)
  self.native(self.b,self.b,source)

 def parent(self,source):
  return next(r for r in self.e._move_completions.values() if r['actor'] is self.b and r['move_id']==source)

 def assert_paid_once(self,source):
  self.assertEqual(self.b.move_uses[source],1)
  self.assertEqual(self.a.move_uses[B.SNATCH],1)
  self.assertEqual(self.b._action_history,['standard'])
  self.assertEqual(self.a._action_history,['standard'])

 def test_minimize_actual_recipient_encounter_expiry_and_learning_not_transferred(self):
  self.prepare(SELF.MINIMIZE)
  original_size=self.a.spec['size'];other_size=self.b.spec['size']
  self.assertNotIn('수축성',G.effective_capabilities(self.a))
  self.assertIn('수축성',G.effective_capabilities(self.b))
  self.activate(SELF.MINIMIZE)
  self.assertEqual((self.a.spec['size'],LIFE.numeric(self.a,'evasion_modifier')),('Small',4))
  self.assertEqual((self.b.spec['size'],LIFE.numeric(self.b,'evasion_modifier')),(other_size,0))
  self.assertNotIn('수축성',G.effective_capabilities(self.a));self.assert_paid_once(SELF.MINIMIZE)
  self.restore();self.valid()
  self.assertEqual((self.a.spec['size'],LIFE.numeric(self.a,'evasion_modifier')),('Small',4))
  self.e.end_encounter(self.e.everyone)
  self.assertEqual((self.a.spec['size'],LIFE.numeric(self.a,'evasion_modifier')),(original_size,0))
  self.assertIn('수축성',G.effective_capabilities(self.b));self.valid()

 def test_roost_actual_recipient_predicate_receipt_and_next_own_turn(self):
  self.prepare(SELF.ROOST)
  expected=min(self.a.max_hp,1+self.a.base_max_hp//2)
  self.activate(SELF.ROOST)
  self.assertEqual((self.a.hp,self.b.hp),(expected,2))
  self.assertEqual((self.a.types,self.b.types),(['노말'],['물']))
  records=[r for r in TIME.records(self.a) if r.get('source')==SELF.ROOST]
  self.assertEqual(len(records),1);self.assertIs(records[0]['turn_owner'],self.a)
  rows=[r for r in self.e._effect_dispatch_receipts.values() if r['source_id']==SELF.ROOST]
  self.assertEqual(len(rows),2)
  self.assertTrue(all(r['actor'] is self.b and r['target'] is self.a and r['status']=='completed' for r in rows))
  self.assert_paid_once(SELF.ROOST);self.restore();self.valid()
  self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone)
  self.e.start_of_turn(self.b,initiative_count=50)
  self.assertEqual(self.a.types,['노말'])
  self.turn(self.a,count=40);self.assertEqual(self.a.types,['노말','비행']);self.valid()

 def test_roost_uses_recipient_nonflying_condition_even_when_original_is_flying(self):
  self.prepare(SELF.ROOST,recipient_types=('물',),user_types=('노말','비행'))
  self.activate(SELF.ROOST)
  self.assertEqual(self.a.types,['물']);self.assertEqual(self.b.types,['노말','비행'])
  self.assertFalse([r for r in TIME.records(self.a) if r.get('source')==SELF.ROOST])
  self.assertEqual(self.a.hp,min(self.a.max_hp,1+self.a.base_max_hp//2))
  self.assertEqual(self.b.hp,2);self.restore();self.valid()

 def test_roost_durable_lifetime_does_not_authorize_forged_dispatch_or_turn_owner(self):
  self.prepare(SELF.ROOST);self.activate(SELF.ROOST);self.restore();self.valid()
  parent=self.parent(SELF.ROOST)
  self.reject(lambda:R.snatch_recipient(self.e,self.b,self.a,SELF.ROOST,{'move_completion':parent['id'],'after_all_targets':True}),reason='actual|retained')
  def false_completion():
   with SELF.completion_scope(self.e,parent,self.b,parent['post_effects']):pass
  self.reject(false_completion,reason='actual completed')
  def corrupt(staged,owner):
   record=next(r for r in TIME.records(owner) if r.get('source')==SELF.ROOST)
   record['turn_owner']=next(a for a in staged.everyone if a.entity_id==self.b.entity_id)
  self.reject(lambda:G.transition(self.e,self.a,corrupt),reason='lifetime|turn owner|contract')
  self.valid()

 def test_roost_pending_response_restore_does_not_repay_or_reroll(self):
  import passive_events as P
  self.prepare(SELF.ROOST)
  key=self.snatch_checkpoint(self.a,'accuracy_resolved');self.begin(self.b)
  B.arm_snatch(self.e,self.a,target=self.b)
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,SELF.ROOST)
  pending=self.e._passive_pending
  self.assertEqual((self.a.hp,self.b.hp),(1,2));self.assertEqual(self.a.types,['노말','비행'])
  paid=deepcopy((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history))
  self.restore()
  with patch.object(Engine,'d20',side_effect=AssertionError('must not reroll paid activation')):
   P.choose(self.e,pending,self.a,key,{'decisions':{'continue_fixture':{'value':False,'reason':'resume original paid Snatch'}}})
  self.assertEqual((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history),paid)
  self.assertEqual((self.a.hp,self.b.hp),(min(self.a.max_hp,1+self.a.base_max_hp//2),2))
  self.assertEqual((self.a.types,self.b.types),(['노말'],['물']))
  self.restore();self.valid()

 def test_roost_pending_routed_return_restore_runs_post_effect_once(self):
  import passive_events as P
  self.prepare(SELF.ROOST)
  key=self.snatch_checkpoint(self.b,'move_resolved');self.begin(self.b)
  B.arm_snatch(self.e,self.a,target=self.b)
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,SELF.ROOST)
  expected=min(self.a.max_hp,1+self.a.base_max_hp//2)
  self.assertEqual(self.a.hp,expected)
  self.restore()
  paid=deepcopy((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history))
  for _ in range(2):
   if self.e._passive_pending is None:break
   try:P.choose(self.e,self.e._passive_pending,self.b,key,{'decisions':{'continue_fixture':{'value':False,'reason':'resume actual recipient return'}}})
   except P.PassiveEventPending:pass
  self.assertIsNone(self.e._passive_pending)
  self.assertEqual((self.a.move_uses,self.b.move_uses,self.a._action_history,self.b._action_history),paid)
  self.assertEqual((self.a.hp,self.b.hp),(expected,2));self.assertEqual(self.a.types,['노말'])
  self.assertEqual(len([r for r in TIME.records(self.a) if r.get('source')==SELF.ROOST]),1)
  self.restore();self.valid()


 def test_snatch_preserves_declined_native_defense_and_rejects_forged_prior_attempt(self):
  import move_defense_reactions as D,passive_events as P
  self.family(B.NULL)
  self.e.gm.set_move(self.b,D.DETECT,reason='actual owned Detect watch')
  D.watch(self.e,self.b,[{'actor_id':self.b.entity_id,'source':D.DETECT}],reason='actual optional defense owner')
  self.begin(self.b);B.arm_snatch(self.e,self.a,target=self.b)
  with self.assertRaises(P.PassiveEventPending):self.native(self.b,self.b,'move/칼춤')
  pending=self.e._passive_pending
  self.assertNotIn(B.SNATCH,self.a.move_uses);self.assertEqual(self.b.stages['atk'],0)
  self.restore()
  # The persistent watch also observes the actual incoming Snatch response.
  # Both are real choice boundaries; neither is fabricated or auto-declined.
  for _ in range(2):
   if self.e._passive_pending is None:break
   try:D.choose(self.e,self.e._passive_pending,self.b,use=False,reason='decline this actual native defense')
   except P.PassiveEventPending:pass
  self.assertIsNone(self.e._passive_pending)
  self.assertEqual((self.a.stages['atk'],self.b.stages['atk']),(2,0))
  self.assert_paid_once('move/칼춤')
  self.assertNotIn(D.DETECT,self.b.move_uses)
  parent=self.parent('move/칼춤');state=parent['defense'][self.b.entity_id]
  self.assertEqual(state['cursor'],1);self.assertEqual(len(state['attempts']),1)
  self.assertEqual(state['attempts'][0]['outcome'],'declined')
  self.assertEqual(state['source_route']['source'],B.SNATCH)
  self.restore();self.valid()
  def corrupt(staged,owner):
   parent=next(r for r in staged._move_completions.values() if r['actor'] is owner and r['move_id']=='move/칼춤')
   parent['defense'][owner.entity_id]['attempts'][0]['actor_id']=self.c.entity_id
  self.reject(lambda:G.transition(self.e,self.b,corrupt),reason='defense attempt|owned source')
  self.valid()

if __name__=='__main__':unittest.main()

