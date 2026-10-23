"""Iron Mind actual read-attempt producer, qualified ownership and durable awareness."""
from copy import copy,deepcopy
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import json,unittest
import test_category2_far_reading as _fixture_test_category2_far_reading
from builder import build_trainer
import iron_mind as I,telepathy as T,perception_communicate as M
import state_grants as G,state_codec as CODEC,roll_context as R
import acquisition_qualification as Q,acquired_features as A

class IronMindTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_far_reading.FarReadingTests.setUpClass.__func__)
 add=_fixture_test_category2_far_reading.FarReadingTests.add
 pokemon=_fixture_test_category2_far_reading.FarReadingTests.pokemon
 restored=_fixture_test_category2_far_reading.FarReadingTests.restored
 snap=_fixture_test_category2_far_reading.FarReadingTests.snap
 def setUp(self):
  _fixture_test_category2_far_reading.FarReadingTests.setUp(self)
  self.e.gm.set_skill(self.a,'집중',3,reason='actual Novice Focus')
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append(I.SOURCE))
 def allow(self,target=None,allowed=True):return _fixture_test_category2_far_reading.FarReadingTests.allow(self,self.a if target is None else target,allowed)
 def thought(self,target=None,text='private surface thought'):return _fixture_test_category2_far_reading.FarReadingTests.thought(self,self.a if target is None else target,text)
 def read(self,key='iron/read',target=None,**options):return _fixture_test_category2_far_reading.FarReadingTests.read(self,key,self.a if target is None else target,**options)
 def fixed(self,win=False,target=None):return _fixture_test_category2_far_reading.FarReadingTests.fixed(self,win,self.a if target is None else target)
 def notices(self,actor=None):return self.e.telepathy_attempts(self.a if actor is None else actor,notices_only=True)
 def test_actual_selected_edge_uses_common_ownership_and_qualification(self):
  self.thought()
  with patch.object(A,'owned_rule_count',wraps=A.owned_rule_count) as acquired,patch.object(Q,'require',wraps=Q.require) as qualified,patch.object(M,'send',wraps=M.send) as communication:
   result=self.read(roll_options=self.fixed(True))
  self.assertGreater(acquired.call_count,0);self.assertGreater(qualified.call_count,0);self.assertEqual(communication.call_count,1)
  self.assertEqual(result['status'],'delivered');self.assertEqual(len(self.notices()),1)
 def test_success_failure_and_willing_reading_each_create_one_attempt_awareness_without_extra_roll(self):
  self.thought()
  for key,win in (('fails',False),('wins',True)):
   with patch.object(R,'resolve',wraps=R.resolve) as rolls:result=self.read(key,roll_options=self.fixed(win))
   self.assertEqual(rolls.call_count,1);self.assertEqual(len(result['check']['rolls']),2)
  self.allow();rng=self.e.rng.getstate();result=self.read('willing')
  self.assertIsNone(result['check']);self.assertEqual(self.e.rng.getstate(),rng)
  self.assertEqual(len(self.notices()),3);self.assertFalse(T.owns(self.a))
 def test_mindlock_and_isolation_blocked_reading_still_trigger_awareness(self):
  G.grant(self.a,'capabilities','Mindlock','fixture:mindlock','fixture')
  result=self.read('mindlock');self.assertEqual(result['reason'],'receiver_blocked')
  self.assertEqual(len(self.notices()),1)
  G.transition(self.e,self.a,lambda e,c:G.revoke(c,'fixture:mindlock'))
  self.a.spec.setdefault('feats',[]).append('Utter Isolation')
  result=self.read('isolation');self.assertEqual(result['reason'],'receiver_blocked');self.assertEqual(len(self.notices()),2)
 def test_awareness_reveals_only_a_read_attempt_not_identity_result_or_thought_content(self):
  self.thought();result=self.read(roll_options=self.fixed(True));notice=self.notices()[0]
  self.assertEqual(set(notice),{'source','recipient_id','kind','at'})
  self.assertEqual(notice['kind'],'telepathy_read_attempt')
  for hidden in ('reader_id','owner_id','status','success','surface_thought','private surface thought'):
   self.assertNotIn(hidden,str(notice))
  self.assertEqual(result['event']['notice']['reader_id'],self.p.entity_id)
 def test_out_of_range_and_unknown_distance_do_not_invent_read_attempts(self):
  self.a.pos=(20,1);self.assertEqual(self.read()['reason'],'out_of_range');self.assertEqual(self.notices(),[])
  self.a.location={'kind':'unknown'};self.assertEqual(self.read('unknown')['reason'],'distance_unknown');self.assertEqual(self.notices(),[])
 def test_projection_and_explicit_trainer_offer_do_not_trigger_read_awareness(self):
  G.grant(self.a,'capabilities','Telepath','fixture:target-telepath','fixture');self.allow()
  result=self.e.project_telepathic_thought(self.p,[self.a],'projected text',request_id='projection')
  self.assertEqual(result['results'][0]['status'],'delivered');self.assertEqual(self.notices(),[])
  self.assertEqual(self.e.offer_telepathic_thought(self.a,self.p,'offered text',request_id='offer')['status'],'delivered')
  self.assertEqual(self.notices(),[])
 def test_owner_changes_do_not_transfer_old_awareness_and_removal_stops_future_notices(self):
  self.thought();self.allow();self.read('before-removal');old=self.notices()
  other=self.add(build_trainer(self.r,'other qualified Edge owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'집중':3},extra={'edges':[]}));other.pos=(5,1)
  def transfer(e,c,new_owner):
   c.spec['edges'].clear();new_owner.spec['edges'].append(I.SOURCE)
  G.transition(self.e,self.a,transfer,participants=(other,))
  self.read('after-removal');self.assertEqual(self.notices(),old)
  self.assertEqual(self.notices(other),[]);self.thought(other);self.allow(other)
  self.read('new-owner',other);self.assertEqual(len(self.notices(other)),1);self.assertEqual(self.notices(),old)
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append('Iron Mind'))
  self.read('after-reacquire');self.assertEqual(len(self.notices()),2)
 def test_import_and_later_invalid_focus_or_duplicate_ownership_are_refused_atomically(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'Novice Focus'):self.e.gm.set_skill(self.a,'집중',2,reason='invalid owned Edge prerequisite')
  self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append('강철의 정신'))
  self.assertEqual(self.snap(),before)
  spec=build_trainer(self.r,'unqualified imported Edge',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'집중':2},extra={'edges':['Iron Mind']})
  with self.assertRaisesRegex(ValueError,'Novice Focus'):self.add(spec)
  self.assertEqual(self.snap(),before)
 def test_aliases_qualify_the_same_canonical_edge_and_pokemon_cannot_own_trainer_edge(self):
  for alias in I.NAMES:
   G.transition(self.e,self.a,lambda e,c:c.spec.__setitem__('edges',[alias]))
   self.assertTrue(I.validate(self.a))
  before=self.snap()
  with self.assertRaises(ValueError):G.transition(self.e,self.t,lambda e,c:c.spec.__setitem__('edges',[I.SOURCE]))
  self.assertEqual(self.snap(),before)
 def test_durable_read_retry_and_both_restores_do_not_duplicate_notices(self):
  self.thought();options=self.fixed(False);self.read('saved',roll_options=options);expected=self.notices()
  saved=self.e.gm.snapshot();loaded=self.restored();idx={x.entity_id:x for x in loaded.everyone};before=CODEC.dump_engine(loaded)
  out=loaded.read_telepathic_thought(idx[self.p.entity_id],idx[self.a.entity_id],request_id='saved',roll_options=options)
  self.assertTrue(out['replayed']);self.assertEqual(loaded.telepathy_attempts(idx[self.a.entity_id],notices_only=True),expected)
  self.assertEqual(CODEC.dump_engine(loaded),before)
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].clear());self.e.gm.restore(saved)
  self.assertEqual(self.notices(),expected);self.assertTrue(self.read('saved',roll_options=options)['replayed'])
  self.assertEqual(self.notices(),expected)
 def test_notice_survives_loss_of_edge_and_focus_after_restore(self):
  self.allow();self.thought();self.read();expected=self.notices()
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].clear());self.e.gm.set_skill(self.a,'집중',2,reason='no longer owns Edge')
  loaded=self.restored();target=next(x for x in loaded.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(loaded.telepathy_attempts(target,notices_only=True),expected)
 def test_late_actual_read_failure_rolls_back_notice_rng_and_communication_history(self):
  self.thought();before=self.snap()
  with patch.object(T,'deliver',side_effect=ValueError('late read effect refusal')):
   with self.assertRaisesRegex(ValueError,'late read'):self.read(roll_options=self.fixed(True))
  self.assertEqual(self.snap(),before);self.assertEqual(self.notices(),[])
 def test_notice_tampering_and_fake_actual_target_are_refused_without_information_or_mutation(self):
  self.thought();self.allow();self.read();before=self.snap()
  with self.assertRaises(ValueError):self.e.telepathy_attempts(copy(self.a),notices_only=True)
  self.assertEqual(self.snap(),before)
  record=M._state(self.e)['requests']['iron/read'];record['result']['event']['notice']['reader_id']=self.t.entity_id
  with self.assertRaises(ValueError):self.snap()
 def test_selected_literal_and_duplicate_csv_source_change_are_refused(self):
  before=self.snap();selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**options:uid+'/different' if uid==I.SOURCE else selected(uid,**options)):
   with self.assertRaises(ValueError):self.read()
  self.assertEqual(self.snap(),before)
  read_bytes=Path.read_bytes
  def altered(path,*args,**options):
   raw=read_bytes(path,*args,**options)
   return raw+b'\nchanged' if path.resolve()==(Path(self.r.root)/'input/db/edges.csv').resolve() else raw
  with patch.object(Path,'read_bytes',altered):
   with self.assertRaises(ValueError):I.policy(self.r)
  self.assertEqual(self.snap(),before)
 def test_literal_csv_duplicate_is_verified_but_not_a_second_rule_or_effect(self):
  value=I.policy(self.r)
  self.assertEqual(value['csv_duplicate'],'C2CSV/input/db/edges.csv:R58:main')
  self.assertEqual(value['minimum_rank'],3);self.assertEqual(value['lines'],[520,522])
  self.thought();self.allow();self.read();self.assertEqual(len(self.notices()),1)
  self.assertEqual(len(M._state(self.e)['requests']),1)

if __name__=='__main__':unittest.main()

