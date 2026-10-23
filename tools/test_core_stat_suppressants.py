"""C09-040/075: current-owner choice and permanent stats through native intake."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_medicine_stock as FIX
from builder import build_trainer
from engine import Combatant
import vitamin_moves as V,move_state as M,food_effects as FOOD
import state_grants as G,form_allocations as FORMS
import common_checks as C,pokemon_party as PARTY,builder,pokemon_entities as ENTITIES


class StatSuppressantTests(unittest.TestCase):
 setUpClass=classmethod(FIX.MedicineStockTests.setUpClass.__func__)
 add=FIX.MedicineStockTests.add
 held=FIX.MedicineStockTests.held
 restored=FIX.MedicineStockTests.restored
 snap=FIX.MedicineStockTests.snap

 def setUp(self):
  FIX.MedicineStockTests.setUp(self)
  self.p.spec['trainer_id']=self.a.entity_id
  self.other=Combatant(self.r,build_trainer(self.r,'Other actual owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
  self.e.gm.add_combatant(self.other,pos=(2,2),side='party',reason='actual independent owner')
  self.a.spec['items']={V.SUPPRESSANT:12,'타우린':8,**dict.fromkeys(V.SUPPRESSANT_BERRIES,2)}

 def dose(self,stat='atk',**options):
  return self.e.use_item(self.a,V.SUPPRESSANT,self.p,selected_stat=stat,owner_consent_by=self.a,**options)

 def berry(self,uid='item/시마열매',physical=False,**options):
  if physical:self.held(self.p,uid,'berry')
  return self.e.use_item(self.p if physical else self.a,uid,self.p,duration_minutes=1,duration_reason='actual Extended berry intake',
                         held_selection='berry' if physical else None,**options)

 def exchange(self,*,owner=None,**options):
  return self.e.consume_food_buff(self.p,buff_id=self.p.buffs[0]['id'],action_kind='free',
                                  action_reason='actual current owner requested stat suppression',
                                  owner_consent_by=owner,**options)

 def test_all_six_selected_stats_and_real_dose_stock_change_only_permanent_base_and_hp(self):
  cases=[(stat,False) for stat in V.STAT_BY_ITEM.values()]+[('atk',True)]
  for stat,physical in cases:
   with self.subTest(stat=stat,physical=physical):
    self.setUp();before=deepcopy(self.p.spec['stats']);runtime=deepcopy(self.p.stats);hp=self.p.base_max_hp
    if physical:self.held(self.a,V.SUPPRESSANT,'suppressant')
    self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a)
    self.assertEqual(self.dose(stat,held_selection='suppressant' if physical else None),(1,0))
    before[stat]-=1;runtime[stat]-=1
    self.assertEqual((self.p.spec['stats'],self.p.stats),(before,runtime))
    self.assertEqual(self.p.base_max_hp,hp-(3 if stat=='hp' else 0))
    self.assertEqual(self.a.spec['items'][V.SUPPRESSANT],12 if physical else 11)
    self.assertEqual(self.a.budget['standard'],0)
    self.assertEqual(self.p.spec['vitamins'],[V.SUPPRESSANT]);self.assertEqual(self.p.spec['vitamin_bonus'][stat],-1)
    if physical:self.assertIn('consumed',self.e._physical_objects['suppressant'])
    row=self.p.spec['stat_history'][-1]
    self.assertEqual((row['source'],row['owner_id'],row['actor_id'],row['stat'],row['delta']),
                     (V.SUPPRESSANT,self.a.entity_id,self.p.entity_id,stat,-1))
    self.assertEqual(self.e.growth_stat_projection(self.p)['permanent']['stats'],before)
    self.assertTrue(self.e.validate_state()['valid'])

 def test_positive_doses_are_retained_and_suppressant_uses_the_same_five_cap(self):
  initial=self.p.spec['stats']['atk']
  self.assertEqual(self.e.use_item(self.a,'타우린',self.p),(1,0));self.assertEqual(self.dose(),(1,0))
  self.assertEqual(self.p.spec['stats']['atk'],initial)
  self.assertEqual(self.p.spec['vitamins'],['item/타우린',V.SUPPRESSANT])
  for _ in range(3):self.e.use_item(self.a,'타우린',self.p)
  before=deepcopy(self.p.spec);stock=self.a.spec['items'][V.SUPPRESSANT]
  self.assertEqual(self.dose(),(0,0));self.assertEqual(self.p.spec,before)
  self.assertEqual(self.a.spec['items'][V.SUPPRESSANT],stock-1)
  self.assertEqual(M.vitamin_state(self.r,self.p.spec)['occupied'],5)
  self.berry();self.assertEqual(self.exchange(owner=self.a)['delta'],-1)
  self.assertEqual(self.p.spec['vitamins'],before['vitamins'])
  self.assertEqual(M.vitamin_state(self.r,self.p.spec)['occupied'],5)

 def test_owner_absence_is_consumed_no_effect_but_refusal_and_false_owner_do_not_pay(self):
  before=deepcopy(self.p.spec);stock=self.a.spec['items'][V.SUPPRESSANT]
  result=self.e.use_item(self.a,V.SUPPRESSANT,self.p,selected_stat='atk')
  self.assertEqual(result,{'status':'consumed','outcome':'no_effect','reason':'owner_consent_missing'})
  self.assertEqual(self.p.spec,before);self.assertEqual(self.a.spec['items'][V.SUPPRESSANT],stock-1)
  for options in ({'owner_consent_by':self.other},{'owner_consent_by':self.a,'selected_stat':'chosen'},
                  {'owner_consent_by':self.a,'selected_stat':True}):
   request={'selected_stat':'atk',**options};snap=self.snap()
   with self.assertRaises(ValueError):self.e.use_item(self.a,V.SUPPRESSANT,self.p,**request)
   self.assertEqual(self.snap(),snap)
  stock=self.a.spec['items'][V.SUPPRESSANT];before=deepcopy(self.p.spec)
  self.assertEqual(self.dose(accepted=False),(0,0));self.assertEqual(self.p.spec,before)
  self.assertEqual(self.a.spec['items'][V.SUPPRESSANT],stock)

 def test_six_berries_use_extended_food_then_owner_gated_buff_without_a_vitamin_slot(self):
  cases=[(uid,stat,False) for uid,stat in V.SUPPRESSANT_BERRIES.items()]+[('item/시마열매','atk',True)]
  for uid,stat,physical in cases:
   with self.subTest(uid=uid,physical=physical):
    self.setUp();before=deepcopy(self.p.spec['stats']);at=self.e.elapsed_seconds
    result=self.berry(uid,physical=physical)
    self.assertEqual(result['status'],'digestion_buff_gained');self.assertEqual(self.e.elapsed_seconds,at+60)
    self.assertEqual(self.p.spec['stats'],before);self.assertEqual(self.a.spec['items'][uid],2 if physical else 1)
    if physical:self.assertIn('consumed',self.e._physical_objects['berry'])
    snap=self.snap();self.assertIsInstance(self.exchange(),C.PendingDecision);self.assertEqual(self.snap(),snap)
    with self.assertRaisesRegex(ValueError,'current owner'):self.exchange(owner=self.other)
    self.assertEqual(self.snap(),snap)
    self.assertEqual(self.p.hp,self.p.base_max_hp)
    effect=self.exchange(owner=self.a);before[stat]-=1
    self.assertEqual((effect['delta'],effect['owner_id']),(-1,self.a.entity_id))
    self.assertEqual(self.p.spec['stats'],before);self.assertFalse(self.p.buffs)
    self.assertEqual(self.p.spec.get('vitamins',[]),[])
    self.assertEqual(self.p.spec['food_consumption_receipts'][-1]['benefit']['owner_id'],self.a.entity_id)
    self.assertTrue(self.e.validate_state()['valid'])

 def test_berry_choice_rechecks_current_owner_after_native_transfer_and_restore(self):
  self.berry()
  PARTY.configure(self.e,self.a,mode='unlimited',reason='existing actual ownership',roster=[self.p])
  PARTY.configure(self.e,self.other,mode='unlimited',reason='new actual owner',roster=[])
  choice=self.e.consume_food_buff(self.p,buff_id=self.p.buffs[0]['id'],move_id=FOOD.STUFF_CHEEKS,owner_consent_by=self.a)
  self.assertEqual(choice['status'],'prepared_for_actual_move')
  PARTY.transfer(self.e,self.a,target=self.p,new_owner=self.other,reason='observed native ownership transfer',request_id='suppression/transfer')
  loaded=self.restored();p=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
  old=next(a for a in loaded.gm.everyone if a.entity_id==self.a.entity_id)
  new=next(a for a in loaded.gm.everyone if a.entity_id==self.other.entity_id)
  before=deepcopy(p.spec['stats'])
  with self.assertRaisesRegex(ValueError,'current owner'):FOOD.move_consumption_plan(loaded,p,FOOD.STUFF_CHEEKS)
  with self.assertRaisesRegex(ValueError,'current owner'):
   loaded.consume_food_buff(p,buff_id=p.buffs[0]['id'],action_kind='free',action_reason='stale owner',owner_consent_by=old)
  self.assertEqual(p.spec['stats'],before)
  result=loaded.consume_food_buff(p,buff_id=p.buffs[0]['id'],action_kind='free',action_reason='new actual owner',owner_consent_by=new)
  self.assertEqual(result['owner_id'],new.entity_id);self.assertFalse(p.buffs)
  loaded.use_item(old,'item/시마열매',p,duration_minutes=1,duration_reason='actual Extended intake for native Move')
  buff_id=p.buffs[0]['id'];before=p.spec['stats']['atk']
  choice=loaded.consume_food_buff(p,buff_id=buff_id,move_id=FOOD.STUFF_CHEEKS,owner_consent_by=new)
  self.assertEqual(choice['status'],'prepared_for_actual_move')
  ENTITIES.observe_loyalty(loaded,p,2,reason='GM observed current owner loyalty before actual Move')
  p.moves=[FOOD.STUFF_CHEEKS];loaded.start_round([p]);loaded.start_of_turn(p)
  result=loaded.use_move(p,p,FOOD.STUFF_CHEEKS);self.assertNotIsInstance(result,C.PendingDecision)
  self.assertEqual(p.spec['stats']['atk'],before-1);self.assertFalse(p.buffs)
  self.assertEqual(p.stages['def'],2);self.assertEqual(p.budget['standard'],0)
  self.assertNotIn('food_move_choice',p.spec)
  receipt=p.spec['food_consumption_receipts'][-1]
  self.assertEqual((receipt['buff_id'],receipt['producer'],receipt['benefit']['owner_id'],receipt['benefit']['delta']),
                   (buff_id,FOOD.STUFF_CHEEKS,new.entity_id,-1))

 def test_signed_form_contribution_survives_switch_growth_and_both_restore_paths(self):
  plan=self.p.spec['initial_allocation']
  normal={'species_base':deepcopy(plan['species_base']),'investment':deepcopy(plan['investment'])}
  alternate=deepcopy(normal)
  for stat in alternate['species_base']:
   if stat!='hp':alternate['species_base'][stat]+=100
  self.e.configure_growth_forms(self.p,{'normal':normal,'alternate':alternate},active='normal',source='combat/struggle')
  original=deepcopy(self.p.spec['form_growth_allocations'])
  G._source(self.p,'independent-stat-source','feature',rule_id='combat/struggle');G.stat(self.p,'atk',3,'independent-stat-source')
  self.dose();self.berry('item/유석열매');self.exchange(owner=self.a)
  self.assertEqual(self.p.spec['form_growth_allocations'],original)
  snapshot=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(snapshot)
  for engine in (self.e,loaded):
   p=next(a for a in engine.gm.everyone if a.entity_id==self.p.entity_id)
   for form in ('alternate','normal'):
    FORMS.switch(engine,p,form);projection=engine.growth_stat_projection(p)
    self.assertEqual(projection['permanent']['investment'],original['plans'][form]['investment'])
    self.assertEqual(projection['permanent']['contributions']['vitamins']['atk'],-1)
    self.assertEqual(projection['permanent']['contributions']['vitamins']['hp'],-1)
    self.assertEqual(projection['effective_stats']['atk'],original['plans'][form]['stats']['atk']+2)
   import downtime as D
   D.gain_exp_combatant(engine,p,'to next level',stat_choices={p.level+1:'spe'})
   self.assertEqual(engine.growth_stat_projection(p)['permanent']['contributions']['vitamins']['hp'],-1)
   self.assertTrue(engine.validate_state()['valid'])

 def test_minimum_base_stat_and_late_berry_failure_preserve_buff_stats_and_action(self):
  uid='item/시마열매';self.a.spec['items'][uid]=100
  while self.p.spec['stats']['atk']>1:
   self.berry(uid);self.exchange(owner=self.a)
  self.berry(uid);before=self.snap()
  with self.assertRaises(ValueError):self.exchange(owner=self.a)
  self.assertEqual(self.snap(),before)
  self.setUp();self.berry();before=self.snap();native=builder.record_allocation
  def fail_after_record(*args,**kwargs):
   native(*args,**kwargs)
   raise ValueError('injected new berry stat receipt failure')
  with patch.object(builder,'record_allocation',side_effect=fail_after_record):
   with self.assertRaisesRegex(ValueError,'berry stat receipt'):self.exchange(owner=self.a)
  self.assertEqual(self.snap(),before)
  self.assertEqual(self.exchange(owner=self.a)['status'],'consumed')

 def test_source_catalog_price_and_selected_payload_corrections_are_narrow(self):
  effects,header=self.r.item_effects(V.SUPPRESSANT)
  self.assertEqual((header['id'],header['price'],header['use']),(V.SUPPRESSANT,500,'consumable'))
  self.assertEqual(effects,[{'type':'stat_base_mod','stat':'chosen','value':-1,'target':'target','vitamin':True}])
  native=self.r.item_effects
  def corrupt(name):
   effects,header=native(name)
   if header.get('id')==V.SUPPRESSANT:effects=deepcopy(effects);effects[0]['value']=True
   return effects,header
  before=self.snap()
  with patch.object(self.r,'item_effects',side_effect=corrupt):
   with self.assertRaisesRegex(ValueError,'reviewed exact effect'):self.dose()
  self.assertEqual(self.snap(),before)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'Pokemon'):self.e.use_item(self.a,V.SUPPRESSANT,self.a,selected_stat='hp',owner_consent_by=self.a)
  self.assertEqual(self.snap(),before)


if __name__=='__main__':unittest.main()
