"""Native Underdog Strength preserves base, Nature and investment provenance."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon,nature_base,species_lookup
import builder as B,downtime as D,growth_stats as GS,underdog_edges as U
import state_grants as G,form_allocations as FORMS,composition_derive as C
from state_codec import dump_engine,load_engine


class UnderdogStrengthTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon()
 def pokemon(self,level=35,species='잉어킹',nature=None):
  return self.add(build_pokemon(self.r,species,level,nature=nature,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':8}))
 def teach(self,**options):return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=U.STRENGTH,safe=True,**options)
 def configure(self):
  plan=self.p.spec['initial_allocation'];normal={'species_base':deepcopy(plan['species_base']),'investment':deepcopy(plan['investment'])}
  alternate=deepcopy(normal)
  for stat in B.STATS:
   if stat!='hp':alternate['species_base'][stat]+=100
  return self.e.configure_growth_forms(self.p,{'normal':normal,'alternate':alternate},active='normal',source='combat/struggle')
 def test_actual_csv_hour_tp_and_native_composition_preserve_allocated_points(self):
  old=GS.project(self.r,self.p.spec);stats=deepcopy(self.p.stats);hp=self.p.hp
  raw=deepcopy(species_lookup(self.r,self.p.spec['species'])['base_stats'])
  with patch.object(C,'derive',wraps=C.derive) as shared:out=self.teach()
  self.assertTrue(any(any(row.get('source')==U.STRENGTH for row in call.args[1]) for call in shared.call_args_list))
  now=self.e.growth_stat_projection(self.p)['permanent']
  self.assertEqual(now['investment'],old['investment']);self.assertEqual(now['species_base'],raw)
  self.assertEqual(now['nature_delta'],dict.fromkeys(B.STATS,0))
  self.assertEqual(self.p.stats,{st:value+1 for st,value in stats.items()})
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds,self.p.hp),(7,3600,hp))
  self.assertEqual(out['definition_origin']['record'],26)
  self.assertEqual(species_lookup(self.r,self.p.spec['species'])['base_stats'],raw)
 def test_duplicate_and_missing_level_capability_balance_or_owner_refuse_before_cost(self):
  self.teach();before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
  for kind in ('level','capability','balance','owner'):
   self.setUp()
   if kind=='level':self.e.gm.set_level(self.p,14,reason='actual correction')
   if kind=='capability':G.replace_baseline(self.e,self.p,'capabilities',[])
   if kind=='balance':self.p.spec['tutor_points']=0
   if kind=='owner':self.p.spec['trainer_id']=self.p.entity_id
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
 def test_low_catalog_sum_does_not_invent_underdog_capability(self):
  G.replace_baseline(self.e,self.p,'capabilities',[]);before=self.snap()
  self.assertLess(sum(species_lookup(self.r,self.p.spec['species'])['base_stats'].values()),45)
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_native_evolution_and_options_respect_real_strength_receipt(self):
  self.assertIn('갸라도스',dict(D.evolution_options(self.r,self.p.spec)));self.teach()
  self.assertEqual(D.evolution_options(self.r,self.p.spec),[]);before=deepcopy(self.p.spec)
  out=D.evolve_combatant(self.e,self.p,'갸라도스')
  self.assertFalse(out['evolved']);self.assertEqual(self.p.spec,before)
 def test_native_levelup_adds_one_allocated_point_without_reapplying_base_bonus(self):
  self.teach();old=GS.project(self.r,self.p.spec);stats=deepcopy(self.p.stats)
  D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={36:'spe'})
  now=self.e.growth_stat_projection(self.p)['permanent']
  self.assertEqual(now['investment'],{st:v+int(st=='spe') for st,v in old['investment'].items()})
  self.assertEqual(self.p.stats,{st:v+int(st=='spe') for st,v in stats.items()})
 def test_bonus_precedes_real_nature_and_is_separate_from_its_delta(self):
  import nature_state as N
  nature=next(name for name in self.r.mech('pokemon/natures')['by_name'] if not N.describe(self.r,name)['neutral'])
  self.p=self.pokemon(nature=nature);raw=deepcopy(self.p.spec['initial_allocation']['species_base']);self.teach()
  out=GS.project(self.r,self.p.spec);effective={st:value+1 for st,value in raw.items()}
  expected=nature_base(effective,nature,self.r)
  self.assertEqual(out['nature_base'],expected)
  self.assertEqual(out['nature_delta'],{st:expected[st]-effective[st] for st in B.STATS})
  proposal=self.e.plan_growth_nature(self.p,nature)
  self.assertEqual(proposal['permanent_stats'],self.p.spec['stats'])
 def test_prerequisite_loss_refunds_once_removes_only_source_and_does_not_reactivate(self):
  original=deepcopy(self.p.stats);self.teach();G._source(self.p,'boost','feature',rule_id='combat/struggle');G.stat(self.p,'atk',3,'boost')
  G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual(self.p.stats,{st:value+3*int(st=='atk') for st,value in original.items()})
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertEqual(U.records(self.p.spec)[0]['status'],'refunded')
  G.replace_baseline(self.e,self.p,'capabilities',['약골']);G.transition(self.e,self.p,lambda e,c:None)
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertFalse(U.blocks_evolution(self.r,self.p.spec))
 def test_gm_level_loss_keeps_other_allocations_and_releases_evolution_prohibition(self):
  self.teach();investment=GS.project(self.r,self.p.spec)['investment'];self.e.gm.set_level(self.p,14,reason='actual corrected level')
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertFalse(U.blocks_evolution(self.r,self.p.spec))
  self.assertEqual(GS.project(self.r,self.p.spec)['investment'],investment)
 def test_inactive_form_base_and_growth_share_same_source_without_double_bonus(self):
  self.configure();old=deepcopy(self.p.spec['form_growth_allocations']);self.teach()
  for name in ('alternate','normal','alternate'):
   FORMS.switch(self.e,self.p,name);out=self.e.growth_stat_projection(self.p)['permanent']
   self.assertEqual(out['investment'],old['plans'][name]['investment'])
   self.assertEqual(out['stats'],{st:v+1 for st,v in old['plans'][name]['stats'].items()})
  D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={36:'spe'})
  for name in ('normal','alternate'):
   FORMS.switch(self.e,self.p,name);out=GS.project(self.r,self.p.spec)
   self.assertEqual(sum(out['investment'].values()),46)
   self.assertEqual(out['stats']['spe'],old['plans'][name]['stats']['spe']+2)
 def test_active_and_refunded_source_survive_json_and_gm_restore(self):
  self.teach();snapshot=self.e.gm.snapshot();G.replace_baseline(self.e,self.p,'capabilities',[])
  self.e.gm.restore(snapshot);self.p=next(a for a in self.e.gm.everyone if a.entity_id==self.p.entity_id)
  self.assertTrue(U.blocks_evolution(self.r,self.p.spec));self.assertEqual(self.p.spec['tutor_points'],7)
  loaded=self.restored();child=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
  self.assertEqual(loaded.growth_stat_projection(child)['permanent']['stats'],self.p.spec['stats'])
  G.replace_baseline(loaded,child,'capabilities',[])
  again=load_engine(self.r,dump_engine(loaded));child=next(a for a in again.gm.everyone if a.entity_id==child.entity_id)
  self.assertEqual(child.spec['tutor_points'],8);self.assertFalse(U.blocks_evolution(self.r,child.spec))
 def test_late_native_migration_failure_rolls_back_hour_payment_stats_and_world(self):
  before=self.snap();native=U.migrate
  def fail(*args,**kwargs):native(*args,**kwargs);raise ValueError('late Underdog migration failure')
  with patch.object(U,'migrate',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late Underdog'):self.teach()
  self.assertEqual(self.snap(),before)
 def test_grooming_hour_credit_is_shared(self):
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True);out=self.teach(from_grooming=True)
  self.assertEqual((self.e.elapsed_seconds,out['seconds'],self.p.spec['tutor_points']),(3600,0,7))
 def test_tampered_origin_or_allocation_evidence_cannot_be_saved(self):
  self.teach();origin=deepcopy(U.records(self.p.spec)[0]['definition_origin'])
  U.records(self.p.spec)[0]['definition_origin']['record']=27
  with self.assertRaises(ValueError):dump_engine(self.e)
  U.records(self.p.spec)[0]['definition_origin']=origin
  self.p.spec['allocation_migrations'][-1]['plan']['investment']['atk']+=1
  with self.assertRaises(ValueError):dump_engine(self.e)
 def test_excluded_definition_refuses_without_hour_or_tp(self):
  previous=self.r.selection.excluded.get(U.STRENGTH);self.r.selection.excluded[U.STRENGTH]='exclude_units'
  try:
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
  finally:
   if previous is None:self.r.selection.excluded.pop(U.STRENGTH,None)
   else:self.r.selection.excluded[U.STRENGTH]=previous


class RealizedPotentialTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from engine import Rules
  from pathlib import Path
  cls.r=Rules(Path(__file__).resolve().parents[1],ruleset='all')
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon()
 def pokemon(self,level=35,species='잉어킹'):
  return self.add(build_pokemon(self.r,species,level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':8}))
 def choice(self,source=U.POTENTIAL,*,amount=None):
  old=GS.project(self.r,self.p.spec);points=U.species_points(self.r,self.p.spec['species']) if amount is None else amount
  out=GS.allocate(old['species_base'],sum(old['investment'].values()),investment=old['investment'],nature=self.p.spec.get('nature'),rules=self.r,
   base_sources=U.base_sources(self.r,self.p.spec),point_budgets=[{'source':source,'points':points}])
  return out['point_sources'][0]['values']
 def decision(self,value,source=U.POTENTIAL,*,species=None):
  pending=self.e.underdog_bonus_policy(self.p,source,species=species)
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  return {'value':value,'reason':'explicit host choice for the actual negative formula','scope':pending['decision_scope']}
 def teach(self,source=U.POTENTIAL,**options):
  if 'growth' not in options:options['growth']=self.choice(source)
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=source,safe=True,**options)
 def test_native_cost_hour_and_explicit_bonus_investment_keep_catalog_and_ordinary_points(self):
  before=GS.project(self.r,self.p.spec);choice=self.choice()
  with patch.object(GS,'compose',wraps=GS.compose) as common:out=self.teach(growth=choice)
  self.assertTrue(any(call.kwargs.get('point_sources') for call in common.call_args_list))
  now=self.e.growth_stat_projection(self.p)['permanent']
  self.assertEqual((out['bonus_points'],self.p.spec['tutor_points'],self.e.elapsed_seconds),(24,6,3600))
  self.assertEqual(now['species_base'],before['species_base']);self.assertEqual(now['investment'],before['investment'])
  self.assertEqual(now['contributions']['bonus_points'],choice)
  self.assertEqual(now['stats'],{st:v+choice[st] for st,v in before['stats'].items()})
  self.assertFalse(U.blocks_evolution(self.r,self.p.spec))
 def test_main_and_homebrew_minimum_levels_remain_different(self):
  self.p=self.pokemon(15);before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
  out=self.teach(U.HOMEBREW)
  self.assertEqual((out['definition_origin']['record'],self.p.spec['tutor_points']),(69,6))
  self.p=self.pokemon(30);self.teach();self.assertEqual(self.p.spec['tutor_points'],6)
 def test_missing_capability_owner_balance_or_explicit_choice_refuses_before_cost(self):
  for kind in ('capability','owner','balance','choice'):
   self.setUp()
   if kind=='capability':G.replace_baseline(self.e,self.p,'capabilities',[])
   if kind=='owner':self.p.spec['trainer_id']=self.p.entity_id
   if kind=='balance':self.p.spec['tutor_points']=1
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(growth=None) if kind=='choice' else self.teach()
   self.assertEqual(self.snap(),before)
 def test_bad_point_sum_negative_component_and_base_relation_refuse(self):
  normal=self.choice()
  bad=dict(normal);bad['spe']+=1
  relation=dict.fromkeys(B.STATS,0);relation['atk']=24
  negative=dict(normal);negative['atk']=-100;negative['spe']+=100+normal['atk']
  for choice in (bad,relation,negative,{'hp':24},True):
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(growth=choice)
   self.assertEqual(self.snap(),before)
 def test_alternate_definitions_cannot_stack_or_repay_duplicate(self):
  self.teach();before=self.snap()
  for uid in (U.POTENTIAL,U.HOMEBREW):
   with self.assertRaises(ValueError):self.teach(uid)
   self.assertEqual(self.snap(),before)
 def test_strength_base_bonus_does_not_reduce_raw_species_point_formula(self):
  self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=U.STRENGTH,safe=True)
  old=GS.project(self.r,self.p.spec);out=self.teach()
  self.assertEqual(out['bonus_points'],24)
  now=GS.project(self.r,self.p.spec);self.assertEqual(now['investment'],old['investment'])
  self.assertTrue(U.blocks_evolution(self.r,self.p.spec));self.assertEqual(self.p.spec['tutor_points'],5)
 def test_zero_bonus_species_is_not_given_invented_extra_points(self):
  self.p=self.pokemon(species='야부엉');self.assertEqual(U.species_points(self.r,self.p.spec['species']),0)
  before=deepcopy(self.p.stats);out=self.teach()
  self.assertEqual((out['bonus_points'],self.p.stats,self.p.spec['tutor_points']),(0,before,6))
 def test_actual_next_level_keeps_bonus_segment_and_adds_only_one_ordinary_point(self):
  self.teach();old=GS.project(self.r,self.p.spec)
  D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={36:'spe'})
  now=GS.project(self.r,self.p.spec)
  self.assertEqual(now['contributions']['bonus_points'],old['contributions']['bonus_points'])
  self.assertEqual(now['investment'],{st:v+int(st=='spe') for st,v in old['investment'].items()})
 def test_evolution_below45_recomputes_bonus_from_new_species_without_refund(self):
  self.p=self.pokemon(species='이상해씨');out=self.teach();self.assertEqual(out['bonus_points'],11)
  self.assertTrue(D.evolve_combatant(self.e,self.p,'이상해풀')['evolved'])
  now=GS.project(self.r,self.p.spec);row=U.records(self.p.spec)[0]
  self.assertEqual(sum(B.species_lookup(self.r,'이상해풀')['base_stats'].values()),40)
  self.assertEqual((row['species_points'],row['status'],self.p.spec['tutor_points']),(5,'active',6))
  self.assertEqual(sum(now['investment'].values()),45);self.assertEqual(sum(now['contributions']['bonus_points'].values()),5)
 def test_evolution45_or_more_removes_bonus_and_refunds_exactly_once(self):
  self.teach();self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  self.assertEqual((self.p.spec['tutor_points'],U.records(self.p.spec)[0]['status']),(8,'refunded'))
  self.assertNotIn('bonus_points',GS.project(self.r,self.p.spec)['contributions'])
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],8)
 def test_original_threshold_applies_even_if_another_source_keeps_underdog(self):
  self.teach();G.grant(self.p,'capabilities','약골','observed-underdog','gm_observation',rule_id='capability/약골')
  self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  self.assertTrue(U.owned(self.p));self.assertEqual(U.records(self.p.spec)[0]['status'],'refunded')
 def test_homebrew_retained_underdog_uses_explicit_negative_interpretation_at_evolution(self):
  self.teach(U.HOMEBREW);G.grant(self.p,'capabilities','약골','observed-underdog','gm_observation',rule_id='capability/약골')
  before=self.snap()
  with self.assertRaises(ValueError):D.evolve_combatant(self.e,self.p,'갸라도스')
  self.assertEqual(self.snap(),before)
  decision=self.decision('signed_points',U.HOMEBREW,species='갸라도스')
  self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스',underdog_decision=decision)['evolved'])
  row=U.records(self.p.spec)[0];self.assertEqual((row['status'],row['species_points'],self.p.spec['tutor_points']),('active',U.species_points(self.r,self.p.spec['species']),6))
  self.assertLess(row['species_points'],0);self.e.growth_stat_projection(self.p)
 def test_capability_loss_removes_only_bonus_points_and_refunds_two_tp(self):
  original=deepcopy(self.p.stats);self.teach();G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual((self.p.stats,self.p.spec['tutor_points']),(original,8))
  G.replace_baseline(self.e,self.p,'capabilities',['약골']);self.assertEqual(self.p.spec['tutor_points'],8)
  self.assertFalse(any(row['status']=='active' for row in U.records(self.p.spec)))
 def test_nature_and_vitamin_contributions_never_enter_species_point_formula(self):
  self.teach();G.transition(self.e,self.p,lambda e,c:GS.apply_vitamin(c,'atk',source='actual-test-vitamin'))
  now=GS.project(self.r,self.p.spec);self.assertEqual(sum(now['contributions']['bonus_points'].values()),24)
  self.assertEqual(now['contributions']['vitamins']['atk'],1)
  proposal=self.e.plan_growth_nature(self.p,self.p.spec.get('nature'))
  self.assertEqual(proposal['permanent_stats'],self.p.spec['stats'])
  import nature_state as N
  selected=None
  for name in self.r.mech('pokemon/natures')['by_name']:
   if N.describe(self.r,name)['neutral']:continue
   try:self.e.plan_growth_nature(self.p,name)
   except ValueError:continue
   selected=name;break
  self.assertIsNotNone(selected)
  self.e.commit_growth_nature(self.a,self.p,selected,investment=None,source=U.POTENTIAL,
   reason='host-authorized actual Nature change with a bonus source',ap_cost=0,hp_policy='preserve_fraction',request_id='potential/nature')
  now=GS.project(self.r,self.p.spec)
  self.assertEqual(sum(now['contributions']['bonus_points'].values()),24)
  self.assertEqual((now['species_base'],now['contributions']['vitamins']['atk']),(proposal['allocation']['species_base'],1))
 def test_dependent_growth_loss_refuses_atomically_until_explicit_host_reallocation(self):
  bonus=dict.fromkeys(B.STATS,0);bonus['spe']=24;self.teach(growth=bonus)
  for level in range(36,43):D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={level:'def'})
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'base relations'):G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual(self.snap(),before);current=GS.project(self.r,self.p.spec)
  normal=GS.allocate(current['species_base'],sum(current['investment'].values()),rules=self.r)['investment']
  self.e.commit_growth_nature(self.a,self.p,self.p.spec.get('nature'),investment=normal,source=U.POTENTIAL,
   reason='explicit host correction before removing the dependent bonus source',ap_cost=0,hp_policy='preserve_fraction',request_id='potential/prerequisite-correction')
  self.assertEqual(GS.project(self.r,self.p.spec)['contributions']['bonus_points'],bonus)
  balance=self.p.spec['tutor_points'];G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual(self.p.spec['tutor_points'],balance+2);self.assertEqual(U.records(self.p.spec)[0]['status'],'refunded')
  self.assertEqual(GS.project(self.r,self.p.spec)['investment'],normal)
 def test_all_current_forms_receive_explicit_bonus_points_and_native_growth(self):
  plan=self.p.spec['initial_allocation'];decl={'species_base':deepcopy(plan['species_base']),'investment':deepcopy(plan['investment'])}
  self.e.configure_growth_forms(self.p,{'normal':deepcopy(decl),'alternate':deepcopy(decl)},active='normal',source='combat/struggle')
  choice=self.choice();self.teach(growth={'normal':choice,'alternate':deepcopy(choice)})
  D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={36:'spe'})
  for name in ('alternate','normal'):
   FORMS.switch(self.e,self.p,name);now=GS.project(self.r,self.p.spec)
   self.assertEqual((sum(now['investment'].values()),sum(now['contributions']['bonus_points'].values())),(46,24))
  loaded=self.restored();child=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
  FORMS.switch(loaded,child,'alternate');loaded.growth_stat_projection(child)
 def test_live_bonus_receipt_survives_json_and_gm_restore(self):
  self.teach();saved=self.e.gm.snapshot();G.replace_baseline(self.e,self.p,'capabilities',[]);self.e.gm.restore(saved)
  self.p=next(a for a in self.e.gm.everyone if a.entity_id==self.p.entity_id)
  loaded=self.restored();child=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
  self.assertEqual(loaded.growth_stat_projection(child)['permanent']['contributions']['bonus_points'],self.choice())
  self.assertEqual(child.spec['tutor_points'],6)
 def test_native_evolution_migrates_bonus_or_refund_in_every_form(self):
  for old_species,new_species,remaining,status,balance in [('이상해씨','이상해풀',5,'active',6),('잉어킹','갸라도스',0,'refunded',8)]:
   self.setUp();self.p=self.pokemon(species=old_species)
   old=self.p.spec['initial_allocation'];declaration={'species_base':deepcopy(old['species_base']),'investment':deepcopy(old['investment'])}
   self.e.configure_growth_forms(self.p,{'normal':declaration,'alternate':deepcopy(declaration)},active='normal',source='combat/struggle')
   choice=self.choice();self.teach(growth={'normal':choice,'alternate':deepcopy(choice)})
   base=B.species_lookup(self.r,new_species)['base_stats'];plan=GS.allocate(base,45,rules=self.r)
   evolved={'species_base':deepcopy(base),'investment':deepcopy(plan['investment'])}
   self.assertTrue(D.evolve_combatant(self.e,self.p,new_species,form_declarations={'normal':evolved,'alternate':deepcopy(evolved)})['evolved'])
   self.assertEqual((U.records(self.p.spec)[0]['status'],self.p.spec['tutor_points']),(status,balance))
   loaded=self.restored();child=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
   for name in ('alternate','normal'):
    FORMS.switch(loaded,child,name);now=loaded.growth_stat_projection(child)['permanent']
    self.assertEqual(sum(now['investment'].values()),45)
    self.assertEqual(sum(now['contributions'].get('bonus_points',{}).values()),remaining)
 def test_signed_input_cannot_reallocate_ordinary_growth_even_if_final_stats_are_legal(self):
  for species,amount in [('잉어킹',24),('절벼게',-2)]:
   self.setUp();self.p=self.pokemon(species=species);choice=self.choice(amount=amount)
   current=GS.project(self.r,self.p.spec);base=current['species_base']
   donor=(min if amount>0 else max)(base,key=base.get);recipient=(max if amount>0 else min)(base,key=base.get)
   previous=choice[donor];choice[donor]=-1 if amount>0 else 1;choice[recipient]-=choice[donor]-previous
   GS.compose(base,current['investment'],points=sum(current['investment'].values()),rules=self.r,
    point_sources=[{'source':U.POTENTIAL,'values':choice}])
   before=self.snap();options={} if amount>0 else {'negative_decision':self.decision('signed_points')}
   with self.assertRaisesRegex(ValueError,'redistribute ordinary'):self.teach(growth=choice,**options)
   self.assertEqual(self.snap(),before)
 def test_late_evolution_failure_restores_species_bonus_receipt_and_tp(self):
  self.teach();before=self.snap();native=U.commit_evolution
  def fail(*args,**kwargs):native(*args,**kwargs);raise ValueError('late evolution source failure')
  with patch.object(U,'commit_evolution',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late evolution'):D.evolve_combatant(self.e,self.p,'갸라도스')
  self.assertEqual(self.snap(),before)
 def test_tampered_bonus_source_or_budget_cannot_be_saved(self):
  self.teach();row=U.records(self.p.spec)[0];row['bonus_investments']['base']['atk']+=1
  with self.assertRaises(ValueError):dump_engine(self.e)
 def test_actual_negative_species_has_no_unscoped_or_silent_zero_default(self):
  self.p=self.pokemon(species='절벼게');self.assertEqual(U.species_points(self.r,self.p.spec['species']),-2)
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
  decision={'value':'signed_points','reason':'missing declaration scope'}
  with self.assertRaises(ValueError):self.teach(negative_decision=decision)
  self.assertEqual(self.snap(),before)
 def test_signed_and_zero_negative_choices_are_explicit_and_persisted(self):
  for value,amount in (('signed_points',-2),('zero_bonus',0)):
   self.setUp();self.p=self.pokemon(species='절벼게');decision=self.decision(value)
   original=deepcopy(self.p.stats);choice=self.choice(amount=amount);out=self.teach(growth=choice,negative_decision=decision)
   self.assertEqual(out['bonus_points'],amount);self.assertEqual(self.p.stats,{st:n+choice[st] for st,n in original.items()})
   loaded=self.restored();child=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
   loaded.growth_stat_projection(child);self.assertEqual(U.records(child.spec)[0]['negative_policy']['values']['selected'],value)
 def test_ineligible_negative_choice_refuses_and_another_actor_cannot_reuse_decision(self):
  self.p=self.pokemon(species='절벼게');decision=self.decision('unavailable');before=self.snap()
  with self.assertRaises(ValueError):self.teach(negative_decision=decision)
  self.assertEqual(self.snap(),before)
  decision=self.decision('signed_points');self.p=self.pokemon(species='절벼게');before=self.snap()
  with self.assertRaises(ValueError):self.teach(negative_decision=decision)
  self.assertEqual(self.snap(),before)


if __name__=='__main__':unittest.main()
