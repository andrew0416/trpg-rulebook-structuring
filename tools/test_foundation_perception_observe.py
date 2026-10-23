"""Actual sensory routes, bounded information, scoped checks and persistence."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_body_modes as _fixture_test_category2_body_modes
from state_codec import dump_engine,load_engine
import perception_observe as O,state_grants as G,world_entities as W,roll_context as RC,survivalist_features as V,aura_state as A,aura_pulse as P


class ObserveTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 def setUp(self):
  _fixture_test_category2_body_modes.Tests.setUp(self);G.grant(self.a,'capabilities','Blindsense','fixture:sense','fixture')
 def policy(self,index=0):return json.loads((ROOT/'data/examples/perception-observe.json').read_text(encoding='utf8'))[index]
 def environment(self,**changes):
  facts={'paths':{'spatial':True,'visual':True,'aura':True},'medium':'air','present':True,'reason':'actual pair sensory environment'};facts.update(changes)
  return self.e.gm.observe_sensory_environment(self.a,self.t,**facts)
 def sense(self,value=None,**options):return self.e.observe_target(self.a,self.t,self.policy() if value is None else value,**options)
 def snap(self):return dump_engine(self.e)
 def test_presence_only_never_discloses_identity_position_type_or_thought(self):
  self.environment();self.t.spec.update(hidden_memory='private secret',text='secret text')
  self.e.gm.observe_surface_thought(self.t,'private thought',reason='observed private thought')
  before=self.snap();result=self.sense();self.assertEqual(result['values'],{'presence':True});self.assertEqual(result['status'],'observed')
  for private in (self.t.entity_id,'private secret','private thought','secret text'):
   self.assertNotIn(private,str(result))
  for information in (['identity'],['position'],['types'],['surface_thought']):
   with self.assertRaises(ValueError):self.sense(information=information)
  self.assertEqual(before,self.snap())
 def test_changed_information_values_drive_the_same_actual_entity_consumer(self):
  self.environment();value=self.policy();value['information']=['position','kind','types','species']
  result=self.sense(value);self.assertEqual(result['values']['position'],W.effective_location(self.e,self.t))
  self.assertEqual(result['values']['types'],self.t.types);self.assertEqual(result['values']['species'],self.t.spec['species'])
  self.assertEqual(set(result['values']),set(value['information']));self.assertNotIn('identity',result['values'])
 def test_unknown_blocked_medium_and_absence_are_distinct_and_reveal_no_detail(self):
  before=self.snap();result=self.sense();self.assertEqual((result['status'],result['reason']),('unknown','path_unknown'));self.assertEqual(before,self.snap())
  self.environment(paths={'spatial':False});result=self.sense();self.assertEqual((result['status'],result['reason']),('not_observable','path_blocked'));self.assertEqual(result['values'],{})
  self.environment(medium='water');result=self.sense();self.assertEqual(result['reason'],'medium_blocked')
  self.environment(present=None);self.assertEqual(self.sense()['reason'],'presence_unknown')
  self.environment(present=False);result=self.sense();self.assertEqual((result['status'],result['values']),('absent',{'presence':False}))
 def test_actual_distance_unknown_coordinates_and_changed_metric_are_explicit(self):
  self.environment();value=self.policy();value['range']['maximum']=5
  result=self.sense(value);self.assertEqual(result['reason'],'out_of_range');self.assertEqual(result['values'],{})
  self.t.location={'kind':'unknown'};self.assertEqual(self.sense()['reason'],'distance_unknown')
  self.t.pos=(5,7);self.environment();value=self.policy();value['range']['maximum']=5
  self.assertEqual(self.sense(value)['status'],'observed');value['range']['metric']='euclidean'
  self.assertEqual(self.sense(value)['reason'],'out_of_range')
 def test_world_movement_invalidates_old_path_until_actual_reobservation(self):
  self.environment();value=self.policy();value['range']['maximum']=20
  self.assertEqual(self.sense(value)['status'],'observed');self.t.pos=(8,3)
  self.assertEqual(self.sense(value)['reason'],'path_unknown');self.environment();self.assertEqual(self.sense(value)['status'],'observed')
  self.e.grid.blocking.add((4,3));self.assertEqual(self.sense(value)['reason'],'path_unknown')
 def test_live_blindsense_does_not_gain_color_or_reading_from_a_declaration(self):
  self.environment();self.t.spec.update(color='red',text='written secret')
  for field in ('color','text'):
   value=self.policy();value['information']=[field]
   result=self.sense(value);self.assertEqual(result['reason'],'sensory_information_unavailable');self.assertEqual(result['values'],{})
 def test_native_darkvision_uses_real_light_and_external_blindness_still_blocks(self):
  G.revoke(self.a,'fixture:sense');G.grant(self.a,'capabilities','Darkvision','fixture:dark','fixture')
  value=self.policy();value.update(source='capability/암흑시야',capabilities=['Darkvision'],mode='visual',path='visual',vision='clear')
  self.environment();self.assertEqual(self.sense(value)['reason'],'lighting_unknown')
  V.observe_environment(self.e,self.a,terrains=['cave'],light='complete_darkness',reason='actual cave darkness')
  self.assertEqual(self.sense(value)['values'],{'presence':True})
  self.assertTrue(self.e.apply_status(self.a,'실명',parameters={'cause':'external'}));self.assertEqual(self.sense(value)['reason'],'vision_blocked')
 def test_actual_capability_and_selected_source_cannot_be_forged_by_copy_or_values(self):
  self.environment();before=self.snap()
  with self.assertRaises(ValueError):self.e.observe_target(copy(self.a),self.t,self.policy())
  with self.assertRaises(ValueError):self.e.observe_target(self.a,copy(self.t),self.policy())
  self.assertEqual(before,self.snap());selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/other' if uid==self.policy()['source'] else selected(uid)):
   with self.assertRaises(ValueError):self.sense()
  self.assertEqual(before,self.snap());G.revoke(self.a,'fixture:sense');before=self.snap()
  with self.assertRaisesRegex(ValueError,'capability'):self.sense()
  self.assertEqual(before,self.snap())
 def test_scoped_native_checks_reveal_only_on_success_and_failure_does_not_mean_absence(self):
  self.environment();value=self.policy();value['check']={'skill':'명령','dc':5,'purpose':'authored call-response presence probe'}
  plan=RC.plan(self.e,self.a,'명령',purpose=value['check']['purpose'],target=self.t)
  result=self.sense(value,roll_options={'fixed':[6]*plan['dice_count']});self.assertTrue(result['check']['passed']);self.assertEqual(result['values'],{'presence':True})
  value['check']['dc']=999;result=self.sense(value,roll_options={'fixed':[1]*plan['dice_count']})
  self.assertEqual((result['status'],result['reason']),('not_observable','check_failed'));self.assertEqual(result['values'],{})
 def test_late_information_failure_rolls_back_actual_native_roll_and_rng(self):
  self.environment();value=self.policy();value['check']={'skill':'명령','dc':0,'purpose':'authored call-response presence probe'};before=self.snap()
  with patch.object(O,'_values',side_effect=ValueError('late sensed information')):
   with self.assertRaisesRegex(ValueError,'late sensed information'):self.sense(value)
  self.assertEqual(before,self.snap())
 def test_actual_registered_object_is_not_relabelled_as_a_pokemon(self):
  W.register_object(self.e,'object/stone',location={'kind':'grid','cell':(4,3)},reason='observed actual stone');obj=self.e._physical_objects['object/stone']
  self.e.gm.observe_sensory_environment(self.a,obj,paths={'spatial':True},medium='air',present=True,reason='actual stone path')
  value=self.policy();value['information']=['presence','kind','types'];result=self.e.observe_target(self.a,obj,value)
  self.assertTrue(result['values']['presence']);self.assertEqual(result['values']['kind'],'physical_object');self.assertIsNone(result['values']['types']);self.assertEqual(result['status'],'partial')
  with self.assertRaises(ValueError):self.e.observe_target(self.a,deepcopy(obj),value)
 def test_native_aura_information_remains_observed_and_surface_thought_pair_specific(self):
  G.grant(self.a,'capabilities','Aura Reader','fixture:aura','fixture');self.environment();value=self.policy(1)
  result=self.sense(value);self.assertEqual(result['status'],'unknown');self.assertTrue(all(v is None for v in result['values'].values()))
  self.e.gm.observe_aura(self.t,living=True,color='observed blue',reason='GM descriptive aura')
  result=self.sense(value);self.assertEqual(result['values'],{'presence':True,'color':'observed blue','mood':None});self.assertEqual(result['unknown_fields'],['mood'])
  G.grant(self.a,'capabilities','Aura Pulse','fixture:pulse','fixture');value=O.native(P.SOURCE,['Aura Pulse'],provider='surface',information=['presence'])
  self.e.gm.observe_surface_thought(self.t,'private current thought',reason='GM observed surface')
  self.assertEqual(self.sense(value)['reason'],'mind_not_open');self.e.set_aura_openness(self.t,self.a,True,reason='actual target willingness')
  self.assertEqual(self.sense(value)['values'],{'presence':True})
  with self.assertRaises(ValueError):self.sense(value,information=['surface_thought'])
  self.assertEqual(self.e.read_aura_thought(self.a,self.t)['surface_thought'],'private current thought')
 def test_environment_json_gm_restore_and_corrupt_evidence_keep_exact_rights(self):
  self.environment();expected=self.sense();saved=self.snap();loaded=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));actors=W.actor_index(loaded)
  self.assertEqual(loaded.observe_target(actors[self.a.entity_id],actors[self.t.entity_id],self.policy()),expected)
  snapshot=self.e.gm.snapshot();self.environment(present=False);self.e.gm.restore(snapshot);self.assertEqual(self.sense(),expected)
  row=getattr(self.e,O.ENV)[O.environment_key(self.a.entity_id,self.t.entity_id)];row['facts']['present']=False
  with self.assertRaises(ValueError):self.sense()
  self.assertFalse(self.e.validate_state()['valid'])
 def test_invalid_environment_and_unknown_declaration_inputs_are_atomic(self):
  before=self.snap()
  for facts in ({'paths':{'spatial':1}},{'paths':{'invented':True}},{'paths':{},'present':1}):
   with self.assertRaises(ValueError):self.environment(**facts)
   self.assertEqual(before,self.snap())
  for mutate in (lambda d:d.update(information=['hidden_memory']),lambda d:d.update(range={'metric':'chebyshev','maximum':True}),lambda d:d.update(guessed=True)):
   value=self.policy();mutate(value)
   with self.assertRaises(ValueError):self.sense(value)
   self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
