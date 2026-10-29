"""Category 2 completion checks for ch03:897-901 PokéManiac."""
from copy import deepcopy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))

from engine import Combatant,Engine,Rules
import common_checks as CHECKS
import pokemon_activities as ACTIVITIES
import world_entities as WORLD


SOURCE='input/ch03-skills-edges-feats.md:897-901'
FEATURE='feat/포켓몬매니아'


class PokemaniacTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(str(ROOT),ruleset='core')

 def setUp(self):
  self.e=Engine(self.rules,seed=897)
  self.trainer=self.actor('trainer','trainer')
  self.target=self.actor('target','pokemon')
  self.target.level=23;self.target.types=['풀','독'];self.target.abilities=['엽록소'];self.target.spec['nature']='대담'
  self.e.gm.everyone=[self.trainer,self.target]
  self.trainer.spec['feats'].append(FEATURE)
  self.trainer.spec['skills']['포켓몬학']='숙련'
  self.trainer.budget={'standard':1,'shift':1,'swift':1}

 def actor(self,name,kind):
  return Combatant(self.rules,{'id':kind+'/'+name,'name':name,'kind':kind,'level':20,'pos':(0,0),
   'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
   'skills':{'포켓몬학':'숙련'},'items':{},'edges':[],'feats':[]})

 def state(self,e=None):
  e=e or self.e
  actors=WORLD.actor_index(e);trainer=actors[self.trainer.entity_id];target=actors[self.target.entity_id]
  return deepcopy((e.rng.getstate(),e.elapsed_seconds,trainer.spec,target.spec,getattr(trainer,'budget',None),
   getattr(trainer,'took_standard',False),getattr(trainer,'_action_history',[])))

 def use(self,**options):
  return self.e.pokemon_activity(self.trainer,'pokemaniac',target=self.target,**options)

 def test_source_clause_and_selected_definition_are_exact(self):
  entries=json.loads((ROOT/'data/verification/category2-class-clause-status.json').read_text(encoding='utf-8'))['entries']
  entry=next(row for row in entries if row['source_clause_id']==SOURCE)
  self.assertEqual(entry['source_clause_id'],SOURCE)
  anchor=entry['anchors'][0]
  actual='\n'.join((ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines()[anchor['start']-1:anchor['end']])
  self.assertEqual(actual,anchor['excerpt'])
  self.assertEqual(self.rules._selected_rule(FEATURE),FEATURE)

 def test_requires_actual_acquisition_and_trained_pokemon_education(self):
  self.trainer.spec['feats'].clear();before=self.state()
  with self.assertRaisesRegex(ValueError,'acquired feature'):self.use(fixed=[6,6,6,6])
  self.assertEqual(self.state(),before)
  self.trainer.spec['feats'].append(FEATURE);self.trainer.spec['skills']['포켓몬학']='초보';before=self.state()
  with self.assertRaisesRegex(ValueError,'prerequisite'):self.use(fixed=[6,6,6])
  self.assertEqual(self.state(),before)

 def test_requires_actual_registered_pokemon_and_selected_source(self):
  foreign=self.actor('foreign','pokemon');foreign.spec['nature']='차분';before=self.state()
  with self.assertRaisesRegex(ValueError,'actual registered'):self.e.pokemon_activity(self.trainer,'pokemaniac',target=foreign,fixed=[6,6,6,6])
  self.assertEqual(self.state(),before)
  before=self.state()
  with self.assertRaisesRegex(ValueError,'Pokemon target'):self.e.pokemon_activity(self.trainer,'pokemaniac',target=self.trainer,fixed=[6,6,6,6])
  self.assertEqual(self.state(),before)
  selected=self.rules._selected_rule
  with patch.object(self.rules,'_selected_rule',side_effect=lambda uid,*args,**options:uid+'@other' if uid==FEATURE else selected(uid,*args,**options)):
   before=self.state()
   with self.assertRaisesRegex(ValueError,'selected feature version'):self.use(fixed=[6,6,6,6])
   self.assertEqual(self.state(),before)

 def test_dc10_success_discloses_exactly_four_fields_and_spends_standard(self):
  result=self.use(fixed=[2,2,3,3])
  self.assertTrue(result['check'].passed);self.assertEqual(result['check'].dc,10)
  self.assertEqual(result['information'],{'level':23,'types':['풀','독'],'nature':'대담','abilities':['엽록소']})
  self.assertEqual(self.trainer.budget['standard'],0);self.assertTrue(self.trainer.took_standard)

 def test_failed_check_discloses_nothing_but_still_spends_standard(self):
  rng=self.e.rng.getstate();result=self.use(fixed=[1,1,1,1])
  self.assertFalse(result['check'].passed);self.assertIsNone(result['information'])
  self.assertEqual(self.trainer.budget['standard'],0);self.assertEqual(self.e.rng.getstate(),rng)

 def test_unavailable_action_and_missing_information_are_atomic(self):
  self.trainer.budget['standard']=0;before=self.state()
  result=self.use()
  self.assertIsInstance(result,CHECKS.PendingDecision);self.assertEqual(self.state(),before)
  self.trainer.budget['standard']=1;self.target.spec.pop('nature');before=self.state()
  result=self.use()
  self.assertIsInstance(result,CHECKS.PendingDecision);self.assertEqual(self.state(),before)

 def test_late_roll_failure_restores_action_rng_and_world(self):
  original=Engine.skill_roll
  def fail_after_roll(engine,*args,**options):
   original(engine,*args,**options);engine.rng.random();raise RuntimeError('late Pokemon knowledge failure')
  before=self.state()
  with patch.object(Engine,'skill_roll',fail_after_roll):
   with self.assertRaisesRegex(RuntimeError,'late Pokemon knowledge failure'):self.use(fixed=[2,2,3,3])
  self.assertEqual(self.state(),before)

 def test_gm_and_json_restore_keep_spent_standard_action(self):
  self.use(fixed=[2,2,3,3]);self.e.gm.snapshot('spent')
  self.trainer.budget['standard']=1;self.e.gm.restore('spent')
  restored=WORLD.actor_index(self.e)[self.trainer.entity_id]
  self.assertEqual(restored.budget['standard'],0);before=self.state()
  self.assertIsInstance(self.e.pokemon_activity(restored,'pokemaniac',target=WORLD.actor_index(self.e)[self.target.entity_id]),CHECKS.PendingDecision)
  self.assertEqual(self.state(),before)
  loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  actors=WORLD.actor_index(loaded);trainer=actors[self.trainer.entity_id];target=actors[self.target.entity_id]
  self.assertEqual(trainer.budget['standard'],0);before=self.state(loaded)
  self.assertIsInstance(loaded.pokemon_activity(trainer,'pokemaniac',target=target),CHECKS.PendingDecision)
  self.assertEqual(self.state(loaded),before);self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state()['issues'])


if __name__=='__main__':unittest.main(verbosity=2)
