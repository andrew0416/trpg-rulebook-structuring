"""Actual stack, lifetime, native attack and persistence boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from engine import Rules
import condition_instances as CI,combat_timing as CLOCK,initiative as I,turn as TURN,effect_instances as E,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add;pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon;restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon(20);self.p.pos=(1,0)
  self.e.gm.observe_loyalty(self.p,6,reason='known obedience')
 def open(self):
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def test_both_kinds_stack_additively_and_keep_actions(self):
  for who in ('a','p'):
   with self.subTest(kind=who):
    self.setUp();self.open();c=getattr(self,who);base=I.value(self.r,c).value
    for n in (1,2,3):
     self.assertTrue(self.e.apply_status(c,'풀죽음',source='move/박치기',applied_by=self.a))
     self.assertEqual(I.value(self.r,c).value,base-5*n)
     self.assertEqual(c.evasion('물리'),0)
    if c is self.a:self.assertTrue(TURN.spend(self.e,c,'standard'))
    self.assertTrue(self.e.validate_state()['valid'])
 def test_full_round_derivative_expires_at_same_count_not_application_round_end(self):
  self.open();base=I.value(self.r,self.p).value;self.e.apply_status(self.p,'풀죽음')
  self.e.end_of_turn(self.a);self.e.end_round();self.assertIn('취약',self.p.conditions)
  self.e.start_round(self.e.gm.everyone);CLOCK.at_count(self.e,21);self.assertIn('취약',self.p.conditions)
  CLOCK.at_count(self.e,20);self.assertNotIn('취약',self.p.conditions)
  self.assertIn('풀죽음',self.p.conditions);self.assertEqual(I.value(self.r,self.p).value,base-5)
  self.assertTrue(self.e.validate_state()['valid'])
 def test_independent_vulnerability_is_not_removed_with_flinch(self):
  self.open();self.e.apply_status(self.p,'취약');self.e.apply_status(self.p,'풀죽음')
  self.e.cure_status(self.p,'풀죽음');self.assertIn('취약',self.p.conditions)
  self.assertFalse(CI.records(self.p,'풀죽음'));self.assertTrue(self.e.validate_state()['valid'])
  self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.gm.everyone)
  CLOCK.at_count(self.e,20);self.assertFalse(CLOCK.records(self.p))
  self.assertIn('취약',self.p.conditions);self.assertTrue(self.e.validate_state()['valid'])
 def test_cure_recall_faint_and_scene_end_restore_initiative_with_separate_child_lifetime(self):
  for ending in ('cure','recall','faint','encounter','scene'):
   with self.subTest(ending=ending):
    self.setUp();self.open();base=I.value(self.r,self.p).value
    for _ in range(2):self.e.apply_status(self.p,'풀죽음')
    if ending=='cure':self.e.cure_status(self.p,'풀죽음')
    elif ending=='recall':self.e.gm.recall(self.p,reason='actual recall')
    elif ending=='faint':
     self.e.gm.faint(self.p,reason='actual faint')
     self.assertEqual(self.p.hp,0);self.assertIn('기절',self.p.conditions)
    else:
     self.e.end_of_turn(self.a)
     if ending=='scene':self.e.end_scene()
     else:self.e.end_encounter()
    self.assertFalse(CI.records(self.p,'풀죽음'))
    self.assertNotIn('풀죽음',self.p.conditions)
    self.assertEqual(I.value(self.r,self.p).value,base)
    if ending!='scene':
     self.assertIn('취약',self.p.conditions)
     self.assertTrue(self.e.validate_state()['valid'])
     if ending!='encounter':self.e.end_of_turn(self.a);self.e.end_round()
     self.e.start_round(self.e.gm.everyone)
     CLOCK.at_count(self.e,21);self.assertIn('취약',self.p.conditions)
     CLOCK.at_count(self.e,20)
     self.assertNotIn('취약',self.p.conditions)
    else:self.assertNotIn('취약',self.p.conditions)
    self.assertTrue(self.e.validate_state()['valid'])
 def test_snapshot_and_json_restore_preserve_count_and_sources(self):
  self.open();self.e.apply_status(self.p,'풀죽음',source='move/박치기',applied_by=self.a)
  self.e.gm.snapshot('flinch');self.e.cure_status(self.p,'풀죽음');self.e.gm.restore('flinch')
  e=self.restored();c=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(I.value(e.r,c).value,I.value(self.r,self.p).value)
  self.assertEqual(CI.records(c,'풀죽음'),CI.records(self.p,'풀죽음'))
  self.assertTrue(e.validate_state()['valid'])
  CLOCK.records(c)[0]['count_deadline']=(999,20)
  self.assertFalse(e.validate_state()['valid'])

 def test_archived_parent_provenance_survives_cure_and_state_codec(self):
  self.open();self.e.apply_status(self.p,'풀죽음',source='move/박치기')
  self.e.cure_status(self.p,'풀죽음')
  archived=deepcopy(self.p.spec['effect_instance_history'])
  self.e.gm.snapshot('cured-flinch')
  self.e.cure_status(self.p,'취약');self.e.gm.restore('cured-flinch')
  self.assertEqual(self.p.spec['effect_instance_history'],archived)
  self.assertFalse(CI.records(self.p,'풀죽음'))
  self.assertIn('취약',self.p.conditions)
  self.assertTrue(self.e.validate_state()['valid'])
  e=self.restored();c=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertIn('취약',c.conditions);self.assertTrue(e.validate_state()['valid'])
  owner=next(x for x in e.gm.everyone if x.entity_id==self.a.entity_id)
  e.end_of_turn(owner);e.end_round();e.start_round(e.gm.everyone)
  CLOCK.at_count(e,20)
  self.assertNotIn('취약',c.conditions);self.assertTrue(e.validate_state()['valid'])

 def test_direct_vulnerable_cure_does_not_erase_flinch_initiative_stacks(self):
  self.open();self.e.apply_status(self.p,'풀죽음')
  self.e.cure_status(self.p,'취약')
  self.assertNotIn('취약',self.p.conditions)
  self.assertTrue(CI.records(self.p,'풀죽음'))
  self.assertTrue(self.e.validate_state()['valid'])
  e=self.restored();c=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertNotIn('취약',c.conditions);self.assertEqual(CLOCK.records(c)[0]['owned_statuses'],set())
  self.assertTrue(e.validate_state()['valid'])
 def test_missing_clock_and_legacy_flag_do_not_invent_sources(self):
  before=deepcopy((self.p.conditions,self.p.custom_conditions,self.p.spec))
  with self.assertRaises(ValueError):self.e.apply_status(self.p,'풀죽음')
  self.assertEqual((self.p.conditions,self.p.custom_conditions,self.p.spec),before)
  self.open();self.p.conditions.add('풀죽음')
  self.assertTrue(I.value(self.r,self.p).unresolved)
  with self.assertRaises(ValueError):self.e.apply_status(self.p,'풀죽음')
 def test_native_headbutt_creates_source_instance_before_later_cure(self):
  self.e.gm.set_move(self.a,'move/박치기',reason='actual learned Move');self.open()
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.p,'move/박치기',set_damage=True)
  self.assertTrue(CI.records(self.p,'풀죽음'));self.assertIn('취약',self.p.conditions)
  self.assertTrue(self.e.validate_state()['valid'])
 def test_paralysis_composition_is_held_without_erasing_stacks(self):
  self.open();self.e.apply_status(self.p,'풀죽음');self.e.apply_status(self.p,'마비')
  self.assertTrue(I.value(self.r,self.p).unresolved)
  self.e.cure_status(self.p,'마비');self.assertFalse(I.value(self.r,self.p).unresolved)

 def test_native_attack_without_clock_rejects_before_damage_budget_or_randomness(self):
  self.e.gm.set_move(self.a,'move/박치기',reason='actual learned Move')
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.a)
  before=deepcopy((self.p.hp,self.a.budget,self.a.move_uses,self.e.rng.getstate()))
  with self.assertRaises(ValueError):self.e.use_move(self.a,self.p,'move/박치기',set_damage=True)
  self.assertEqual((self.p.hp,self.a.budget,self.a.move_uses,self.e.rng.getstate()),before)
 def test_two_sources_keep_later_vulnerability_after_first_deadline(self):
  self.open();self.e.apply_status(self.p,'풀죽음',source='move/박치기')
  self.e.end_of_turn(self.a);CLOCK.at_count(self.e,10)
  self.e.apply_status(self.p,'풀죽음',source='move/사념의박치기')
  self.e.end_round();self.e.start_round(self.e.gm.everyone)
  CLOCK.at_count(self.e,20);self.assertIn('취약',self.p.conditions)
  CLOCK.at_count(self.e,10);self.assertNotIn('취약',self.p.conditions)
  self.assertEqual(len(CI.records(self.p,'풀죽음')),2)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_faster_target_can_receive_flinch(self):
  self.open();base=I.value(self.r,self.p).value
  self.assertGreater(base,I.value(self.r,self.a).value)
  self.assertTrue(self.e.apply_status(self.p,'풀죽음',source='move/박치기',applied_by=self.a))
  self.assertEqual(I.value(self.r,self.p).value,base-5)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_native_immunity_rejects_atomically_but_explicit_force_survives_restore(self):
  self.p.status_immune={'풀죽음'}
  def state():return deepcopy((self.p.conditions,self.p.custom_conditions,self.p.spec,self.p.hp,
                              hasattr(self.a,'budget'),getattr(self.a,'budget',None),
                              self.a.move_uses,self.e.rng.getstate(),self.e.log_lines))
  before=state()
  for flag in (None,1,'true'):
   with self.subTest(force=flag):
    with self.assertRaisesRegex(ValueError,'explicit GM force flag required'):
     self.e.apply_status(self.p,'풀죽음',force=flag)
    self.assertEqual(state(),before)
  with self.assertRaisesRegex(ValueError,'current explicit initiative count'):
   self.e.apply_status(self.p,'풀죽음',force=True)
  self.assertEqual(state(),before)
  self.open();base=I.value(self.r,self.p).value
  before=state()
  self.assertFalse(self.e.apply_status(self.p,'풀죽음',source='move/박치기',applied_by=self.a))
  self.assertEqual(state(),before)
  self.assertFalse(CI.records(self.p,'풀죽음'));self.assertFalse(CLOCK.records(self.p))
  self.assertEqual(I.value(self.r,self.p).value,base)
  self.assertTrue(self.e.apply_status(self.p,'풀죽음',source='gm/forced-flinch',applied_by=self.a,force=True))
  self.assertEqual(I.value(self.r,self.p).value,base-5)
  self.assertEqual(len(CI.records(self.p,'풀죽음')),1);self.assertIn('취약',self.p.conditions)
  self.assertTrue(self.e.validate_state()['valid'])
  self.e.gm.snapshot('forced-flinch');self.e.cure_status(self.p,'풀죽음');self.e.gm.restore('forced-flinch')
  self.assertEqual(I.value(self.r,self.p).value,base-5)
  e=self.restored();c=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(c.status_immune,{'풀죽음'});self.assertEqual(I.value(e.r,c).value,base-5)
  self.assertFalse(e.apply_status(c,'풀죽음'));self.assertEqual(len(CI.records(c,'풀죽음')),1)
  self.assertTrue(e.apply_status(c,'풀죽음',source='gm/forced-flinch',force=True))
  self.assertEqual(len(CI.records(c,'풀죽음')),2);self.assertEqual(I.value(e.r,c).value,base-10)
  self.assertTrue(e.validate_state()['valid'])

 def test_child_requires_exact_canonical_active_or_archived_parent(self):
  for archived in (False,True):
   for damage in ('missing','forged_id','missing_metadata','wrong_family','wrong_condition','wrong_holder','wrong_source','wrong_statuses','other_actor'):
    with self.subTest(archived=archived,damage=damage):
     self.setUp();self.open();self.e.apply_status(self.p,'풀죽음',source='move/박치기')
     if archived:self.e.cure_status(self.p,'풀죽음')
     rows=self.p.spec['effect_instance_history'] if archived else CI.records(self.p)
     parent=rows[0];child=CLOCK.records(self.p)[0]
     self.assertEqual(child['flinch_parent_id'],parent['id'])
     self.assertTrue(self.e.validate_state()['valid'])
     if damage=='missing':
      if archived:self.p.spec['effect_instance_history'].clear()
      else:self.p.custom_conditions[CI.KEY].clear()
     elif damage=='forged_id':child['flinch_parent_id']=self.p.entity_id+':effect:999'
     elif damage=='missing_metadata':parent.pop(E.KEY)
     elif damage=='wrong_family':parent[E.KEY]['kind']='roll_components'
     elif damage=='wrong_condition':parent['effect']['condition']='억압'
     elif damage=='wrong_holder':parent[E.KEY]['holder_id']=self.a.entity_id
     elif damage=='wrong_source':child['source']='move/사념의박치기'
     elif damage=='wrong_statuses':child['statuses']=['풀죽음']
     else:
      self.e.apply_status(self.a,'풀죽음')
      child['flinch_parent_id']=CI.records(self.a,'풀죽음')[0]['id']
     self.assertFalse(self.e.validate_state()['valid'])

 def test_child_rejects_malformed_deadlines_and_parent_dates(self):
  for archived in (False,True):
   for field in ('deadline_round','deadline_count','applied_round','applied_count'):
    for bad in (True,1.0,float('nan'),float('inf'),'20',None):
     with self.subTest(archived=archived,field=field,bad=bad):
      self.setUp();self.open();self.e.apply_status(self.p,'풀죽음')
      if archived:self.e.cure_status(self.p,'풀죽음')
      parent=(self.p.spec['effect_instance_history'] if archived else CI.records(self.p))[0]
      child=CLOCK.records(self.p)[0]
      if field.startswith('deadline'):
       deadline=list(child['count_deadline']);deadline[0 if field=='deadline_round' else 1]=bad
       child['count_deadline']=deadline
      else:parent[field]=bad
      self.assertFalse(self.e.validate_state()['valid'])

 def test_active_child_rejects_future_application_even_with_matching_deadline(self):
  for archived in (False,True):
   for future in ('round','same_round_count'):
    with self.subTest(archived=archived,future=future):
     self.setUp();self.open();self.e.apply_status(self.p,'풀죽음')
     if archived:self.e.cure_status(self.p,'풀죽음')
     parent=(self.p.spec['effect_instance_history'] if archived else CI.records(self.p))[0]
     if future=='round':parent['applied_round']+=1
     else:parent['applied_count']=19
     CLOCK.records(self.p)[0]['count_deadline']=(parent['applied_round']+1,parent['applied_count'])
     self.assertFalse(self.e.validate_state()['valid'])

 def test_expired_child_cannot_remain_active(self):
  for boundary in ('exact_count','later_round','completed_successor_round'):
   with self.subTest(boundary=boundary):
    self.setUp();self.open();self.e.apply_status(self.p,'풀죽음')
    self.e.cure_status(self.p,'풀죽음');child=deepcopy(CLOCK.records(self.p)[0])
    self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.gm.everyone)
    if boundary=='exact_count':CLOCK.at_count(self.e,20)
    elif boundary=='completed_successor_round':CLOCK.at_count(self.e,21);self.e.end_round()
    else:self.e.end_round();self.e.start_round(self.e.gm.everyone)
    CLOCK.install(self.e,self.p,child)
    self.assertFalse(self.e.validate_state()['valid'])

 def test_scene_archives_do_not_require_a_new_scene_to_replay_old_counts(self):
  self.open();self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.gm.everyone)
  CLOCK.at_count(self.e,10);self.e.apply_status(self.p,'풀죽음');self.e.end_scene()
  self.assertFalse(CLOCK.records(self.p));self.assertFalse(CI.records(self.p,'풀죽음'))
  self.assertTrue(self.p.spec['effect_instance_history'])
  self.e.start_round(self.e.gm.everyone);CLOCK.at_count(self.e,30)
  self.assertTrue(self.e.validate_state()['valid'])
  self.assertTrue(self.restored().validate_state()['valid'])

 def test_core_plus_errata_cure_and_codec_keep_independent_child(self):
  core=self.r
  try:
   self.r=Rules(str(ROOT),ruleset='core+errata');self.setUp();self.open()
   base=I.value(self.r,self.p).value
   self.e.apply_status(self.p,'풀죽음',source='move/박치기',applied_by=self.a)
   self.e.cure_status(self.p,'풀죽음');self.assertEqual(I.value(self.r,self.p).value,base)
   e=self.restored();c=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
   self.assertIn('취약',c.conditions);self.assertFalse(CI.records(c,'풀죽음'))
   self.assertTrue(e.validate_state()['valid'])
   owner=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   e.end_of_turn(owner);e.end_round();e.start_round(e.gm.everyone)
   CLOCK.at_count(e,21);self.assertIn('취약',c.conditions)
   CLOCK.at_count(e,20);self.assertNotIn('취약',c.conditions)
   self.assertTrue(e.validate_state()['valid'])
  finally:self.r=core

 def test_child_rejects_competing_timing_and_payload_fields_in_state_and_import(self):
  for archived in (False,True):
   for field in ('manual_end','owner_turn','round_end_deadline','accuracy_modifier','unexpected_payload'):
    with self.subTest(archived=archived,field=field):
     self.setUp();self.open();self.e.apply_status(self.p,'풀죽음',applied_by=self.a)
     if archived:self.e.cure_status(self.p,'풀죽음')
     payload=CODEC.dump_engine(self.e)
     saved=next(node for node in payload['nodes'].values() if node['kind']=='dict' and
                any(pair[0]=='flinch_parent_id' for pair in node['items']))
     serial=self.a.custom_conditions['combat_turn_serial']
     if field=='owner_turn':
      engine_node=payload['nodes'][payload['root']['$ref']]
      actor_ref=dict(payload['nodes'][engine_node['attrs']['$ref']]['items'])['_active_turn_actor']
      actual={'turn_owner':self.a,'turn_deadline':serial}
      encoded={'turn_owner':actor_ref,'turn_deadline':serial}
     else:
      value=True if field=='manual_end' else self.e.round_no if field=='round_end_deadline' else -99 if field=='accuracy_modifier' else 'unreviewed effect'
      actual=encoded={field:value}
     CLOCK.records(self.p)[0].update(actual)
     saved['items'].extend([[key,value] for key,value in encoded.items()])
     self.assertFalse(self.e.validate_state()['valid'])
     with self.assertRaises(CODEC.StateCodecError):
      CODEC.load_engine(self.r,json.loads(json.dumps(payload,ensure_ascii=False)))

 def test_child_rejects_missing_envelope_or_invalid_ownership_and_installation(self):
  for damage in ('missing_owned','missing_installing','owned_list','unrelated_owned','absent_owned','installing_true','installing_zero'):
   with self.subTest(damage=damage):
    self.setUp();self.open();self.e.apply_status(self.p,'풀죽음');child=CLOCK.records(self.p)[0]
    if damage=='missing_owned':child.pop('owned_statuses')
    elif damage=='missing_installing':child.pop('installing')
    elif damage=='owned_list':child['owned_statuses']=['취약']
    elif damage=='unrelated_owned':child['owned_statuses']={'풀죽음'}
    elif damage=='absent_owned':self.p.conditions.discard('취약')
    elif damage=='installing_true':child['installing']=True
    else:child['installing']=0
    self.assertFalse(self.e.validate_state()['valid'])
