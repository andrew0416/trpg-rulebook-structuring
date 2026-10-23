from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import downtime as D,state_grants as G
from state_codec import dump_engine,load_engine

class GrowthImportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self):
  self.e=Engine(self.r);spec=build_pokemon(self.r,'잉어킹',5,moves=[],abilities=[])
  self.investment=deepcopy(spec.pop('initial_allocation')['investment'])
  self.c=Combatant(self.r,spec);self.e.everyone=self.e.gm.everyone=[self.c]
  self.args=dict(source='combat/struggle',reason='declared investment from character record',request_id='legacy/import')
 def test_import_preserves_stats_sources_and_grows_after_restore(self):
  c=self.c;G._source(c,'bonus','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'bonus')
  c.spec['vitamin_bonus']={'atk':1}
  import state_fields as F
  stats=deepcopy(c.spec['stats']);stats['atk']+=1;F.base_patch(c,{'stats':stats},reason='existing vitamin',source='combat/struggle')
  original=(deepcopy(c.stats),c.hp,c.level,deepcopy(c.spec['stat_history']))
  out=self.e.import_growth_investment(c,self.investment,**self.args)
  self.assertEqual((c.stats,c.hp,c.level,c.spec['stat_history']),original)
  self.assertEqual(out['projection']['permanent']['investment'],self.investment)
  self.assertEqual(out['projection']['permanent']['growth_events'],[])
  loaded=load_engine(self.r,dump_engine(self.e));owner=loaded.everyone[0]
  D.gain_exp_combatant(loaded,owner,'to next level',stat_choices={6:'spe'})
  projected=loaded.growth_stat_projection(owner)
  self.assertEqual(sum(projected['permanent']['investment'].values()),16)
  self.assertEqual(projected['effective_stats']['atk'],projected['permanent']['stats']['atk']+3)
  before=dump_engine(loaded)
  self.assertTrue(loaded.import_growth_investment(owner,self.investment,**self.args)['replayed'])
  self.assertEqual(dump_engine(loaded),before)
 def test_bad_budget_mismatch_and_existing_evidence_are_atomic(self):
  bad=deepcopy(self.investment);bad['atk']+=1
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'budget'):self.e.import_growth_investment(self.c,bad,**self.args)
  self.assertEqual(dump_engine(self.e),before)
  self.c.spec['stats']['spe']+=1;self.c.stats['spe']+=1;before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'does not match'):self.e.import_growth_investment(self.c,self.investment,**self.args)
  self.assertEqual(dump_engine(self.e),before)
  self.setUp();self.e.import_growth_investment(self.c,self.investment,**self.args);before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'existing allocation'):
   self.e.import_growth_investment(self.c,self.investment,**dict(self.args,request_id='another'))
  self.assertEqual(dump_engine(self.e),before)
 def test_untracked_runtime_source_and_late_failure_leave_no_import(self):
  from unittest.mock import patch
  import growth_stats as GS
  self.c.stats['atk']+=1;before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'untracked effective'):
   self.e.import_growth_investment(self.c,self.investment,**self.args)
  self.assertEqual(dump_engine(self.e),before)
  self.setUp();before=dump_engine(self.e)
  with patch.object(GS,'project_actor',side_effect=ValueError('late projection')):
   with self.assertRaisesRegex(ValueError,'late projection'):
    self.e.import_growth_investment(self.c,self.investment,**self.args)
  self.assertEqual(dump_engine(self.e),before)
 def test_existing_observed_growth_is_not_counted_twice(self):
  D.gain_exp_combatant(self.e,self.c,'to next level',stat_choices={6:'spe'})
  investment=deepcopy(self.investment);investment['spe']+=1
  self.e.import_growth_investment(self.c,investment,**self.args)
  self.assertEqual(len(self.c.spec['growth_investment_events']),1)
  self.assertEqual(self.e.growth_stat_projection(self.c)['permanent']['growth_events'],[])
  D.gain_exp_combatant(self.e,self.c,'to next level',stat_choices={7:'spe'})
  out=self.e.growth_stat_projection(self.c)['permanent']
  self.assertEqual(sum(out['investment'].values()),17);self.assertEqual(len(out['growth_events']),1)

if __name__=='__main__':unittest.main()
