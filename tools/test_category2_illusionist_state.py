"""Direct contract tests for C10-050..053 Illusionist transitions."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
CANON=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(CANON/'engine')]

from builder import build_pokemon,build_trainer
from engine import Combatant,Engine,Rules
import importlib.util
def _overlay(name):
 spec=importlib.util.spec_from_file_location(name,STAGE/'engine'/(name+'.py'));module=importlib.util.module_from_spec(spec)
 sys.modules[name]=module;spec.loader.exec_module(module);return module
I=_overlay('illusion_state');S=_overlay('special_entities');P=_overlay('perception_observe')
from state_codec import dump_engine,load_engine

_canonical_policy=S.policy
def _stage_policy(engine):
    value=_canonical_policy(engine)
    value['sources']=deepcopy(value['sources']);value['sources']['illusion']=[I.SOURCE]
    return value
S.policy=_stage_policy


class IllusionistStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(CANON),ruleset='all')
 def setUp(self):
  spec=build_pokemon(self.rules,'조로아',20,name='illusionist');spec['pos']=(1,1);spec['side']='party'
  self.owner=Combatant(self.rules,spec)
  trainer=build_trainer(self.rules,'observer',20,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'집중':3})
  trainer.update(id='trainer/observer',pos=(2,1),side='party',feats=[])
  self.observer=Combatant(self.rules,trainer)
  self.engine=Engine(self.rules,507);self.engine.everyone=self.engine.gm.everyone=[self.owner,self.observer]
 def row(self):return self.engine._physical_objects['illusion/test']
 def create(self,**changes):
  args=dict(location={'kind':'grid','cell':(2,1)},dimensions_cm={'length':50,'width':20,'height':10},appearance='blue fox',reason='direct Illusionist test')
  args.update(changes);return I.create(self.engine,self.owner,'illusion/test',**args)
 def sense(self,actor,mode,*fields):
  declaration=P.native(I.SOURCE,[],information=fields,mode=mode)
  return P.observe(self.engine,actor,self.row(),declaration)

 def test_create_spends_standard_and_round_trips_native_world_state(self):
  self.engine.start_round(self.engine.everyone);self.engine.start_of_turn(self.owner,initiative_count=20)
  result=self.create();self.assertEqual(self.owner.budget['standard'],0)
  self.assertEqual((result['entity']['kind'],result['state_view']['maximum_dimension_cm']),('illusion',50))
  restored=load_engine(self.rules,json.loads(json.dumps(dump_engine(self.engine),ensure_ascii=False)))
  self.assertEqual(restored._physical_objects['illusion/test']['appearance'],'blue fox')
  self.assertTrue(S.view(restored,'illusion/test')['state_view']['restorable'])

 def test_visual_projection_does_not_leak_identity_and_other_senses_are_empty(self):
  self.create()
  visual=self.sense(self.observer,'visual','presence','identity','kind','text','position')
  self.assertEqual((visual['status'],visual['values']['presence'],visual['values']['text']),('partial',True,'blue fox'))
  self.assertIsNone(visual['values']['identity']);self.assertIsNone(visual['values']['kind'])
  heard=self.sense(self.observer,'auditory','presence')
  self.assertEqual((heard['status'],heard['reason'],heard['values']),('absent','visual_only_illusion',{'presence':False}))

 def test_touch_and_owned_piercing_source_reveal_without_forging_physical_body(self):
  self.create();I.reveal(self.engine,self.observer,'illusion/test',method='touch',reason='actual adjacent physical contact')
  self.assertEqual(self.row()['status'],'marred')
  seen=self.sense(self.observer,'visual','identity','kind')
  self.assertEqual(seen['values'],{'identity':'illusion/test','kind':'illusion'})
  second=Combatant(self.rules,build_trainer(self.rules,'seer',20,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'집중':3},extra={'feats':['feat/정체밝힘-시야']}))
  second.pos=(8,8);self.engine.everyone.append(second)
  I.reveal(self.engine,second,'illusion/test',method='pierce',source='feat/정체밝힘-시야',reason='owned Unveiled Sight')
  self.assertIn(second.entity_id,S.view(self.engine,'illusion/test')['state_view']['revealed_to'])

 def test_simple_and_complex_continuous_manipulation_use_distinct_costs(self):
  self.create();self.engine.start_round(self.engine.everyone);self.engine.start_of_turn(self.owner,initiative_count=20)
  I.manipulate(self.engine,self.owner,'illusion/test',location={'kind':'grid','cell':(3,1)},appearance='dancing flame',complexity='simple',reason='simple continuous motion')
  self.assertEqual((self.owner.budget['swift'],self.owner.budget['standard']),(0,1))
  self.engine.end_of_turn(self.owner);self.engine.start_of_turn(self.observer,initiative_count=10);self.engine.end_of_turn(self.observer);self.engine.end_round()
  self.engine.start_round(self.engine.everyone);self.engine.start_of_turn(self.owner,initiative_count=20)
  I.manipulate(self.engine,self.owner,'illusion/test',location={'kind':'grid','cell':(2,2)},appearance='walking skeleton',complexity='complex',reason='complex continuous motion')
  self.assertEqual((self.owner.budget['swift'],self.owner.budget['standard']),(1,0))

 def test_invalid_size_range_and_unavailable_action_are_atomic(self):
  self.engine.start_round(self.engine.everyone);self.engine.start_of_turn(self.owner,initiative_count=20)
  before=(deepcopy(self.owner.budget),deepcopy(self.engine._physical_objects),self.engine.rng.getstate())
  with self.assertRaisesRegex(ValueError,'at most 50'):self.create(dimensions_cm={'length':51,'width':20,'height':10})
  self.assertEqual((self.owner.budget,self.engine._physical_objects,self.engine.rng.getstate()),before)
  with self.assertRaisesRegex(ValueError,'Focus-rank'):self.create(location={'kind':'grid','cell':(20,20)})
  self.assertEqual((self.owner.budget,self.engine._physical_objects,self.engine.rng.getstate()),before)
  self.create();created=deepcopy(self.row());budget=deepcopy(self.owner.budget)
  with self.assertRaisesRegex(ValueError,'action is unavailable'):
   I.manipulate(self.engine,self.owner,'illusion/test',location={'kind':'grid','cell':(2,1)},appearance='complex dragon',complexity='complex',reason='no second standard action')
  self.assertEqual((self.row(),self.owner.budget),(created,budget))

 def test_creator_dismissal_is_terminal_and_survives_validation(self):
  self.create();I.dismiss(self.engine,self.owner,'illusion/test',reason='creator ended the image')
  self.assertEqual(self.row()['status'],'dismissed')
  self.assertEqual(self.sense(self.observer,'visual','presence')['status'],'absent')
  with self.assertRaisesRegex(ValueError,'already dismissed'):I.dismiss(self.engine,self.owner,'illusion/test',reason='cannot repeat')


if __name__=='__main__':unittest.main()
