"""Whole source state for feature multiplicity, specialization and Style Poffin dice."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from contest import ContestEngine,ContestRules
import acquired_features as A
import contest_features as F
import state_codec as CODEC
import items as ITEMS
import pokemon_party as PARTY

class AcquiredBranchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core');cls.contest_rules=ContestRules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,seed=151);self.ce=ContestEngine(self.contest_rules,seed=19)
  self.c=Combatant(self.rules,build_trainer(self.rules,'style-owner',25,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':6,'매력':6,'직감':6,'교활':6,'협박':6}))
  self.c.spec.update(classes=[F.STYLE],feature_choices={F.STYLE:['근사함','귀여움']},feats=[])
  self.ps=[]
  for n in range(3):
   p=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',30,'style-pokemon-'+str(n),abilities=[],moves=['move/연속자르기','move/헤롱헤롱']))
   p.spec.update(trainer_id=self.c.entity_id,poffins=['근사함']*3+['귀여움']*3)
   self.ps.append(p)
  self.e.everyone=self.e.gm.everyone=[self.c,*self.ps]
 def pool(self,p=None,trainer=None,engine=None):
  return self.ce.stat_pool_from_combatant(p or self.ps[0],trainer=trainer or self.c,engine=engine or self.e,smart_stat_policy='ptu-original-special-defense')
 def load(self):
  e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  return e,{c.entity_id:c for c in e.everyone}
 def test_all_global_branch_validations_require_actual_corresponding_parent_acquisition(self):
  uid=F.FLOURISH;self.c.spec.update(feats=[uid]);self.c.spec['feature_choices'][uid]=['근사함','강인함']
  before=deepcopy(self.c.spec)
  with self.assertRaisesRegex(ValueError,'matching acquired class'):A.validate_class_slots(self.c)
  with self.assertRaises(ValueError):ITEMS.register_feats(self.e,self.c)
  self.assertEqual(self.c.spec,before)
  self.c.spec['feature_choices'][uid]=['근사함'];self.c.spec['classes']=[]
  with self.assertRaisesRegex(ValueError,'matching acquired class'):A.validate_class_slots(self.c)
 def test_stat_branch_aliases_canonicalize_without_allowing_duplicate_specializations(self):
  self.c.spec.update(classes=['class/스탯-에이스'],feats=['feat/스탯-링크'],feature_choices={'class/스탯-에이스':['atk','방어'],'feat/스탯-링크':['공격','def']})
  self.assertEqual([x['branch'] for x in A.feature_instances(self.c)],['atk','def'])
  self.assertEqual(A.count_for_class(self.c,'class/스탯-에이스'),4)
  self.c.spec['feature_choices']['feat/스탯-링크']=['공격','atk']
  with self.assertRaisesRegex(ValueError,'branch aliases'):A.validate_class_slots(self.c)
 def test_branch_slots_still_share_four_class_limit_and_round_trip_instances(self):
  self.c.spec.update(classes=[F.STYLE,'class/타입-에이스'],feats=[F.FLOURISH],feature_choices={F.STYLE:['근사함','귀여움'],'class/타입-에이스':['불꽃','물'],F.FLOURISH:['근사함','귀여움']})
  A.validate_class_slots(self.c);self.assertEqual(len(A.class_instances(self.c)),4)
  e,actors=self.load();c=actors[self.c.entity_id]
  self.assertEqual(A.class_instances(c),A.class_instances(self.c));self.assertEqual(A.feature_instances(c),A.feature_instances(self.c))
  c.spec['feature_choices']['class/타입-에이스'].append('풀')
  with self.assertRaisesRegex(ValueError,'four slots'):A.validate_class_slots(c)
 def test_single_feature_repeated_alias_acquisition_rejects_without_changing_owned_state(self):
  self.c.spec['feats']=['feat/근사한-행위','Cool Conduct'];self.c.spec['feat_ranks']={'feat/근사한-행위':1}
  # Source title aliases, unlike separate acquired ranks, are not two copies.
  self.c.spec['feats'][1]=self.rules.selection.units['feat/근사한-행위']['eng']
  before=deepcopy(self.c.spec)
  with self.assertRaisesRegex(ValueError,'duplicate feature'):ITEMS.register_feats(self.e,self.c)
  self.assertEqual(self.c.spec,before)
  self.c.spec['feats']=['feat/근사한-행위'];self.c.spec['feat_ranks']={'feat/근사한-행위':2}
  A.validate_class_slots(self.c);self.assertEqual(len(A.feature_instances(self.c)),2)
 def test_all_five_style_branches_add_two_real_contest_dice_without_consumption(self):
  for stat in ('아름다움','근사함','귀여움','슬기로움','강인함'):
   with self.subTest(stat=stat):
    self.c.spec['feature_choices']={F.STYLE:[stat]}
    for p in self.ps:p.spec['poffins']=[stat]*3
    history=deepcopy(self.ps[0].spec['poffins']);self.c.spec['classes']=[];ordinary=self.pool();self.c.spec['classes']=[F.STYLE]
    enhanced=self.pool();self.assertEqual(enhanced[stat],ordinary[stat]+2)
    self.assertTrue(all(enhanced[other]==ordinary[other] for other in ordinary if other!=stat))
    self.assertEqual(self.ps[0].spec['poffins'],history)
    choices=F.style_expert(self.e,self.c);self.assertEqual(F.poffin_dice(self.e,self.c,self.ps[0],stat,choices),5)
 def test_actual_contest_constructor_uses_bonus_and_snapshot_reverts_source_removal(self):
  enhanced=self.pool();self.e.gm.snapshot('style')
  contestant=self.ce.contestant_from_combatants(self.e,self.ps[0],self.c,'매력',smart_stat_policy='ptu-original-special-defense')
  self.assertEqual(contestant.stat_dice,enhanced)
  self.c.spec['classes']=[];ordinary=self.pool();self.assertEqual(enhanced['근사함']-ordinary['근사함'],2)
  self.e.gm.restore('style');self.assertEqual(self.pool(),enhanced)
  e,actors=self.load();self.assertEqual(self.pool(actors[self.ps[0].entity_id],actors[self.c.entity_id],e),enhanced)
 def test_current_owner_transfer_removes_only_style_bonus_and_retains_physical_poffins(self):
  new=Combatant(self.rules,build_trainer(self.rules,'new-owner',25,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
  self.e.everyone.append(new);PARTY.configure(self.e,self.c,mode='unlimited',reason='observed roster',roster=self.ps)
  PARTY.configure(self.e,new,mode='unlimited',reason='observed empty roster',roster=[])
  enhanced=self.pool();p=self.ps[0];history=deepcopy(p.spec['poffins'])
  PARTY.transfer(self.e,self.c,target=p,new_owner=new,reason='observed voluntary transfer',request_id='style-transfer')
  ordinary=self.pool(p,new);self.assertEqual(enhanced['근사함']-ordinary['근사함'],2);self.assertEqual(enhanced['귀여움']-ordinary['귀여움'],2)
  self.assertEqual(p.spec['poffins'],history)
  with self.assertRaises(ValueError):self.pool(p,self.c)
 def test_style_dice_cannot_bootstrap_its_own_three_physical_poffin_prerequisite(self):
  self.c.spec['feature_choices']={F.STYLE:['근사함']}
  for p in self.ps:p.spec['poffins']=['근사함']
  before=[deepcopy(p.spec) for p in self.ps]
  with self.assertRaises(ValueError):self.pool()
  self.assertEqual([p.spec for p in self.ps],before)
 def test_live_remaining_pool_removes_and_restores_only_unspent_style_contribution(self):
  c=self.ce.contestant_from_combatants(self.e,self.ps[0],self.c,'매력',smart_stat_policy='ptu-original-special-defense')
  before=deepcopy(c.stat_dice)
  self.ce.perform(c,'연속자르기','근사함',[],False,spend_stat_dice=1)
  self.assertEqual(c.stat_dice['근사함'],before['근사함']-1)
  self.c.spec['classes']=[]
  self.ce.perform(c,'헤롱헤롱','귀여움',[],False)
  self.assertEqual(c.stat_dice['근사함'],before['근사함']-3)
  self.assertEqual(c.stat_dice['귀여움'],before['귀여움']-2)
  self.c.spec['classes']=[F.STYLE]
  self.ce.perform(c,'연속자르기','근사함',[],False)
  self.assertEqual(c.stat_dice['근사함'],before['근사함']-1)
  self.assertEqual(c.stat_dice['귀여움'],before['귀여움'])
  payload=json.loads(json.dumps(CODEC.dump_contest(self.ce,[c]),ensure_ascii=False))
  ce,participants=CODEC.load_contest(self.contest_rules,payload,native_rules=self.rules)
  loaded=participants[0];engine,pokemon,trainer,_,_=ce._native_intro_bindings[loaded]
  trainer.spec['classes']=[];ce.perform(loaded,'헤롱헤롱','귀여움',[],False)
  self.assertEqual(loaded.stat_dice['근사함'],before['근사함']-3)
 def test_live_native_contest_rejects_former_owner_after_transfer_before_roll(self):
  c=self.ce.contestant_from_combatants(self.e,self.ps[0],self.c,'매력',smart_stat_policy='ptu-original-special-defense')
  new=Combatant(self.rules,build_trainer(self.rules,'receiver',25,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
  self.e.everyone.append(new);PARTY.configure(self.e,self.c,mode='unlimited',reason='observed roster',roster=self.ps)
  PARTY.configure(self.e,new,mode='unlimited',reason='empty roster',roster=[])
  PARTY.transfer(self.e,self.c,target=self.ps[0],new_owner=new,reason='observed transfer',request_id='active-contest-transfer')
  before=(deepcopy(c.stat_dice),self.ce.rng.getstate())
  with self.assertRaises(ValueError):self.ce.perform(c,'연속자르기','근사함',[],False,spend_stat_dice=1)
  self.assertEqual((c.stat_dice,self.ce.rng.getstate()),before)
 def test_type_branch_never_accepts_untyped_or_error_placeholder(self):
  for value in ('None','에러'):
   self.c.spec.update(classes=['class/타입-에이스'],feats=[],feature_choices={'class/타입-에이스':[value]})
   with self.assertRaises(ValueError):A.validate_class_slots(self.c)

if __name__=='__main__':unittest.main()
