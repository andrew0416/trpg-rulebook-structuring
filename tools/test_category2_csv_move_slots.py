"""Three source variants reuse the native owned move-capacity consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from ruleset import RuleFilter
import items as I,move_state as M,state_grants as G,state_codec as C,world_entities as W

ROOT=Path(__file__).resolve().parents[1]
GUIDANCE='C2CSV/input/db/feats.csv:R107:main'
LIFELONG='C2CSV/input/db/feats.csv:R110:main'
FOILING='C2CSV/input/db/feats.csv:R265:main'
SIX=('몸통박치기','울음소리','덩굴채찍','씨뿌리기','잎날가르기','성장')

class CsvMoveSlotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')
 def setUp(self):self.fixture()
 def fixture(self,feats=(GUIDANCE,),moves=SIX):
  self.e=Engine(self.r,seed=973)
  self.t=Combatant(self.r,build_trainer(self.r,'Actual CSV Mentor',30,
   {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},extra={'feats':list(feats)}))
  self.e.gm.add_combatant(self.t,pos=(0,0),side='party',reason='actual acquired source owner')
  self.p=Combatant(self.r,build_pokemon(self.r,'이상해씨',50,moves=list(moves),
   abilities=[],extra={'trainer_id':self.t.entity_id}))
  self.e.gm.add_combatant(self.p,pos=(0,1),side='party',reason='actual current owned Pokemon')
 def register(self):return I.register_feats(self.e,self.t,pokemon=[self.p])
 def state(self):return deepcopy((self.t.spec,self.p.spec,self.p.moves,self.e.rng.getstate()))
 def select(self,move):
  return M.select_foiling(self.e,self.t,self.p,move,feature=FOILING,
   reason='GM observes completed Extended action and actual known Grass Status choice')
 def test_guidance_native_registration_seventh_move_only_once_and_atomic_last_source_loss(self):
  self.register();self.register()
  self.assertEqual(M.describe(self.r,self.p.spec)['total'],7)
  self.e.gm.set_move(self.p,'수면가루',reason='actual learned seventh natural move')
  self.assertEqual(M.describe(self.r,self.p.spec)['slot_count'],7)
  before=self.state()
  with self.assertRaises(ValueError):self.e.gm.set_move(self.p,'독가루',reason='eighth exceeds actual capacity')
  self.assertEqual(self.state(),before)
  source='feature:'+self.t.entity_id+':'+GUIDANCE
  with self.assertRaises(ValueError):G.revoke(self.p,source,engine=self.e)
  self.assertEqual(self.state(),before)
  self.e.gm.set_move(self.p,'수면가루',add=False,reason='explicit chosen forgotten move')
  G.revoke(self.p,source,engine=self.e)
  view=M.describe(self.r,self.p.spec);self.assertEqual((view['total'],view['slot_count']),(6,6))
 def test_lifelong_four_taught_moves_retains_total_channel_and_fifth_refuses(self):
  self.fixture((LIFELONG,),());self.register()
  for move in ('화염방사','열풍','10만볼트','냉동빔'):
   M.observe_learning(self.e,self.p,move,method='tutor',source='feat/기술-가르침',
    paid_tp=2,reason='actual completed paid Tutor lesson')
  view=M.describe(self.r,self.p.spec)
  self.assertEqual((view['taught'],view['taught_count'],view['total'],view['slot_count']),(4,4,6,4))
  before=self.state()
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):
   M.observe_learning(self.e,self.p,'물의파동',method='tutor',source='feat/기술-가르침',
    paid_tp=2,reason='fifth taught move exceeds its channel')
  self.assertEqual(self.state(),before)
 def test_foiling_replaces_only_one_known_grass_status_exemption(self):
  self.fixture((FOILING,));self.select('씨뿌리기')
  self.e.gm.set_move(self.p,'수면가루',reason='seventh learned natural move after exemption')
  self.select('수면가루');view=M.describe(self.r,self.p.spec)
  self.assertEqual((view['slot_count'],set(view['exempt'])),(6,{'move/수면가루'}))
  before=self.state()
  for invalid in ('몸통박치기','버섯포자'):
   with self.assertRaises(ValueError):self.select(invalid)
   self.assertEqual(self.state(),before)
 def test_csv_ownership_cannot_be_inferred_from_body_or_duplicate_representations(self):
  for csv,body in ((GUIDANCE,M.GUIDANCE),(LIFELONG,M.LIFELONG),(FOILING,M.FOILING)):
   for owned in ([],[body],[csv,csv],[csv,body]):
    self.fixture(());self.t.spec['feats']=owned;before=self.state()
    with self.assertRaises(ValueError):
     if csv==FOILING:self.select('씨뿌리기')
     else:M.register_passive_feature(self.e,self.t,csv,[self.p])
    self.assertEqual(self.state(),before)
 def test_foreign_target_and_unselected_or_changed_csv_sources_refuse_atomically(self):
  for csv in (GUIDANCE,LIFELONG,FOILING):
   self.fixture((csv,));self.p.spec['trainer_id']='another-actual-owner';before=self.state()
   with self.assertRaises(ValueError):
    if csv==FOILING:self.select('씨뿌리기')
    else:self.register()
   self.assertEqual(self.state(),before)
   self.fixture((csv,));before=self.state();old=self.r.ruleset
   self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[csv]});self.r._apply_ruleset()
   try:
    with self.assertRaises(ValueError):
     if csv==FOILING:self.select('씨뿌리기')
     else:self.register()
    self.assertEqual(self.state(),before)
   finally:self.r.ruleset=old;self.r._apply_ruleset()
   read=Path.read_bytes
   def changed(path):
    raw=read(path);return raw+b'changed' if path.name=='feats.csv' else raw
   with patch.object(Path,'read_bytes',changed):
    with self.assertRaises(ValueError):
     if csv==FOILING:self.select('씨뿌리기')
     else:self.register()
   self.assertEqual(self.state(),before)
 def test_combined_sources_json_restore_keep_independent_channels_and_exact_source_ids(self):
  self.fixture((GUIDANCE,LIFELONG,FOILING));self.register();self.select('씨뿌리기')
  M.observe_learning(self.e,self.p,'냉동빔',method='tutor',
   source='feat/기술-가르침',paid_tp=2,reason='observed completed teaching')
  expected=M.describe(self.r,self.p.spec);self.assertEqual((expected['total'],expected['taught'],expected['slot_count']),(7,4,6))
  self.assertEqual({r['rule_id'] for r in expected['sources']},{GUIDANCE,LIFELONG,FOILING})
  restored=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  pokemon=W.actor_index(restored)[self.p.entity_id]
  self.assertEqual(M.describe(self.r,pokemon.spec),expected)
  self.assertEqual(pokemon.moves,self.p.moves)

if __name__=='__main__':unittest.main()
