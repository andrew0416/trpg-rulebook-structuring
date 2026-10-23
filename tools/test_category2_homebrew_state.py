"""Permanent Tera choice versus active form, effective types and native cleanup."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import homebrew_state as H
import effects_ext as EXT
import state_grants as G
class HomebrewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='homebrew');cls.core=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,9);spec=build_pokemon(self.r,'이상해씨',10);spec['pos']=(0,0);self.a=Combatant(self.r,spec)
  spec=build_pokemon(self.r,'꼬렛',10);spec['pos']=(1,0);self.b=Combatant(self.r,spec);self.e.everyone=self.e.gm.everyone=[self.a,self.b]
 def test_permanent_type_is_not_an_active_transform(self):
  old=list(self.a.types);H.observe_type(self.e,self.a,'불꽃',reason='established permanent choice')
  self.assertFalse(EXT._eval_cond(self.e,self.a,self.b,'user is terastallized',{}));self.assertEqual(self.a.types,old)
  H.observe_active(self.e,self.a,True,reason='existing active state')
  self.assertTrue(EXT._eval_cond(self.e,self.a,self.b,'user is terastallized',{}));self.assertEqual(self.a.types,['불꽃']);self.assertEqual(H.stab_types(self.a),old)
 def test_native_damage_base_keeps_old_stab_without_adding_new_stab(self):
  grass=self.r.move('move/덩굴채찍');fire=self.r.move('move/불꽃세례')
  before_grass=self.e.damage_base(self.a,grass);before_fire=self.e.damage_base(self.a,fire)
  H.observe_type(self.e,self.a,'불꽃',reason='type choice');H.observe_active(self.e,self.a,True,reason='active')
  self.assertEqual(self.e.damage_base(self.a,grass),before_grass);self.assertEqual(self.e.damage_base(self.a,fire),before_fire)
  self.assertIn('불꽃',H.ability_stab_types(self.a));self.assertEqual(H.damage_bonus(self.a,fire),10)
 def test_native_type_change_is_ineffective_and_cannot_reappear_after_expiry(self):
  H.observe_type(self.e,self.a,'불꽃',reason='type choice');H.observe_active(self.e,self.a,True,reason='active');before=deepcopy(self.a.spec)
  self.assertFalse(G.type_operation(self.a,'add',['물'],'blocked-source'));self.assertEqual(self.a.spec,before)
  self.e.end_scene();self.assertFalse(H.tera_active(self.a));self.assertEqual(self.a.types,['풀','독']);self.assertEqual(self.a.spec['tera_type'],'불꽃')
 def test_native_faint_boundary_ends_form_but_preserves_permanent_choice(self):
  H.observe_type(self.e,self.a,'불꽃',reason='type choice');H.observe_active(self.e,self.a,True,reason='active')
  self.e.take_damage(self.a,self.a.hp)
  self.assertFalse(self.a.spec[H.KEY]['active']);self.assertEqual(self.a.types,['풀','독']);self.assertEqual(self.a.spec['tera_type'],'불꽃')
 def test_snapshot_restores_active_receipt_and_original_stab(self):
  H.observe_type(self.e,self.a,'불꽃',reason='type choice');H.observe_active(self.e,self.a,True,reason='active');self.e.gm.snapshot('tera')
  self.e.end_scene();self.e.gm.restore('tera');self.assertEqual(self.a.types,['불꽃']);self.assertEqual(H.stab_types(self.a),['풀','독'])
 def test_invalid_choice_and_unselected_profile_are_atomic(self):
  before=deepcopy(self.a.spec)
  with self.assertRaises(ValueError):H.observe_type(self.e,self.a,'스텔라',reason='missing actual ability')
  self.assertEqual(self.a.spec,before)
  e=Engine(self.core,9);a=Combatant(self.core,build_pokemon(self.core,'이상해씨',10));e.everyone=e.gm.everyone=[a]
  with self.assertRaises(ValueError):H.observe_type(e,a,'불꽃',reason='not selected')
  self.assertNotIn('tera_type',a.spec)
 def test_native_fixed_damage_adds_exactly_ten_for_active_tera_type(self):
  fire=self.r.move('move/불꽃세례');grass=self.r.move('move/덩굴채찍')
  before_fire=self.e.roll_damage(self.a,self.b,fire,set_damage=True);before_grass=self.e.roll_damage(self.a,self.b,grass,set_damage=True)
  H.observe_type(self.e,self.a,'불꽃',reason='type choice');H.observe_active(self.e,self.a,True,reason='active')
  self.assertEqual(self.e.roll_damage(self.a,self.b,fire,set_damage=True),before_fire+10)
  self.assertEqual(self.e.roll_damage(self.a,self.b,grass,set_damage=True),before_grass)
 def test_actual_evolution_preserves_permanent_choice_and_form_receipt(self):
  import downtime
  spec=build_pokemon(self.r,'이상해씨',16);spec['pos']=(0,1);a=Combatant(self.r,spec);self.e.everyone.append(a)
  H.observe_type(self.e,a,'불꽃',reason='permanent choice');H.observe_active(self.e,a,True,reason='existing state')
  uid=a.entity_id;receipt=deepcopy(a.spec[H.KEY]);spec_identity=a.spec
  self.assertTrue(downtime.evolve(self.r,a.spec,'이상해풀'))
  self.assertIs(a.spec,spec_identity);self.assertEqual(a.entity_id,uid);self.assertEqual(a.spec['tera_type'],'불꽃');self.assertEqual(a.spec[H.KEY],receipt)
  self.assertEqual(a.types,['불꽃']);self.assertEqual(H.stab_types(a),['풀','독'])
  self.e.end_scene();self.assertEqual(a.spec['tera_type'],'불꽃');self.assertEqual(a.types,['풀','독'])
 def test_stab_ability_readers_keep_original_and_include_tera_only_while_active(self):
  import effects as FX
  fire=self.r.move('move/불꽃세례');grass=self.r.move('move/덩굴채찍');water=self.r.move('move/물대포')
  self.a.registry.append({'type':'gain_keyword','moves':'STAB damaging','keyword':'우선','_ability':'test-ability'})
  self.a.modifiers.append({'type':'damage_roll_mod','moves':'STAB','value':7,'_ability':'test-ability'})
  def bonus(move):return FX.passive_damage_mods(self.e,self.a,self.b,move,{})[1]
  self.assertNotIn('우선',EXT.keywords_for(self.a,fire));self.assertEqual(bonus(fire),0);self.assertEqual(bonus(grass),7)
  H.observe_type(self.e,self.a,'불꽃',reason='type choice');H.observe_active(self.e,self.a,True,reason='active')
  for move in (grass,fire):self.assertIn('우선',EXT.keywords_for(self.a,move));self.assertEqual(bonus(move),7)
  self.assertNotIn('우선',EXT.keywords_for(self.a,water));self.assertEqual(bonus(water),0)
  self.assertFalse(EXT._move_matches({'moves':'STAB'},fire,self.a))
  self.e.end_scene();self.assertNotIn('우선',EXT.keywords_for(self.a,fire));self.assertEqual(bonus(fire),0)
 def test_stellar_permanent_choice_requires_actual_ability_without_fabricated_defense_type(self):
  self.a.abilities.append('스텔라버스트')
  H.observe_type(self.e,self.a,'스텔라',reason='actual ability-backed chosen imitation')
  self.assertEqual(H.tera_type(self.a),'스텔라');self.assertEqual(self.a.types,['풀','독'])
  before=deepcopy(self.a.spec)
  with self.assertRaises(ValueError):H.observe_active(self.e,self.a,True,reason='needs distinct Stellar Blast radiation state')
  self.assertEqual(self.a.spec,before)
if __name__=='__main__':unittest.main()
