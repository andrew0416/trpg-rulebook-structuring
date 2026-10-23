"""Core Power source correction, legacy choices, and native state consumers."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
import capability_actions as CAP
import trainer_capabilities as TRAINER
import state_codec as CODEC
import state_fields as F
import state_grants as G
import items as ITEMS

class PowerPolicyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=616)
  self.c=self.actor('power-owner')
 def actor(self,name,**extra):
  c=Combatant(self.r,build_trainer(self.r,name,20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':20},abilities=[],extra=extra))
  self.e.gm.add_combatant(c,pos=(1,1),side='party',reason='actual created trainer enters roster')
  return c
 def restored(self):
  return CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
 def test_new_builder_core_policy_all_skill_boundaries_and_native_limits(self):
  self.assertEqual((self.c.spec['power_basis'],self.c.spec['power_policy'],CAP.power(self.c)),('derived',TRAINER.CORE_POWER_POLICY,4))
  for athletics in range(1,7):
   for combat in range(1,7):
    F.base_patch(self.c,{'skills':{'육상':athletics,'전투':combat}},reason='actual acquired ranks')
    expected=4+int(athletics>=3)+int(combat>=4)
    self.assertEqual(CAP.power(self.c),expected)
    self.assertEqual(CAP.limits(self.c),CAP.policy(self.c)['weight_limits_kg'][str(expected)])
 def test_current_and_base_supplied_values_keep_their_authority(self):
  for basis,expected in [(None,7),('current',7),('base',9)]:
   extra={'movement':{'power':7,'land':5},'edges':['파워 부스트'],'skills':{'육상':6,'전투':6}}
   if basis is not None:extra['power_basis']=basis
   c=self.actor('supplied-'+str(basis),**extra)
   self.assertEqual(c.spec['power_basis'],basis or 'current');self.assertNotIn('power_policy',c.spec)
   self.assertEqual(CAP.power(c),expected)
  e=self.restored()
  self.assertEqual([CAP.power(c) for c in e.everyone],[4,7,7,9])
 def test_legacy_explicit_policies_preserved_by_builder_gm_and_durable_restore(self):
  a=self.actor('legacy-adept',power_basis='derived',power_policy='ch02:123',skills={'육상':3,'전투':3})
  b=self.actor('legacy-novice',power_basis='derived',power_policy='ch02:208',skills={'육상':3,'전투':3})
  self.assertEqual((CAP.power(a),CAP.power(b)),(4,5))
  self.e.gm.snapshot('explicit-policies')
  a.spec['power_policy']=TRAINER.CORE_POWER_POLICY
  self.e.gm.restore('explicit-policies')
  self.assertEqual((a.spec['power_policy'],b.spec['power_policy']),('ch02:123','ch02:208'))
  e=self.restored();saved={c.name:c for c in e.everyone}
  self.assertEqual((saved[a.name].spec['power_policy'],CAP.power(saved[a.name])),('ch02:123',4))
  self.assertEqual((saved[b.name].spec['power_policy'],CAP.power(saved[b.name])),('ch02:208',5))
 def test_missing_or_unknown_legacy_choice_is_not_inferred_or_mutated(self):
  for choice in (None,'unknown-source'):
   self.c.spec.pop('power_policy',None)
   if choice is not None:self.c.spec['power_policy']=choice
   before=deepcopy(self.c.spec)
   with self.assertRaisesRegex(ValueError,'explicit source choice'):CAP.power(self.c)
   self.assertEqual(self.c.spec,before)
  self.c.spec.pop('power_basis');self.c.spec.pop('power_policy')
  with self.assertRaisesRegex(ValueError,'actual sheet Power'):CAP.power(self.c)
 def test_carrying_native_consumers_follow_live_skills_and_saved_source(self):
  F.base_patch(self.c,{'skills':{'육상':3,'전투':3}},reason='actual novice Athletics')
  state=self.e.gm.set_carried_objects(self.c,[{'id':'observed-crate','weight_kg':25}],reason='weighed crate')
  self.assertEqual((CAP.power(self.c),state['band'],CAP.accuracy(self.c)),(5,'normal',0))
  self.e.gm.snapshot('core-power-carry')
  F.base_patch(self.c,{'skills':{'육상':2,'전투':3}},reason='explicit rank correction')
  self.assertEqual((CAP.power(self.c),CAP.load(self.c)['band'],CAP.accuracy(self.c)),(4,'heavy',-2))
  self.e.gm.restore('core-power-carry')
  e=self.restored();c=next(x for x in e.everyone if x.entity_id==self.c.entity_id)
  self.assertEqual((c.spec['power_policy'],CAP.power(c),CAP.load(c)['band']),(TRAINER.CORE_POWER_POLICY,5,'normal'))
  F.base_patch(c,{'skills':{'육상':2,'전투':3}},reason='actual lower rank')
  self.assertEqual(CAP.load(c)['band'],'heavy')
 def test_traveler_and_power_boost_stack_once_and_removal_preserves_base(self):
  self.c.spec.update(edges=['여행자','파워 부스트'],edge_choices={'여행자':['power']},skills={'육상':2,'생존':3,'전투':4})
  ITEMS.register_feats(self.e,self.c);ITEMS.register_feats(self.e,self.c)
  self.assertEqual(CAP.power(self.c),8)
  e=self.restored();c=next(x for x in e.everyone if x.entity_id==self.c.entity_id)
  self.assertEqual(CAP.power(c),8)
  c.spec['edges'].remove('파워 부스트');G.revoke(c,'feature:'+c.entity_id+':edge/파워-부스트',engine=e)
  self.assertEqual(CAP.power(c),6)
  c.spec['edge_choices']['여행자']=[];self.assertEqual(CAP.power(c),5)
  c.spec['edge_choices']['여행자']=['power'];c.spec['skills']['생존']=2
  self.assertEqual(CAP.power(c),5)
 def test_land_only_extra_still_derives_power_and_derived_with_current_rejects(self):
  c=self.actor('land-only',movement={'land':8},skills={'육상':3})
  self.assertEqual((c.movement,CAP.power(c)),(8,5))
  bad=self.actor('ambiguous',movement={'power':7},power_basis='derived')
  with self.assertRaisesRegex(ValueError,'supplied current value'):CAP.power(bad)

if __name__=='__main__':unittest.main()
