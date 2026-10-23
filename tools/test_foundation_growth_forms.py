from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import form_allocations as F,state_grants as G
from state_codec import dump_engine,load_engine

class GrowthFormTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self):
  self.e=Engine(self.r);self.c=Combatant(self.r,build_pokemon(self.r,'잉어킹',5,moves=[],abilities=[]));self.e.everyone=self.e.gm.everyone=[self.c]
  plan=self.c.spec['initial_allocation'];normal={'species_base':deepcopy(plan['species_base']),'investment':deepcopy(plan['investment'])}
  alternate=deepcopy(normal)
  for stat in alternate['species_base']:
   if stat!='hp':alternate['species_base'][stat]+=100
  self.forms={'normal':normal,'alternate':alternate}
 def configure(self):return self.e.configure_growth_forms(self.c,self.forms,active='normal',source='combat/struggle')
 def test_switch_preserves_investment_and_applies_shared_source_once(self):
  self.configure();c=self.c;G._source(c,'boost','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'boost')
  original=deepcopy(c.spec['form_growth_allocations'])
  for form in ('alternate','normal','alternate'):
   F.switch(self.e,c,form);out=self.e.growth_stat_projection(c)
   self.assertEqual(out['permanent']['form'],form);self.assertEqual(sum(out['permanent']['investment'].values()),15)
   self.assertEqual(out['effective_stats']['atk'],out['permanent']['stats']['atk']+3)
  self.assertEqual(c.spec['form_growth_allocations'],original)
  loaded=load_engine(self.r,dump_engine(self.e));owner=loaded.everyone[0]
  F.switch(loaded,owner,'normal');self.assertEqual(loaded.growth_stat_projection(owner)['permanent']['form'],'normal')
 def test_provider_hp_exception_survives_forms_without_authorizing_future_growth(self):
  import growth_stats as GS,downtime as D
  c=self.c;base=deepcopy(c.spec['initial_allocation']['species_base'])
  higher=min((k for k in base if base[k]>base['hp']),key=lambda k:base[k])
  investment=dict.fromkeys(base,0);investment['hp']=base[higher]-base['hp']-1
  investment[max(base,key=base.get)]=15-investment['hp']
  plan=GS.compose(base,investment,points=15,rules=self.r)
  spec=deepcopy(c.spec);spec['stats']=deepcopy(plan['stats']);spec['initial_allocation']=plan
  self.c=c=Combatant(self.r,spec)
  owner=Combatant(self.r,{'id':'growth/provider','name':'provider','kind':'trainer','level':10,
   'stats':dict.fromkeys(base,10),'classes':['class/불굴의-투지']})
  c.spec['trainer_id']=owner.entity_id;self.e.everyone=self.e.gm.everyone=[c,owner]
  declaration={'species_base':base,'investment':investment}
  self.e.configure_growth_forms(c,{'normal':declaration,'alternate':deepcopy(declaration)},active='normal',source='combat/struggle')
  D.gain_exp_combatant(self.e,c,'to next level',stat_choices={6:'hp'})
  for plan in c.spec['form_growth_allocations']['plans'].values():
   self.assertTrue(plan['relation_bounds']);self.assertEqual(plan['stats']['hp'],plan['stats'][higher])
   self.assertEqual(plan['relation_bounds'][0]['provider']['trainer_id'],owner.entity_id)
  owner.spec['classes']=[]
  loaded=load_engine(self.r,dump_engine(self.e));c=loaded.everyone[0]
  F.switch(loaded,c,'alternate');loaded.growth_stat_projection(c)
  before=dump_engine(loaded)
  with self.assertRaisesRegex(ValueError,'base relations'):
   D.gain_exp_combatant(loaded,c,'to next level',stat_choices={7:'hp'})
  self.assertEqual(dump_engine(loaded),before)
  D.gain_exp_combatant(loaded,c,'to next level',stat_choices={7:max(base,key=base.get)})
  self.assertEqual(c.level,7);self.assertNotIn('stat_relation_exempt',c.spec)

 def test_wrong_budget_or_inactive_form_drift_rejected_atomically(self):
  before=dump_engine(self.e);self.forms['alternate']['investment']['atk']+=1
  with self.assertRaisesRegex(ValueError,'budget'):self.configure()
  self.assertEqual(dump_engine(self.e),before);self.forms['alternate']['investment']['atk']-=1;self.configure()
  before=dump_engine(self.e)
  def mutate(e,c):c.spec['form_allocations']['forms']['alternate']['atk']+=1
  with self.assertRaisesRegex(ValueError,'untracked form'):G.transition(self.e,self.c,mutate)
  self.assertEqual(dump_engine(self.e),before)

 def test_all_form_nature_commit_preserves_switching_and_receipt(self):
  import nature_state as N
  self.configure();nature=None
  for name in self.r.mech('pokemon/natures')['by_name']:
   if N.describe(self.r,name)['neutral']:continue
   try:self.e.plan_growth_nature(self.c,name)
   except ValueError:continue
   nature=name;break
  self.assertIsNotNone(nature)
  old=deepcopy(self.c.spec['form_growth_allocations']);args=dict(investment=None,source='combat/struggle',reason='all-form migration',ap_cost=0,hp_policy='preserve_fraction',request_id='form/nature')
  self.e.commit_growth_nature(self.c,self.c,nature,**args)
  self.assertEqual(self.c.spec['form_growth_history'][0]['previous'],old)
  for form in ('alternate','normal'):
   F.switch(self.e,self.c,form);out=self.e.growth_stat_projection(self.c)
   self.assertEqual(sum(out['permanent']['investment'].values()),15)
   self.assertEqual(self.c.spec['form_growth_allocations']['nature'],nature)
  before=dump_engine(self.e);self.assertTrue(self.e.commit_growth_nature(self.c,self.c,nature,**args)['replayed']);self.assertEqual(dump_engine(self.e),before)
 def test_one_invalid_form_nature_investment_rolls_back_every_form(self):
  self.configure();investments={name:deepcopy(row['investment']) for name,row in self.c.spec['form_growth_allocations']['plans'].items()}
  investments['alternate']['atk']+=1;before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'budget'):
   self.e.commit_growth_nature(self.c,self.c,None,investment=investments,source='combat/struggle',reason='invalid alternate',ap_cost=0,hp_policy='preserve_fraction',request_id='invalid')
  self.assertEqual(dump_engine(self.e),before)

 def test_native_level_growth_updates_every_form_and_survives_restore(self):
  import downtime as D
  self.configure();c=self.c
  G._source(c,'growth-boost','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'growth-boost')
  before=deepcopy(c.spec['form_growth_allocations'])
  D.gain_exp_combatant(self.e,c,'to next level',stat_choices={6:'spe'})
  self.assertEqual(c.level,6);record=c.spec['form_growth_allocations']
  self.assertEqual(record['budget'],16);self.assertEqual(record['level'],6)
  self.assertEqual(c.spec['form_growth_history'][-1]['previous'],before)
  for name,plan in record['plans'].items():
   self.assertEqual(plan['investment']['spe'],before['plans'][name]['investment']['spe']+1)
   self.assertEqual(sum(plan['investment'].values()),16)
  loaded=load_engine(self.r,dump_engine(self.e));owner=loaded.everyone[0]
  for form in ('alternate','normal','alternate'):
   F.switch(loaded,owner,form);out=loaded.growth_stat_projection(owner)
   self.assertEqual(sum(out['permanent']['investment'].values()),16)
   self.assertEqual(out['effective_stats']['atk'],out['permanent']['stats']['atk']+3)
  D.gain_exp_combatant(loaded,owner,'to next level',stat_choices={7:'spe'})
  self.assertEqual(owner.spec['form_growth_allocations']['budget'],17)

 def test_failed_inactive_form_growth_leaves_xp_and_every_form_unchanged(self):
  from unittest.mock import patch
  import downtime as D,growth_stats as GS
  self.configure();before=dump_engine(self.e);native=GS.increment
  def reject_inactive(rules,spec,*args,**kwargs):
   if kwargs.get('_base_stats',{}).get('atk',0)>100:raise ValueError('inactive form growth rejected')
   return native(rules,spec,*args,**kwargs)
  with patch.object(GS,'increment',side_effect=reject_inactive):
   with self.assertRaisesRegex(ValueError,'inactive form'):
    D.gain_exp_combatant(self.e,self.c,'to next level',stat_choices={6:'spe'})
  self.assertEqual(dump_engine(self.e),before)

 def test_conflicting_hp_growth_rolls_back_all_forms(self):
  from unittest.mock import patch
  import downtime as D,growth_stats as GS
  self.configure();before=dump_engine(self.e);native=GS.increment
  def different_choices(rules,spec,points,strategy,choice,**kwargs):
   chosen='spe' if kwargs.get('_base_stats',{}).get('atk',0)>100 else 'hp'
   return native(rules,spec,points,strategy,chosen,**kwargs)
  with patch.object(GS,'increment',side_effect=different_choices):
   with self.assertRaisesRegex(ValueError,'shared HP'):
    D.gain_exp_combatant(self.e,self.c,'to next level')
  self.assertEqual(dump_engine(self.e),before)

 def vitamin_owner(self):
  from builder import build_trainer
  import vitamin_moves as V
  owner=Combatant(self.r,build_trainer(self.r,'Vitamin owner',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'items':dict.fromkeys(V.STAT_ITEMS,2)}))
  self.e.everyone.append(owner)
  return owner

 def test_vitamin_updates_all_forms_without_spending_investment(self):
  import vitamin_moves as V,downtime as D
  self.configure();owner=self.vitamin_owner();c=self.c
  G._source(c,'vitamin-boost','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'vitamin-boost')
  old=deepcopy(c.spec['form_growth_allocations']);uid=next(k for k,v in V.STAT_BY_ITEM.items() if v=='atk')
  self.assertEqual(self.e.use_item(owner,uid,c),(1,0))
  self.assertEqual(owner.spec['items'][uid],1);self.assertEqual(c.spec['vitamins'],[uid])
  self.assertEqual(c.spec['form_growth_allocations'],old)
  for name in ('alternate','normal','alternate'):
   F.switch(self.e,c,name);out=self.e.growth_stat_projection(c)
   self.assertEqual(out['permanent']['investment'],old['plans'][name]['investment'])
   self.assertEqual(out['permanent']['contributions']['vitamins']['atk'],1)
   self.assertEqual(out['effective_stats']['atk'],old['plans'][name]['stats']['atk']+4)
  loaded=load_engine(self.r,dump_engine(self.e));c=loaded.everyone[0]
  D.gain_exp_combatant(loaded,c,'to next level',stat_choices={6:'spe'})
  for name in ('normal','alternate'):
   F.switch(loaded,c,name);out=loaded.growth_stat_projection(c)
   self.assertEqual(sum(out['permanent']['investment'].values()),16)
   self.assertEqual(out['permanent']['contributions']['vitamins']['atk'],1)
   self.assertEqual(out['effective_stats']['atk'],out['permanent']['stats']['atk']+3)

 def test_hp_vitamin_keeps_shared_hp_and_one_dose(self):
  import vitamin_moves as V
  self.configure();owner=self.vitamin_owner();old=self.c.base_max_hp
  uid=next(k for k,v in V.STAT_BY_ITEM.items() if v=='hp')
  self.e.use_item(owner,uid,self.c)
  for name in ('alternate','normal'):
   F.switch(self.e,self.c,name)
   self.assertEqual(self.c.base_max_hp,old+3)
   self.assertEqual(sum(self.e.growth_stat_projection(self.c)['permanent']['investment'].values()),15)
  self.assertEqual(owner.spec['items'][uid],1)

 def test_late_vitamin_failure_restores_item_action_and_every_form(self):
  from unittest.mock import patch
  import vitamin_moves as V,vitamin_capacity as CAPACITY
  self.configure();owner=self.vitamin_owner()
  self.e.start_round([owner,self.c]);self.e.start_of_turn(owner)
  before=dump_engine(self.e);uid=next(k for k,v in V.STAT_BY_ITEM.items() if v=='atk')
  with patch.object(CAPACITY,'record',side_effect=ValueError('late dose failure')):
   with self.assertRaisesRegex(ValueError,'late dose'):
    self.e.use_item(owner,uid,self.c)
  self.assertEqual(dump_engine(self.e),before)

 def evolution_setup(self):
  from builder import species_lookup
  import growth_stats as GS
  self.c=Combatant(self.r,build_pokemon(self.r,'잉어킹',20,moves=[],abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c]
  old=self.c.spec['initial_allocation']
  normal={'species_base':deepcopy(old['species_base']),'investment':deepcopy(old['investment'])}
  self.e.configure_growth_forms(self.c,{'normal':normal,'alternate':deepcopy(normal)},active='normal',source='combat/struggle')
  base=species_lookup(self.r,'갸라도스')['base_stats'];plan=GS.allocate(base,30,rules=self.r)
  normal={'species_base':deepcopy(base),'investment':deepcopy(plan['investment'])}
  alternate=deepcopy(normal);alternate['species_base']['atk']+=100
  return {'normal':normal,'alternate':alternate}

 def test_native_evolution_migrates_every_form_preserves_sources_and_history(self):
  import downtime as D
  declarations=self.evolution_setup();c=self.c
  previous=deepcopy(c.spec['form_growth_allocations'])
  G._source(c,'evolution/boost','feature',rule_id='combat/struggle');G.stat(c,'atk',3,'evolution/boost')
  result=D.evolve_combatant(self.e,c,'갸라도스',form_declarations=declarations)
  self.assertTrue(result['evolved']);self.assertEqual(c.spec['form_growth_history'][-1]['previous'],previous)
  self.assertEqual(c.spec['form_growth_allocations']['budget'],30)
  loaded=load_engine(self.r,dump_engine(self.e));c=loaded.everyone[0]
  for name in ('alternate','normal'):
   F.switch(loaded,c,name);out=loaded.growth_stat_projection(c)
   self.assertEqual(out['permanent']['investment'],declarations[name]['investment'])
   self.assertEqual(c.stats['atk'],out['permanent']['stats']['atk']+3)
  before=dump_engine(loaded)
  self.assertFalse(D.evolve_combatant(loaded,c,'갸라도스',form_declarations=declarations)['evolved'])
  self.assertEqual(dump_engine(loaded),before)

 def test_missing_or_invalid_evolution_form_leaves_entire_actor_unchanged(self):
  import downtime as D
  declarations=self.evolution_setup();before=dump_engine(self.e)
  bad=deepcopy(declarations);bad['alternate']['investment']['atk']+=1
  for proposal in (None,{'normal':declarations['normal']},bad):
   with self.assertRaises(ValueError):D.evolve_combatant(self.e,self.c,'갸라도스',form_declarations=proposal)
   self.assertEqual(dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
