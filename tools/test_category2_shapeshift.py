"""C10-111 official mass correction on the existing native body-mode path."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import body_modes as MODE,body_state as BODY,state_codec as CODEC,state_grants as G

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 def setUp(self):
  _fixture_test_category2_body_modes.Tests.setUp(self);self.p.spec.update(weight_kg=20,weight_class=2)
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 known=_fixture_test_category2_body_modes.Tests.known
 normal=_fixture_test_category2_body_modes.Tests.normal
 def shape(self,ratio=1,kind='object',**kwargs):
  offsets=kwargs.pop('offsets',[(0,0)]);appearance={'kind':kind,'description':'observed imitation'}
  if kind=='pokemon':
   appearance['size']=self.p.spec['size']
   pending=MODE.shapeshift_size_choices(self.e,self.p,appearance=appearance,offsets=offsets,mass_ratio=ratio,
     mass_weight_class=kwargs.get('mass_weight_class'),height_m=kwargs.get('height_m'))
   kwargs['pokemon_size_choice']={'value':True,'reason':'GM observes this exact intended Pokemon appearance is comparable to the actual original body','scope':pending['decision_scope']}
  return self.e.change_body_mode(self.p,'shapeshift',mass_ratio=ratio,appearance=appearance,offsets=offsets,reason='observed changed shape',**kwargs)
 def test_mass_bounds_repeated_changes_and_standard_action(self):
  self.known(self.p,'변신');self.p.spec['height_m']=2
  for ratio in (0.5,1,1.5):
   self.begin(self.p);out=self.shape(ratio)
   self.assertEqual(out['mass_ratio'],ratio);self.assertIsNone(out['volume_ratio']);self.assertIsNone(out['height_m']);self.assertIsNone(out['size_ratio'])
   self.assertEqual(out['weight_kg'],20*ratio);self.assertEqual(self.p.spec['weight_kg'],20)
   self.assertEqual(self.p.weight_class,{0.5:1,1:2,1.5:3}[ratio]);self.assertEqual(self.p.spec['weight_class'],2)
   self.assertEqual(self.p.budget['standard'],0)
  self.begin(self.p);self.normal(self.p)
  self.assertEqual(BODY.projection(self.p)['height_m'],2);self.assertEqual(self.p.budget['standard'],0)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(20,2))
 def test_appearance_does_not_copy_machine_or_pokemon_mechanics(self):
  self.known(self.p,'변신')
  before=deepcopy(self.p.spec)
  stats=deepcopy(self.p.stats);moves=deepcopy(self.p.moves);ev=self.p.evasion('물리')
  for kind in ('object','moving_object','complex_machine','pokemon'):
   self.begin(self.p);out=self.shape(kind=kind,height_m=0.4,offsets=[(0,0),(0,1)])
   self.assertEqual(out['height_m'],0.4);self.assertEqual(out['cells'],{(3,3),(3,4)})
   self.assertEqual(out['appearance']['kind'],kind)
   if kind in ('complex_machine','pokemon'):
    self.assertEqual(out['appearance_limits'],{'source':'capability/형상변환자','appearance_only':True,'simplified_machine':kind=='complex_machine','grants_copied_mechanics':False})
   else:self.assertIsNone(out['appearance_limits'])
   self.assertEqual(self.p.stats,stats);self.assertEqual(self.p.moves,moves);self.assertEqual(self.p.evasion('물리'),ev)
   for key in ('species','types','abilities','capabilities','weight_class','weight_kg'):
    self.assertEqual(self.p.spec.get(key),before.get(key))
 def test_invalid_shapes_capability_cost_and_collision_are_atomic(self):
  self.begin(self.p)
  with self.assertRaises(ValueError):self.shape()
  self.known(self.p,'변신')
  for kwargs in ({'ratio':0.499},{'ratio':1.501},{'ratio':True},{'ratio':float('nan')},{'size_ratio':1.1},{'kind':'computer_program'},{'height_m':-1},{'offsets':[(0,0),(4,0)]},{'volume_ratio':1},{'ratio':1.5,'mass_weight_class':1}):
   before=deepcopy((self.p.spec,self.p.budget,self.e.rng.getstate()))
   with self.assertRaises(ValueError):self.shape(**kwargs)
   self.assertEqual((self.p.spec,self.p.budget,self.e.rng.getstate()),before)
  self.shape();before=deepcopy((self.p.spec,self.p.budget))
  with self.assertRaises(ValueError):self.shape(1.5)
  self.assertEqual((self.p.spec,self.p.budget),before)
 def test_changed_body_is_used_by_native_area_targeting(self):
  self.known(self.p,'변신');self.begin(self.p)
  self.shape(offsets=[(0,0),(0,-1),(0,-2)])
  # Anchor at (3,3) is outside the blast; the observed extension at (3,1) is inside.
  self.a.pos=(1,1);self.t.pos=(2,1)
  move=deepcopy(self.r.move('move/눈보라'))
  targets=self.e.targets_in_range(self.a,move,self.e.everyone,self.t)
  self.assertIn(self.p,targets)
  self.begin(self.p);self.normal(self.p)
  targets=self.e.targets_in_range(self.a,move,self.e.everyone,self.t)
  self.assertNotIn(self.p,targets)
 def test_snapshot_json_lifetime_forgetting_and_corruption(self):
  self.known(self.p,'변신');self.begin(self.p);self.shape(1.5,'pokemon',offsets=[(0,0),(0,1)])
  self.e.end_of_turn(self.p);self.e.end_encounter(self.e.everyone);self.e.gm.snapshot('shape')
  saved=deepcopy(self.p.spec[MODE.KEY]);restored=self.restored()
  actor=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(actor.spec[MODE.KEY],saved);self.assertEqual(BODY.cells(actor),{(3,3),(3,4)})
  self.assertEqual((BODY.weight_kg(actor),actor.weight_class),(30,3))
  self.e.gm.set_move(self.p,'move/변신',add=False,reason='forgotten')
  self.begin(self.p);self.normal(self.p);self.assertNotIn(MODE.KEY,self.p.spec)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(20,2))
  self.e.gm.restore('shape');self.assertEqual(self.p.spec[MODE.KEY],saved)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(30,3))
  for key,value in (('mass_ratio',2),('mass_weight_class',1),('volume_ratio',1),('appearance',{'kind':'pokemon','description':'x','abilities':['copy']})):
   self.p.spec[MODE.KEY][key]=value
   with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
   self.p.spec[MODE.KEY]=deepcopy(saved)

 def test_native_ditto_without_using_transform_retains_own_mechanics(self):
  from builder import build_pokemon
  c=self.add(build_pokemon(self.r,'메타몽',10,moves=[],abilities=[],pos=(12,3)))
  before=deepcopy((c.spec['species'],c.spec['types'],c.stats,c.moves,c.abilities,c.spec.get('movement')))
  self.begin(c)
  appearance={'kind':'pokemon','description':'Pikachu appearance only','size':'소형'}
  pending=MODE.shapeshift_size_choices(self.e,c,mass_ratio=1,appearance=appearance,offsets=[(0,0)])
  choice={'value':True,'reason':'GM observes this small Pikachu appearance is comparable to the actual Ditto body','scope':pending['decision_scope']}
  out=self.e.change_body_mode(c,'shapeshift',mass_ratio=1,appearance=appearance,offsets=[(0,0)],pokemon_size_choice=choice,reason='observed unchanged mass')
  self.assertFalse(out['appearance_limits']['grants_copied_mechanics'])
  self.assertEqual((c.spec['species'],c.spec['types'],c.stats,c.moves,c.abilities,c.spec.get('movement')),before)
  self.assertNotIn('move/변신',c.moves)
  self.assertEqual(c.budget['standard'],0)
 def test_simplified_machine_projection_and_malformed_state_reject_both_saves(self):
  from unittest.mock import patch
  self.known(self.p,'변신');self.begin(self.p);self.shape(kind='complex_machine')
  projection=BODY.projection(self.p);self.assertTrue(projection['appearance_limits']['simplified_machine'])
  self.e.gm.snapshot('machine');restored=self.restored();p=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(BODY.projection(p)['appearance_limits'],projection['appearance_limits'])
  self.begin(self.p);self.normal(self.p);self.e.gm.restore('machine')
  saved=deepcopy(self.p.spec[MODE.KEY]);self.p.spec[MODE.KEY]['appearance']['functions']=['computer']
  with self.assertRaises(ValueError):self.e.gm.snapshot('invalid')
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  # Corrupt a retained snapshot externally; restore validates before live commit.
  snap=self.e.gm.snapshots['machine']
  snap['combatants'][id(self.p)]['spec'][MODE.KEY]['appearance']['functions']=['computer']
  self.p.spec[MODE.KEY]=saved;before=deepcopy(self.p.spec)
  with self.assertRaises(ValueError):self.e.gm.restore('machine')
  self.assertEqual(self.p.spec,before)
 def test_unknown_mass_and_overlapping_class_endpoints_require_actual_observation(self):
  self.known(self.p,'변신');self.begin(self.p);self.p.spec.pop('weight_kg')
  before=deepcopy((self.p.spec,self.p.budget,self.e.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'original body mass'):self.shape(1.5)
  self.assertEqual((self.p.spec,self.p.budget,self.e.rng.getstate()),before)
  self.shape();self.assertIsNone(BODY.weight_kg(self.p))
  self.begin(self.p);self.normal(self.p);self.p.spec['weight_kg']=20;self.begin(self.p)
  before=deepcopy((self.p.spec,self.p.budget,self.e.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'shared Weight Class boundary'):self.shape(1.25)
  self.assertEqual((self.p.spec,self.p.budget,self.e.rng.getstate()),before)
  self.shape(1.25,mass_weight_class=3)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(25,3))
 def test_legacy_volume_save_requires_explicit_mass_reapplication(self):
  self.known(self.p,'변신');self.begin(self.p);self.shape()
  row=self.p.spec[MODE.KEY];row['volume_ratio']=row.pop('mass_ratio');row.pop('mass_weight_class')
  with self.assertRaisesRegex(ValueError,'legacy volume'):self.e.gm.snapshot('legacy')
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_weight_grants_layer_over_current_physical_class_and_survive_return(self):
  self.known(self.p,'변신')
  G._source(self.p,'fixture/independent-weight','effect')
  G.weight(self.p,-1,'fixture/independent-weight',mode='add')
  self.assertEqual(self.p.weight_class,1)
  self.begin(self.p);self.shape(1.5)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(30,2))
  self.begin(self.p);self.shape(0.5)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(10,1))
  self.begin(self.p);self.normal(self.p)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(20,1))
  G.revoke(self.p,'fixture/independent-weight',engine=self.e)
  self.assertEqual(self.p.weight_class,2)
 def test_native_weight_class_damage_expression_and_individual_projection_use_mass(self):
  import effects,pokemon_entities as P
  self.known(self.p,'변신');self.begin(self.p);self.shape(1.5)
  self.assertEqual(P.actor_projection(self.p)['weight_kg'],30)
  self.assertEqual(P.actor_projection(self.p)['weight_class'],3)
  self.assertEqual(effects.evaluate('8 - target.weight_class',{'target':self.p}),5)
 def test_native_physical_and_telekinetic_push_consume_current_mass_before_cost(self):
  self.known(self.p,'변신');self.p.spec['skills']['전투']=3
  caster=self.t;caster.spec['skills'].update({'전투':3,'육상':3,'집중':3})
  caster.spec['movement']['power']=3;caster.pos=(2,3)
  G.replace_baseline(self.e,caster,'capabilities',['염력'])
  self.begin(self.p);self.shape(1.5);self.begin(caster)
  before=deepcopy((caster.budget,self.p.spec,self.p.pos,self.e.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'heavier than actual Heavy'):
   self.e.push(caster,self.p,challenger_skill='전투',defender_skill='전투')
  self.assertEqual((caster.budget,self.p.spec,self.p.pos,self.e.rng.getstate()),before)
  with self.assertRaisesRegex(ValueError,'exceeds Focus-based Heavy'):
   self.e.telekinetic_maneuver(caster,self.p,'push',defender_skill='전투')
  self.assertEqual((caster.budget,self.p.spec,self.p.pos,self.e.rng.getstate()),before)
  self.begin(self.p);self.normal(self.p);self.begin(caster)
  out=self.e.push(caster,self.p,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
                  challenger_options={'fixed':[6]*3},defender_options={'fixed':[1]*3})
  self.assertEqual(out['target_position'],(4,3));self.assertEqual(caster.budget['standard'],0)
 def test_native_threaded_consumes_both_current_user_and_target_mass(self):
  G.replace_baseline(self.e,self.p,'capabilities',['실 날리기']);self.known(self.p,'변신')
  self.t.spec['weight_kg']=28;self.begin(self.p);self.shape(1.5)
  out=self.e.threaded(self.p,self.t,willing=True,path=[(7,3),(6,3)],reason='actual thirty kg user pulls twenty eight kg target')
  self.assertEqual(out['mover'],'target');self.assertEqual(self.t.pos,(6,3))
  self.setUp();G.replace_baseline(self.e,self.p,'capabilities',['실 날리기'])
  self.p.spec.update(weight_kg=28,weight_class=3);self.t.spec.update(weight_kg=20,weight_class=2)
  self.known(self.t,'변신');self.begin(self.t)
  self.e.change_body_mode(self.t,'shapeshift',mass_ratio=1.5,appearance={'kind':'object','description':'changed target'},offsets=[(0,0)],reason='actual observed thirty kg target')
  self.begin(self.p)
  out=self.e.threaded(self.p,self.t,willing=True,path=[(3,3),(4,3)],reason='actual heavier target pulls twenty eight kg user')
  self.assertEqual(out['mover'],'actor');self.assertEqual(self.p.pos,(4,3))
 def test_native_weighted_mount_consumes_current_rider_mass(self):
  import capability_actions as LOAD,control_mount as M
  self.known(self.p,'변신');self.p.spec['skills']['곡예']=3
  self.t.spec['movement']['power']=3;self.t.pos=(4,3)
  value=json.loads((Path(self.r.root)/'data/examples/control-mount.json').read_text(encoding='utf-8'))[0]
  value['authority']='gm'
  self.begin(self.p);self.shape(1.5);self.begin(self.p)
  out=self.e.board_mount(self.p,self.t,value,gm_mountable=True,roll_options={'fixed':[6]*3})
  self.assertTrue(out['passed']);self.assertEqual(M.rider_load(self.t)[0],30)
  self.assertEqual((LOAD.load(self.t)['weight_kg'],LOAD.load(self.t)['band']),(30,'staggering'))
  self.assertEqual(self.p.spec['weight_kg'],20)
 def test_transform_weight_replacement_preserves_own_mass_and_exposes_physical_class_on_removal(self):
  import effects_ext as FX
  self.known(self.p,'변신');self.t.spec['weight_class']=5
  self.begin(self.p);self.shape(1.5)
  FX.h_transform(self.e,self.p,self.t,{}, {'source_id':'move/변신','effect_occurrence':'mass-regression'})
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(30,5))
  source=self.p.custom_conditions['transformed']['source']
  G.revoke(self.p,source,engine=self.e)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class),(30,3))
 def test_as_one_reads_current_classes_with_source_lifetime_and_no_baseline_write(self):
  import csv_item_form_contracts as FORM
  self.known(self.p,'변신');G.replace_baseline(self.e,self.p,'capabilities',['혼연일체'])
  self.e.gm.set_ability(self.t,'긴장감',reason='actual basic mount ability')
  self.t.spec.update(weight_kg=40,weight_class=3);self.known(self.t,'변신');self.begin(self.t)
  self.e.change_body_mode(self.t,'shapeshift',mass_ratio=1.5,appearance={'kind':'pokemon','description':'observed changed mount'},offsets=[(0,0)],reason='actual sixty kg mount')
  self.begin(self.p);self.shape(1.5)
  G._source(self.p,'fixture/metal','effect');G.weight(self.p,-1,'fixture/metal',mode='add')
  self.assertEqual(self.p.weight_class,2)
  row=FORM.mount_as_one(self.e,self.p,self.t,ability='긴장감')
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class,self.p.spec['weight_class']),(30,4,2))
  FORM.dismount_as_one(self.e,self.p)
  self.assertEqual((BODY.weight_kg(self.p),self.p.weight_class,self.p.spec['weight_class']),(30,2,2))
  self.assertNotIn(row['source'],G.state(self.p)['weight_sources']['sources'])
  G.revoke(self.p,'fixture/metal',engine=self.e);self.assertEqual(self.p.weight_class,3)
if __name__=='__main__':unittest.main()
