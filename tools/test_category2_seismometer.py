"""Native Seismometer acquisition, actual underground information and shared receipt reuse."""
from copy import copy,deepcopy
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import json,unittest
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_trainer
from grid import Grid
import tremorsense as T,capability_parameter_edges as P,precise_threadings as PRECISE
import state_grants as G,state_codec as CODEC,world_entities as W,skill_modifiers as S
import perception_observe as O,activity_jobs as JOBS,acquisition_qualification as Q
import acquisition_receipts as RECEIPTS

class SeismometerTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon(20,tutor_points=8);self.t=self.pokemon(20)
  G.replace_baseline(self.e,self.p,'capabilities',['진동감지'])
  self.e.gm.set_skill(self.p,'통찰','3d6+2',reason='actual observed Intuition pool')
  self.e.grid=Grid(18,8);self.a.pos=(0,6);self.p.pos=(2,1);self.t.pos=(7,1)
 def snap(self):return CODEC.dump_engine(self.e)
 def teach(self,edge=T.EDGE,**options):
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=edge,safe=True,**options)
 def environment(self,target=None,**options):
  values={'paths':{},'medium':'underground','present':True,'geometry':{'size':'2m length','shape':'curved cylinder'},'reason':'actual current underground target and observed geometry'}
  values.update(options);return self.e.gm.observe_sensory_environment(self.p,self.t if target is None else target,**values)
 def sense(self,target=None,**options):return self.e.tremorsense(self.p,self.t if target is None else target,**options)
 def test_selected_csv_acquisition_uses_actual_shared_qualification_job_cost_and_receipt(self):
  with patch.object(Q,'require',wraps=Q.require) as qualify,patch.object(JOBS,'run_fixed',wraps=JOBS.run_fixed) as job:
   out=self.teach(edge='C2CSV/input/db/poke-edges.csv:R55:main')
  self.assertGreater(qualify.call_count,0);self.assertEqual(job.call_count,1)
  self.assertEqual((out['point_cost'],out['definition_origin']['record'],self.p.spec['tutor_points'],self.e.elapsed_seconds),(1,55,7,3600))
  row=P.records(self.p,T.EDGE)[0];self.assertEqual((row['trainer_id'],row['acquired_level'],row['status']),(self.a.entity_id,20,'active'))
  receipt=next(row for row in RECEIPTS.read(self.e,self.p) if row['source_id']==T.EDGE)
  self.assertEqual((receipt['basis'],receipt['provider_id'],receipt['debit']['payer_id'],receipt['debit']['amount']),('native_learned_edge',self.a.entity_id,self.p.entity_id,1))
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_real_five_or_five_plus_intuition_range_uses_common_observation_without_skill_mutation(self):
  self.environment();before=self.snap()
  self.assertEqual(self.sense()['values'],{'position':W.effective_location(self.e,self.t),'size':'2m length','shape':'curved cylinder'})
  self.assertEqual(self.snap(),before)
  self.t.pos=(8,1);self.environment();self.assertEqual(self.sense()['reason'],'out_of_range')
  original=deepcopy(self.p.spec['skills']);pool=S.rank(self.r,self.p,'통찰')
  self.teach(edge='Seismometer');self.t.pos=(10,1);self.environment();before=self.snap()
  with patch.object(O,'observe',wraps=O.observe) as common:
   result=self.sense()
  self.assertEqual(common.call_count,1);self.assertEqual(result['status'],'observed')
  self.assertEqual(T.declaration(self.p)['range']['maximum'],8)
  self.assertEqual((self.p.spec['skills'],S.rank(self.r,self.p,'통찰')),(original,pool))
  self.assertEqual(self.snap(),before);self.t.pos=(11,1);self.environment()
  self.assertEqual(self.sense()['reason'],'out_of_range')
 def test_live_rank_changes_range_only_and_pokemon_pool_constant_is_not_metres(self):
  self.teach();self.e.gm.set_skill(self.p,'통찰','4d6-2',reason='observed new actual Intuition pool')
  self.assertEqual(T.declaration(self.p)['range']['maximum'],9)
  self.t.pos=(11,1);self.environment();self.assertEqual(self.sense()['status'],'observed')
  self.e.gm.set_skill(self.p,'통찰','2d6+9',reason='observed lower dice rank with independent constant')
  self.assertEqual(T.declaration(self.p)['range']['maximum'],7);self.assertEqual(self.sense()['reason'],'out_of_range')
 def test_underground_is_actual_pair_evidence_and_ground_does_not_require_visual_line_of_sight(self):
  self.assertEqual(self.sense()['reason'],'medium_unknown')
  self.environment(medium='air');self.assertEqual(self.sense()['reason'],'medium_blocked')
  self.e.grid.blocking.add((4,1));self.environment(paths={'visual':False,'spatial':False})
  result=self.sense();self.assertEqual(result['status'],'observed')
  self.environment(present=False);self.assertEqual((self.sense()['status'],self.sense()['values']),('absent',{}))
  self.environment(present=None);self.assertEqual(self.sense()['reason'],'presence_unknown')
 def test_unknown_shape_and_size_are_reported_as_unknown_and_private_information_is_refused(self):
  self.environment(geometry={'size':None,'shape':None});result=self.sense()
  self.assertEqual(result['status'],'partial');self.assertEqual(set(result['unknown_fields']),{'size','shape'})
  self.assertEqual(result['values']['position'],W.effective_location(self.e,self.t))
  before=self.snap()
  for fields in (['identity'],['species'],['types'],['surface_thought']):
   with self.assertRaises(ValueError):self.sense(information=fields)
  self.assertEqual(self.snap(),before)
 def test_location_and_body_changes_invalidate_old_geometry_until_reobserved(self):
  self.environment();self.assertEqual(self.sense()['status'],'observed')
  self.t.pos=(6,1);self.assertEqual(self.sense()['reason'],'medium_unknown');self.environment()
  self.e.gm.set_footprint(self.t,[(0,0),(1,0)],reason='actual changed target body shape')
  self.assertEqual(self.sense()['reason'],'medium_unknown')
  self.environment(geometry={'size':'3m length','shape':'new branched body'});self.assertEqual(self.sense()['values']['shape'],'new branched body')
  self.e.gm.observe_actor_measurements(self.t,{'height_m':3.1},reason='actual target dimensions changed')
  self.assertEqual(self.sense()['reason'],'medium_unknown');self.environment(geometry={'size':'3.1m length','shape':'new branched body'})
  self.e.gm.set_actor_description(self.t,{'appearance':'actual changed spherical form'},reason='actual form correction')
  self.assertEqual(self.sense()['reason'],'medium_unknown');self.environment(geometry={'size':'3.1m diameter','shape':'sphere'})
  self.assertEqual(self.sense()['values']['shape'],'sphere')
  self.t.location={'kind':'unknown'};self.assertEqual(self.sense()['reason'],'distance_unknown')
 def test_actual_registered_object_can_be_sensed_without_actor_relabelling_or_identity_leak(self):
  loc=deepcopy(W.location_of(self.p));loc['cell']=(6,1)
  W.register_object(self.e,'buried-pipe',location=loc,reason='observed buried physical pipe')
  obj=self.e._physical_objects['buried-pipe'];self.environment(obj)
  before=self.snap();result=self.sense(obj)
  self.assertEqual(result['values'],{'position':W.effective_location(self.e,obj),'size':'2m length','shape':'curved cylinder'})
  self.assertNotIn('buried-pipe',str(result));self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.sense(deepcopy(obj))
  with self.assertRaises(ValueError):self.e.tremorsense(copy(self.p),obj)
  self.assertEqual(self.snap(),before)
  W.finish_physical_use(self.e,obj,'destroyed',{'source':'gm/observed-destruction','former_holder_id':self.p.entity_id})
  self.assertEqual(self.sense(obj)['reason'],'medium_unknown')
  self.environment(obj,geometry={'size':'scattered 2m','shape':'broken fragments'})
  self.assertEqual(self.sense(obj)['values']['shape'],'broken fragments')
 def test_invalid_geometry_or_wrong_actual_pair_does_not_write_partial_world_evidence(self):
  before=self.snap()
  for geometry in ({'size':'1m'},{'size':True,'shape':'sphere'},{'size':'1m','shape':''},{'size':'1m','shape':'sphere','identity':'private'}):
   with self.assertRaises(ValueError):self.environment(geometry=geometry)
   self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.environment(copy(self.t))
  self.assertEqual(self.snap(),before)
 def test_teaching_rejects_level_capability_owner_and_missing_tp_atomically(self):
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
 def test_source_owned_capability_loss_refunds_only_when_last_source_ends_once(self):
  self.teach();G.grant(self.p,'capabilities','Tremorsense','independent-sense','feature')
  G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual((self.p.spec['tutor_points'],P.records(self.p,T.EDGE)[0]['status']),(7,'active'))
  G.transition(self.e,self.p,lambda e,c:G.revoke(c,'independent-sense'))
  self.assertEqual((self.p.spec['tutor_points'],P.records(self.p,T.EDGE)[0]['status']),(8,'refunded'))
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],8)
  with self.assertRaises(ValueError):self.sense()
  G.replace_baseline(self.e,self.p,'capabilities',['진동감지']);self.teach()
  self.assertEqual([row['status'] for row in P.records(self.p,T.EDGE)],['refunded','active'])
  self.assertEqual(self.p.spec['tutor_points'],7)
 def test_precise_threadings_and_seismometer_share_receipt_owner_but_independent_parameters_and_refunds(self):
  G.replace_baseline(self.e,self.p,'capabilities',['진동감지','실 날리기'])
  self.teach();self.teach(edge=PRECISE.SOURCE)
  self.assertEqual((T.declaration(self.p)['range']['maximum'],PRECISE.parameters(self.p)),(8,{'range':6,'accuracy':3}))
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(6,7200))
  G.replace_baseline(self.e,self.p,'capabilities',['실 날리기'])
  self.assertEqual(self.p.spec['tutor_points'],7);self.assertEqual(PRECISE.records(self.p)[0]['status'],'active')
  self.e.gm.set_level(self.p,19,reason='actual shared level prerequisite loss')
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertEqual(PRECISE.parameters(self.p),{})
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],8)
 def test_late_shared_job_failure_rolls_back_time_tp_receipt_world_and_rng(self):
  real=JOBS.run_fixed
  def broken(*args,**options):
   real(*args,**options);raise ValueError('late native teaching job refusal')
  before=self.snap()
  with patch.object(JOBS,'run_fixed',side_effect=broken):
   with self.assertRaisesRegex(ValueError,'late native'):self.teach()
  self.assertEqual(self.snap(),before)
 def test_json_and_gm_restore_retain_current_information_and_refuse_forged_source_or_geometry(self):
  self.teach();self.environment();saved=self.e.gm.snapshot();loaded=self.restored()
  observer=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id);target=next(c for c in loaded.everyone if c.entity_id==self.t.entity_id)
  self.assertEqual(loaded.tremorsense(observer,target),self.sense())
  self.e.gm.set_level(self.p,19,reason='temporary correction');self.e.gm.restore(saved)
  self.assertEqual(T.declaration(self.p)['range']['maximum'],8);self.assertEqual(self.p.spec['tutor_points'],7)
  P.records(self.p,T.EDGE)[0]['definition_origin']['record']=54
  with self.assertRaises(ValueError):self.snap()
  P.records(self.p,T.EDGE)[0]['definition_origin']['record']=55
  getattr(self.e,O.ENV)[O.environment_key(self.p.entity_id,self.t.entity_id)]['facts']['geometry']['shape']='tampered'
  with self.assertRaises(ValueError):self.snap()
 def test_external_json_acquisition_replays_after_restore_without_second_cost(self):
  source='input/'+self.r.selection.units[T.EDGE]['source']['file']
  document={'schema':1,'id':'seismometer-author','variants':[{'rule_id':T.EDGE,
   'source':{'file':source,'sha256':sha256((Path(self.r.root)/source).read_bytes()).hexdigest()},
   'inputs':{},'values':{'teaching_operation':{'kind':'edge','edge':T.EDGE,'safe':True}}}]}
  out=self.e.execute_source_policy_teaching(self.a,self.p,document,request_id='seismometer/native')
  self.assertEqual(out['status'],'PolicyTeachingCompleted');self.assertFalse(out['replayed'])
  loaded=self.restored();owner=next(c for c in loaded.everyone if c.entity_id==self.a.entity_id);p=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id)
  before=CODEC.dump_engine(loaded);again=loaded.execute_source_policy_teaching(owner,p,document,request_id='seismometer/native')
  self.assertTrue(again['replayed']);self.assertEqual(CODEC.dump_engine(loaded),before)
 def test_base_and_edge_source_selection_are_enforced_before_information_or_state_change(self):
  self.environment();before=self.snap();selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/different' if uid==T.SOURCE else selected(uid)):
   with self.assertRaises(ValueError):self.sense()
  self.assertEqual(self.snap(),before)
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/different' if uid==T.EDGE else selected(uid)):
   with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)

if __name__=='__main__':unittest.main()
