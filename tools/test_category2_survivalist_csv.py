"""Two exact CSV contracts over native Survivalist skill and movement paths."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules,Combatant
from grid import Grid
import survivalist_features as V
import movement_actions as MOVEMENT
import state_grants as GRANTS
import state_codec as CODEC
import world_entities as WORLD
import frequency as FREQUENCY
import turn as TURN


class SurvivalistCSVTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')
 def fixture(self):
  e=Engine(self.r,seed=1717);e.grid=Grid(1,8)
  stats=dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=10)
  a=Combatant(self.r,dict(id='trainer/a',name='Survivalist',kind='trainer',size='중형',level=20,stats=stats,skills={'생존':6,'육상':4,'곡예':4,'은신':3,'통찰':3,'집중':3},classes=[V.SURVIVALIST],feats=[],movement={'land':3}))
  b=Combatant(self.r,dict(id='trainer/b',name='Other',kind='trainer',size='중형',level=20,stats=stats,skills={'육상':4},movement={'land':3}))
  e.gm.add_combatant(a,pos=(0,0),side='party',reason='actual Survivalist owner')
  e.gm.add_combatant(b,pos=(0,6),side='foe',reason='actual other actor')
  return e,a,b
 def select(self,e,a,terrains=('forest',),clause=None,minutes=2):
  return e.survivalist_activity(a,'select_csv_terrains',clause_id=clause or V.CSV_CLAUSES[0],terrains=list(terrains),minutes=minutes,reason='GM actual noncombat Extended Action')
 def env(self,e,a,*terrains):
  e.survivalist_activity(a,'observe_environment',terrains=list(terrains),light='normal',reason='GM actual present terrain')
 def test_two_exact_rows_remain_distinct_and_daily_extended_action_is_paid_once(self):
  policy=V.csv_policy(self.r);rows=policy['clauses']
  self.assertEqual(set(rows),set(V.CSV_CLAUSES));self.assertNotEqual(rows[V.CSV_CLAUSES[0]]['name'],rows[V.CSV_CLAUSES[1]]['name'])
  self.assertNotEqual(rows[V.CSV_CLAUSES[0]]['cell_sha256'],rows[V.CSV_CLAUSES[1]]['cell_sha256'])
  for clause in V.CSV_CLAUSES:
   with self.subTest(clause=clause):
    e,a,b=self.fixture();row=self.select(e,a,clause=clause)
    self.assertEqual(e.elapsed_seconds,120);self.assertEqual(a._action_history,['extended'])
    self.assertEqual(row['clause_id'],clause);self.assertEqual(row['frequency'],{'kind':'daily','period':0,'used':1})
    self.assertEqual(V.selected(e,a),('forest',));self.assertNotIn('_survivalist_nights',a.spec)
    before=CODEC.dump_engine(e)
    with self.assertRaisesRegex(ValueError,'daily selection exhausted'):self.select(e,a,clause=V.CSV_CLAUSES[1],terrains=('cave',))
    self.assertEqual(CODEC.dump_engine(e),before)
 def test_actual_five_skill_rolls_use_current_terrain_once_for_both_sources(self):
  for clause in V.CSV_CLAUSES:
   e,a,b=self.fixture();a.spec['feats']=['feat/내추럴-파이터']
   self.select(e,a,('forest','cave'),clause);self.env(e,a,'forest','cave')
   for skill,n in [('생존',6),('육상',4),('곡예',4),('은신',3),('통찰',3),('집중',3)]:
    self.assertEqual(e.skill_roll(a,skill,fixed=[1]*n).total,n+(0 if skill=='집중' else 2))
   self.env(e,a,'desert');self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,6)
   self.env(e,a,'forest');self.assertEqual(e.skill_roll(b,'육상',fixed=[1]*4).total,4)
 def test_actual_naturewalk_shift_and_class_withdrawal_follow_the_same_choice(self):
  for owns in (True,False):
   e,a,b=self.fixture();self.select(e,a);self.env(e,a,'forest')
   e.grid.slow={(0,1),(0,2),(0,3)}
   MOVEMENT.observe_cell_terrain(e,[(0,y) for y in range(1,4)],['forest'],'observed forest corridor')
   GRANTS.grant(a,'capabilities','Naturewalk(cave)','independent:cave','fixture')
   if not owns:a.spec['classes']=[]
   e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(a)
   e.approach(a,b)
   self.assertEqual(a.pos,(0,3) if owns else (0,1));self.assertEqual(a.budget['shift'],0)
   self.assertIn('cave',MOVEMENT.naturewalk_terrains(e,a))
   self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,8 if owns else 6)
   self.assertTrue(WORLD.validate_world(e)['valid'])
 def test_two_four_six_feature_thresholds_and_next_day_replacement(self):
  e,a,b=self.fixture();self.select(e,a,('forest',))
  for feats,rank,values in [(['feat/내추럴-파이터'],None,('forest','cave')),(['feat/내추럴-파이터','feat/트래퍼','feat/야생-가이드'],None,('forest','cave','urban')),(['feat/내추럴-파이터','feat/트래퍼','feat/야생-가이드',V.TALENT],2,('mountain','grassland','ocean','desert'))]:
   FREQUENCY.new_day(a);a.spec['feats']=feats
   if rank:a.spec['feat_ranks']={V.TALENT:rank}
   row=self.select(e,a,values,clause=V.CSV_CLAUSES[1])
   self.assertEqual(V.selected(e,a),values);self.assertEqual(len(values),{2:2,4:3,6:4}[row['feature_count']])
   sources=[r for r in GRANTS.state(a)['sources'].values() if r['kind']=='survivalist_csv_selection']
   self.assertEqual(len(sources),1);self.assertEqual(sources[0]['selection_sequence'],row['sequence'])
  self.assertEqual(len(a.spec[V.CSV_STATE]['history']),4)
 def test_explicit_withdrawal_preserves_independent_capability_and_spent_quota(self):
  e,a,b=self.fixture();self.select(e,a);self.env(e,a,'forest')
  GRANTS.grant(a,'capabilities','Naturewalk(cave)','independent:cave','fixture')
  e.survivalist_activity(a,'withdraw_csv_terrains',reason='actual choice source withdrawn')
  self.assertEqual(V.selected(e,a),());self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,6)
  self.assertEqual(MOVEMENT.naturewalk_terrains(e,a),frozenset({'cave'}))
  self.assertFalse(FREQUENCY.activation_allowed(a,V.CSV_QUOTA,V.CSV_FREQUENCY,engine=e))
  self.assertTrue(WORLD.validate_world(e)['valid'])
 def test_json_and_gm_restores_keep_actual_source_daily_quota_and_consumers(self):
  for clause in V.CSV_CLAUSES:
   e,a,b=self.fixture();self.select(e,a,clause=clause);self.env(e,a,'forest')
   payload=CODEC.dump_engine(e);e.gm.snapshot('csv choice')
   e.survivalist_activity(a,'withdraw_csv_terrains',reason='temporarily withdraw')
   e.gm.restore('csv choice',reason='restore exact daily selection')
   loaded=CODEC.load_engine(self.r,json.loads(json.dumps(payload,ensure_ascii=False)))
   for world in (e,loaded):
    owner=WORLD.actor_index(world)[a.entity_id]
    self.assertEqual(V.selected(world,owner),('forest',));self.assertEqual(world.skill_roll(owner,'생존',fixed=[1]*6).total,8)
    self.assertEqual(owner.spec[V.CSV_STATE]['history'][-1]['clause_id'],clause)
    self.assertFalse(FREQUENCY.activation_allowed(owner,V.CSV_QUOTA,V.CSV_FREQUENCY,engine=world))
    self.assertIn('forest',MOVEMENT.naturewalk_terrains(world,owner))
 def test_unknown_duplicate_capacity_unowned_and_changed_source_fail_atomically(self):
  invalids=[lambda e,a:self.select(e,a,('forest','cave')),lambda e,a:self.select(e,a,('forest','forest')),lambda e,a:self.select(e,a,('unknown',)),lambda e,a:self.select(e,a,clause='unreviewed'),lambda e,a:self.select(e,a,minutes=0)]
  for invoke in invalids:
   e,a,b=self.fixture();before=CODEC.dump_engine(e)
   with self.assertRaises(ValueError):invoke(e,a)
   self.assertEqual(before,CODEC.dump_engine(e))
  for classes,rank in [([],6),([V.SURVIVALIST],2)]:
   e,a,b=self.fixture();a.spec['classes']=classes;a.spec['skills']['생존']=rank;before=CODEC.dump_engine(e)
   with self.assertRaises(ValueError):self.select(e,a)
   self.assertEqual(before,CODEC.dump_engine(e))
  e,a,b=self.fixture();before=CODEC.dump_engine(e);original=e.r._selected_rule
  with patch.object(e.r,'_selected_rule',side_effect=lambda uid,**kw:'changed/source' if uid==V.CLASS_SOURCE else original(uid,**kw)):
   with self.assertRaises(ValueError):self.select(e,a)
  self.assertEqual(before,CODEC.dump_engine(e))
 def test_corrupt_owner_source_quota_clock_and_projection_reject_persistence(self):
  changes=[lambda a:a.spec[V.CSV_STATE].update(owner_id='trainer/b'),lambda a:a.spec[V.CSV_STATE]['history'][-1].update(cell_sha256='wrong'),lambda a:a.spec[V.CSV_STATE]['history'][-1]['terrains'].append('cave'),lambda a:a.spec[V.CSV_STATE]['history'][-1].update(terrains=['cave']),lambda a:a.spec[V.CSV_STATE]['history'][-1].update(completed_seconds=1),lambda a:a.spec['frequency_state']['activations'][V.CSV_QUOTA].update(used=0),lambda a:GRANTS.state(a)['sources'].clear()]
  for mutate in changes:
   e,a,b=self.fixture();self.select(e,a);mutate(a)
   self.assertFalse(WORLD.validate_world(e)['valid'])
   with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(e)
 def test_late_source_failure_rolls_back_clock_frequency_action_rng_and_aliases(self):
  e,a,b=self.fixture();before=CODEC.dump_engine(e);spec=a.spec;original=GRANTS._source
  def fail(actor,source,kind,**metadata):
   if kind=='survivalist_csv_selection':raise RuntimeError('late CSV source failure')
   return original(actor,source,kind,**metadata)
  with patch.object(GRANTS,'_source',side_effect=fail):
   with self.assertRaisesRegex(RuntimeError,'late CSV source'):self.select(e,a)
  self.assertIs(a.spec,spec);self.assertEqual(before,CODEC.dump_engine(e))


if __name__=='__main__':unittest.main(verbosity=2)
