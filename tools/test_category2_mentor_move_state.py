"""Native teaching routes preserve exact natural/taught exception evidence."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import pokemon_teaching as T,move_state as M,state_codec as C,state_grants as G

class MentorMoveStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=946)
  self.a=Combatant(self.r,build_trainer(self.r,'Mentor',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[],extra={'skills':{'매력':5,'포켓몬학':3},'feats':[T.MENTOR,T.MOVE_TUTOR,T.EGG_TUTOR]}))
  self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual Mentor');T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='actual selected class skills')
 def pokemon(self,level=32):
  c=Combatant(self.r,build_pokemon(self.r,'브케인',level,moves=[],abilities=[],extra={'tutor_points':8}));self.e.gm.add_combatant(c,pos=(0,1),side='party',reason='actual non-owned teaching target');return c
 def teach(self,c,name,feature=T.MENTOR,**kw):return T.teach_feature(self.e,self.a,target=c,move_id=name,feature=feature,seconds=60,reason='GM observes one minute Extended activity',**kw)
 def before(self,c):return deepcopy((self.a.spec,c.spec,c.moves,self.e.elapsed_seconds,self.e.rng.getstate()))
 def test_mentor_sum_both_selected_ranks_and_natural_exception_roundtrip(self):
  c=self.pokemon();result=self.teach(c,'화염방사');self.assertEqual(result['classification'],'natural')
  self.assertEqual(c.spec['tutor_points'],7);self.assertEqual(self.e.elapsed_seconds,60)
  self.assertEqual(M.describe(self.r,c.spec)['taught_count'],0)
  self.assertEqual(c.spec['move_learning']['move/화염방사']['mentor_skill_ranks'],[5,3])
  restored=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)));q=next(x for x in restored.everyone if x.entity_id==c.entity_id)
  restored.gm.set_level(q,31,reason='observed lower current level retains natural Mentor receipt')
  self.assertEqual(M.describe(self.r,q.spec)['classifications']['move/화염방사'],'natural')
 def test_mentor_out_of_allowance_rejects_before_tp_time_frequency_and_retry(self):
  c=self.pokemon(31);before=self.before(c)
  with self.assertRaisesRegex(ValueError,'allowance'):self.teach(c,'화염방사')
  self.assertEqual(self.before(c),before)
  self.e.gm.set_level(c,32,reason='actual level observation creates eligibility');self.teach(c,'화염방사')
  self.assertEqual(c.spec['tutor_points'],7)
 def test_move_tutor_other_owner_is_valid_and_counts_taught_daily_once(self):
  c=self.pokemon(30);result=self.teach(c,'열풍',T.MOVE_TUTOR)
  self.assertEqual(result['classification'],'taught');self.assertEqual(c.spec['tutor_points'],6)
  before=self.before(c)
  with self.assertRaisesRegex(ValueError,'daily frequency'):self.teach(c,'누르기',T.MOVE_TUTOR)
  self.assertEqual(self.before(c),before)
 def test_egg_tutor_natural_once_even_after_forgotten_and_new_day(self):
  import frequency as F
  c=self.pokemon(5);result=self.teach(c,'두번차기',T.EGG_TUTOR)
  self.assertEqual(result['classification'],'natural');self.assertEqual(c.spec['tutor_points'],6)
  self.assertEqual((result['point_cost'],self.e.elapsed_seconds),(2,60))
  self.e.gm.set_move(c,'move/두번차기',add=False,reason='actual chosen forgetting');F.new_day(self.a);F.new_day(c)
  before=self.before(c)
  with self.assertRaisesRegex(ValueError,'only once'):self.teach(c,'탐내기',T.EGG_TUTOR)
  self.assertEqual(self.before(c),before)
  loaded=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)));actors={a.entity_id:a for a in loaded.everyone}
  teacher=actors[self.a.entity_id];pupil=actors[c.entity_id]
  self.assertEqual(pupil.spec['egg_tutor_history'],c.spec['egg_tutor_history'])
  before=deepcopy((teacher.spec,pupil.spec,loaded.elapsed_seconds,loaded.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'only once'):T.teach_feature(loaded,teacher,target=pupil,move_id='탐내기',feature=T.EGG_TUTOR,seconds=60,reason='same actual pupil after restore')
  self.assertEqual((teacher.spec,pupil.spec,loaded.elapsed_seconds,loaded.rng.getstate()),before);self.assertTrue(loaded.validate_state()['valid'])
 def test_actual_evolution_preserves_early_natural_receipt_identity_and_runtime_sources(self):
  import downtime as D
  c=self.pokemon();self.teach(c,'화염방사');identity=c.entity_id;spec_alias=c.spec
  G._source(c,'actual-boost','effect');G.stat(c,'atk',2,'actual-boost')
  G.numeric(c,'movement',2,'actual-boost')
  old_skill=deepcopy(c.spec['skills']);result=D.evolve_combatant(self.e,c,'마그케인')
  self.assertTrue(result['evolved']);self.assertEqual(c.entity_id,identity);self.assertIs(c.spec,spec_alias)
  self.assertEqual(c.stats['atk'],c.spec['stats']['atk']+2);self.assertEqual(c.movement,c.spec['movement']['land']+2)
  self.assertEqual(c.spec['skills'],old_skill);self.assertEqual(M.describe(self.r,c.spec)['classifications']['move/화염방사'],'natural')
  self.assertEqual(c.spec['move_learning']['move/화염방사']['species_id'],'pokemon/브케인')
  self.assertEqual(c.spec['stat_history'][-1]['event'],'evolution')
  G.revoke(c,'actual-boost',engine=self.e)
  self.assertEqual(c.stats['atk'],c.spec['stats']['atk']);self.assertEqual(c.movement,c.spec['movement']['land'])
 def test_forged_mentor_natural_receipt_is_rejected_by_world_and_export(self):
  c=self.pokemon();self.teach(c,'화염방사')
  c.spec['move_learning']['move/화염방사']['mentor_skill_ranks']=[3,3]
  with self.assertRaisesRegex(ValueError,'allowance'):M.validate_actor(c)
  with self.assertRaises(ValueError):C.dump_engine(self.e)

if __name__=='__main__':unittest.main()
