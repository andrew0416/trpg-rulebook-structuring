"""Teaching consumes actual world state, never detached or foreign sheets."""
from copy import copy,deepcopy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Combatant
from builder import build_pokemon
import test_category2_progression_state as fixtures
import pokemon_teaching as T

class TeachingParticipantsTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 setUp=fixtures.ProgressionStateTests.setUp
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 def pokemon(self,register=True):
  spec=build_pokemon(self.r,'근육몬',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6})
  return self.add(spec) if register else Combatant(self.r,spec)
 def teach(self,actor,target):
  return T.teach_edge(self.e,actor,target=target,edge=T.EDGE,skill='육상',safe=True)
 def test_detached_target_rejected_without_time_points_or_sheet_changes(self):
  target=self.pokemon(False);before=self.snap();sheet=deepcopy(target.spec)
  with self.assertRaisesRegex(ValueError,'actual registered'):self.teach(self.a,target)
  self.assertEqual(before,self.snap());self.assertEqual(sheet,target.spec)
 def test_detached_teacher_cannot_supply_owner_identity(self):
  target=self.pokemon();spec=deepcopy(self.a.spec);spec['id']='detached-teacher'
  teacher=Combatant(self.r,spec);target.spec['trainer_id']=teacher.entity_id
  before=self.snap();sheet=deepcopy(teacher.spec)
  with self.assertRaisesRegex(ValueError,'actual registered'):self.teach(teacher,target)
  self.assertEqual(before,self.snap());self.assertEqual(sheet,teacher.spec)
 def test_registered_foreign_rule_object_rejected_before_learning(self):
  target=self.pokemon();before=self.snap();target.r=copy(self.r)
  try:
   with self.assertRaisesRegex(ValueError,'actual registered'):self.teach(self.a,target)
  finally:target.r=self.r
  self.assertEqual(before,self.snap())
 def test_setup_on_detached_teacher_does_not_create_machine_or_skill_choices(self):
  spec=deepcopy(self.a.spec);spec.update(id='detached',feats=[T.MENTOR],skills={'매력':3,'포켓몬학':3},items={'TM35':1})
  teacher=Combatant(self.r,spec);before=self.snap();sheet=deepcopy(teacher.spec)
  with self.assertRaisesRegex(ValueError,'actual registered'):
   T.register_machine(self.e,teacher,instance_id='machine',code='TM35')
  with self.assertRaisesRegex(ValueError,'actual registered'):
   T.select_mentor_skills(self.e,teacher,['매력','포켓몬학'],reason='observed choice')
  self.assertEqual(before,self.snap());self.assertEqual(sheet,teacher.spec)
 def test_machine_cannot_spend_inventory_on_detached_target(self):
  self.a.spec['items']['TM35']=1;T.register_machine(self.e,self.a,instance_id='machine',code='TM35')
  target=Combatant(self.r,build_pokemon(self.r,'브케인',32,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':6}))
  before=self.snap();sheet=deepcopy(target.spec)
  with self.assertRaisesRegex(ValueError,'actual registered'):
   T.teach_machine(self.e,self.a,target=target,instance_id='machine')
  self.assertEqual(before,self.snap());self.assertEqual(sheet,target.spec)
 def test_mentor_cannot_spend_frequency_on_detached_nonowned_target(self):
  self.a.spec.update(feats=[T.MENTOR],skills={'매력':5,'포켓몬학':3})
  T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='observed choice')
  target=Combatant(self.r,build_pokemon(self.r,'브케인',32,moves=[],abilities=[],extra={'tutor_points':6}))
  before=self.snap();sheet=deepcopy(target.spec)
  with self.assertRaisesRegex(ValueError,'actual registered'):
   T.teach_feature(self.e,self.a,target=target,move_id='화염방사',feature=T.MENTOR,seconds=60,reason='observed duration')
  self.assertEqual(before,self.snap());self.assertEqual(sheet,target.spec)
 def test_off_field_live_teacher_is_still_an_actual_participant(self):
  target=self.pokemon();self.e.everyone=self.e.gm.everyone=[target];self.e._time_actors=[self.a]
  self.teach(self.a,target)
  self.assertEqual(target.spec['tutor_points'],5);self.assertEqual(self.e.elapsed_seconds,3600)
 def test_registered_pair_still_teaches_through_native_transaction(self):
  target=self.pokemon();out=self.teach(self.a,target)
  self.assertEqual(out['point_cost'],1);self.assertEqual(target.spec['tutor_points'],5)
  self.assertEqual(self.e.elapsed_seconds,3600)

if __name__=='__main__':unittest.main()
