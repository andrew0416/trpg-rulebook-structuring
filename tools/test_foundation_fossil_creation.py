"""Actual fossils, declared work/materials and one linked native offspring."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_training as fixtures
from builder import build_trainer
from state_codec import dump_engine,load_engine
import creation_fossil as F,crafting_recipes as Q,pokemon_entities as P,pokemon_party as PARTY,pokemon_progression as PROGRESSION,world_entities as W


class FossilTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.PolicyTrainingTests.setUpClass.__func__)
 add=fixtures.PolicyTrainingTests.add
 def setUp(self):
  fixtures.PolicyTrainingTests.setUp(self);self.a.spec['edges']=[F.SOURCE]
  self.a.spec['items']['복원기']=1;self.a.spec['money']=1000;self.a.spec['crafting_scrap']={'화석':200};self.a.spec['shards']={'빨강':2,'파랑':1}
  self.fossil=P.prepare_fossil(self.e,self.a,'f1',{'species':'pokemon/암나이트','status':'fossil'})
  self.a.spec['fossils']={'f1':self.fossil}
 def policy(self,index=1):return json.loads((ROOT/'data/examples/fossil-creation.json').read_text(encoding='utf8'))[index]
 def restore(self,value=None,**options):
  return self.e.restore_declared_fossil(self.a,self.fossil['entity_id'],self.policy() if value is None else value,
    **dict({'request_id':'restore','inputs':{'matrix':{'option':0,'scrap_value':100}},'reason':'actual owned fossil and machine'},**options))
 def details(self):return {'gender':'female','nature':'노력','abilities':[],'moves':[],'special_appearance':False,'inheritance_moves':[]}
 def hatch(self,row,**options):return self.e.hatch_restored_fossil(self.a,row['entity_id'],**dict({'name':'restored child','ready':True,'reason':'actual observed birth','details':self.details()},**options))
 def snap(self):return dump_engine(self.e)
 def default(self,**options):return self.restore(self.policy(0),inputs=None,**options)
 def test_actual_material_work_wait_and_declared_birth_produce_one_native_child(self):
  before=self.snap();plan=self.e.plan_fossil_restoration(self.a,self.fossil['entity_id'],self.policy(),inputs={'matrix':{'option':0,'scrap_value':100}},reason='observed actual restoration')
  self.assertEqual(before,self.snap());self.assertEqual(plan['species'],'pokemon/암나이트')
  out=self.restore();egg=out['egg'];self.assertEqual(egg['parents'],[]);self.assertEqual(egg['hatch_level'],17);self.assertNotIn('stats',egg)
  self.assertEqual(self.e.elapsed_seconds,180);self.assertEqual(self.a.spec['crafting_scrap']['화석'],100);self.assertEqual(self.a.spec['shards']['빨강'],1)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(egg)
  self.assertEqual(before,self.snap());self.e.advance_time(90,[self.a])
  child=self.hatch(egg,ready=None)['pokemon'];self.assertEqual((child.level,child.spec['tutor_points']),(17,3));self.assertEqual(child.spec[PROGRESSION.LEVEL_STATE]['awards'],[])
  self.assertEqual(child.spec['fossil_entity_id'],self.fossil['entity_id']);self.assertEqual(self.fossil['pokemon_id'],child.entity_id)
  before=self.snap();replayed=self.restore();self.assertTrue(replayed['replayed']);self.assertEqual(replayed['egg']['pokemon_id'],child.entity_id);self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):self.hatch(egg)
  self.assertEqual(before,self.snap());self.assertTrue(self.e.validate_state()['valid'])
 def test_missing_permission_knowledge_and_machine_pay_nothing(self):
  mutations=[lambda:self.a.spec.update(edges=[]),lambda:self.a.spec['skills'].update({'포켓몬학':1}),lambda:self.a.spec['items'].update({'복원기':0})]
  for mutate in mutations:
   self.setUp();mutate();before=self.snap()
   with self.assertRaises(ValueError):self.restore()
   self.assertEqual(before,self.snap())
 def test_fake_fossil_wrong_owner_and_changed_request_cannot_duplicate(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.e.restore_declared_fossil(self.a,'fossil/fake',self.policy(),request_id='fake',reason='unobserved')
  self.assertEqual(before,self.snap());other=self.add(build_trainer(self.r,'other',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'edges':[F.SOURCE]}))
  before=self.snap()
  with self.assertRaises(ValueError):self.e.restore_declared_fossil(other,self.fossil['entity_id'],self.policy(),request_id='wrong',reason='wrong owner')
  self.assertEqual(before,self.snap());self.restore();before=self.snap();changed=self.policy();changed['hatch']['level']=16
  with self.assertRaisesRegex(ValueError,'replace'):self.restore(changed)
  with self.assertRaisesRegex(ValueError,'unconsumed'):self.restore(request_id='second')
  self.assertEqual(before,self.snap())
 def test_nonstandard_species_requires_an_explicit_real_gm_choice(self):
  row=P.prepare_fossil(self.e,self.a,'other',{'species':'pokemon/이상해씨','status':'fossil'})
  self.a.spec['fossils']['other']=row;self.fossil=row;before=self.snap()
  for choice in (None,False,1):
   with self.assertRaisesRegex(ValueError,'GM-approved'):self.default(gm_species_approved=choice)
   self.assertEqual(before,self.snap())
  egg=self.default(gm_species_approved=True)['egg'];child=self.hatch(egg)['pokemon']
  self.assertEqual(child.spec['species'],'pokemon/이상해씨');self.assertEqual(child.level,10);self.assertTrue(self.e.validate_state()['valid'])
 def test_native_machine_family_preserves_portable_access_and_rejects_damage(self):
  self.a.spec['items']['복원기']=0;self.a.spec['accessible_equipment']=['휴대용 복원기'];before=self.snap()
  self.a.spec['damaged_items']=['휴대용 복원기'];before=self.snap()
  with self.assertRaisesRegex(ValueError,'machine'):self.default()
  self.assertEqual(before,self.snap());self.a.spec['damaged_items']=[]
  egg=self.default()['egg'];child=self.hatch(egg)['pokemon'];self.assertEqual(child.level,10)
  self.assertEqual(self.fossil[F.CONTRACT]['plan']['machine']['name'],'휴대용 복원기')
 def test_material_alternatives_and_aggregate_balances_are_real(self):
  inputs={'matrix':{'option':0,'scrap_value':0},'crystal':{'option':1,'scrap_value':0}}
  self.restore(inputs=inputs);self.assertEqual(self.a.spec['money'],900);self.assertEqual(self.a.spec['crafting_scrap']['화석'],200)
  self.assertEqual(self.a.spec['shards'],{'빨강':2,'파랑':0})
  self.setUp();value=self.policy();value['materials'].extend([dict(deepcopy(value['materials'][0]),id='more'),dict(deepcopy(value['materials'][0]),id='last')])
  inputs={key:{'option':0,'scrap_value':100} for key in ('matrix','more','last')};before=self.snap()
  with self.assertRaisesRegex(ValueError,'aggregate'):self.restore(value,inputs=inputs)
  self.assertEqual(before,self.snap())
 def test_late_payment_failure_rolls_back_job_time_resources_and_fossil(self):
  before=self.snap();pay=Q.pay_materials
  def fail(*args):pay(*args);raise ValueError('late paid restoration')
  with patch.object(Q,'pay_materials',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late paid restoration'):self.restore()
  self.assertEqual(before,self.snap());self.assertIs(self.a.spec['fossils']['f1'],self.fossil)
  self.restore();self.assertEqual(self.e.elapsed_seconds,180)
 def test_late_egg_construction_failure_rolls_back_actual_debits(self):
  before=self.snap()
  with patch.object(P,'prepare_egg',side_effect=ValueError('late restored egg')):
   with self.assertRaisesRegex(ValueError,'late restored egg'):self.restore()
  self.assertEqual(before,self.snap());self.assertEqual(self.fossil['status'],'fossil')
 def test_late_birth_failure_and_unknown_choices_preserve_lineage(self):
  row=self.default()['egg'];before=self.snap()
  for ready in (None,False,1):
   with self.assertRaises(ValueError):self.hatch(row,ready=ready)
   self.assertEqual(before,self.snap())
  invalid=self.details();invalid.pop('gender')
  with self.assertRaises(ValueError):self.hatch(row,details=invalid)
  with patch.object(PARTY,'finish_hatch',side_effect=ValueError('late fossil birth')):
   with self.assertRaisesRegex(ValueError,'late fossil birth'):self.hatch(row)
  self.assertEqual(before,self.snap());self.assertEqual(self.fossil['status'],'restored_to_egg')
  self.hatch(row);self.assertTrue(self.e.validate_state()['valid'])
 def test_transfer_json_restore_and_replay_keep_the_original_restorer(self):
  row=self.default()['egg'];other=self.add(build_trainer(self.r,'recipient',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'edges':[]}))
  self.e.gm.transfer_egg(self.a,other,row['entity_id'],reason='actual gift',request_id='gift')
  loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)));actors=W.actor_index(loaded);before=dump_engine(loaded)
  out=loaded.restore_declared_fossil(actors[self.a.entity_id],self.fossil['entity_id'],self.policy(0),request_id='restore',inputs=None,reason='actual owned fossil and machine')
  self.assertTrue(out['replayed']);self.assertEqual(out['egg']['owner_id'],other.entity_id);self.assertEqual(before,dump_engine(loaded))
  child=loaded.hatch_restored_fossil(actors[other.entity_id],row['entity_id'],name='gift offspring',ready=True,reason='GM observed gift readiness',details=self.details())['pokemon']
  self.assertEqual(child.spec['trainer_id'],other.entity_id);actual=P.fossil_index(loaded)[self.fossil['entity_id']][1]
  self.assertEqual(actual['restored_by'],self.a.entity_id);self.assertEqual(actual['pokemon_id'],child.entity_id)
  self.assertTrue(loaded.validate_state()['valid'])
 def test_changed_birth_source_and_payment_evidence_are_rejected(self):
  row=self.restore()['egg'];egg=P.egg_index(self.e)[row['entity_id']][1]
  for field,value in ((F.BIRTH,{'level':1,'tutor_points':1,'seconds':0}),('source','gm/forged'),('produced_at',0)):
   previous=deepcopy(egg[field]);egg[field]=value;self.assertFalse(self.e.validate_state()['valid']);egg[field]=previous
  contract=self.fossil[F.CONTRACT];contract['payments'][0]['amount']+=1
  self.assertFalse(self.e.validate_state()['valid']);contract['payments'][0]['amount']-=1
  self.assertTrue(self.e.validate_state()['valid'])
 def test_gm_restore_preserves_one_lifetime_and_forged_birth_override_is_rejected(self):
  row=self.default()['egg'];snapshot=self.e.gm.snapshot();self.hatch(row);self.e.gm.restore(snapshot)
  self.assertEqual(P.fossil_index(self.e)[self.fossil['entity_id']][1]['status'],'restored_to_egg')
  before=self.snap();self.assertTrue(self.default()['replayed']);self.assertEqual(before,self.snap());self.hatch(row)
  fossil=P.fossil_index(self.e)[self.fossil['entity_id']][1];fossil.pop(F.CONTRACT)
  self.assertFalse(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
