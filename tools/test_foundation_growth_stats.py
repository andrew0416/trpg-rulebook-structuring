from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from builder import allocation_plan,allocate_stats,STATS

class GrowthStatsTests(unittest.TestCase):
 def test_actual_investment_sum_and_strict_base_relations(self):
  base=dict(zip(STATS,[4,8,6,3,5,7]));out=allocation_plan(base,30,'attack')
  self.assertEqual(sum(out['investment'].values()),30)
  self.assertEqual(out['stats'],allocate_stats(base,30,'attack'))
  for stat in STATS:self.assertEqual(out['stats'][stat],base[stat]+out['investment'][stat])
  for hi in STATS:
   for lo in STATS:
    if base[hi]>base[lo]:self.assertGreater(out['stats'][hi],out['stats'][lo])
 def test_excluded_stat_and_explicit_relation_exception_are_recorded(self):
  base=dict(zip(STATS,[0,8,6,3,5,7]));out=allocation_plan(base,20,'bulky',excluded=['hp'],relation_exempt=['atk'])
  self.assertEqual(out['investment']['hp'],0);self.assertEqual(out['stats']['hp'],0)
  self.assertEqual(out['excluded'],['hp']);self.assertEqual(out['relation_exempt'],['atk'])
 def test_plan_is_detached_and_never_infers_investment_from_final_values(self):
  base=dict.fromkeys(STATS,5);out=allocation_plan(base,0);out['stats']['atk']=99
  self.assertEqual(out['investment']['atk'],0);self.assertEqual(base['atk'],5);self.assertEqual(out['nature_base']['atk'],5)

class NativeGrowthPlanTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from engine import Rules
  cls.r=Rules(ROOT)
 def test_builder_retains_direct_investment_and_does_not_certify_override(self):
  from builder import build_pokemon
  spec=build_pokemon(self.r,'이상해씨',5,moves=['struggle'])
  plan=spec['initial_allocation'];self.assertEqual(sum(plan['investment'].values()),15)
  self.assertEqual(plan['stats'],spec['stats']);self.assertIsNot(plan['stats'],spec['stats'])
  changed=dict(spec['stats']);changed['atk']+=1
  override=build_pokemon(self.r,'이상해씨',5,moves=['struggle'],extra={'stats':changed})
  self.assertNotIn('initial_allocation',override)

class NativeGrowthIncrementTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from engine import Rules
  cls.r=Rules(ROOT)
 def test_level_up_records_new_investment_and_separates_vitamins(self):
  from builder import build_pokemon
  import downtime as D,growth_stats as G
  spec=build_pokemon(self.r,'이상해씨',5,moves=['struggle']);original=dict(spec['initial_allocation']['investment'])
  spec['vitamin_bonus']={'atk':1};spec['stats']['atk']+=1
  D.level_up(self.r,spec)
  out=G.project(self.r,spec);self.assertEqual(sum(out['investment'].values()),16)
  self.assertEqual(out['contributions']['vitamins']['atk'],1);self.assertEqual(out['stats'],spec['stats'])
  event=spec['growth_investment_events'][0];self.assertEqual(sum(event['investment_delta'].values()),1)
  self.assertEqual(spec['initial_allocation']['investment'],original)
 def test_projection_rejects_untracked_final_stats_and_missing_initial(self):
  from builder import build_pokemon
  import growth_stats as G
  spec=build_pokemon(self.r,'이상해씨',5,moves=['struggle']);spec['stats']['atk']+=1
  with self.assertRaisesRegex(ValueError,'untracked'):G.project(self.r,spec)
  spec.pop('initial_allocation')
  with self.assertRaisesRegex(ValueError,'initial investment'):G.project(self.r,spec)
 def test_invalid_growth_choice_leaves_event_history_unchanged(self):
  from builder import build_pokemon
  from copy import deepcopy
  import downtime as D
  spec=build_pokemon(self.r,'이상해씨',5,moves=['struggle']);before=deepcopy(spec)
  with self.assertRaises(ValueError):D.level_up(self.r,spec,stat_choice='invalid')
  self.assertEqual(spec,before)

class EvolutionAllocationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from engine import Rules
  cls.r=Rules(ROOT)
 def test_evolution_reallocation_retains_prior_evidence_and_vitamins(self):
  from builder import build_pokemon
  from copy import deepcopy
  import downtime as D,growth_stats as G
  spec=build_pokemon(self.r,'잉어킹',19,moves=[],abilities=[]);initial=deepcopy(spec['initial_allocation'])
  spec['vitamin_bonus']={'atk':2};spec['stats']['atk']+=2
  D.level_up(self.r,spec);before=deepcopy(spec['growth_investment_events'])
  self.assertTrue(D.evolve(self.r,spec,'갸라도스'))
  out=G.project(self.r,spec);self.assertEqual(sum(out['investment'].values()),30)
  self.assertEqual(out['contributions']['vitamins']['atk'],2);self.assertEqual(out['stats'],spec['stats'])
  self.assertEqual(spec['initial_allocation'],initial);self.assertEqual(spec['growth_investment_events'],before)
  self.assertEqual(out['growth_events'],[]);self.assertEqual(len(out['allocation_migrations']),1)
  D.level_up(self.r,spec);out=G.project(self.r,spec);self.assertEqual(sum(out['investment'].values()),31);self.assertEqual(len(out['growth_events']),1)
 def test_actual_actor_evolution_keeps_granted_stat_separate_and_restoreable(self):
  from builder import build_pokemon
  from engine import Engine,Combatant
  import downtime as D,growth_stats as G,state_grants as S
  from state_codec import dump_engine,load_engine
  e=Engine(self.r);c=Combatant(self.r,build_pokemon(self.r,'잉어킹',20,moves=[],abilities=[]));e.everyone=e.gm.everyone=[c]
  S._source(c,'test/evolution-stat','feature',rule_id='combat/struggle');S.stat(c,'atk',3,'test/evolution-stat')
  D.evolve_combatant(e,c,'갸라도스');out=G.project(self.r,c.spec)
  self.assertEqual(c.stats['atk'],out['stats']['atk']+3)
  restored=load_engine(self.r,dump_engine(e));owner=restored.everyone[0]
  self.assertEqual(G.project(self.r,owner.spec),out);self.assertEqual(owner.stats['atk'],out['stats']['atk']+3)

class ActorGrowthProjectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from engine import Rules
  cls.r=Rules(ROOT)
 def setUp(self):
  from engine import Engine,Combatant
  from builder import build_pokemon
  self.e=Engine(self.r);self.c=Combatant(self.r,build_pokemon(self.r,'잉어킹',20,moves=[],abilities=[]));self.e.everyone=self.e.gm.everyone=[self.c]
 def test_ordered_clamp_sources_and_stages_remain_separate(self):
  import state_grants as G
  from state_codec import dump_engine
  c=self.c;base=c.spec['stats']['atk'];G._source(c,'clamp','feature',rule_id='combat/struggle')
  G.stat(c,'atk',-100,'clamp',minimum=2);G._source(c,'bonus','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'bonus');c.stages['atk']=2
  before=dump_engine(self.e);out=self.e.growth_stat_projection(c)
  self.assertEqual(out['permanent']['stats']['atk'],base);self.assertEqual(out['effective_stats']['atk'],5);self.assertEqual(out['combat_stages']['atk'],2)
  self.assertEqual([x['after'] for x in out['source_operations']['atk']],[2,5]);self.assertEqual(dump_engine(self.e),before)
  out['combat_stages']['atk']=6;self.assertEqual(c.stages['atk'],2)
 def test_untracked_effective_or_legacy_offset_rejected(self):
  import state_grants as G
  self.c.stats['atk']+=1
  with self.assertRaisesRegex(ValueError,'untracked effective'):self.e.growth_stat_projection(self.c)
  G._source(self.c,'bonus','feature',rule_id='combat/struggle');G.stat(self.c,'atk',3,'bonus')
  with self.assertRaisesRegex(ValueError,'unattributed'):self.e.growth_stat_projection(self.c)
 def test_withdraw_source_preserves_permanent_allocation(self):
  import state_grants as G
  c=self.c;before=self.e.growth_stat_projection(c)['permanent'];G._source(c,'bonus','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'bonus')
  self.assertEqual(self.e.growth_stat_projection(c)['permanent'],before)
  G.transition(self.e,c,lambda e,a:G.revoke(a,'bonus',engine=e))
  out=self.e.growth_stat_projection(c);self.assertEqual(out['permanent'],before);self.assertEqual(out['effective_stats'],before['stats'])

class ExplicitInvestmentTests(unittest.TestCase):
 def test_explicit_budget_relations_and_exceptions(self):
  import growth_stats as G
  base=dict.fromkeys(STATS,5);base['atk']=8;investment=dict.fromkeys(STATS,0);investment['def']=3
  with self.assertRaisesRegex(ValueError,'relations'):G.compose(base,investment,points=3)
  out=G.compose(base,investment,points=3,relation_exempt=['def']);self.assertEqual(out['stats']['def'],8)
  with self.assertRaisesRegex(ValueError,'budget'):G.compose(base,investment,points=4,relation_exempt=['def'])
 def test_native_nature_plan_keeps_same_nature_investment_without_consuming(self):
  from engine import Rules,Engine,Combatant
  from builder import build_pokemon
  from state_codec import dump_engine
  r=Rules(ROOT);e=Engine(r);c=Combatant(r,build_pokemon(r,'잉어킹',5,moves=[],abilities=[]));e.everyone=e.gm.everyone=[c]
  before=dump_engine(e);out=e.plan_growth_nature(c,None)
  self.assertEqual(out['permanent_stats'],c.spec['stats']);self.assertEqual(out['allocation']['investment'],c.spec['initial_allocation']['investment']);self.assertEqual(dump_engine(e),before)
  import nature_state as N,growth_stats as G
  from builder import species_lookup
  nature=next(name for name in r.mech('pokemon/natures')['by_name'] if not N.describe(r,name)['neutral'])
  proposal=G.allocate(species_lookup(r,c.spec['species'])['base_stats'],15,nature=nature,rules=r)
  changed=e.plan_growth_nature(c,nature,investment=proposal['investment'])
  self.assertEqual(changed['allocation']['nature_base'],proposal['nature_base']);self.assertTrue(any(changed['allocation']['nature_delta'].values()))
  self.assertEqual(dump_engine(e),before)


if __name__=='__main__':unittest.main()
