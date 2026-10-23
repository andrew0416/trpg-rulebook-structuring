"""Actual trainer growth event identity; downstream entitlements stay separate."""
from pathlib import Path
from copy import copy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine
import world_entities as W

class TrainerProgressionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,19)
  self.c=Combatant(self.rules,build_trainer(self.rules,'growth',5,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c];self.c.spec['exp_bank']=3
 def award(self,**kw):
  return self.e.award_trainer_progression(self.c,**dict({'kind':'experience','amount':19,'request_id':'event/one','reason':'observed reward'},**kw))
 def test_repeated_experience_preserves_bank_levels_rng_and_logs(self):
  first=self.award();self.assertEqual(first['attained_levels'],[6,7]);self.assertEqual(self.c.spec['exp_bank'],2)
  before=dump_engine(self.e);self.assertEqual(self.award(),first);self.assertEqual(dump_engine(self.e),before)
  first['attained_levels'].clear();self.assertEqual(self.award()['attained_levels'],[6,7])
  self.award(request_id='event/two');self.assertEqual(self.c.level,9);self.assertEqual(self.c.spec['exp_bank'],1)
 def test_saved_milestone_replay_preserves_bank_and_does_not_level_again(self):
  first=self.award(kind='milestone',amount=None);self.assertEqual(self.c.level,6);self.assertEqual(self.c.spec['exp_bank'],3)
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id];before=dump_engine(restored)
  self.assertEqual(restored.award_trainer_progression(c,kind='milestone',request_id='event/one',reason='observed reward'),first)
  self.assertEqual(dump_engine(restored),before)
 def test_changed_intent_invalid_amount_and_fake_actor_leave_no_partial_state(self):
  self.award();before=dump_engine(self.e)
  for kw in [{'amount':20},{'kind':'milestone','amount':None},{'request_id':'bad','amount':-1},{'request_id':'bad','amount':True}]:
   with self.subTest(kw=kw),self.assertRaises(ValueError):self.award(**kw)
   self.assertEqual(dump_engine(self.e),before)
  with self.assertRaises(ValueError):self.e.award_trainer_progression(copy(self.c),kind='milestone',request_id='fake',reason='fake')
  self.assertEqual(dump_engine(self.e),before)
 def test_late_validation_failure_rolls_back_entire_event(self):
  from unittest.mock import patch
  before=dump_engine(self.e)
  with patch('state_fields.validate_actor',side_effect=ValueError('late validation')):
   with self.assertRaisesRegex(ValueError,'late validation'):self.award()
  self.assertEqual(dump_engine(self.e),before)
  self.assertEqual(self.award()['attained_levels'],[6,7])

 def test_ordinary_rights_issue_once_with_pending_qualified_choice(self):
  first=self.award();pending=self.e.pending_trainer_entitlements(self.c)
  self.assertEqual([(x['level'],x['kind'],x['status']) for x in pending],[(6,'edge','pending_choice'),(7,'feat','pending_choice')])
  self.assertEqual(first['entitlement_ids'],[x['entitlement_id'] for x in pending])
  before=dump_engine(self.e);self.award();self.assertEqual(dump_engine(self.e),before)
  pending[0]['status']='spent';self.assertEqual(self.e.pending_trainer_entitlements(self.c)[0]['status'],'pending_choice')
  self.assertEqual(self.c.spec.get('edges',[]),[]);self.assertEqual(self.c.spec.get('feats',[]),[])
 def test_current_level_alone_does_not_backfill_rights_and_no_level_awards_nothing(self):
  self.assertEqual(self.e.pending_trainer_entitlements(self.c),[])
  result=self.award(amount=1);self.assertEqual(result['attained_levels'],[]);self.assertEqual(result['entitlement_ids'],[])
  self.assertEqual(self.e.pending_trainer_entitlements(self.c),[])
  self.award(kind='milestone',amount=None,request_id='new')
  self.assertEqual([r['level'] for r in self.e.pending_trainer_entitlements(self.c)],[6])
 def test_pending_rights_survive_save_and_deleted_award_is_rejected(self):
  from state_codec import StateCodecError
  self.award();restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  self.assertEqual(restored.pending_trainer_entitlements(c),self.e.pending_trainer_entitlements(self.c))
  c.spec['trainer_entitlements']['awards'].pop('ordinary/level/6')
  with self.assertRaises(StateCodecError):dump_engine(restored)
  self.c.spec.pop('trainer_entitlements')
  with self.assertRaises(StateCodecError):dump_engine(self.e)
 def test_entitlement_source_failure_rolls_back_level_and_bank(self):
  from unittest.mock import patch
  before=dump_engine(self.e)
  with patch('trainer_entitlements.verified_source',side_effect=ValueError('source changed')):
   with self.assertRaisesRegex(ValueError,'source changed'):self.award()
  self.assertEqual(dump_engine(self.e),before)

 def test_corrupt_completed_event_rejects_native_replay_and_save(self):
  from state_codec import StateCodecError
  from copy import deepcopy
  self.award();event=self.c.spec['trainer_progression_events']['event/one'];original=deepcopy(event)
  for mutate in [lambda e:e['result'].update(bank_after=9),lambda e:e['result'].update(reason='changed'),lambda e:e['request'].update(amount=90)]:
   mutate(event);before=deepcopy(self.c.spec);rng=self.e.rng.getstate();logs=list(self.e.log_lines)
   with self.assertRaises(ValueError):self.award()
   with self.assertRaises(StateCodecError):dump_engine(self.e)
   self.assertEqual(self.c.spec,before);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.e.log_lines,logs)
   event.clear();event.update(deepcopy(original))
  self.c.spec['trainer_entitlements']['awards'].pop('ordinary/level/6')
  with self.assertRaisesRegex(ValueError,'missing its ordinary entitlement'):self.award()
 def test_legacy_receipt_remains_readable_without_invented_request(self):
  self.award();self.c.spec['trainer_progression_events']['event/one'].pop('request')
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  result=restored.award_trainer_progression(c,kind='experience',amount=19,request_id='event/one',reason='observed reward')
  self.assertEqual(result['level_after'],7);self.assertNotIn('request',c.spec['trainer_progression_events']['event/one'])

if __name__=='__main__':unittest.main()
