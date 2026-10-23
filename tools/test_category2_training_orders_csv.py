"""Direct contract checks for feats.csv R14-R17 Training Orders."""
from copy import deepcopy
from pathlib import Path
import hashlib, json, os, sys, unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('PTK_CANONICAL_ROOT',STAGE))
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine')]

from engine import Rules,Engine,Combatant
# engine.py gives its canonical directory import priority.  Restore the partial
# overlay before loading the three staged modules under direct test.
sys.path.insert(0,str(STAGE/'engine'))
for _module in ('training_features','training_rewards','priority_limited','action_resources'):
 sys.modules.pop(_module,None)
import training_features as T
import items as ITEMS
import pokemon_entities as ENTITIES
import initiative as INIT
import effects_ext as EXT
import priority_limited as PRIORITY
import combat_timing as TIMING


CLAUSES={
 T.AGILITY:('C2CSV/input/db/feats.csv:R14:main','1ea0969df4c848bab6e7903e9896732dd1faa366630195872d54f2e284069833'),
 T.BRUTAL:('C2CSV/input/db/feats.csv:R15:main','83c421d0722a8664ccfcf027dccda5eef5cc98511f71e68b092dcc93ae4d28ec'),
 T.FOCUSED:('C2CSV/input/db/feats.csv:R16:main','ec3e69b742d57f29aec7faa451d3f15cb1af8a3dbbcbee5acff583d7c3385fd4'),
 T.INSPIRED:('C2CSV/input/db/feats.csv:R17:main','ceb571a811658fda314f712a4740b608b73616bc4d9d77f5b8cdaef7b35cee59'),
}


class TrainingOrdersCSVTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def fixture(self):
  e=Engine(self.r,seed=814);common=dict(level=20,stats={'hp':60,'atk':20,'def':15,'spa':20,'spd':15,'spe':10},movement={'land':6,'swim':3,'sky':0},pos=(0,0))
  t=Combatant(self.r,dict(common,name='trainer',kind='trainer',feats=list(T.RULES),skills={'육상':3,'명령':3,'협박':3,'매력':3},moves=[]))
  p=Combatant(self.r,dict(common,name='partner',kind='pokemon',trainer_id=t.entity_id,trainer=t.name,skills={'육상':'2d6+1'},moves=['move/불꽃세례'],pos=(1,0)))
  foe=Combatant(self.r,dict(common,name='foe',kind='pokemon',skills={'육상':'2d6+1'},moves=[],pos=(2,0)))
  e.everyone=e.gm.everyone=[t,p,foe];e.time_actors(e.everyone);t.side=p.side='party';foe.side='enemy'
  ENTITIES.observe_loyalty(e,p,3,reason='actual willing owned partner');ITEMS.register_feats(e,t)
  return e,t,p,foe
 def open(self,e):e.start_round(e.everyone)
 def audible(self,e,t,p,allowed=True):
  e.gm.observe_sensory_environment(t,p,paths={'auditory':allowed},present=True,reason='actual audible order path')
 def issue(self,uid):
  e,t,p,foe=self.fixture();self.open(e);self.audible(e,t,p);out=e.manual_feat(t,uid,p);return e,t,p,foe,out

 def test_exact_csv_cells_and_runtime_mapping(self):
  self.assertEqual(T.CSV_CLAUSES,{uid:value[0] for uid,value in CLAUSES.items()})
  self.assertEqual(hashlib.sha256((ROOT/'input/db/feats.csv').read_bytes()).hexdigest(),'4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd')
  ledger=json.loads((ROOT/'data/verification/category2-class-csv-clause-status.json').read_text(encoding='utf8'))
  rows={row['id']:row for row in ledger['rows']}
  for uid,(clause,digest) in CLAUSES.items():
   self.assertEqual(rows[clause]['cell_sha256'],digest);self.assertEqual(rows[clause]['name'],T.RULES[uid]['aliases'][0])
   self.assertIn('당신을 대상으로도 사용할 수 있습니다',rows[clause]['source_text'])

 def test_four_orders_reuse_all_existing_bonus_consumers(self):
  e,t,p,foe,out=self.issue(T.AGILITY)
  self.assertEqual((out['status'],e.move_profile(p,'land')[0],INIT.value(self.r,p).value),('applied',7,14))
  e,t,p,foe,out=self.issue(T.BRUTAL);move=self.r.move('move/불꽃세례')
  self.assertTrue(e.accuracy_check(p,foe,move,fixed_roll=19)[2]);self.assertEqual(T.bonus(p,'effect'),1)
  e,t,p,foe,out=self.issue(T.FOCUSED)
  self.assertTrue(e.accuracy_check(p,foe,self.r.move('move/불꽃세례'),fixed_roll=4)[0]);self.assertEqual(e.skill_roll(p,'육상',fixed=[1,1]).total,5)
  e,t,p,foe,out=self.issue(T.INSPIRED)
  self.assertEqual((p.evasion('물리'),EXT.save_dc(e,p,'마비',11)),(4,9))

 def test_priority_limited_reserves_standard_preserves_rest_and_expires_at_owner_turn(self):
  e,t,p,foe,out=self.issue(T.FOCUSED)
  self.assertIsNone(e._active_turn_actor);self.assertEqual(t.pending_action_loss,{'standard':1})
  self.assertEqual(PRIORITY.records(t)[0]['payment']['phase'],'reserved');self.assertTrue(PRIORITY.validate(t));self.assertEqual(T.bonus(p,'skill'),2)
  e.start_of_turn(t)
  self.assertEqual(t.budget,{'standard':0,'shift':1,'swift':1});self.assertEqual(PRIORITY.records(t)[0]['payment']['phase'],'paid')
  self.assertFalse(T.records(p));self.assertEqual(T.bonus(p,'skill'),0);self.assertFalse(TIMING.records(p))

 def test_actual_auditory_communication_and_between_turn_failures_are_atomic_for_order_state(self):
  e,t,p,foe=self.fixture();self.open(e);before=deepcopy(getattr(t,'pending_action_loss',None))
  with self.assertRaisesRegex(ValueError,'not delivered'):e.manual_feat(t,T.FOCUSED,p)
  self.assertEqual(getattr(t,'pending_action_loss',None),before);self.assertFalse(T.records(p));self.assertFalse(PRIORITY.records(t))
  self.audible(e,t,p,False)
  with self.assertRaisesRegex(ValueError,'not delivered'):e.manual_feat(t,T.FOCUSED,p)
  self.assertFalse(T.records(p));self.assertFalse(PRIORITY.records(t))
  e,t,p,foe=self.fixture();self.open(e);self.audible(e,t,p);e.start_of_turn(foe)
  with self.assertRaisesRegex(ValueError,'between turns'):e.manual_feat(t,T.FOCUSED,p)
  self.assertFalse(T.records(p));self.assertIsNone(getattr(t,'pending_action_loss',None))

 def test_owned_target_and_explicit_self_exception(self):
  e,t,p,foe=self.fixture();self.open(e);self.audible(e,t,foe)
  with self.assertRaisesRegex(ValueError,'trainer identity|different trainer'):e.manual_feat(t,T.FOCUSED,foe)
  self.assertFalse(T.records(foe));self.assertIsNone(getattr(t,'pending_action_loss',None))
  e,t,p,foe=self.fixture();self.open(e);out=e.manual_feat(t,T.FOCUSED,t)
  self.assertEqual(out['communication']['mode'],'self_target_exception');self.assertEqual(T.bonus(t,'accuracy'),1)
  self.assertEqual(out['source_clause_id'],CLAUSES[T.FOCUSED][0])

 def test_order_stacks_with_same_active_training_then_only_order_expires(self):
  e,t,p,foe=self.fixture()
  e.train_pokemon(t,[(p,[T.FOCUSED])],minutes=30,reason='observed training',request_id='base-training',safe=True)
  self.assertEqual(T.bonus(p,'skill'),2);self.open(e);self.audible(e,t,p);e.manual_feat(t,T.FOCUSED,p)
  self.assertEqual(T.bonus(p,'skill'),4);self.assertEqual([r['mode'] for r in T.records(p)],['training','orders'])
  e.start_of_turn(t)
  self.assertEqual(T.bonus(p,'skill'),2);self.assertEqual([r['mode'] for r in T.records(p)],['training'])

 def test_no_second_priority_order_and_no_after_turn_order(self):
  e,t,p,foe,out=self.issue(T.AGILITY)
  with self.assertRaisesRegex(ValueError,'already reserved|already has a live'):e.manual_feat(t,T.BRUTAL,p)
  e.start_of_turn(t);e.end_of_turn(t)
  with self.assertRaisesRegex(ValueError,'already taken'):e.manual_feat(t,T.BRUTAL,p)


if __name__=='__main__':unittest.main(verbosity=2)
