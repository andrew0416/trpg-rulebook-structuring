"""Actual chapter Mixed Sweeper training reuses source-owned growth and commits."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon,STATS,species_lookup
import growth_stats as GS,mixed_sweeper as M,state_grants as G
import acquisition_qualification as Q,activity_jobs as JOBS
import downtime as D,form_allocations as FORMS
from state_codec import dump_engine

class MixedSweeperTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon()
 def pokemon(self,level=40,minimum=15,*,defensive=False,one_low=None):
  spec=build_pokemon(self.r,'피츄',level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':8})
  values=dict.fromkeys(STATS,0);values.update(atk=minimum,spa=minimum,spe=level+10-2*minimum)
  if defensive:values.update(spd=4,**{'def':1});values['spe']-=5
  if one_low is not None:values[one_low]-=1;values['spe']+=1
  plan=GS.compose(species_lookup(self.r,'피츄')['base_stats'],values,points=level+10,rules=self.r,strategy='balanced')
  spec.update(stats=deepcopy(plan['stats']),initial_allocation=deepcopy(plan))
  return self.add(spec)
 def bonus(self,stat='spe',amount=3):
  row=dict.fromkeys(STATS,0);row[stat]=amount;return row
 def teach(self,**options):
  options.setdefault('growth',self.bonus())
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=M.SOURCE,safe=True,**options)
 def configure(self):
  initial=self.p.spec['initial_allocation']
  normal={'species_base':deepcopy(initial['species_base']),'investment':deepcopy(initial['investment'])}
  other=deepcopy(normal)
  for stat in STATS:
   if stat!='hp':other['species_base'][stat]+=100
  return self.e.configure_growth_forms(self.p,{'normal':normal,'alternate':other},active='normal',source='combat/struggle')
 def test_three_ranks_reuse_actual_jobs_qualification_composition_and_never_change_species_base(self):
  old=GS.project(self.r,self.p.spec);catalog=deepcopy(species_lookup(self.r,'피츄')['base_stats'])
  with patch.object(GS,'migrate_sources',wraps=GS.migrate_sources) as migration,patch.object(Q,'require',wraps=Q.require) as qualified,patch.object(JOBS,'run_fixed',wraps=JOBS.run_fixed) as jobs:
   for rank in (1,2,3):self.assertEqual(self.teach()['rank'],rank)
  self.assertEqual((migration.call_count,jobs.call_count),(3,3));self.assertGreaterEqual(qualified.call_count,6)
  now=self.e.growth_stat_projection(self.p)['permanent']
  self.assertEqual(now['investment'],old['investment']);self.assertEqual(now['species_base'],catalog)
  self.assertEqual(now['nature_base'],old['nature_base']);self.assertEqual(now['stats']['spe'],old['stats']['spe']+9)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(5,10800))
  self.assertEqual(species_lookup(self.r,'피츄')['base_stats'],catalog);self.assertNotIn('트위스트파워',self.p.spec['abilities'])
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_rank_level_and_both_direct_investments_are_required_before_payment(self):
  for level,minimum,count in [(9,5,0),(10,4,0),(10,5,1),(19,10,1),(20,10,2),(39,15,2)]:
   self.setUp();self.p=self.pokemon(level,minimum)
   for _ in range(count):self.teach()
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
 def test_level_one_initial_points_are_actual_eligible_investment(self):
  self.p=self.pokemon(10,5);self.assertEqual(self.p.spec.get('growth_investment_events',[]),[])
  self.assertEqual(self.teach()['rank'],1)
 def test_either_attack_alone_below_threshold_cannot_be_replaced_by_the_other(self):
  for stat in ('atk','spa'):
   self.setUp();self.p=self.pokemon(10,5,one_low=stat);before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
 def test_actual_gm_untracked_stat_edit_cannot_corrupt_acquired_investment(self):
  self.teach();before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.set_stat(self.p,'atk',delta=100,reason='untracked investment is not a stat source')
  self.assertEqual(self.snap(),before)
 def test_each_allowed_defensive_stat_is_a_point_contribution(self):
  for stat in ('hp','def','spd','spe'):
   self.setUp();self.p=self.pokemon(defensive=True);old=GS.project(self.r,self.p.spec)
   self.teach(growth=self.bonus(stat));now=GS.project(self.r,self.p.spec)
   self.assertEqual(now['stats'],{st:v+3*int(st==stat) for st,v in old['stats'].items()})
   self.assertEqual(now['investment'],old['investment']);self.assertEqual(now['nature_base'],old['nature_base'])
 def test_illegal_budget_attack_choices_unknown_forms_and_base_relation_fail_atomically(self):
  bad=[self.bonus('atk'),self.bonus('spa'),self.bonus(amount=2),dict(self.bonus(),hp=True),{'unknown':self.bonus()},self.bonus('hp')]
  for value in bad:
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(growth=value)
   self.assertEqual(self.snap(),before)
 def test_temporary_stats_and_vitamins_do_not_fabricate_level_point_prerequisites(self):
  self.p=self.pokemon(10,4)
  G._source(self.p,'stat-boost','feature',rule_id='combat/struggle')
  for stat in ('atk','spa'):G.stat(self.p,stat,100,'stat-boost')
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
  G.transition(self.e,self.p,lambda e,c:G.revoke(c,'stat-boost',engine=e))
  GS.apply_vitamin(self.p,'atk',source='combat/struggle');GS.apply_vitamin(self.p,'spa',source='combat/struggle')
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_native_levelup_adds_only_fresh_ordinary_points(self):
  self.teach();old=GS.project(self.r,self.p.spec)
  D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={41:'spe'})
  now=GS.project(self.r,self.p.spec)
  self.assertEqual(now['investment']['spe'],old['investment']['spe']+1)
  self.assertEqual(now['contributions']['point_sources'],old['contributions']['point_sources'])
  self.assertEqual(now['stats']['spe'],old['stats']['spe']+1)
 def test_level_loss_refunds_only_lost_ranks_once_and_requires_new_training_on_reacquisition(self):
  for _ in range(3):self.teach()
  old=GS.project(self.r,self.p.spec);self.e.gm.set_level(self.p,19,reason='actual corrected level')
  self.assertEqual([r['rank'] for r in M.source_rows(self.r,self.p.spec)],[1]);self.assertEqual(self.p.spec['tutor_points'],7)
  self.assertEqual(GS.project(self.r,self.p.spec)['stats']['spe'],old['stats']['spe']-6)
  self.e.gm.set_level(self.p,9,reason='lost last rank');self.assertEqual(self.p.spec['tutor_points'],8)
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],8)
  self.e.gm.set_level(self.p,40,reason='restored prerequisite');self.assertFalse(M.source_rows(self.r,self.p.spec))
  self.teach();self.assertEqual((len(M.records(self.p.spec)),self.p.spec['tutor_points'],self.e.elapsed_seconds),(4,7,14400))
 def test_real_nature_reallocation_and_durable_replay_refund_lost_investment_once(self):
  self.teach();values=dict.fromkeys(STATS,0);values.update(atk=4,spa=4,spe=42)
  import nature_state as N
  neutral=next(name for name in self.r.mech('pokemon/natures')['by_name'] if N.describe(self.r,name)['neutral'])
  options=dict(investment=values,source='combat/struggle',reason='explicit actual reallocation',ap_cost=0,hp_policy='preserve_damage',request_id='mixed-reallocate')
  self.e.commit_growth_nature(self.a,self.p,neutral,**options)
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertFalse(M.source_rows(self.r,self.p.spec))
  self.e.commit_growth_nature(self.a,self.p,neutral,**options);self.assertEqual(self.p.spec['tutor_points'],8)
  self.assertEqual(GS.project(self.r,self.p.spec)['investment'],values)
 def test_actual_forms_keep_each_bonus_and_growth_without_stacking(self):
  self.configure();self.teach(growth={'normal':self.bonus('spe'),'alternate':self.bonus('spe')})
  original=deepcopy(self.p.spec['form_growth_allocations'])
  for form in ('alternate','normal','alternate'):
   FORMS.switch(self.e,self.p,form)
   self.assertEqual(GS.project(self.r,self.p.spec)['contributions']['bonus_points']['spe'],3)
  D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={41:'spe'})
  for form in ('normal','alternate'):
   FORMS.switch(self.e,self.p,form)
   self.assertEqual(GS.project(self.r,self.p.spec)['investment']['spe'],original['plans'][form]['investment']['spe']+1)
  self.e.gm.set_level(self.p,9,reason='actual all-form loss')
  for form in ('normal','alternate'):
   FORMS.switch(self.e,self.p,form);self.assertNotIn('bonus_points',GS.project(self.r,self.p.spec)['contributions'])
 def test_form_hp_must_agree_before_hour_is_consumed(self):
  self.p=self.pokemon(defensive=True);self.configure();before=self.snap()
  with self.assertRaises(ValueError):self.teach(growth={'normal':self.bonus('hp'),'alternate':self.bonus('spe')})
  self.assertEqual(self.snap(),before)
 def test_actual_evolution_keeps_source_bonus_or_refunds_when_new_ordinary_allocation_loses_it(self):
  self.teach();out=D.evolve_combatant(self.e,self.p,'피카츄');self.assertTrue(out['evolved'])
  projection=GS.project(self.r,self.p.spec);active=M.source_rows(self.r,self.p.spec)
  if active:self.assertEqual(projection['contributions']['bonus_points']['spe'],3)
  else:self.assertEqual(self.p.spec['tutor_points'],8)
  self.assertEqual(len(M.records(self.p.spec)),1);self.assertTrue(self.e.validate_state()['valid'])
 def test_actual_underdog_recomposition_preserves_other_source_and_withdrawal(self):
  import underdog_edges as U
  self.teach()
  G.grant(self.p,'capabilities','약골','observed-underdog','gm_observation',rule_id='capability/약골')
  old=GS.project(self.r,self.p.spec)
  self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=U.STRENGTH,safe=True)
  now=GS.project(self.r,self.p.spec)
  self.assertEqual(now['contributions']['point_sources'],old['contributions']['point_sources'])
  self.assertEqual(now['investment'],old['investment'])
  G.transition(self.e,self.p,lambda e,c:G.revoke(c,'observed-underdog',engine=e))
  self.assertTrue(any(row['source']==U.STRENGTH for row in U.source_rows(self.r,self.p.spec)))
  G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual(GS.project(self.r,self.p.spec)['stats'],old['stats'])
 def test_actual_potential_and_mixed_points_keep_canonical_source_order_at_each_evolution_form(self):
  import underdog_edges as U
  for forms in (False,True):
   self.setUp()
   if forms:self.configure()
   self.teach()
   G.grant(self.p,'capabilities','약골','observed-underdog','gm_observation',rule_id='capability/약골')
   current=GS.project(self.r,self.p.spec);plans=self.p.spec.get('form_growth_allocations',{}).get('plans',{'base':current});choices={}
   for name,plan in plans.items():
    # Explicit equal HP allocation in both actual forms, rather than separately
    # weighted auto choices which correctly fail the existing shared-HP rule.
    choices[name]=self.bonus(amount=U.species_points(self.r,self.p.spec['species']))
   self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=U.POTENTIAL,growth=choices if forms else choices['base'],safe=True)
   options={}
   if forms:
    declarations={};base=species_lookup(self.r,'피카츄')['base_stats']
    for name,plan in self.p.spec['form_growth_allocations']['plans'].items():
     values=deepcopy(base)
     declarations[name]={'species_base':values,'investment':deepcopy(plan['investment'])}
    options['form_declarations']=declarations
   self.assertTrue(D.evolve_combatant(self.e,self.p,'피카츄',**options)['evolved'])
   for name in plans:
    if forms:FORMS.switch(self.e,self.p,name)
    now=GS.project(self.r,self.p.spec)
    self.assertEqual([row['source'] for row in now['contributions']['point_sources']],[U.POTENTIAL,M.SOURCE+':rank:1'])
    self.assertEqual(now['contributions']['point_sources'][1]['values'],self.bonus())
   self.assertTrue(self.e.validate_state()['valid'])
 def test_missing_balance_and_actual_owner_refuse_before_training(self):
  for field,value in [('tutor_points',0),('tutor_points',None),('trainer_id','unknown-owner')]:
   self.setUp();self.p.spec[field]=value;before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
 def test_actual_ordinary_training_credit_preserves_completed_hour(self):
  self.e.complete_training_hour(self.a,[self.p],safe=True,reason='actual completed ordinary training',request_id='mixed-hour')
  before=self.e.elapsed_seconds;self.teach(from_training=True)
  self.assertEqual(self.e.elapsed_seconds,before);self.assertEqual(len(M.source_rows(self.r,self.p.spec)),1)
 def test_json_and_gm_restore_validate_rank_receipts_without_reapplication(self):
  self.teach();saved=self.e.gm.snapshot();expected=GS.project(self.r,self.p.spec)
  self.p.spec['learned_poke_edges'][-1]['rank']=3
  self.e.gm.restore(saved);self.p=next(c for c in self.e.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(GS.project(self.r,self.p.spec),expected)
  loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(GS.project(self.r,p.spec),expected);self.assertEqual(p.spec['tutor_points'],7)
  p.spec['learned_poke_edges'][-1]['point_cost']=2
  with self.assertRaises(ValueError):dump_engine(loaded)
 def test_late_failure_rolls_back_hour_tp_investment_logs_and_rng(self):
  before=self.snap()
  with patch.object(GS,'migrate_sources',side_effect=RuntimeError('late native consumer failure')):
   with self.assertRaises(RuntimeError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_conflicting_csv_is_not_aliased_into_chapter_source(self):
  for edge in ('poke_edge/쌍두스위퍼','쌍두스위퍼','C2CSV/input/db/poke-edges.csv:R65:main'):
   before=self.snap()
   with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=edge,growth=self.bonus(),safe=True)
   self.assertEqual(self.snap(),before)
  self.assertEqual(self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge='Mixed Sweeper',growth=self.bonus(),safe=True)['edge'],M.SOURCE)
 def test_selected_parent_and_live_source_hash_are_checked_before_payment(self):
  parent=M.definition(self.r)['selected_parent'];self.r.selection.excluded[parent]='exclude_units'
  try:
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
  finally:self.r.selection.excluded.pop(parent,None)
  from pathlib import Path
  real=Path.read_bytes;source=(Path(self.r.root)/'input/ch05-pokemon.md').resolve()
  def changed(path):return real(path)+b' tamper' if path.resolve()==source else real(path)
  before=self.snap()
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)

