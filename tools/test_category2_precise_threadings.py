"""Actual Precise Threadings acquisition and Threaded status attack/displacement."""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import json,unittest
import test_category2_progression_state as _fixture_test_category2_progression_state
import precise_threadings as P,threaded as T,state_grants as G,state_codec as CODEC
import world_entities as W,forced_movement as FORCED,turn as TURN
import acquisition_qualification as Q,activity_jobs as JOBS,effects_ext as EXT
from grid import Grid
from builder import build_trainer

class PreciseThreadingsTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
  self.p=self.pokemon(20,tutor_points=8,weight_kg=20)
  self.t=self.pokemon(20,tutor_points=0,weight_kg=10)
  G.replace_baseline(self.e,self.p,'capabilities',['실 날리기'])
  self.e.grid=Grid(14,6);self.a.pos=(0,4);self.p.pos=(2,1);self.t.pos=(6,1)
 def snap(self):return CODEC.dump_engine(self.e)
 def teach(self,**options):return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=options.pop('edge',P.SOURCE),safe=True,**options)
 def round(self,distance=4):
  self.p.pos=(2,1);self.t.pos=(2+distance,1)
  self.e.start_round([self.p,self.t]);TURN.reset_budget(self.e,self.t);self.e.start_of_turn(self.p)
 def use(self,target=None,**options):
  values={'willing':True,'path':[self.t.pos,(self.t.pos[0]-1,1)],'reason':'actual approved pull route toward the heavier participant'}
  values.update(options)
  return self.e.threaded(self.p,self.t if target is None else target,**values)
 def obj(self,uid='anchor',weight=50,cell=(6,1)):
  loc=deepcopy(W.location_of(self.p));loc['cell']=cell
  W.register_object(self.e,uid,location=loc,weight_kg=weight,reason='actual measured object on this map')
  return self.e._physical_objects[uid]
 def decision(self,target,mover):
  pending=self.e.threaded_equal_weight_policy(self.p,target)
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  return {'value':mover,'scope':pending['decision_scope'],'reason':'GM declares the outcome omitted by the source for these equal observed weights'}
 def test_csv_acquisition_uses_native_qualification_hour_tp_and_origin_once(self):
  with patch.object(Q,'require',wraps=Q.require) as shared,patch.object(JOBS,'run_fixed',wraps=JOBS.run_fixed) as job:
   out=self.teach(edge='C2CSV/input/db/poke-edges.csv:R54:main')
  self.assertGreater(shared.call_count,0);self.assertEqual(job.call_count,1)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(7,3600))
  self.assertEqual((out['range'],out['accuracy'],out['definition_origin']['record']),(6,3,54))
  row=P.records(self.p)[0];self.assertEqual((row['trainer_id'],row['acquired_level'],row['point_cost']),(self.a.entity_id,20,1))
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_prerequisite_owner_and_tp_refuse_without_hour_or_partial_receipt(self):
  for kind in ('level','capability','owner','points'):
   self.setUp()
   if kind=='level':self.e.gm.set_level(self.p,19,reason='actual level correction')
   if kind=='capability':G.replace_baseline(self.e,self.p,'capabilities',[])
   if kind=='owner':
    another=self.add(build_trainer(self.r,'other owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
    self.p.spec['trainer_id']=another.entity_id
   if kind=='points':self.p.spec['tutor_points']=0
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before,kind)
 def test_actual_four_or_six_metre_reach_and_shared_forced_path(self):
  self.round(5);before=self.snap()
  with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before)
  self.setUp();self.teach();self.round(6);other_budget=deepcopy(self.t.budget);hp=self.t.hp
  with patch.object(FORCED,'along_path',wraps=FORCED.along_path) as common:
   out=self.use(path=[(8,1),(7,1),(6,1)])
  self.assertEqual(common.call_count,1);self.assertEqual(out['range'],6)
  self.assertEqual((self.t.pos,self.p.pos),((6,1),(2,1)))
  self.assertEqual(self.t.budget,other_budget);self.assertEqual(self.t.hp,hp)
  self.assertEqual(self.p.budget,{'standard':1,'shift':0,'swift':1})
  self.setUp();self.teach();self.round(7);before=self.snap()
  with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before)
 def test_actual_status_attack_six_vs_three_changes_hit_without_move_or_rank_mutation(self):
  base_move=deepcopy(self.r.move('move/실뿜기'));self.round()
  roll=3+self.t.evasion('변화');target_budget=deepcopy(self.t.budget)
  actual=type(self.e).accuracy_check;observed=[]
  def accuracy(engine,*args,**kw):
   observed.append(deepcopy(args[2]));return actual(engine,*args,**kw)
  with patch.object(type(self.e),'accuracy_check',new=accuracy):
   out=self.use(willing=False,fixed_accuracy=roll)
  self.assertEqual(len(observed),1);self.assertEqual(observed[0]['class'],'변화')
  self.assertFalse(out['hit']);self.assertEqual(out['accuracy'],6);self.assertEqual(self.t.pos,(6,1));self.assertEqual(self.t.budget,target_budget)
  self.assertEqual(self.p.budget['shift'],0)
  self.setUp();skills=deepcopy(self.p.spec['skills']);self.teach();self.round()
  out=self.use(willing=False,fixed_accuracy=3+self.t.evasion('변화'))
  self.assertTrue(out['hit']);self.assertEqual(out['accuracy'],3);self.assertEqual(self.t.pos,(5,1))
  self.assertEqual(self.r.move('move/실뿜기'),base_move);self.assertEqual(self.p.spec['skills'],skills)
 def test_heavier_object_pulls_user_without_object_or_standard_movement_budget(self):
  obj=self.obj();self.round()
  before=deepcopy(obj);target_budget=deepcopy(self.t.budget)
  out=self.use(obj,path=[(2,1),(3,1),(4,1)])
  self.assertEqual(out['mover'],'actor');self.assertEqual(self.p.pos,(4,1))
  self.assertEqual(obj,before);self.assertIs(self.e._physical_objects['anchor'],obj)
  self.assertEqual(self.p.budget,{'standard':1,'shift':0,'swift':1});self.assertEqual(self.t.budget,target_budget)
  self.assertEqual(self.p._regular_shift_movement_used,False)
 def test_lighter_actual_object_moves_in_place_with_sourced_world_location(self):
  obj=self.obj('spool',3);self.round();other_budget=deepcopy(self.t.budget)
  out=self.use(obj,path=[(6,1),(5,1),(4,1)])
  self.assertEqual(out['mover'],'target');self.assertIs(self.e._physical_objects['spool'],obj)
  self.assertEqual(W.grid_cell(obj),(4,1));self.assertEqual(self.p.pos,(2,1))
  self.assertEqual(out['movement']['source'],P.CAPABILITY);self.assertEqual(self.t.budget,other_budget)
  self.assertIn(P.CAPABILITY,json.dumps(obj,ensure_ascii=False))
 def test_unknown_weight_map_path_and_forged_object_refuse_before_cost_or_rng(self):
  for kind in ('weight','map','path','direction','reason','willing','roll'):
   self.setUp();self.round();opts={}
   if kind=='weight':self.p.spec.pop('weight_kg')
   if kind=='map':self.e.grid=None
   if kind=='path':opts['path']=[]
   if kind=='direction':opts['path']=[(6,1),(7,1)]
   if kind=='reason':opts['reason']=''
   if kind=='willing':opts['willing']='yes'
   if kind=='roll':opts.update(willing=False,fixed_accuracy=True)
   before=self.snap()
   with self.assertRaises(ValueError):self.use(**opts)
   self.assertEqual(self.snap(),before,kind)
  self.setUp();obj=self.obj();self.round();before=self.snap()
  with self.assertRaises(ValueError):self.use(deepcopy(obj),path=[(2,1),(3,1)])
  self.assertEqual(self.snap(),before)
 def test_equal_weights_require_explicit_scoped_decision_and_cannot_reuse_after_weight_change(self):
  self.t.spec['weight_kg']=20;self.round();before=self.snap()
  with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before)
  decision=self.decision(self.t,'target')
  unscoped=deepcopy(decision);unscoped.pop('scope');before=self.snap()
  with self.assertRaises(ValueError):self.use(equal_decision=unscoped)
  self.assertEqual(self.snap(),before)
  self.t.spec['weight_kg']=19;before=self.snap()
  with self.assertRaises(ValueError):self.use(equal_decision=decision)
  self.assertEqual(self.snap(),before)
  self.p.spec['weight_kg']=21;self.t.spec['weight_kg']=21;before=self.snap()
  with self.assertRaises(ValueError):self.use(equal_decision=decision)
  self.assertEqual(self.snap(),before)
  self.p.spec['weight_kg']=20
  self.t.spec['weight_kg']=20
  out=self.use(equal_decision=decision)
  self.assertEqual((out['mover'],self.t.pos),('target',(5,1)))
 def test_explicit_equal_weight_no_movement_still_pays_shift(self):
  self.t.spec['weight_kg']=20;self.round()
  out=self.use(equal_decision=self.decision(self.t,'none'),path=[self.t.pos])
  self.assertTrue(out['hit']);self.assertIsNone(out['movement']);self.assertEqual(self.t.pos,(6,1))
  self.assertEqual(self.p.budget['shift'],0)
 def test_actual_collision_and_cell_entry_interrupt_use_shared_forced_owner(self):
  self.round();self.a.pos=(4,1)
  out=self.use(path=[(6,1),(5,1),(4,1)])
  self.assertEqual((self.t.pos,out['movement']['stopped_by']),((5,1),'collision'))
  self.setUp();self.round()
  def stop(e,c,cell):c.hp=0
  with patch.object(EXT,'on_enter_cell',side_effect=stop) as entered:
   out=self.use(path=[(6,1),(5,1),(4,1)])
  self.assertEqual(entered.call_count,1)
  self.assertEqual((self.t.pos,out['movement']['stopped_by']),((5,1),'interrupted'))
 def test_actual_body_footprint_controls_reach_and_blocking_line_refuses_before_payment(self):
  self.teach();self.p.spec['size']='large';self.round(7)
  out=self.use()
  self.assertEqual((out['range'],self.t.pos),(6,(8,1)))
  self.setUp();self.teach();self.round(6);self.e.grid.blocking.add((5,1));before=self.snap()
  with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before)
 def test_native_ranged_opportunity_attack_can_interrupt_before_status_roll(self):
  self.round();origin=self.t.pos
  def stop(e,c,why):c.hp=0
  with patch.object(TURN,'trigger_aoo',side_effect=stop) as aoo,patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as hit:
   out=self.use(willing=False,fixed_accuracy=20)
  self.assertEqual(aoo.call_count,1);self.assertEqual(hit.call_count,0)
  self.assertTrue(out['interrupted']);self.assertFalse(out['hit'])
  self.assertEqual(self.t.pos,origin);self.assertEqual(self.p.budget['shift'],0)
 def test_level_loss_refunds_once_and_reacquisition_uses_current_cost(self):
  self.teach();self.e.gm.set_level(self.p,19,reason='corrected below actual prerequisite')
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertEqual(P.records(self.p)[0]['status'],'refunded')
  self.e.gm.set_level(self.p,19,reason='repeat correction')
  self.assertEqual(self.p.spec['tutor_points'],8)
  self.e.gm.set_level(self.p,20,reason='actual prerequisite recovered');self.teach()
  self.assertEqual(self.p.spec['tutor_points'],7);self.assertEqual(len(P.records(self.p)),2)
 def test_actual_move_derived_capability_and_independent_source_control_refund(self):
  G.replace_baseline(self.e,self.p,'capabilities',[])
  self.e.gm.set_move(self.p,'move/실뿜기',reason='actual permanent learned move')
  self.assertTrue(P.owned(self.p));self.teach()
  G.grant_moves(self.p,['move/실뿜기'],'independent-threaded','feature',lifetime='while_owned')
  self.e.gm.set_move(self.p,'move/실뿜기',add=False,reason='forget only permanent learned source')
  self.assertTrue(P.owned(self.p));self.assertEqual(self.p.spec['tutor_points'],7)
  G.transition(self.e,self.p,lambda e,c:G.revoke(c,'independent-threaded'))
  self.assertFalse(P.owned(self.p));self.assertEqual(self.p.spec['tutor_points'],8)
  G.transition(self.e,self.p,lambda e,c:None)
  self.assertEqual(self.p.spec['tutor_points'],8)
 def test_late_teaching_job_and_forced_motion_failure_roll_back_world_cost_rng_and_receipts(self):
  real=JOBS.run_fixed
  def broken_job(*a,**kw):
   real(*a,**kw);raise ValueError('late common job refusal')
  before=self.snap()
  with patch.object(JOBS,'run_fixed',side_effect=broken_job):
   with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
  obj=self.obj('spool',3);self.round();real_force=FORCED.along_path;before=self.snap()
  def broken_force(*a,**kw):
   real_force(*a,**kw);raise ValueError('late forced movement refusal')
  with patch.object(FORCED,'along_path',side_effect=broken_force):
   with self.assertRaises(ValueError):self.use(obj,path=[(6,1),(5,1)])
  self.assertEqual(self.snap(),before);self.assertIs(self.e._physical_objects['spool'],obj)
 def test_json_and_gm_restore_keep_native_parameters_and_reject_forged_origin(self):
  self.teach();saved=self.e.gm.snapshot();loaded=self.restored()
  p=next(x for x in loaded.everyone if x.entity_id==self.p.entity_id)
  self.assertEqual(T.parameters(p),{'range':6,'accuracy':3,'action_cost':'shift'})
  self.e.gm.set_level(self.p,19,reason='temporary correction');self.e.gm.restore(saved)
  self.assertEqual(T.parameters(self.p)['range'],6);self.assertEqual(self.p.spec['tutor_points'],7)
  P.records(self.p)[0]['definition_origin']['record']=56
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
 def test_external_json_acquisition_and_durable_restore_replay_use_same_native_edge(self):
  source='input/'+self.r.selection.units[P.SOURCE]['source']['file']
  document={'schema':1,'id':'precise-threadings-author','variants':[{'rule_id':P.SOURCE,
   'source':{'file':source,'sha256':sha256((Path(self.r.root)/source).read_bytes()).hexdigest()},
   'inputs':{},'values':{'teaching_operation':{'kind':'edge','edge':P.SOURCE,'safe':True}}}]}
  args={'request_id':'precise-threadings/native'}
  out=self.e.execute_source_policy_teaching(self.a,self.p,document,**args)
  self.assertEqual(out['status'],'PolicyTeachingCompleted');self.assertFalse(out['replayed'])
  loaded=self.restored();owner=next(x for x in loaded.everyone if x.entity_id==self.a.entity_id);p=next(x for x in loaded.everyone if x.entity_id==self.p.entity_id)
  before=CODEC.dump_engine(loaded);again=loaded.execute_source_policy_teaching(owner,p,document,**args)
  self.assertTrue(again['replayed']);self.assertEqual(CODEC.dump_engine(loaded),before)

if __name__=='__main__':unittest.main()

