"""Native Skill Improvement, permanent changes, evolution and refunds."""
from pathlib import Path
from copy import deepcopy
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon
from engine import Engine
import pokemon_skill_edges as E,pokemon_teaching as T,skill_modifiers as S,downtime as D
import pokemon_skill_profiles as P,researcher_features as R

class SkillEdgeStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_progression_state.ProgressionStateTests.setUp
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def pokemon(self,species='근육몬',level=35):
  return self.add(build_pokemon(self.r,species,level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6}))
 def teach(self,c,skill):return self.e.pokemon_activity(self.a,'teach_edge',target=c,edge=T.EDGE,skill=skill,safe=True)
 def rank(self,c,skill):return E.skill_pool(self.r,c.spec,S.skill_id(self.r.skill_policy,skill))
 def test_no_feature_prerequisite_one_hour_one_point_and_distinct_skills(self):
  c=self.pokemon();self.assertFalse(self.a.spec.get('feats'));self.assertFalse(self.a.spec.get('edges'))
  self.teach(c,'육상');self.assertEqual((self.rank(c,'육상'),c.spec['tutor_points'],self.e.elapsed_seconds),((5,0),5,3600))
  before=self.snap()
  with self.assertRaises(ValueError):self.teach(c,'Athletics')
  self.assertEqual(self.snap(),before)
  self.teach(c,'전투');self.assertEqual((self.rank(c,'전투'),c.spec['tutor_points'],self.e.elapsed_seconds),((5,2),4,7200))
  out=self.e.skill_roll(c,'전투',fixed=[1]*5);self.assertEqual(out.total,7)
 def test_below_species_default_allowed_and_above_default_rejects_before_cost(self):
  c=self.pokemon();self.e.gm.set_skill(c,'육상','3d6+3',reason='individual background')
  self.teach(c,'육상');self.assertEqual(self.rank(c,'육상'),(4,3))
  self.e.gm.set_skill(c,'전투','5d6+2',reason='other permanent source')
  before=self.snap()
  with self.assertRaises(ValueError):self.teach(c,'전투')
  self.assertEqual(before,self.snap())
 def test_training_at_six_uses_the_same_permanent_overflow_refund_without_losing_tp(self):
  c=self.pokemon('괴력몬',35);out=self.teach(c,'육상')
  self.assertEqual((out['rank'],out['point_cost'],out['refunded_points']),(6,1,1))
  self.assertEqual((c.spec['tutor_points'],self.e.elapsed_seconds,len(E.active(c.spec))),(6,3600,0))
 def test_actual_evolution_refunds_both_overflowing_investments_once(self):
  c=self.pokemon();self.teach(c,'육상');self.teach(c,'전투');self.assertEqual(c.spec['tutor_points'],4)
  out=D.evolve_combatant(self.e,c,'괴력몬');self.assertTrue(out['evolved'])
  self.assertEqual((self.rank(c,'육상'),self.rank(c,'전투'),c.spec['tutor_points']),((6,0),(6,0),6))
  self.assertTrue(all(r['status']=='refunded' for r in c.spec['learned_poke_edges']))
  before=self.snap();self.assertFalse(D.evolve_combatant(self.e,c,'괴력몬')['evolved']);self.assertEqual(before,self.snap())
  self.assertEqual(self.e.skill_roll(c,'전투',fixed=[1]*6).total,6)
 def test_evolution_at_six_keeps_investment_and_species_flat_modifiers(self):
  c=self.pokemon('스라크',35);self.teach(c,'육상');self.teach(c,'곡예')
  self.assertTrue(D.evolve_combatant(self.e,c,'핫삼')['evolved'])
  self.assertEqual((self.rank(c,'육상'),self.rank(c,'곡예'),c.spec['tutor_points']),((6,2),(5,0),4))
  self.assertEqual(len(E.active(c.spec)),2)
 def test_permanent_gm_change_refunds_once_and_does_not_clamp_other_sources(self):
  c=self.pokemon();self.teach(c,'육상');before=c.spec['tutor_points']
  receipt=self.e.gm.set_skill(c,'육상','7d6+4',reason='permanent skill reward',request_id='reward')
  self.assertEqual((self.rank(c,'육상'),c.spec['tutor_points']),((6,4),before+1))
  self.assertEqual(receipt['derived_after']['tutor_points'],before+1)
  self.assertEqual(self.e.gm.set_skill(c,'육상','7d6+4',reason='permanent skill reward',request_id='reward'),receipt)
  self.assertEqual(c.spec['tutor_points'],before+1)
  self.e.gm.set_skill(c,'전투','8d6+1',reason='independent permanent rank; no invested edge')
  self.assertEqual(self.rank(c,'전투'),(8,1));self.assertEqual(c.spec['tutor_points'],before+1)
 def test_temporary_pushed_dice_and_flat_roll_bonus_do_not_refund(self):
  c=self.pokemon();self.teach(c,'육상')
  c.spec['pushed_skill']={'source':R.SOURCE,'feature':R.SKILL_TRAINER,'trainer_id':self.a.entity_id,'skill':'육상','training_source':'completed training','completed_at':self.e.elapsed_seconds}
  out=self.e.skill_roll(c,'육상',fixed=[1]*6,mods=4)
  self.assertEqual(out.total,10);self.assertEqual((len(E.active(c.spec)),c.spec['tutor_points']),(1,5))
 def test_gm_and_durable_restore_preserve_investments_refunds_and_actual_pool(self):
  c=self.pokemon();self.teach(c,'육상');saved=self.e.gm.snapshot()
  self.e.gm.set_skill(c,'육상','7d6',reason='permanent reward');self.e.gm.restore(saved)
  c=next(a for a in self.e.gm.everyone if a.entity_id==c.entity_id)
  self.assertEqual((self.rank(c,'육상'),c.spec['tutor_points']),((5,0),5))
  self.e.gm.set_skill(c,'육상','7d6',reason='permanent reward')
  loaded=self.restored();other=next(a for a in loaded.gm.everyone if a.entity_id==c.entity_id)
  self.assertEqual(other.spec['learned_poke_edges'],c.spec['learned_poke_edges']);self.assertEqual(other.spec['tutor_points'],6)
  loaded.gm.set_skill(other,'육상','8d6',reason='further independent reward');self.assertEqual(other.spec['tutor_points'],6)
  self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state()['issues'])
 def test_invalid_refund_balance_rejects_gm_patch_and_evolution_without_partial_effect(self):
  c=self.pokemon();self.teach(c,'육상');c.spec.pop('tutor_points');before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.set_skill(c,'육상','7d6',reason='permanent reward')
  self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):D.evolve_combatant(self.e,c,'괴력몬')
  self.assertEqual(before,self.snap())
 def test_duplicate_investment_and_bad_refund_receipt_fail_state_validation(self):
  c=self.pokemon();self.teach(c,'육상');row=deepcopy(c.spec['learned_poke_edges'][0]);c.spec['learned_poke_edges'].append(row)
  self.assertFalse(self.e.validate_state()['valid']);c.spec['learned_poke_edges'].pop()
  self.e.gm.set_skill(c,'육상','7d6',reason='actual permanent reward')
  c.spec['learned_poke_edges'][0]['refund']['points']=2;self.assertFalse(self.e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
