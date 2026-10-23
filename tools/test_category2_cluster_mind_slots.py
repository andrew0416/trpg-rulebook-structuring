"""Cluster Mind reuses actual learned-move capacity, payment and withdrawal."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import move_state as M,state_grants as G,state_codec as C,world_entities as W
import pokemon_teaching as T,frequency as F,items as I

SOURCE='ability/클러스터마인드'
GUIDANCE='C2CSV/input/db/feats.csv:R107:main'

class ClusterMindSlotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def setUp(self):
  self.e=Engine(self.r,seed=1403)
  self.c=Combatant(self.r,build_pokemon(self.r,'브케인',50,moves=[],abilities=[],extra={'tutor_points':8}))
  self.e.gm.add_combatant(self.c,pos=(0,1),side='party',reason='actual current learner')
  self.natural=sorted(M.natural_moves(self.r,self.c.spec));self.assertGreaterEqual(len(self.natural),10)
 def state(self):return deepcopy((self.c.spec,self.c.moves,self.c.abilities,self.e.elapsed_seconds,self.e.rng.getstate()))
 def learn(self,names):
  for mid in names:self.e.gm.set_move(self.c,mid,reason='observed actual natural learning')
 def test_native_acquisition_adds_two_total_slots_once_without_auto_learning(self):
  self.learn(self.natural[:6]);before=self.state()
  with self.assertRaisesRegex(ValueError,'exceed sourced capacity'):self.learn(self.natural[6:7])
  self.assertEqual(self.state(),before)
  for name in ('클러스터마인드',SOURCE,'Cluster Mind'):
   self.e.gm.set_ability(self.c,name,reason='actual acquired exact ability or equivalent spelling')
  view=M.describe(self.r,self.c.spec)
  self.assertEqual((view['total'],view['taught'],view['slot_count']),(8,3,6))
  self.assertEqual([s['rule_id'] for s in view['sources']].count(SOURCE),1)
  self.learn(self.natural[6:8]);before=self.state()
  with self.assertRaisesRegex(ValueError,'exceed sourced capacity'):self.learn(self.natural[8:9])
  self.assertEqual(self.state(),before);self.assertTrue(self.e.validate_state()['valid'])
 def test_native_fourth_tutor_is_still_rejected_before_time_tp_and_daily_use(self):
  teacher=Combatant(self.r,build_trainer(self.r,'Actual Cluster Tutor',20,
   {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[],
   extra={'skills':{'매력':5,'포켓몬학':3},'feats':[T.MENTOR,T.MOVE_TUTOR]}))
  self.e.gm.add_combatant(teacher,pos=(0,0),side='party',reason='actual acquired Tutor')
  T.select_mentor_skills(self.e,teacher,['매력','포켓몬학'],reason='actual selected Mentor skills')
  self.e.gm.set_ability(self.c,SOURCE,reason='actual Cluster Mind ownership')
  def teach(name):return T.teach_feature(self.e,teacher,target=self.c,move_id=name,
   feature=T.MOVE_TUTOR,seconds=60,reason='actual completed paid one-minute lesson')
  for name in ('누르기','열풍','진흙뿌리기'):
   self.assertEqual(teach(name)['classification'],'taught');F.new_day(teacher);F.new_day(self.c)
  self.assertEqual((self.c.spec['tutor_points'],self.e.elapsed_seconds),(2,180))
  before=deepcopy((teacher.spec,self.state()))
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):teach('잠꼬대')
  self.assertEqual((teacher.spec,self.state()),before)
  self.assertEqual((M.describe(self.r,self.c.spec)['total'],M.describe(self.r,self.c.spec)['taught_count']),(8,3))
 def test_last_owned_source_requires_explicit_forgetting_and_suppression_keeps_learning(self):
  self.e.gm.set_ability(self.c,SOURCE,reason='actual permanent ability');self.learn(self.natural[:8])
  G.grant(self.c,'abilities','클러스터마인드','independent:cluster','fixture');G.reconcile(self.e,self.c)
  self.e.gm.set_ability(self.c,SOURCE,add=False,reason='one actual owner ends, independent owner remains')
  self.c.abilities_suppressed=True;G.reconcile(self.e,self.c)
  view=M.describe(self.r,self.c.spec)
  self.assertEqual((view['total'],view['slot_count']),(8,8));self.assertIn('struggle',self.c.moves)
  self.c.abilities_suppressed=False;before=self.state()
  with self.assertRaisesRegex(ValueError,'explicit forgotten-move'):G.revoke(self.c,'independent:cluster',engine=self.e)
  self.assertEqual(self.state(),before)
  for mid in self.natural[6:8]:self.e.gm.set_move(self.c,mid,add=False,reason='explicit chosen forgotten natural move')
  G.revoke(self.c,'independent:cluster',engine=self.e)
  view=M.describe(self.r,self.c.spec);self.assertEqual((view['total'],view['slot_count']),(6,6))
  self.assertEqual(set(view['known']),set(self.natural[:6]));self.assertIn('struggle',self.c.moves)
  self.assertTrue(self.e.validate_state()['valid'])
 def test_guidance_composes_ninth_slot_and_both_restores_keep_actual_sources(self):
  owner=Combatant(self.r,build_trainer(self.r,'Actual Guidance Owner',30,
   {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},extra={'feats':[GUIDANCE]}))
  self.e.gm.add_combatant(owner,pos=(0,0),side='party',reason='actual acquired Guidance')
  self.c.spec['trainer_id']=owner.entity_id
  self.e.gm.set_ability(self.c,SOURCE,reason='actual independently acquired Cluster Mind')
  I.register_feats(self.e,owner,pokemon=[self.c]);I.register_feats(self.e,owner,pokemon=[self.c]);self.learn(self.natural[:9])
  expected=M.describe(self.r,self.c.spec);self.assertEqual((expected['total'],expected['taught'],expected['slot_count']),(9,3,9))
  self.assertEqual({s['rule_id'] for s in expected['sources']},{GUIDANCE,SOURCE})
  snap=self.e.gm.snapshot();self.e.gm.set_move(self.c,self.natural[8],add=False,reason='actual later forgetting')
  self.e.gm.restore(snap)
  self.e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  self.c=W.actor_index(self.e)[self.c.entity_id]
  self.assertEqual(M.describe(self.r,self.c.spec),expected);before=self.state()
  with self.assertRaisesRegex(ValueError,'exceed sourced capacity'):self.learn(self.natural[9:10])
  self.assertEqual(self.state(),before)
  with self.assertRaisesRegex(ValueError,'explicit forgotten-move'):self.e.gm.set_ability(self.c,SOURCE,add=False,reason='last actual ability owner ends')
  self.assertEqual(self.state(),before);self.assertTrue(self.e.validate_state()['valid'])
 def test_changed_or_unselected_source_refuses_before_actual_state_changes(self):
  before=self.state();selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:SOURCE+'-unreviewed' if uid==SOURCE else selected(uid)):
   with self.assertRaisesRegex(ValueError,'own source policy'):self.e.gm.set_ability(self.c,SOURCE,reason='unreviewed selected version')
  self.assertEqual(self.state(),before)
  read=Path.read_bytes
  def changed(path):
   raw=read(path);return raw+b'changed' if path.name=='abilities.csv' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.e.gm.set_ability(self.c,SOURCE,reason='changed original source is not silently accepted')
  self.assertEqual(self.state(),before)

if __name__=='__main__':unittest.main()
