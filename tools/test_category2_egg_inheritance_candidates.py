"""Direct C05-144 parent-known Egg/TM inheritance-list state tests."""
from copy import deepcopy
from pathlib import Path
import importlib.util,json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
CANON=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(CANON/'engine'),str(CANON/'tools')]
import test_foundation_egg_creation as FIX
from builder import build_pokemon
from state_codec import dump_engine,load_engine
import materialization_origins as ORIGIN,world_entities as WORLD

def _overlay(name):
 spec=importlib.util.spec_from_file_location(name,STAGE/'engine'/(name+'.py'));module=importlib.util.module_from_spec(spec)
 sys.modules[name]=module;spec.loader.exec_module(module);return module
EGG=_overlay('creation_egg')


class EggInheritanceCandidateTests(unittest.TestCase):
 setUpClass=classmethod(FIX.EggTests.setUpClass.__func__)
 add=FIX.EggTests.add
 def setUp(self):
  FIX.EggTests.setUp(self)
  father=self.add(build_pokemon(self.r,'파라스',5,moves=['move/맹독'],abilities=['건조피부'],extra={'trainer_id':self.a.entity_id,'gender':'male'}))
  self.parents=[self.parents[0],father]
 def policy(self):
  return deepcopy(json.loads((STAGE/'data/examples/egg-creation.json').read_text(encoding='utf-8'))[0])
 def inherited(self):return ['move/뿌리박기','move/맹독']
 def create(self,**changes):
  args={'request_id':'core-inheritance','compatible':True,'species':'pokemon/이상해씨','inheritance_moves':self.inherited(),'reason':'actual C05-144 parent and child catalogs'}
  args.update(changes);return self.e.create_declared_egg(self.a,self.parents,self.policy(),**args)
 def choices(self):
  return {'gender':'female','nature':'노력','abilities':['심록'],'moves':[],'special_appearance':False,'inheritance_moves':self.inherited()}

 def test_actual_parent_sexes_species_candidates_and_source_partitions_are_bound(self):
  before=dump_engine(self.e)
  plan=self.e.plan_egg_creation(self.a,self.parents,self.policy(),compatible=True,species='이상해씨',inheritance_moves=self.inherited(),reason='read-only exact candidate plan')
  self.assertEqual(before,dump_engine(self.e))
  self.assertEqual(plan['species_candidates'],['pokemon/이상해씨','pokemon/파라스'])
  self.assertEqual([x['gender'] for x in plan['parent_facts']],['female','male'])
  self.assertEqual(plan['inheritance_candidates'],self.inherited())
  self.assertEqual(plan['inheritance_candidate_sources'],{'kind':'parent_known_egg_and_tm','egg_moves':['move/뿌리박기'],'tm_moves':['move/맹독'],'declared_moves':[]})

 def test_complete_inheritance_list_survives_egg_transfer_hatch_and_lineage_restore(self):
  row=self.create();actual=next(x for x in self.a.spec['eggs'] if x['entity_id']==row['entity_id'])
  self.assertEqual(actual['inheritance_moves'],self.inherited())
  self.assertEqual(actual[EGG.CONTRACT]['plan']['inheritance_candidate_sources']['tm_moves'],['move/맹독'])
  result=self.e.hatch_declared_egg(self.a,row['entity_id'],name='child',ready=True,reason='actual readiness',choices=self.choices())
  child=result['pokemon'];self.assertEqual(child.spec['inheritance_moves'],self.inherited())
  self.assertEqual(ORIGIN.read(self.e,child.entity_id)['inputs'],[row['entity_id']])
  loaded=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)));actors=WORLD.actor_index(loaded);restored=actors[child.entity_id]
  self.assertEqual(restored.spec['inheritance_moves'],self.inherited())
  self.assertEqual(ORIGIN.read(loaded,restored.entity_id)['native_ref']['entity_id'],row['entity_id'])

 def test_omitted_unlearned_tm_and_reordered_list_reject_without_state_or_time_change(self):
  before=dump_engine(self.e)
  invalid=(['move/뿌리박기'],['move/뿌리박기','move/솔라빔'],list(reversed(self.inherited())))
  for index,moves in enumerate(invalid):
   with self.assertRaises(ValueError):self.create(request_id='bad-'+str(index),inheritance_moves=moves)
   self.assertEqual(dump_engine(self.e),before)

 def test_parent_knowledge_is_snapshotted_and_later_forgetting_does_not_rewrite_the_egg(self):
  row=self.create();actual=next(x for x in self.a.spec['eggs'] if x['entity_id']==row['entity_id']);historical=deepcopy(actual[EGG.BINDING])
  self.e.gm.set_move(self.parents[1],'move/맹독',False,reason='parent later forgot its formerly known TM')
  self.assertEqual(actual[EGG.BINDING],historical);self.assertEqual(actual['inheritance_moves'],self.inherited())
  self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
