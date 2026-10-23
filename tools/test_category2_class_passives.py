"""Full category2 state evidence for Scholar, Acrobat and Dynamism source entries."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
import items as ITEMS
import state_grants as GRANTS
import state_codec as CODEC
import skill_modifiers as SKILLS
import initiative as INIT
import jump_actions as JUMP
import movement_actions as MOVEMENT

class ClassPassiveStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,seed=144)
  spec=build_trainer(self.rules,'edge-owner',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[])
  spec.update(skills={'일반지식':5,'곡예':3,'교활':3,'육상':2},movement={},movement_basis='trainer_base')
  self.c=Combatant(self.rules,spec);self.c.pos=(1,1)
  self.e.everyone=self.e.gm.everyone=[self.c];self.e.grid=Grid(12,4)
 def equip(self,edges):
  self.c.spec['edges']=edges
  ITEMS.register_feats(self.e,self.c)
 def restored(self):
  engine=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  return engine,engine.everyone[0]
 def remove(self,e,c,uid):
  c.spec['edges']=[x for x in c.spec['edges'] if x!=uid]
  GRANTS.revoke(c,'feature:'+c.entity_id+':'+uid,engine=e)
 def test_scholar_six_skill_domain_stacking_save_and_source_removal(self):
  self.c.spec['edge_choices']={'edge/단정적인-경향':'육체'}
  self.equip(['edge/학자','edge/단정적인-경향']);ITEMS.register_feats(self.e,self.c)
  for skill in ('일반지식','의학','오컬트학','포켓몬학','기술학','생존'):
   with self.subTest(skill=skill):
    rank=SKILLS.rank(self.rules,self.c,skill)[2]
    result=self.e.skill_roll(self.c,skill,fixed=[1]*rank)
    self.assertEqual(result.modifier,2 if skill=='생존' else 1)
    self.assertIn('edge/학자',[s[0] for s in SKILLS.modifiers(self.rules,self.c,skill,0)['sources']])
  self.assertEqual(self.e.skill_roll(self.c,'교활',fixed=[1]*3).modifier,0)
  self.assertEqual(self.e.skill_roll(self.c,'곡예',fixed=[1]*3).modifier,1)
  e,c=self.restored();self.assertEqual(e.skill_roll(c,'생존',fixed=[1]*2).modifier,2)
  self.remove(e,c,'edge/학자')
  self.assertEqual(e.skill_roll(c,'생존',fixed=[1]*2).modifier,1)
  self.assertEqual(e.skill_roll(c,'일반지식',fixed=[1]*5).modifier,0)
 def test_scholar_invalid_prerequisite_duplicate_and_extra_choice_reject_before_rng(self):
  self.c.spec['edges']=['edge/학자'];self.c.spec['skills']['일반지식']=4
  for change in ({},{'skills':{'일반지식':5},'edges':['edge/학자','Scholar']},{'edges':['edge/학자'],'edge_choices':{'학자':['생존']}}):
   self.c.spec.update(change);before=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.e.skill_roll(self.c,'생존')
   self.assertEqual(self.e.rng.getstate(),before)
 def test_acrobat_base_and_current_limits_real_jump_save_and_source_removal(self):
  self.equip(['edge/곡예사']);ITEMS.register_feats(self.e,self.c)
  self.assertEqual(JUMP.limits(self.c),{'high_jump':1,'long_jump':2})
  self.assertEqual(MOVEMENT.capabilities(self.e,self.c)['long_jump'],2)
  e,c=self.restored();self.assertEqual(JUMP.limits(c),{'high_jump':1,'long_jump':2})
  result=e.jump(c,(3,1),jump_id='acrobat-1',apex_height=1,clear_path=True,difficult=False,reason_text='observed clear two-metre gap')
  self.assertTrue(result['landed']);self.assertEqual(c.pos,(3,1))
  self.remove(e,c,'edge/곡예사');self.assertEqual(JUMP.limits(c),{'high_jump':0,'long_jump':1})
  self.c.spec.update(movement_basis='base',movement={'land':6,'high_jump':2,'long_jump':4})
  self.assertEqual(JUMP.limits(self.c),{'high_jump':3,'long_jump':5})
  self.assertEqual(MOVEMENT.capabilities(self.e,self.c)['high_jump'],3)
  self.c.spec['weight_class']=2
  fall=self.e.falling_damage(self.c,meters=3,action_id='acrobat-fall',intentional=True,natural_sky=False,natural_sky_reason='trainer has no natural flight',reason='intentional three metre drop')
  self.assertEqual((fall['base_high_jump'],fall['damage_distance'],fall['damage']),(3,0,0))
  self.c.spec['movement_basis']='current'
  self.assertEqual(JUMP.limits(self.c),{'high_jump':2,'long_jump':4})
 def test_acrobat_prerequisite_duplicate_live_rank_and_traveler_stack(self):
  self.c.spec.update(edges=['edge/곡예사'],skills={'곡예':2})
  with self.assertRaises(ValueError):JUMP.limits(self.c)
  self.c.spec.update(skills={'곡예':3},edges=['edge/곡예사','Acrobat'])
  with self.assertRaises(ValueError):JUMP.limits(self.c)
  self.c.spec.update(edges=['edge/곡예사','edge/여행자'],edge_choices={'edge/여행자':['jump']},skills={'곡예':3,'생존':6})
  self.assertEqual(JUMP.limits(self.c),{'high_jump':3,'long_jump':4})
  self.c.spec['skills']['생존']=4;self.assertEqual(JUMP.limits(self.c),{'high_jump':2,'long_jump':3})
 def test_dynamism_live_guile_rank_equipment_save_and_source_removal(self):
  self.c.spec['initiative_basis']='base';self.equip(['edge/패기']);ITEMS.register_feats(self.e,self.c)
  GRANTS._source(self.c,'equipment:independent-speed','equipment',rule_id='state/initiative_bonus')
  GRANTS.numeric(self.c,'initiative_bonus',2,'equipment:independent-speed')
  base=self.c.staged('spe');self.assertEqual(INIT.value(self.rules,self.c).value,base+5)
  self.c.spec['skills']['교활']=5;self.assertEqual(INIT.value(self.rules,self.c).value,base+7)
  e,c=self.restored();self.assertEqual(INIT.value(e.r,c).value,base+7)
  self.remove(e,c,'edge/패기');self.assertEqual(INIT.value(e.r,c).value,base+2)
  GRANTS.remove_owned(e,c,'equipment:independent-speed');self.assertEqual(INIT.value(e.r,c).value,base)
 def test_dynamism_explicit_basis_prerequisite_virtuoso_and_unresolved_composition(self):
  self.c.spec.update(edges=['edge/패기'],skills={'교활':3})
  with self.assertRaises(ValueError):INIT.value(self.rules,self.c)
  self.c.spec.update(initiative_basis='base',skills={'교활':2})
  with self.assertRaises(ValueError):INIT.value(self.rules,self.c)
  self.c.spec.update(skills={'교활':6},edges=['edge/패기','거장'],edge_choices={'거장':['교활']})
  self.assertEqual(INIT.value(self.rules,self.c).value,self.c.staged('spe')+8)
  self.c.spec['initiative_basis']='current';self.c.initiative_bonus=8
  self.assertEqual(INIT.value(self.rules,self.c).value,self.c.staged('spe')+8)
  self.c.spec['initiative_basis']='base';self.c.initiative_bonus=0;self.c.conditions.add('마비')
  self.assertTrue(INIT.value(self.rules,self.c).unresolved)
  self.c.conditions.clear();self.c.spec['edges'].append('Dynamism')
  with self.assertRaises(ValueError):INIT.value(self.rules,self.c)


 def test_core_explicit_derived_capabilities_rank_thresholds_and_codec(self):
  import capability_actions as CAP
  import state_fields as F
  self.c.spec.update(edges=[],movement={},movement_basis='trainer_base',power_basis='derived',power_policy='ch02:123')
  for rank in range(1,7):
   for other in range(1,7):
    F.base_patch(self.c,{'skills':{'곡예':rank,'육상':other,'전투':rank}},reason='observed actual skill ranks')
    caps=MOVEMENT.capabilities(self.e,self.c);land=(rank+other)//2+3
    self.assertEqual((caps['high_jump'],caps['long_jump'],caps['land'],caps['swim']),(int(rank>=4)+int(rank>=6),rank//2,land,land//2))
    self.assertEqual(CAP.power(self.c),4+int(other>=4)+int(rank>=4))
    self.assertEqual(CAP.throwing_range(self.e,self.c),other+4)
  e,c=self.restored()
  self.assertEqual(c.spec['power_policy'],'ch02:123');self.assertEqual(CAP.power(c),6)
  self.assertEqual(JUMP.limits(c),{'high_jump':2,'long_jump':3})
  self.assertEqual((e.move_profile(c,movement_mode='land')[0],e.move_profile(c,movement_mode='swim')[0]),(9,4))
  self.assertEqual(CAP.throwing_range(e,c),10)
  self.assertEqual(CAP.limits(c),e.r.capability_policy['weight_limits_kg']['6'])
 def test_core_power_conflicting_source_choice_and_current_authority(self):
  import capability_actions as CAP
  self.c.spec.update(edges=[],movement={},power_basis='derived',skills={'육상':3,'전투':3})
  self.c.spec.pop('power_policy',None)  # An imported legacy derived sheet has no inferred policy.
  before=deepcopy(self.c.spec)
  with self.assertRaisesRegex(ValueError,'explicit source choice'):CAP.power(self.c)
  self.assertEqual(self.c.spec,before)
  self.c.spec['power_policy']='ch02:123';self.assertEqual(CAP.power(self.c),4)
  self.c.spec['power_policy']='ch02:208';self.assertEqual(CAP.power(self.c),5)
  self.c.spec.update(power_basis='current',movement={'power':7})
  self.assertEqual(CAP.power(self.c),7)
  self.c.spec['power_basis']='derived'
  with self.assertRaisesRegex(ValueError,'supplied current value'):CAP.power(self.c)


 def test_default_builder_derived_runtime_gear_growth_gm_and_codec(self):
  from unittest.mock import patch
  import state_fields as F
  c=Combatant(self.rules,build_trainer(self.rules,'default-derived',10,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10}))
  self.e.everyone=self.e.gm.everyone=[c];self.c=c
  self.assertEqual((c.spec['movement_basis'],c.spec['movement'],c.movement),('trainer_base',{},5))
  self.assertEqual(self.e.move_profile(c)[0],5)
  lookup=self.rules.item_effects
  with patch.object(self.rules,'item_effects',side_effect=lambda name: ([{'type':'speed_mod','value':2}],{'id':'item/state-speed-fixture','use':'held'}) if name=='state-speed-fixture' else lookup(name)):
   ITEMS.register_item(self.e,c,'state-speed-fixture')
  self.assertEqual((c.movement,self.e.move_profile(c)[0]),(7,7))
  F.base_patch(c,{'skills':{'육상':4,'곡예':4}},reason='observed acquired ranks')
  self.assertEqual((c.movement,self.e.move_profile(c)[0]),(9,9))
  self.e.gm.snapshot('derived-gear')
  ITEMS.unregister_item(self.e,c,'state-speed-fixture');self.assertEqual((c.movement,self.e.move_profile(c)[0]),(7,7))
  self.e.gm.restore('derived-gear');self.assertEqual((c.movement,self.e.move_profile(c)[0]),(9,9))
  e,loaded=self.restored();self.assertEqual((loaded.movement,e.move_profile(loaded)[0]),(9,9))
  ITEMS.unregister_item(e,loaded,'state-speed-fixture');self.assertEqual((loaded.movement,e.move_profile(loaded)[0]),(7,7))
  self.assertEqual(loaded._movement_delta,0)
 def test_explicit_current_builder_and_legacy_movement_codec(self):
  spec=build_trainer(self.rules,'current-sheet',10,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},extra={'movement':{'land':8}})
  c=Combatant(self.rules,spec);self.e.everyone=self.e.gm.everyone=[c];self.c=c
  self.assertEqual((c.spec['movement_basis'],c.movement,self.e.move_profile(c)[0]),('current',8,8))
  c.__dict__['movement']=c.__dict__.pop('_movement_value')
  e,c=self.restored();self.assertEqual((c.movement,e.move_profile(c)[0]),(8,8))
  GRANTS.numeric(c,'movement',2,'fixture:equipment');self.assertNotIn('movement',c.__dict__)
  self.assertEqual(c.movement,10);GRANTS.remove_owned(e,c,'fixture:equipment');self.assertEqual(c.movement,8)
 def test_legacy_derived_raw_movement_requires_explicit_migration(self):
  self.c.__dict__.pop('_movement_delta',None);self.c.__dict__['movement']=4
  with self.assertRaisesRegex(ValueError,'legacy derived movement'):MOVEMENT.capabilities(self.e,self.c)
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  self.e.gm.set_movement_capabilities(self.c,{},basis='trainer_base',reason='GM re-establishes base-derived state with no unknown runtime modifier')
  self.assertNotIn('movement',self.c.__dict__)
  self.assertEqual(self.c.movement,5)
  self.restored()


 def test_unknown_ability_grant_rejects_before_receipt_or_equipment_mutation(self):
  from unittest.mock import patch
  before={'spec':deepcopy(self.c.spec),'abilities':list(self.c.abilities)}
  with self.assertRaisesRegex(ValueError,'unresolved ability grant'):
   GRANTS.register_feature_effect(self.e,self.c,self.c,'fixture','feat/fixture',0,{'type':'grant_ability','grant_ability':'햇볕'})
  self.assertEqual(self.c.spec,before['spec']);self.assertEqual(self.c.abilities,before['abilities'])
  self.assertNotIn(GRANTS.KEY,self.c.spec)
  with patch.object(self.rules,'item_effects',return_value=([{'type':'speed_mod','value':2},{'type':'grant_ability','grant_ability':'missing-ability'}],{'id':'item/fixture','use':'held'})):
   with self.assertRaisesRegex(ValueError,'unresolved ability grant'):ITEMS.register_item(self.e,self.c,'fixture')
  self.assertEqual(self.c.movement,5);self.assertNotIn('_item_reg',self.c.__dict__)

 def test_dynamism_numeric_child_receipt_requires_exact_unique_live_parent(self):
  self.c.spec['initiative_basis']='base';self.equip(['edge/패기'])
  source='feature:'+self.c.entity_id+':edge/패기';part=source+':0'
  state=self.c.spec[GRANTS.KEY]
  self.assertIn(part,state['sources'][source]['effect_sources'])
  self.assertEqual(INIT.value(self.rules,self.c).value,self.c.staged('spe')+3)
  before=deepcopy(state);rng=self.e.rng.getstate()
  state['sources'][source]['effect_sources']=[]
  self.assertTrue(INIT.value(self.rules,self.c).unresolved)
  self.assertEqual(self.e.rng.getstate(),rng)

  self.c.spec[GRANTS.KEY]=deepcopy(before);state=self.c.spec[GRANTS.KEY]
  state['sources']['gm:conflicting-parent']={'kind':'gm','grants':{},'rule_id':'state/initiative_bonus','effect_sources':[part]}
  self.assertTrue(INIT.value(self.rules,self.c).unresolved)
  self.assertEqual(self.e.rng.getstate(),rng)

if __name__=='__main__':unittest.main()
