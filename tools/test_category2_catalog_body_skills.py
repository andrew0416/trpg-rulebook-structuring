"""Five source clauses: template facts, move routes, species pools, trainer body."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine')]
from engine import Rules,Engine,Combatant
import builder as B,body_state as BODY,pokemon_entities as P,skill_modifiers as S,state_fields as F,state_grants as G
from tools import test_category3_batch13_pokemon as Fixtures

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,721)
  self.t=Combatant(self.r,B.build_trainer(self.r,'trainer',10,{s:10 for s in F.STATS},pos=(1,1)))
  self.e.gm.add_combatant(self.t)
 def pokemon(self,species):
  p=Combatant(self.r,B.build_pokemon(self.r,species,10,abilities=[],pos=(3,1)))
  self.e.gm.add_combatant(p);return p
 def loaded(self):
  e=Engine.import_state(self.r,self.e.export_state());return e,{c.entity_id:c for c in e.everyone}
 def test_species_breeding_diet_habitat_are_known_template_facts_not_individual_guesses(self):
  p=self.pokemon('이상해씨');view=P.species_projection(self.r,p.spec['species'])['template_facts']
  self.assertEqual(view['breeding']['egg_groups'],['괴수','식물'])
  self.assertEqual(view['breeding']['sex_distribution']['male'],0.875)
  self.assertEqual((view['hatch_guidance'],view['diet'],view['habitat']),('10일','초식, 광영양','숲, 초원, 우림'))
  self.assertFalse(view['breeding']['individual_compatibility_inferred'])
  self.assertIsNone(self.e.gm.describe_actor(p)['gender'])
  p.spec['diet_observation']={'food':'GM actual meal','source':'observation'}
  self.e.gm.snapshot('facts');p.spec['diet_observation']['food']='temporary';self.e.gm.restore('facts')
  e,actors=self.loaded();q=actors[p.entity_id]
  self.assertEqual(P.species_projection(e.r,q.spec['species'])['template_facts'],view)
  self.assertEqual(q.spec['diet_observation']['food'],'GM actual meal')
  view['breeding']['egg_groups'].clear()
  self.assertEqual(self.r.species[p.spec['species']]['egg_groups'],['괴수','식물'])
 def test_four_template_learning_routes_stay_distinct_and_do_not_grant_moves(self):
  p=self.pokemon('이상해씨');before=list(p.moves)
  routes=P.species_projection(self.r,p.spec['species'])['template_facts']['move_learning_routes']
  for route,field in [('level_up','level_up'),('egg','egg'),('tm_hm','tm'),('tutor','tutor')]:
   self.assertEqual(routes[route]['listed'],self.r.learnsets['이상해씨'][field])
   self.assertFalse(routes[route]['acquired_by_individual'])
   self.assertTrue(all(row['source']==field for row in routes[route]['resolved']))
  self.assertEqual(p.moves,before)
  self.assertTrue(set(p.moves)-{'struggle'}<={row['to'] for row in routes['level_up']['resolved'] if row.get('level',0)<=10})
  routes['egg']['listed'].clear();self.assertTrue(self.r.learnsets['이상해씨']['egg'])
 def test_actual_machine_learning_history_is_separate_from_template_and_durable(self):
  f=Fixtures.Tests();f.r=self.r;f.setUp()
  species=f.p.spec['species'];before=P.species_projection(self.r,species)['template_facts']['move_learning_routes']
  f.machine('TM35');f.act('teach_machine',target=f.p,instance_id='m')
  self.assertEqual(f.p.spec['move_learning']['move/화염방사']['method'],'tm')
  self.assertEqual(P.species_projection(self.r,species)['template_facts']['move_learning_routes'],before)
  e=Engine.import_state(self.r,f.e.export_state());p=next(c for c in e.everyone if c.entity_id==f.p.entity_id)
  self.assertEqual(p.spec['move_learning'],f.p.spec['move_learning'])
  self.assertIn('move/화염방사',p.moves)
 def test_species_skill_constants_and_porygon_extra_skill_use_independent_answers(self):
  for species,skill,dice,bonus,total in [('이상해씨','육상',3,2,8),('폴리곤','기술학',3,0,6),('폴리곤2','기술학',4,1,9),('폴리곤Z','기술학',5,3,13)]:
   with self.subTest(species=species):
    p=self.pokemon(species)
    view=P.species_projection(self.r,p.spec['species'])['template_facts']['species_skills'][skill]
    self.assertEqual((view['rank'],int(view['mod'])),(dice,bonus))
    roll=self.e.skill_roll(p,skill,fixed=[2]*dice)
    self.assertEqual((roll.rank,roll.modifier,roll.total),(dice,bonus,total))
    self.assertEqual(S.rank(self.r,p,skill)[2],dice)
  self.e.gm.snapshot('pools');self.e.gm.restore('pools')
  e,actors=self.loaded()
  for p in actors.values():
   if p.kind=='pokemon' and p.spec['species']=='pokemon/폴리곤2':self.assertEqual(e.skill_roll(p,'기술학',fixed=[2]*4).total,9)
 def test_explicit_numeric_skill_override_means_zero_constant_and_alias_conflicts_reject(self):
  p=self.pokemon('이상해씨');F.base_patch(p,{'skills':dict(p.spec['skills'],육상=3)},reason='GM explicit plain3d6 override')
  self.assertEqual(self.e.skill_roll(p,'육상',fixed=[2]*3).total,6)
  e,actors=self.loaded();self.assertEqual(e.skill_roll(actors[p.entity_id],'육상',fixed=[2]*3).total,6)
  p.spec['skills']['athletics']='3d6+2'
  with self.assertRaisesRegex(ValueError,'conflicting'):S.rank(self.r,p,'육상')
 def test_trainer_default_medium_has_native_one_cell_body_but_unknown_override_stays_unknown(self):
  self.assertEqual(self.t.spec['size'],'중형')
  self.assertEqual(BODY.cells(self.t,require_complete=True),{(1,1)})
  p=self.pokemon('이상해씨');self.assertIn((1,1),self.e.occupied(p))
  unknown=Combatant(self.r,B.build_trainer(self.r,'unknown',5,{s:5 for s in F.STATS},extra={'size':None}))
  self.assertFalse(BODY.projection(unknown)['geometry_complete'])
  e,actors=self.loaded();self.assertEqual(BODY.cells(actors[self.t.entity_id],require_complete=True),{(1,1)})
 def test_weight_exact_pound_boundaries_kg_and_source_gaps(self):
  for weight,wc in [(55,3),(110,3),(111,4),(220,4),(221,5)]:self.assertEqual(BODY.trainer_weight(weight)['weight_class'],wc)
  self.assertEqual(BODY.trainer_weight(90,unit='kg')['weight_class'],4)
  self.assertEqual(BODY.trainer_weight(100,unit='kg')['weight_class'],5)
  for weight,unit in [(54,'lb'),(110.5,'lb'),(50,'kg')]:self.assertEqual(BODY.trainer_weight(weight,unit=unit)['classification'],'source_unspecified')
  for invalid in (-1,True,float('inf'),'NaN','1e10000'):
   with self.assertRaises(ValueError):BODY.trainer_weight(invalid)
 def test_observed_weight_reaches_native_fall_grant_revoke_and_both_restores(self):
  self.e.gm.observe_trainer_weight(self.t,150,reason='GM measured150lb')
  self.assertEqual(self.t.weight_class,4)
  G.weight(self.t,-1,'fixture:weight',mode='add')
  self.e.gm.observe_trainer_weight(self.t,100,reason='GM corrected actual measurement')
  self.assertEqual((self.t.spec['weight_class'],self.t.weight_class),(3,2))
  self.e.gm.snapshot('weight');self.e.gm.observe_trainer_weight(self.t,230,reason='temporary body observation');self.e.gm.restore('weight')
  e,actors=self.loaded();t=actors[self.t.entity_id]
  self.assertEqual((t.spec['weight_class'],t.weight_class),(3,2))
  G.remove_owned(e,t,'fixture:weight');self.assertEqual(t.weight_class,3)
  result=e.falling_damage(t,meters=0,action_id='body-weight-proof',intentional=False,natural_sky=False,natural_sky_reason='trainer has no flight',reason='actual zero-distance landing')
  self.assertEqual(result['weight_class'],3)
  before=deepcopy(t.spec)
  with self.assertRaises(ValueError):e.gm.observe_trainer_weight(t,100,weight_class=5,reason='contradicts source')
  self.assertEqual(t.spec,before)
 def test_unspecified_weight_stores_unknown_or_explicit_gm_class_without_guessing(self):
  self.e.gm.observe_trainer_weight(self.t,110.5,reason='exact fractional observed weight')
  self.assertIsNone(self.t.weight_class)
  self.assertEqual(BODY.projection(self.t)['weight_observation']['classification'],'source_unspecified')
  self.e.gm.observe_trainer_weight(self.t,110.5,weight_class=4,reason='GM explicitly classifies fractional boundary')
  self.assertEqual((self.t.weight_class,BODY.projection(self.t)['weight_observation']['classification']),(4,'gm_explicit'))
  e,actors=self.loaded();self.assertEqual(actors[self.t.entity_id].weight_class,4)

if __name__=='__main__':unittest.main(verbosity=2)
