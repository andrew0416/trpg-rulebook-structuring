"""Actual Ability Mastery acquisition, source effects, refunds and persistence."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import unittest
import test_category2_progression_state as _fixture_test_category2_progression_state
from engine import Rules
from builder import build_pokemon
import ability_mastery as A,state_grants as G,downtime as D
from state_codec import dump_engine,load_engine

class AbilityMasteryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(Path(__file__).resolve().parents[1],ruleset='all')
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon()
 def pokemon(self,level=60,species='잉어킹',abilities=None):
  return self.add(build_pokemon(self.r,species,level,moves=[],abilities=abilities or [],extra={'trainer_id':self.a.entity_id,'tutor_points':12}))
 def teach(self,ability='단순',**kw):
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=A.SOURCE,ability=ability,safe=True,**kw)
 def test_actual_entry_uses_owned_grant_hour_and_live_ability_effect(self):
  before=self.e.elapsed_seconds
  with patch.object(G,'grant',wraps=G.grant) as shared:out=self.teach()
  self.assertTrue(any(c.args[1]=='abilities' and c.kwargs.get('rule_id')==A.SOURCE for c in shared.call_args_list))
  self.assertEqual((out['point_cost'],out['definition_origin']['record'],self.p.spec['tutor_points'],self.e.elapsed_seconds-before),(3,28,9,3600))
  self.assertEqual(self.p.spec['abilities'],[]);self.assertIn('단순',self.p.abilities)
  self.assertIn('단순',self.p.spec[G.KEY]['ability_receipts'])
  self.e.change_stage(self.p,'atk',1);self.assertEqual(self.p.stages['atk'],2)
 def test_qualification_cost_owner_and_explicit_choice_fail_atomically(self):
  for kind in ('level','cost','owner','outside','missing','choice_field'):
   self.setUp()
   if kind=='level':self.p=self.pokemon(level=59)
   elif kind=='cost':self.p.spec['tutor_points']=2
   elif kind=='owner':self.p.spec['trainer_id']=self.p.entity_id
   before=self.snap()
   with self.assertRaises(ValueError):
    if kind=='outside':self.teach('심록')
    elif kind=='missing':self.teach(None)
    elif kind=='choice_field':self.teach(stat='atk')
    else:self.teach()
   self.assertEqual(self.snap(),before)
 def test_own_species_basic_hidden_and_high_ability_pools(self):
  for species,pool,ability in [('잉어킹','기본 특성','단순'),('잉어킹','숨겨진 특성','디코이'),('파이리','대단한 특성','회피')]:
   self.setUp();self.p=self.pokemon(species=species)
   self.assertIn(ability,self.r.learnsets[species]['abilities'][pool])
   out=self.teach(ability);self.assertIn(out['ability'],A.candidates(self.r,self.p.spec))
 def test_duplicate_ability_and_duplicate_edge_do_not_charge(self):
  self.p=self.pokemon(abilities=['단순']);before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
  self.setUp();self.teach();before=self.snap()
  with self.assertRaises(ValueError):self.teach('쓱쓱')
  self.assertEqual(self.snap(),before)
 def test_native_level_loss_removes_only_its_grant_and_refunds_once(self):
  self.teach();self.e.gm.set_level(self.p,59,reason='actual correction below prerequisite')
  row=A.records(self.p.spec)[0]
  self.assertEqual((row['status'],self.p.spec['tutor_points']),('refunded',12))
  self.assertNotIn('단순',self.p.abilities);self.assertNotIn(row['grant_source'],self.p.spec[G.KEY]['sources'])
  self.e.change_stage(self.p,'atk',1);self.assertEqual(self.p.stages['atk'],1)
  self.e.gm.set_level(self.p,58,reason='still below prerequisite')
  self.assertEqual(self.p.spec['tutor_points'],12)
  self.restored()
 def test_independent_permanent_ability_remains_after_edge_withdrawal(self):
  self.teach();G.replace_baseline(self.e,self.p,'abilities',['단순'])
  self.e.gm.set_level(self.p,59,reason='actual level loss after independent acquisition')
  self.assertIn('단순',self.p.abilities);self.assertIn('단순',self.p.spec[G.KEY]['ability_receipts'])
  self.e.change_stage(self.p,'atk',1);self.assertEqual(self.p.stages['atk'],2)
 def test_reacquisition_after_real_refund_has_new_source_and_no_old_effects(self):
  self.teach();first=A.records(self.p.spec)[0]['grant_source']
  self.e.gm.set_level(self.p,59,reason='prerequisite loss')
  self.e.gm.set_level(self.p,60,reason='actual restored qualification')
  self.teach('디코이');rows=A.records(self.p.spec)
  self.assertNotEqual(rows[-1]['grant_source'],first)
  self.assertEqual((len(rows),self.p.spec['tutor_points']),(2,9));self.assertNotIn('단순',self.p.abilities)
 def test_native_evolution_uses_same_slot_mapping_for_owned_and_baseline_abilities(self):
  self.teach('방탄');out=D.evolve_combatant(self.e,self.p,'갸라도스')
  self.assertTrue(out['evolved']);row=A.records(self.p.spec)[0]
  self.assertEqual(row['current_ability'],'ability/위협')
  self.assertIn('위협',self.p.abilities);self.assertNotIn('방탄',self.p.abilities)
  self.assertEqual(self.p.spec['abilities'],[]);self.assertEqual(len(row['ability_evolutions']),1)
  loaded=self.restored();target=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id)
  self.assertIn('위협',target.abilities)
  self.e.gm.set_level(self.p,59,reason='post-evolution prerequisite loss')
  self.assertNotIn('위협',self.p.abilities);self.assertEqual(self.p.spec['tutor_points'],12)
 def test_json_and_gm_restore_preserve_one_owned_ability_and_no_extra_payment(self):
  self.teach();before=dump_engine(self.e);loaded=load_engine(self.r,deepcopy(before))
  target=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual((target.abilities.count('단순'),target.spec['tutor_points']),(1,9))
  snapshot=self.e.gm.snapshot('ability-mastery')
  self.e.gm.restore(snapshot)
  self.assertEqual((self.p.abilities.count('단순'),self.p.spec['tutor_points']),(1,9))
 def test_late_registration_failure_rolls_back_world_clock_points_and_receipts(self):
  before=self.snap();native=G.ensure_ability
  def fail(e,c,name):
   result=native(e,c,name)
   if name=='단순':raise ValueError('late native Ability registration failure')
   return result
  with patch.object(G,'ensure_ability',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late native Ability'):self.teach()
  self.assertEqual(self.snap(),before)
 def test_tampered_cost_choice_or_grant_cannot_save(self):
  for field,value in [('point_cost',1),('ability','ability/심록'),('current_ability','ability/쓱쓱'),('grant_source','invented')]:
   self.setUp();self.teach();A.records(self.p.spec)[0][field]=value
   with self.assertRaises(ValueError):dump_engine(self.e)
 def test_missing_acquisition_or_mutated_owned_grant_cannot_save(self):
  for kind in ('receipt','grant'):
   self.setUp();self.teach();row=A.records(self.p.spec)[0]
   if kind=='receipt':self.p.spec['learned_poke_edges']=[]
   else:self.p.spec[G.KEY]['sources'][row['grant_source']]['grants']['abilities']=['심록']
   with self.assertRaises(ValueError):dump_engine(self.e)
 def test_unresolved_species_ability_does_not_silently_pick_a_variant(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.teach('쓱쓱')
  self.assertEqual(self.snap(),before)
 def test_external_json_choice_executes_native_acquisition_and_replays_after_restore(self):
  path='input/'+self.r.selection.units[A.SOURCE]['source']['file']
  document={'schema':1,'id':'ability-mastery-author','variants':[{'rule_id':A.SOURCE,
   'source':{'file':path,'sha256':sha256((Path(self.r.root)/path).read_bytes()).hexdigest()},
   'inputs':{'chosen':{'type':'string','authority':'context','question':'Actual natural Ability choice'}},
   'values':{'teaching_operation':{'kind':'edge','edge':A.SOURCE,'safe':True,'ability':{'$input':'chosen'}}}}]}
  args={'context':{'chosen':'단순'},'request_id':'ability-mastery/native'}
  out=self.e.execute_source_policy_teaching(self.a,self.p,document,**args)
  self.assertEqual(out['status'],'PolicyTeachingCompleted');self.assertFalse(out['replayed'])
  loaded=self.restored();teacher=next(c for c in loaded.everyone if c.entity_id==self.a.entity_id);target=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id)
  before=dump_engine(loaded);again=loaded.execute_source_policy_teaching(teacher,target,document,**args)
  self.assertTrue(again['replayed']);self.assertEqual(dump_engine(loaded),before)

if __name__=='__main__':unittest.main()
