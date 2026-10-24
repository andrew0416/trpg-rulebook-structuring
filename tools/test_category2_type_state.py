"""Independent Core p238 matrix, source-owned types and profile-specific forms."""
from pathlib import Path
from copy import deepcopy
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
import type_state as T
import state_grants as G
import effects as FX
import homebrew_state as H
from state_codec import StateCodecError

# Transcribed independently from official Core p238 image: weak/resist/immune.
CHART = {
 '노말': ('','바위 강철','고스트'),
 '불꽃': ('풀 얼음 벌레 강철','불꽃 물 바위 드래곤',''),
 '물': ('불꽃 땅 바위','물 풀 드래곤',''),
 '전기': ('물 비행','전기 풀 드래곤','땅'),
 '풀': ('물 땅 바위','불꽃 풀 독 비행 벌레 드래곤 강철',''),
 '얼음': ('풀 땅 비행 드래곤','불꽃 물 얼음 강철',''),
 '격투': ('노말 얼음 바위 악 강철','독 비행 에스퍼 벌레 페어리','고스트'),
 '독': ('풀 페어리','독 땅 바위 고스트','강철'),
 '땅': ('불꽃 전기 독 바위 강철','풀 벌레','비행'),
 '비행': ('풀 격투 벌레','전기 바위 강철',''),
 '에스퍼': ('격투 독','에스퍼 강철','악'),
 '벌레': ('풀 에스퍼 악','불꽃 격투 독 비행 고스트 강철 페어리',''),
 '바위': ('불꽃 얼음 비행 벌레','격투 땅 강철',''),
 '고스트': ('에스퍼 고스트','악','노말'),
 '드래곤': ('드래곤','강철','페어리'),
 '악': ('에스퍼 고스트','격투 악 페어리',''),
 '강철': ('얼음 바위 페어리','불꽃 물 전기 강철',''),
 '페어리': ('격투 드래곤 악','불꽃 독 강철',''),
}

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.core=Rules(str(ROOT),ruleset='core');cls.home=Rules(str(ROOT),ruleset='homebrew');cls.poly=Rules(str(ROOT),ruleset='polygon')
 def engine(self,r=None):
  r=r or self.core;e=Engine(r,971)
  a=Combatant(r,build_trainer(r,'attacker',10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),pos=(0,0)))
  p=Combatant(r,build_pokemon(r,'이상해씨',10,abilities=['심록'],pos=(1,0)))
  e.gm.add_combatant(a);e.gm.add_combatant(p)
  return e,a,p
 def restored(self,e,c):
  n=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  return n,next(a for a in n.everyone if a.entity_id==c.entity_id)
 def test_baseline_catalog_has_eighteen_type_domain_and_exact_typo_receipt(self):
  self.assertEqual(len(T.CORE_TYPES),18);self.assertEqual(set(T.allowed_types(self.core)),set(CHART)|{'유리'})
  for species in self.core.species.values():
   if species.get('types'):
    with self.subTest(species=species['id']):
     self.assertIn(len(species['types']),(1,2));self.assertEqual(T.validate_types(self.core,species['types']),species['types'])
  from ptk_structure import parse_pokemon
  rows,_,_=parse_pokemon(str(ROOT/'input/db/pokemon.csv'))
  parsed=next(x for x in rows if x['id']=='pokemon/블레이범-히스이')
  catalog=self.core.species[parsed['id']]
  self.assertEqual(catalog['types'],['불꽃','고스트']);self.assertEqual(catalog['types_raw'],['불','고스트'])
  self.assertEqual(catalog['_type_normalization'],parsed['_type_normalization'])
  e,_,p=self.engine();spec=build_pokemon(self.core,'블레이범 히스이',40,abilities=['맹화']);c=Combatant(self.core,spec);e.gm.add_combatant(c)
  self.assertEqual(e.type_multiplier('물',c)[0],1.5)
  n,c=self.restored(e,c);self.assertEqual(c.types,['불꽃','고스트'])
 def test_all_324_core_matchups_match_official_chart_and_typeless_stays_neutral(self):
  e,_,p=self.engine()
  for attack,(weak,resist,immune) in CHART.items():
   for defense in CHART:
    p.types=[defense]
    expected=0 if defense in immune.split() else 1.5 if defense in weak.split() else .5 if defense in resist.split() else 1
    with self.subTest(attack=attack,defense=defense):self.assertEqual(e.type_multiplier(attack,p)[0],expected)
   p.types=[];self.assertEqual(e.type_multiplier(attack,p)[0],1)
 def test_dual_triple_type_clauses_are_independent_native_cases(self):
  e,_,p=self.engine()
  for types,value in [(['노말','독'],1),(['불꽃','물'],.25),(['풀','얼음'],2),(['풀','물'],1),(['불꽃','물','드래곤'],.125),(['풀','얼음','벌레'],3)]:
   p.types=types;self.assertEqual(e.type_multiplier('불꽃',p)[0],value)
  p.types=['물','비행','땅'];self.assertEqual(e.type_multiplier('전기',p)[0],0)
 def test_source_owned_third_type_and_base_edit_survive_both_restore_paths(self):
  e,_,p=self.engine();e.gm.set_types(p,['풀','얼음'],reason='explicit base observation')
  G.type_operation(p,'add',['벌레'],'source/forest');self.assertEqual(e.type_multiplier('불꽃',p)[0],3)
  e.gm.snapshot('triple');G.remove_owned(e,p,'source/forest');self.assertEqual(e.type_multiplier('불꽃',p)[0],2)
  e.gm.restore('triple');self.assertEqual(p.types,['풀','얼음','벌레'])
  n,c=self.restored(e,p);self.assertEqual(n.type_multiplier('불꽃',c)[0],3)
  n.gm.set_types(c,['물'],reason='new permanent type');self.assertEqual(c.types,['물','벌레'])
  G.remove_owned(n,c,'source/forest');self.assertEqual(c.types,['물']);self.assertEqual(c.spec['types'],['물'])
 def test_native_move_type_controls_applied_damage_without_granting_trend_ability(self):
  e,a,p=self.engine();e.gm.set_stat(p,'spd',value=20,reason='equal defense');e.gm.set_types(p,['노말'],reason='neutral target')
  move=self.core.move('move/불꽃세례');self.assertEqual(move['type'],'불꽃');self.assertEqual(move['damage_base'],4)
  self.assertEqual(e.roll_damage(a,p,move,set_damage=True),11)
  e.gm.set_types(p,['풀'],reason='weak target');before=p.hp
  self.assertEqual(e.resolve_attack_damage(a,p,move,set_damage=True),16);self.assertEqual(p.hp,before-16)
  e.gm.set_types(p,['바위','강철'],reason='observed types')
  self.assertNotIn('옹골참',p.abilities);self.assertNotIn('ability/옹골참',p.abilities)
  n,c=self.restored(e,p);self.assertEqual(n.type_multiplier(move['type'],c)[0],1)
 def test_electric_status_immunity_tracks_actual_types_and_source_removal(self):
  e,_,p=self.engine();G.type_operation(p,'add',['전기'],'source/electric')
  before=e.rng.getstate();self.assertFalse(e.apply_status(p,'마비'));self.assertNotIn('마비',p.conditions);self.assertEqual(e.rng.getstate(),before)
  n,c=self.restored(e,p);self.assertFalse(n.apply_status(c,'마비'))
  G.remove_owned(n,c,'source/electric');self.assertTrue(n.apply_status(c,'마비'));self.assertIn('마비',c.conditions)
  n,c=self.restored(n,c);self.assertIn('마비',c.conditions);self.assertEqual(c.types,['풀','독'])
 def test_invalid_gm_grant_fallback_effect_and_setter_are_atomic(self):
  e,a,p=self.engine()
  for mutation in [lambda:e.gm.set_types(p,['불'],reason='not a native identity'),lambda:G.type_operation(p,'add',['wrong'],'bad'),lambda:G.type_operation(p,'remove',['풀'],'bad',fallback='wrong'),lambda:FX.h_type_change(e,a,p,{'target':'target','add_type':'wrong'},{}),lambda:setattr(p,'types',['풀','풀']),lambda:setattr(p,'types','불꽃')]:
   before=deepcopy(p.spec);raw=list(p._types);rng=e.rng.getstate()
   with self.assertRaises(ValueError):mutation()
   self.assertEqual(p.spec,before);self.assertEqual(p._types,raw);self.assertEqual(e.rng.getstate(),rng)
  bad=dict(self.core.move('move/불꽃세례'),type='wrong');before=e.rng.getstate()
  with self.assertRaises(ValueError):e.roll_damage(a,p,bad)
  self.assertEqual(e.rng.getstate(),before)
 def test_corrupt_legacy_type_state_cannot_be_silently_saved(self):
  for corruption in ('base','runtime','fallback'):
   e,_,p=self.engine()
   if corruption=='base':p.spec['types']=['wrong']
   elif corruption=='runtime':p._types=['wrong']
   else:
    G.type_operation(p,'remove',['물'],'source/remove');p.spec[G.KEY]['type_sources']['sources']['source/remove']['fallback']='wrong'
   with self.assertRaises(StateCodecError):e.export_state()
 def test_glitch_is_source_selected_and_does_not_replace_bug_or_core_chart(self):
  for r in (self.core,self.home):
   with self.assertRaises(ValueError):T.validate_types(r,['에러'])
  e,_,p=self.engine(self.poly);original=deepcopy(self.poly.mech('combat/type-chart'))
  e.gm.set_types(p,['에러'],reason='GM adopts the Polygon proposed Glitch type')
  for attack,expected in [('고스트',1.5),('에스퍼',1.5),('노말',.5),('전기',.5),('불꽃',1)]:self.assertEqual(e.type_multiplier(attack,p)[0],expected)
  for defense,expected in [('전기',1.5),('에스퍼',1.5),('강철',1.5),('고스트',.5),('독',.5),('풀',1)]:
   e.gm.set_types(p,[defense],reason='observed Glitch matchup target');self.assertEqual(e.type_multiplier('에러',p)[0],expected)
  e.gm.set_types(p,['전기'],reason='distinct Bug comparison');self.assertEqual(e.type_multiplier('벌레',p)[0],1)
  self.assertEqual(self.poly.mech('combat/type-chart'),original)
  e.gm.set_types(p,['에러'],reason='explicit Glitch identity');n,c=self.restored(e,p)
  self.assertEqual(c.types,['에러']);self.assertEqual(n.type_multiplier('고스트',c)[0],1.5)
 def test_explicit_custom_extension_is_admitted_without_mutating_base_matrix(self):
  r=deepcopy(self.poly);matrix=dict.fromkeys(T.CORE_TYPES+('에러','수정'),1)
  r.ruleset.profile['type_extensions']={'수정':{'source_id':T.GLITCH_SOURCE,'reason':'GM declares a distinct source adaptation','attack_vs':dict(matrix),'defense_vs':dict(matrix)}}
  r.ruleset.profile['type_extensions']['수정']['defense_vs']['불꽃']=2
  self.assertEqual(T.validate_types(r,['수정']),['수정']);self.assertEqual(T.matchup(r,'불꽃','수정'),2)
  self.assertEqual(T.matchup(r,'에러','수정'),1)
  del r.ruleset.profile['type_extensions']['수정']['reason']
  with self.assertRaises(ValueError):T.validate_types(r,['수정'])
 def test_tera_defense_immunity_and_stab_survive_durable_restore_then_end(self):
  e,a,p=self.engine(self.home);e.begin_encounter(e.everyone)
  G.type_operation(p,'add',['전기'],'source/before-tera')
  H.observe_type(e,p,'물',reason='permanent choice');H.observe_active(e,p,True,reason='actual active form')
  self.assertEqual(p.types,['물']);self.assertEqual(e.type_multiplier('불꽃',p)[0],.5)
  self.assertIsNone(e.immune_to(p,'마비'));self.assertEqual(H.stab_types(p),['풀','독','전기'])
  before=deepcopy(p.spec);self.assertFalse(FX.h_type_change(e,a,p,{'target':'target','add_type':'고스트'},{}));self.assertEqual(p.spec,before)
  n,c=self.restored(e,p);self.assertEqual(c.types,['물']);self.assertEqual(H.stab_types(c),['풀','독','전기'])
  G.remove_owned(n,c,'source/before-tera');self.assertEqual(c.types,['물']);n.end_encounter()
  self.assertEqual(c.types,['풀','독']);self.assertEqual(c.spec['tera_type'],'물');self.assertNotIn('고스트',c.types)

if __name__=='__main__':unittest.main()
