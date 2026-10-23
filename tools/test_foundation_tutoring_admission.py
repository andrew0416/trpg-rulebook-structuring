"""Selected tutoring errata at actual acquisition, before every native cost."""
from pathlib import Path
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_mentor_move_state as fixture
import pokemon_teaching as T,move_state as M,state_codec as C

class TutoringAdmissionTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MentorMoveStateTests.setUpClass.__func__)
 setUp=fixture.MentorMoveStateTests.setUp
 pokemon=fixture.MentorMoveStateTests.pokemon
 teach=fixture.MentorMoveStateTests.teach
 def attempt(self,level,name,allowed):
  self.setUp();pokemon=self.pokemon(level);before=C.dump_engine(self.e)
  if not allowed:
   with self.assertRaisesRegex(ValueError,'tutoring restriction'):self.teach(pokemon,name,T.MOVE_TUTOR)
   self.assertEqual(C.dump_engine(self.e),before)
  else:
   result=self.teach(pokemon,name,T.MOVE_TUTOR)
   self.assertEqual((result['point_cost'],pokemon.spec['tutor_points'],self.e.elapsed_seconds),(2,6,60))
   self.assertIn(self.r.move_id(name),pokemon.moves)
  return pokemon
 def test_under_twenty_accepts_db6_at_will_and_eot_but_rejects_scene(self):
  for name,allowed in [('탐내기',True),('코골기',True),('누르기',False),('불꽃의맹세',False)]:
   with self.subTest(name=name):self.attempt(19,name,allowed)
 def test_twenty_to_twenty_nine_accepts_scene_db9_but_not_db10(self):
  for level in (20,29):
   for name,allowed in [('누르기',True),('열풍',False),('탐내기',True)]:
    with self.subTest(level=level,name=name):self.attempt(level,name,allowed)
 def test_thirty_removes_errata_limit_without_removing_tutor_cost(self):
  self.attempt(30,'열풍',True)
 def test_status_move_has_no_damage_base_but_keeps_frequency_gate(self):
  self.attempt(19,'잠꼬대',False);self.attempt(20,'잠꼬대',True)
 def test_egg_tutor_uses_same_admission_and_retains_natural_route(self):
  pokemon=self.pokemon(5);result=self.teach(pokemon,'두번차기',T.EGG_TUTOR)
  self.assertEqual(result['classification'],'natural')
  self.assertEqual(pokemon.spec['move_learning']['move/두번차기']['tutoring_admission']['damage_base'],3)
 def test_restore_uses_learning_level_not_current_level_and_rejects_forged_proof(self):
  pokemon=self.attempt(30,'열풍',True)
  loaded=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  restored=next(a for a in loaded.everyone if a.entity_id==pokemon.entity_id)
  loaded.gm.set_level(restored,19,reason='later level correction does not re-teach a move')
  M.validate_actor(restored)
  restored.spec['move_learning']['move/열풍']['tutoring_admission']['damage_base']=6
  with self.assertRaisesRegex(ValueError,'tutoring admission'):C.dump_engine(loaded)

if __name__=='__main__':unittest.main()
