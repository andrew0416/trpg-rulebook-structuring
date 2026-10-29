"""All eighteen printed Books, their common study lifetime and native consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
from native_scenario_fixture import assert_rejected_unchanged
import study_books as B
import action_points as AP
import frequency as F
import state_codec as CODEC
import world_entities as W

SKILLS=dict.fromkeys(('일반 지식','의학','오컬트학','포켓몬학','기술학','생존','집중','직감','은신','육상','명령'),6)


class StudyBooksTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

 def setUp(self):
  previous=self.rules.rulings;self.rules.rulings=deepcopy(previous)
  self.addCleanup(setattr,self.rules,'rulings',previous)
  self.fresh()

 def fresh(self):
  self.e=Engine(self.rules,seed=102518)
  self.e.grid=Grid(30,30)
  self.t=self.trainer('reader',(0,0))

 def trainer(self,name,pos):
  c=Combatant(self.rules,{'id':'trainer/'+name,'name':name,'kind':'trainer','level':30,'pos':pos,
   'stats':{'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'skills':dict(SKILLS),
   'classes':['class/연구원'],'feature_choices':{'class/연구원':[['general','apothecary']]},
   'feats':[],'edges':[],'items':{},'money':100000})
  self.e.gm.add_combatant(c,pos=pos,side='party',reason='actual book reader or patient')
  self.e.gm.set_footprint(c,[(0,0)],reason='actual one-cell Trainer')
  return c

 def pokemon(self,name='patient',owner=None,pos=(1,0)):
  p=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',10,name=name,extra={'trainer_id':(owner or self.t).entity_id}))
  self.e.gm.add_combatant(p,pos=pos,side='party',reason='actual owned Pokemon')
  self.e.gm.set_footprint(p,[(0,0)],reason='actual one-cell Pokemon')
  return p

 def book(self,book,rank=2,details=None,edition=None,**study):
  default={'study_manual':{'skill':'은신','use':'lock-picking'},'type_manual':{'type':'풀'},'travel':{'region':'Route 1'},'daycare':{'egg_group':'식물'}}
  identity='book/'+book+'/'+str(len(getattr(self.e,'_physical_objects',{})))
  B.observe(self.e,self.t,identity,book,details=default.get(book,{}) if details is None else details,edition=edition,reason='actual printed Book in hand')
  rows=[]
  for n in range(1,rank+1):rows.append(B.study(self.e,self.t,identity,n,reason='study actual printed rank',**({'during_rest':True} if book=='caretaker' and n==2 else {}),**study))
  return identity,rows

 def rejected(self,fn,reason):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)

 def restore(self,*actors):
  ids=[x.entity_id for x in actors]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=W.actor_index(self.e);self.t=index[self.t.entity_id]
  return [index[uid] for uid in ids]

 def physical(self,actor,item,uid):
  import items as I
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual item body',kind='item_instance',item_rule_id=item,owner_id=actor.entity_id)
  I.equip_held(self.e,actor,item,source_instance_id=uid)
  return uid

 def crafted(self,item,uid,category='몬스터볼'):
  if 'edge/몬스터볼' not in self.t.spec['edges']:self.t.spec['edges'].append('edge/몬스터볼')
  self.t.spec['items']['몬스터볼 공구함']=1
  value={'id':'actual/'+uid,'source':'edge/몬스터볼','output':{'item_id':item,'key':item},
   'requirements':[{'id':'permission','condition':{'kind':'owned','fields':['edges'],'names':['edge/몬스터볼']},'reason':'actual acquired Basic Balls'}],
   'materials':[{'id':'cost','options':[{'kind':'value','category':category,'amount':100,'scrap':True,'money':True}]}],'seconds':60}
  policy={'mode':'create','instance_ids':[uid],'owner_id':self.t.entity_id,'state':'intact','attachments':[]}
  return self.e.craft_recipe(self.t,value,product_policy=policy,event_id=uid,reason='actual paid maker work')

 def test_native_bookworm_pool_source_difference_well_read_substitution_and_recovery(self):
  import trainer_feature_acquisition as A,researcher_fields as R
  self.rules=Rules(ROOT,ruleset='core+errata')
  for edition,expected in [('book',3),('local_csv',2)]:
   with self.subTest(edition=edition):
    self.fresh()
    self.rejected(lambda:A.acquire_static(self.e,self.t,R.BREADTH,acquisition_request_id='invalid/non-education',selection={'edition':edition,'edges':[{'id':edge,'choice':None} for edge in ('edge/강철의-정신','edge/메딕-훈련','edge/브리더')]}),'Education prerequisite')
    self.rejected(lambda:A.acquire_static(self.e,self.t,R.BREADTH,acquisition_request_id='invalid/repeated-core-edge',selection={'edition':edition,'edges':[{'id':'edge/몬스터볼','choice':None} for _ in range(3)]}),'repeat restriction')
    for uid in (R.BREADTH,R.BOOKWORM):A.acquire_static(self.e,self.t,uid,acquisition_request_id=uid,selection={'edition':edition,**({'edges':[{'id':edge,'choice':None} for edge in ('edge/몬스터볼','edge/메딕-훈련','edge/브리더')]} if uid==R.BREADTH else {})})
    self.assertEqual(R.study_points(self.e,self.t)['maximum'],expected)
    A.acquire_static(self.e,self.t,R.WELL_READ,acquisition_request_id='actual/well-read',selection={'edition':edition})
    self.t.spec['skills']['의학']=3
    ap=AP.available(self.t);identity,studies=self.book('traditional_medicine',payment='study')
    self.assertEqual((AP.available(self.t),R.study_points(self.e,self.t)['drained']),(ap,2))
    self.t,=self.restore(self.t);AP.extended_rest(self.t,request_id='actual/bookworm-rest')
    self.assertEqual(R.study_points(self.e,self.t)['drained'],0)
    self.assertFalse(B.active(self.t,'traditional_medicine'))
    B.renew(self.e,self.t,[r['source_id'] for r in studies],payment='study',reason='explicit continued study-point Drains')
    self.assertEqual(R.study_points(self.e,self.t)['drained'],2)

 def test_all_eighteen_physical_texts_have_two_sequential_rank_producers(self):
  self.assertEqual(len(B.BOOKS),18)
  for book in B.BOOKS:
   with self.subTest(book=book):
    self.fresh();before=self.e.elapsed_seconds
    _,rows=self.book(book)
    self.assertTrue(B.active(self.t,book,2))
    self.assertEqual(self.e.elapsed_seconds-before,3600)
    self.assertEqual(self.t.spec['ap_removed'],1 if book=='caretaker' else 2)
    self.assertEqual([r['rank'] for r in rows],[1,2])

 def test_missing_physical_book_skipped_rank_duplicate_and_cost_failure_are_atomic(self):
  self.rejected(lambda:B.study(self.e,self.t,'missing',1,reason='x'),'physical Study Book')
  obj=B.observe(self.e,self.t,'book/one','study_manual',details={'skill':'은신','use':'lock-picking'},reason='actual manual')
  self.rejected(lambda:B.study(self.e,self.t,obj['id'],2,reason='x'),'sequentially')
  B.study(self.e,self.t,obj['id'],1,reason='actual rank one')
  self.rejected(lambda:B.study(self.e,self.t,obj['id'],1,reason='x'),'sequentially')
  AP.charge(self.t,AP.available(self.t),mode='drain')
  self.rejected(lambda:B.study(self.e,self.t,obj['id'],2,reason='x'),'available AP')

 def test_all_eighteen_each_printed_rank_threshold_is_checked_at_the_actual_study_boundary(self):
  defaults={'study_manual':{'skill':'은신','use':'lock-picking'},'type_manual':{'type':'풀'},'travel':{'region':'Route 1'},'daycare':{'egg_group':'식물'}}
  for book,(skill,one,two,_) in B.BOOKS.items():
   with self.subTest(book=book):
    self.fresh();uid='actual/threshold-book'
    B.observe(self.e,self.t,uid,book,details=defaults.get(book,{}),reason='actual printed rank boundary')
    self.t.spec['skills'][skill]=one-1
    self.rejected(lambda:B.study(self.e,self.t,uid,1,reason='below actual printed rank one'),'printed Skill')
    self.t.spec['skills'][skill]=one;B.study(self.e,self.t,uid,1,reason='actual printed rank one')
    self.t.spec['skills'][skill]=two-1
    options={'during_rest':True} if book=='caretaker' else {}
    self.rejected(lambda:B.study(self.e,self.t,uid,2,reason='below actual printed rank two',**options),'printed Skill')
    self.t.spec['skills'][skill]=two;B.study(self.e,self.t,uid,2,reason='actual printed rank two',**options)
    self.assertTrue(B.active(self.t,book,2))

 def test_actual_rest_epoch_renewal_withdrawal_and_saved_book_receipts(self):
  identity,rows=self.book('study_manual')
  self.t,=self.restore(self.t)
  self.assertEqual(B.manual_bonus(self.t,'은신'),2)
  F.new_day(self.t)
  self.assertTrue(B.active(self.t,'study_manual',2))
  AP.extended_rest(self.t,request_id='actual/first-extended-rest')
  self.assertFalse(B.active(self.t,'study_manual'))
  before=self.e.elapsed_seconds
  self.rejected(lambda:B.renew(self.e,self.t,[rows[1]['source_id']],reason='x'),'rank one')
  renewed=B.renew(self.e,self.t,[r['source_id'] for r in rows],reason='actual post-rest renewal')
  self.assertEqual(self.e.elapsed_seconds,before)
  self.assertEqual((self.t.spec['ap_removed'],len(renewed)),(2,2))
  B.withdraw(self.e,self.t,renewed[1]['source_id'])
  self.assertEqual(B.manual_bonus(self.t,'은신'),0)
  self.assertEqual(self.t.spec['ap_removed'],2)

 def test_spooked_explicit_kr_novice_adept_and_may_adept_expert_remain_selectable(self):
  self.t.spec['skills']['오컬트학']=3
  B.observe(self.e,self.t,'book/kr','spooked',details={},edition='korean',reason='KR explicit ranks')
  B.observe(self.e,self.t,'book/may','spooked',details={},edition='may2015',reason='May explicit ranks')
  B.study(self.e,self.t,'book/kr',1,reason='actual KR rank')
  self.rejected(lambda:B.study(self.e,self.t,'book/may',1,reason='x'),'printed Skill')
  self.t.spec['skills']['오컬트학']=4
  B.study(self.e,self.t,'book/kr',2,reason='actual KR second rank')
  B.study(self.e,self.t,'book/may',1,reason='actual May first rank')
  self.rejected(lambda:B.study(self.e,self.t,'book/may',2,reason='x'),'printed Skill')

 def test_study_manual_native_stunt_and_nonstacking_skill_bonus_not_permanent_edges(self):
  self.book('study_manual')
  import skill_stunts as ST
  choices=ST.choices(self.e,self.t)
  self.assertEqual(len(choices),1)
  self.assertEqual(self.t.spec['edges'],[])
  roll=self.e.skill_roll(self.t,'은신',fixed=[1]*5,skill_stunt={'choice_id':choices[0]['id'],'apply':True,'matches_approved_use':True,'reason':'actual lock'})
  self.assertEqual(roll.total,5+6+2)
  self.assertEqual(B.manual_bonus(self.t,'은신',3),3)
  AP.extended_rest(self.t,request_id='actual/no-fake-edge')
  self.assertEqual(ST.choices(self.e,self.t),())

 def test_temporary_book_stunt_does_not_fill_permanent_approval_capacity(self):
  import skill_stunts as ST
  self.book('study_manual',rank=1)
  temporary=ST.choices(self.e,self.t)[0]
  self.t.spec['edges'].append(ST.SOURCE)
  def approve(identity):
   return self.e.approve_skill_stunt(self.t,choice_id=identity,skill='은신',use='hiding in library shelves',reason='actual narrow permanent edge use',approved=True)
  before=deepcopy(self.t.spec)
  with self.assertRaisesRegex(ValueError,'no unassigned'):approve(temporary['id'])
  self.assertEqual(self.t.spec,before)
  approve('permanent/library')
  choices=ST.choices(self.e,self.t)
  self.assertEqual([(r['id'],r['source']) for r in choices],[('permanent/library',ST.SOURCE),(temporary['id'],temporary['source'])])
  self.assertEqual(self.t.spec['ap_removed'],1)
  for identity in ('permanent/library',temporary['id']):
   roll=self.e.skill_roll(self.t,'은신',fixed=[1]*5,skill_stunt={'choice_id':identity,'apply':True,'matches_approved_use':True,'reason':'actual matching narrow use'})
   self.assertEqual((roll.rank,roll.total),(6,11))
  with self.assertRaisesRegex(ValueError,'no unassigned'):approve('unearned/second')
  self.t,=self.restore(self.t)
  self.assertEqual(len(ST.choices(self.e,self.t)),2)
  AP.extended_rest(self.t,request_id='actual/book-stunt-expiry')
  self.assertEqual([(r['id'],r['source']) for r in ST.choices(self.e,self.t)],[('permanent/library',ST.SOURCE)])
  with self.assertRaisesRegex(ValueError,'no unassigned'):approve('still-unearned/second')

 def test_study_manual_uses_larger_actual_equipment_group_not_sum_and_keeps_feat_bonus(self):
  import items as I,skill_modifiers as S
  self.book('study_manual')
  W.register_object(self.e,'actual/trench',location={'kind':'unknown'},reason='actual reinforced trenchcoat',kind='item_instance',item_rule_id='item/보강된-트렌치코트',owner_id=self.t.entity_id)
  I.register_item(self.e,self.t,'item/보강된-트렌치코트',source_instance_id='actual/trench')
  result=S.modifiers(self.rules,self.t,'은신',3)
  self.assertEqual(result['modifier'],7)
  self.assertFalse(any(source==B.ITEMS['study_manual'] for source,_,_ in result['sources']))

 def test_joy_and_ball_and_mechanical_crafting_share_value_cost_owner(self):
  import crafting_recipes as R
  for book,category,item in [('joy_cooking','음식','item/초코바'),('ball_manual','몬스터볼','item/몬스터볼-2'),('diy','기계','item/몬스터볼-2')]:
   with self.subTest(book=book):
    self.fresh();self.book(book)
    value={'id':'actual/book-test','source':'edge/기본-요리' if book=='joy_cooking' else 'edge/몬스터볼','output':{'item_id':item,'key':item},
     'requirements':[{'id':'reader','condition':{'kind':'skill','skill':'일반 지식','rank':3,'effective':False},'reason':'actual capable reader'}],
     'materials':[{'id':'cost','options':[{'kind':'value','category':category,'amount':100,'scrap':True,'money':True}]}],'seconds':60}
    result=R.craft(self.e,self.t,value,reason='actual crafting with book')
    self.assertEqual(result['money_spent'],90)

 def test_discount_floor_zero_still_has_native_receipt_and_zero_authored_cost_is_not_admitted(self):
  import crafting_recipes as R
  self.book('ball_manual')
  value=json.loads((ROOT/'data/examples/crafting-recipes.json').read_text(encoding='utf8'))[0]
  self.t.spec['edges'].append('edge/몬스터볼');self.t.spec['items']['몬스터볼 공구함']=1
  value['materials'][0]['options'][0]['amount']=1
  out=R.craft(self.e,self.t,value,reason='actual one-value cost with printed ten-percent discount')
  self.assertEqual((out['money_spent'],out['materials'][0]['amount']),(0,0))
  self.assertEqual(out['recipe_definition']['materials'][0]['options'][0]['amount'],1)
  self.assertTrue(self.e.validate_state()['valid'])
  value['materials'][0]['options'][0]['amount']=0
  self.rejected(lambda:R.craft(self.e,self.t,value,reason='invalid authored cost'),'material amount')

 def test_ball_actual_physical_maker_bonus_survives_rest_and_diy_needs_current_reading(self):
  self.book('ball_manual');self.book('diy')
  self.crafted('item/몬스터볼-2','made:ball')
  self.crafted('item/몬스터볼-2','made:second')
  import items as I
  I.equip_held(self.e,self.t,'item/몬스터볼-2',source_instance_id='made:ball')
  out=self.e.pokemon_activity(self.t,'dismantle',item='item/몬스터볼-2',held_selection='made:ball')
  self.assertEqual(out['value'],187)
  AP.extended_rest(self.t,request_id='actual/maker-rest')
  self.assertEqual(B.ball_accuracy(self.e,'made:second'),2)
  self.t,=self.restore(self.t)
  I.equip_held(self.e,self.t,'item/몬스터볼-2',source_instance_id='made:second')
  out=self.e.pokemon_activity(self.t,'dismantle',item='item/몬스터볼-2',held_selection='made:second')
  self.assertEqual(out['value'],125)

 def test_joy_actual_meal_maker_native_intake_heals_tick_and_fungi_recipe_is_mushroom_only(self):
  import chef_cooking as CHEF
  self.book('joy_cooking');self.book('fungi')
  self.t.spec['items'].update({'요리 세트':1,'큰버섯':1,'작은버섯':2,'오랭열매':2})
  result=CHEF.cook(self.e,self.t,recipe='hearty_meal',ingredients='big_mushroom',units=1,minutes=5,reason='actual Mushroom-only meal',book_fungi=True)
  self.assertEqual(result['materials'][0]['key'],'큰버섯')
  self.assertNotIn(CHEF.CLASS,self.t.spec['feats'])
  self.t.hp=1;before=self.t.hp
  out=self.e.pokemon_activity(self.t,'serve_chef_food',batch_id=result['batch_id'],target=self.t,minutes=1,reason='actual Meal consumption')
  self.assertEqual(self.t.hp-before,self.e.tick(self.t))
  self.assertEqual(out['joy_of_cooking_healed'],self.e.tick(self.t))
  self.assertTrue(self.e.validate_state()['valid'])

 def test_berries_once_daily_yield_and_food_scrap_only_mulch(self):
  import crafting_activities as A
  self.book('berries');self.t.spec['crafting_scrap']={'음식':100}
  self.e.advance_time(172800,[self.t])
  for uid in ('berry-one','berry-two'):
   self.e.gm.observe_plant(self.t,plant_id=uid,berry='버치열매',planted_at=0,last_harvest_day=None,soft_soil=True,reason='actual mature berry plant')
  out=A.harvest_berry(self.e,self.t,plant_id='berry-one',fixed=2,book_bonus=True)
  self.assertEqual(out['amount'],max(0,2-1+out['soil_bonus'])+1)
  self.assertEqual(out['receipt']['study_book']['study']['book'],'berries')
  self.rejected(lambda:A.harvest_berry(self.e,self.t,plant_id='berry-two',fixed=2,book_bonus=True),'already used')
  result=B.craft_mulch(self.e,self.t,food_scrap=100,seconds=300,reason='GM unprinted cost and duration')
  self.assertEqual((result['scrap_spent'],self.t.spec['crafting_scrap']['음식'],self.t.spec['items']['비료']),(100,0,1))

 def test_joy_actual_meal_planner_refreshment_keeps_paid_maker_after_rest_and_native_intake(self):
  import chef_cooking as CHEF,trainer_feature_acquisition as A,food_effects as FOOD,items as I,materialization_origins as ORIGIN
  self.book('joy_cooking');p=self.pokemon()
  self.t.spec['edges'].append('edge/기본-요리');self.t.spec['items']['요리 세트']=1
  A.acquire_static(self.e,self.t,CHEF.CLASS,acquisition_request_id='actual/book-chef')
  policy={'mode':'create','instance_ids':['actual/joy-refreshment'],'owner_id':self.t.entity_id,'state':'intact','attachments':[]}
  options={'recipe':'meal_planner','item':'item/맛있는물','minutes':5,'reason':'actual Chef-made Refreshment','product_policy':policy,'event_id':'actual/joy-refreshment-production'}
  made=CHEF.cook(self.e,self.t,**options)
  self.assertNotIn('batch_id',made);self.assertEqual(made['money_spent'],36)
  self.assertEqual(self.t.spec['items'][made['item']],0)
  view=ORIGIN.read(self.e,'actual/joy-refreshment')
  self.assertEqual((view['outputs'],view['native_ref']['production_id']),(['actual/joy-refreshment'],made['production_id']))
  self.assertEqual(B.validate_product(self.e,self.e._physical_objects['actual/joy-refreshment'])['production_id'],made['production_id'])
  quantity=CHEF.cook(self.e,self.t,recipe='meal_planner',item='item/맛있는물',minutes=5,reason='actual separately paid ordinary quantity')
  self.assertEqual((quantity['money_spent'],quantity['product_instance_ids'],self.t.spec['items'][quantity['item']]),(36,[],1))
  AP.extended_rest(self.t,request_id='actual/refreshment-maker-rest')
  self.t,p=self.restore(self.t,p);p.hp=1
  before=self.e.export_state();self.assertEqual(CHEF.cook(self.e,self.t,**options),made);self.assertEqual(self.e.export_state(),before)
  native=self.t.spec['crafting_products'][quantity['production_id']]['transformation']['result']
  saved=native['meal_planner_book_discount']['owner_id'];native['meal_planner_book_discount']['owner_id']=p.entity_id
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  native['meal_planner_book_discount']['owner_id']=saved
  I.equip_held(self.e,self.t,'item/맛있는물',source_instance_id='actual/joy-refreshment')
  self.rejected(lambda:self.e.use_item(self.t,'item/맛있는물',p,held_selection='actual/joy-refreshment',duration_minutes=1,duration_reason='held food requires its actual sourced transfer'),'held food self-use only')
  given=I.exchange_items(self.e,self.t,p,swap=False,consent_by=(self.t,),first_selection='actual/joy-refreshment')
  self.assertEqual(given['transfers'],[{'from':self.t.entity_id,'to':p.entity_id,'item':'item/맛있는물','instance_id':'actual/joy-refreshment'}])
  self.assertEqual(B.validate_product(self.e,self.e._physical_objects['actual/joy-refreshment'])['maker_id'],self.t.entity_id)
  self.e.use_item(p,'item/맛있는물',p,held_selection='actual/joy-refreshment',duration_minutes=1,duration_reason='actual same crafted Refreshment intake')
  self.assertEqual(p.hp,min(p.max_hp,1+FOOD.DRINKS['item/맛있는물']+self.e.tick(p)))
  self.e.advance_time(3600,[self.t,p]);p.hp=1
  self.e.use_item(self.t,'item/맛있는물',p,duration_minutes=1,duration_reason='ordinary quantity has no actual consumed maker unit')
  self.assertEqual(p.hp,min(p.max_hp,1+FOOD.DRINKS['item/맛있는물']))
  self.assertTrue(self.e.validate_state()['valid'])

 def test_first_aid_kit_actual_native_healing_consumes_ap_and_adds_ten(self):
  self.book('first_aid');self.t.spec['items']['응급치료키트']=1
  p=self.pokemon();p.hp=1;self.e.apply_status(p,'독')
  before=AP.available(self.t)
  result=B.first_aid_kit(self.e,self.t,p,fixed=[1]*6,reason='actual Kit check')
  self.assertEqual((result['medicine_total'],result['book_bonus']),(16,10))
  self.assertEqual((AP.available(self.t),self.t.spec['items']['응급치료키트']),(before-1,1))
  self.assertNotIn('독',p.conditions)

 def test_first_aid_rank_two_delegates_one_daily_native_expertise_and_target_limit(self):
  self.book('first_aid');self.t.spec['items']['응급치료키트']=1
  p=self.pokemon();p.hp=1
  result=B.first_aid_expertise(self.e,self.t,p)
  self.assertEqual(p.hp,p.max_hp)
  self.assertTrue(result['tool_retained'])
  self.rejected(lambda:B.first_aid_expertise(self.e,self.t,p),'daily|Daily')

 def test_traditional_medicine_rank_specific_cs_and_repeat_food_buff(self):
  import food_effects as FOOD
  identity,_=self.book('traditional_medicine',1)
  p=self.pokemon();self.t.spec['items']['힘의가루']=5
  for _ in range(3):
   p.hp=1;B.use_herbal(self.e,self.t,p,'힘의가루')
  self.assertEqual(FOOD.herbal_state(p)['count'],3)
  self.assertEqual(list(p.stages.values()),[0]*5)
  self.assertEqual(len(p.buffs),1)
  B.study(self.e,self.t,identity,2,reason='actual herbal preparation')
  self.e.apply_status(p,'마비')
  self.e.consume_food_buff(p,buff_id=p.buffs[0]['id'],save_condition='마비')
  self.e.start_round([self.t,p]);self.e.start_of_turn(p,initiative_count=10)
  self.e.end_of_turn(p);self.e.end_encounter([self.t,p],round_elapsed_seconds=0)
  p.hp=1
  B.use_herbal(self.e,self.t,p,'힘의가루',repeat_food_buff=True)
  self.assertEqual(len(p.buffs),1)
  self.assertTrue(FOOD.herbal_state(p)['uses'][-1]['repeat_food_buff'])
  self.t,p=self.restore(self.t,p)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_dowsing_native_double_activation_colors_and_single_book_die(self):
  self.book('dowsing');self.t.spec['items']['다우징 로드']=1
  import crafting_activities as A
  faces={str(i):4 for i in range(7)}
  result=A.dowse(self.e,self.t,outdoors=True,book_color='빨강',fixed=faces)
  self.assertEqual((result['pool'],result['remaining_uses']),(7,1))
  self.assertEqual(result['gained'],{'빨강':7})
  self.rejected(lambda:A.dowse(self.e,self.t,outdoors=True,book_color='파랑',fixed=faces),'daily Dowsing')

 def test_tinfoil_iron_mind_and_telepathy_focus_stunt_are_temporary(self):
  self.book('tinfoil')
  import iron_mind as I,skill_stunts as ST
  self.assertTrue(I.validate(self.t))
  self.assertEqual([(r['skill'],r['use']) for r in ST.choices(self.e,self.t)],[('집중','resisting Telepathy')])
  self.assertNotIn('정신봉인',G.effective_capabilities(self.t))
  self.assertEqual(self.t.spec['edges'],[])

 def test_tinfoil_does_not_hide_malformed_or_unqualified_native_iron_mind(self):
  import iron_mind as I
  self.book('tinfoil');self.t.spec['edges']='malformed'
  before=deepcopy(self.t.spec)
  with self.assertRaisesRegex(ValueError,'Edge list'):I.validate(self.t)
  self.assertEqual(self.t.spec,before)
  self.t.spec['edges']=[I.SOURCE];self.t.spec['skills']['집중']=1
  before=deepcopy(self.t.spec)
  with self.assertRaisesRegex(ValueError,'Novice Focus|qualification'):I.validate(self.t)
  self.assertEqual(self.t.spec,before)

 def test_tinfoil_opposed_hue_scene_failure_lock_and_never_tint(self):
  self.book('tinfoil');reader=self.trainer('aura-reader',(1,0))
  G.grant(reader,'capabilities','Aura Reader','fixture:actual-aura-reader','fixture')
  info={'color':'blue','personality':'kind','worldview':'fair','brightness':'bright','mood':'happy','intentions':'help'}
  self.e.gm.observe_aura(self.t,living=True,**info,reason='actual currently observed target Aura')
  result=B.read_aura(self.e,reader,self.t,reader_skill='직감',target_skill='집중',reader_roll=[1]*6,target_roll=[6]*6)
  self.assertTrue(all(v is None for v in result['color_information'].values()))
  self.assertTrue(all(v is None for v in result['brightness_information'].values()))
  self.rejected(lambda:B.read_aura(self.e,reader,self.t,reader_skill='직감',target_skill='집중',reader_roll=[6]*6,target_roll=[1]*6),'cannot retry')
  self.e.end_scene([self.t,reader])
  result=B.read_aura(self.e,reader,self.t,reader_skill='직감',target_skill='집중',reader_roll=[6]*6,target_roll=[1]*6)
  self.assertEqual(result['color_information']['color'],'blue');self.assertIsNone(result['brightness_information']['brightness'])

 def test_spooked_actual_hand_tag_sees_native_invisibility_and_blocks_curse_only_while_held(self):
  import items as I,invisibility_state as V
  self.book('spooked');p=self.pokemon()
  G.grant(p,'capabilities','투명','fixture:actual-invisibility','fixture')
  V.change(self.e,p,True,reason='actual native Invisibility activation')
  self.assertEqual(V.visual_block(self.e,p,observer=self.t),'target_invisible')

  W.register_object(self.e,'actual/hand-tag',location={'kind':'unknown'},reason='actual owned Cleanse Tag',kind='item_instance',item_rule_id='item/순결의부적-1',owner_id=self.t.entity_id)
  I.equip_held(self.e,self.t,'item/순결의부적-1',source_instance_id='actual/hand-tag',slot_id='주요손')
  self.assertIsNone(V.visual_block(self.e,p,observer=self.t))
  self.assertFalse(self.e.apply_status(self.t,'저주',source='move/저주',applied_by=p))
  self.assertNotIn('저주',self.t.conditions)
  I.drop_equipment(self.e,self.t,['actual/hand-tag'],slots=('held','주요손'),consent_by=(self.t,))
  self.assertEqual(V.visual_block(self.e,p,observer=self.t),'target_invisible')

 def test_curse_immunity_preserves_actual_actor_and_native_partial_preflight(self):
  self.book('spooked')
  self.rejected(lambda:self.e.apply_status(self.t,'저주',_field_deferred='invalid'),'field deferral')
  ghost=Combatant(self.rules,dict(self.t.spec,id='trainer/not-registered',name='not-registered'))
  self.rejected(lambda:self.e.apply_status(ghost,'저주'),'registered|actual|world')

 def test_type_manual_may_xp_not_csv_level_and_nonconsecutive_day_guard(self):
  import pokemon_activities as A
  self.book('type_manual');p=self.pokemon()
  self.assertEqual(B.type_capture(self.t,p),-5)
  out=A.experience_training(self.e,self.t,targets=[p],book_target=p,safe=True)
  self.assertEqual(out['study_book']['bonus_xp'],10)
  self.rejected(lambda:A.experience_training(self.e,self.t,targets=[p],book_target=p,safe=True),'already|training|once')
  F.new_day(self.t)
  F.new_day(p)
  self.rejected(lambda:A.experience_training(self.e,self.t,targets=[p],book_target=p,safe=True),'consecutive days')
  F.new_day(self.t);F.new_day(p)
  A.experience_training(self.e,self.t,targets=[p],book_target=p,safe=True)

 def test_actual_crafted_ball_accuracy_and_book_capture_bonus_preserve_legacy_ball(self):
  from unittest.mock import patch
  self.book('ball_manual');self.book('type_manual');self.crafted('item/몬스터볼-2','made:throw')
  import items as I
  I.equip_held(self.e,self.t,'item/몬스터볼-2',source_instance_id='made:throw')
  p=self.pokemon();p.spec.pop('trainer_id');p.spec.update(wild=True,side='wild');p.side='wild'
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  original=Engine.accuracy_check
  with patch.object(Engine,'accuracy_check',autospec=True,side_effect=original) as actual:
   self.e.throw_ball(self.t,p,physical_instance_id='made:throw',fixed_accuracy=20,fixed_capture=1)
  self.assertEqual(actual.call_args.kwargs['situational'],2)
  record=self.t.spec['capture_attempts']['capture-'+str(self.t.spec['capture_attempt_serial'])]
  self.assertTrue(record['hit']);self.assertEqual(record['resolution']['modifiers']['type_manual'],1)
  self.fresh();p=self.pokemon();p.spec.pop('trainer_id');p.spec.update(wild=True,side='wild');p.side='wild'
  self.t.spec['items']['몬스터볼']=1
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  self.assertFalse(self.e.throw_ball(self.t,p,fixed_accuracy=1,fixed_capture=1))
  self.assertEqual(self.t.spec['items']['몬스터볼'],0)

 def test_daycare_actual_group_and_first_inheritance_level_is_ten(self):
  self.book('daycare')
  self.t.spec['edges'].append('edge/브리더')
  mother=self.pokemon('mother');mother.spec['gender']='female'
  father=Combatant(self.rules,build_pokemon(self.rules,'치코리타',10,name='father',moves=[],abilities=[],extra={'trainer_id':self.t.entity_id,'gender':'male'}))
  self.e.gm.add_combatant(father,pos=(2,0),side='party',reason='actual compatible father')
  value=json.loads((ROOT/'data/examples/egg-creation.json').read_text(encoding='utf8'))[0]
  value['species']['parents']=[0];value['inheritance'].update(kind='declared',moves=[],tutoring_policy='core');value['hatch']['level']=10
  egg=self.e.create_declared_egg(self.t,[mother,father],value,request_id='actual/daycare-egg',compatible=True,species='치코리타',inheritance_moves=[],reason='actual male species enabled by studied Egg Group')
  child=self.e.hatch_declared_egg(self.t,egg['entity_id'],name='child',ready=True,reason='observed actual hatch',choices={'gender':'female','nature':'노력','abilities':['심록'],'moves':[],'special_appearance':False,'inheritance_moves':[]})['pokemon']
  self.assertEqual(B.first_inheritance_level(child,20),10)
  import growth_milestones as GROWTH
  self.assertIn('inheritance:10',child.spec[GROWTH.KEY]);self.assertNotIn('inheritance:20',child.spec[GROWTH.KEY])
  self.assertTrue(self.e.validate_state()['valid'])

 def test_fishing_snare_only_actual_fished_pokemon_and_two_distinct_stat_choices(self):
  import pokemon_activities as A,wild_equipment as E
  self.book('fishing',rank=1);p=self.pokemon();other=self.pokemon('not-fished',pos=(2,0))
  p.spec.pop('trainer_id');p.spec.update(wild=True,evolved=False,size='Small');p.side='wild'
  self.t.spec['items'].update({'좋은낚싯대':1,'미끼':1})
  self.assertFalse(B.fishing_snare(self.t,p))
  A.fishing(self.e,self.t,phase='start',rod='좋은낚싯대',attachment='미끼')
  A.fishing(self.e,self.t,phase='wait',roll_d20=20)
  A.fishing(self.e,self.t,phase='reel',target=p,fixed=[6]*6)
  self.assertTrue(B.fishing_snare(self.t,p));self.assertFalse(B.fishing_snare(self.t,other))
  self.assertEqual((p.stages['atk'],p.stages['spe']),(0,0))
  self.assertNotIn('풀죽음',p.conditions)
  self.assertEqual(E.snare_bonus(self.e,self.t,p),2)
  self.assertEqual(E.snare_bonus(self.e,self.t,other),0)

 def test_fishing_rank_two_noncombat_immediate_selected_flinch_and_actual_ten_second_derivative(self):
  import pokemon_activities as A,condition_instances as CI,initiative as INIT
  self.book('fishing');p=self.pokemon();p.spec.pop('trainer_id');p.spec.update(wild=True,evolved=False,size='Small');p.side='wild'
  self.t.spec['items'].update({'좋은낚싯대':1,'미끼':1})
  A.fishing(self.e,self.t,phase='start',rod='좋은낚싯대',attachment='미끼')
  A.fishing(self.e,self.t,phase='wait',roll_d20=20)
  self.rejected(lambda:A.fishing(self.e,self.t,phase='reel',target=p,fixed=[6]*6,book_stats=['atk','atk']),'two distinct')
  A.fishing(self.e,self.t,phase='reel',target=p,fixed=[6]*6,book_stats=['atk','spe'])
  self.assertTrue(B.fishing_snare(self.t,p));self.assertFalse(self.e.encounter_active)
  self.assertEqual((p.stages['atk'],p.stages['spe']),(-1,-1))
  self.assertEqual(INIT.value(self.rules,p).value,p.staged('spe')-5)
  parent=CI.records(p,'풀죽음')[0]
  self.assertIn('noncombat_flinch',parent);self.assertNotIn('applied_round',parent);self.assertNotIn('applied_count',parent)
  self.assertIn('취약',p.conditions)
  self.t,p=self.restore(self.t,p)
  self.e.advance_time(9,[p]);self.assertIn('취약',p.conditions)
  self.e.advance_time(1,[p]);self.assertNotIn('취약',p.conditions);self.assertIn('풀죽음',p.conditions)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_noncombat_selected_flinch_stacks_immediately_with_independent_actual_deadlines(self):
  import initiative as INIT
  p=self.pokemon();base=INIT.value(self.rules,p).value
  self.e.apply_status(p,'풀죽음',source='move/박치기',applied_by=self.t)
  self.assertEqual(INIT.value(self.rules,p).value,base-5)
  self.e.advance_time(5,[p]);self.e.apply_status(p,'풀죽음',source='move/사념의박치기',applied_by=self.t)
  self.assertEqual(INIT.value(self.rules,p).value,base-10)
  self.e.advance_time(4,[p]);self.assertIn('취약',p.conditions)
  self.e.advance_time(1,[p]);self.assertIn('취약',p.conditions)
  self.e.advance_time(5,[p]);self.assertNotIn('취약',p.conditions)
  self.assertEqual(INIT.value(self.rules,p).value,base-10)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_noncombat_flinch_entering_actual_combat_keeps_original_elapsed_deadline(self):
  p=self.pokemon();self.e.apply_status(p,'풀죽음',source='move/박치기')
  self.e.advance_time(9,[p]);self.e.start_round([self.t,p])
  self.assertIn('취약',p.conditions)
  self.e.advance_time(1,[p]);self.assertNotIn('취약',p.conditions)
  self.assertIn('풀죽음',p.conditions);self.assertTrue(self.e.validate_state()['valid'])

 def test_noncombat_flinch_cure_recall_faint_scene_and_independent_vulnerability_keep_ownership(self):
  import condition_instances as CI
  for ending in ('cure','recall','faint','scene','other_vulnerability','manual_vulnerability_cure'):
   with self.subTest(ending=ending):
    self.fresh();p=self.pokemon()
    if ending=='other_vulnerability':self.e.apply_status(p,'취약')
    self.e.apply_status(p,'풀죽음',source='move/박치기')
    applied_at=self.e.elapsed_seconds
    if ending=='cure':self.e.cure_status(p,'풀죽음')
    elif ending=='recall':self.e.gm.recall(p,reason='actual recall')
    elif ending=='faint':self.e.gm.faint(p,reason='actual fainting')
    elif ending=='scene':self.e.end_scene([self.t,p])
    elif ending=='manual_vulnerability_cure':self.e.cure_status(p,'취약')
    if ending in ('cure','recall','faint','scene'):self.assertFalse(CI.records(p,'풀죽음'))
    if ending=='scene':self.assertEqual(self.e.elapsed_seconds,applied_at)
    if ending in ('cure','recall','faint','scene'):self.assertIn('취약',p.conditions)
    if ending=='manual_vulnerability_cure':self.assertNotIn('취약',p.conditions)
    self.t,p=self.restore(self.t,p)
    self.e.advance_time(10,[p])
    self.assertEqual('취약' in p.conditions,ending=='other_vulnerability')
    self.assertTrue(self.e.validate_state()['valid'])

 def test_noncombat_flinch_restore_rejects_parent_source_target_and_exact_deadline_tampering(self):
  import condition_instances as CI,combat_timing as CLOCK,effect_lifetime_policy as LIFE
  p=self.pokemon();self.e.apply_status(p,'풀죽음',source='move/박치기')
  state=self.e.export_state();uid=p.entity_id
  for change in ('source','definition','future','fake_round','deadline','target','parent'):
   with self.subTest(change=change):
    self.e=CODEC.load_engine(self.rules,deepcopy(state));index=W.actor_index(self.e);self.t=index[self.t.entity_id];p=index[uid]
    parent=CI.records(p,'풀죽음')[0];child=CLOCK.records(p)[0]
    if change=='source':parent['noncombat_flinch']['text']['sha256']='0'*64
    elif change=='definition':parent['noncombat_flinch']['definition_sha256']='0'*64
    elif change=='future':parent['noncombat_flinch']['at']+=1
    elif change=='fake_round':parent['applied_round']=1
    elif change=='deadline':child[LIFE.KEY]['end_at']+=1
    elif change=='target':child['lifetime_target']=self.t
    else:child['flinch_parent_id']='not-the-actual-parent'
    with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)

 def test_noncombat_flinch_does_not_silently_adapt_an_unreviewed_core_247_definition(self):
  from unittest.mock import patch
  p=self.pokemon();selected=deepcopy(self.rules.units['condition/풀죽음'])
  selected['mech']['data']['legacy_core247']='next turn that round; no next-round carry'
  before=self.e.export_state()
  with patch.dict(self.rules.units,{'condition/풀죽음':selected}),self.assertRaisesRegex(ValueError,'reviewed source adapter'):
   self.e.apply_status(p,'풀죽음')
  self.assertEqual(self.e.export_state(),before)

 def test_fungi_negative_effect_immunity_applies_only_reader_and_owned_pokemon(self):
  import herb_mushroom_rules as M
  self.book('fungi');p=self.pokemon();other=self.trainer('not-owner',(2,0))
  self.physical(self.t,'item/작은버섯','actual/mushroom')
  known=M.appraise(self.e,self.t,instance_id='actual/mushroom')
  self.assertEqual(known['status'],'identified');self.assertNotIn('check',known)
  before=self.t.hp;self.e.use_item(self.t,'item/작은버섯',held_selection='actual/mushroom')
  self.assertEqual(self.t.hp,before)
  self.physical(p,'item/큰버섯','actual/owned-mushroom')
  before=p.hp;self.e.use_item(p,'item/큰버섯',held_selection='actual/owned-mushroom')
  self.assertEqual(p.hp,before);self.assertNotIn('독',p.conditions)
  self.physical(p,'item/향기버섯','actual/owned-balm')
  stages=dict(p.stages);self.e.use_item(p,'item/향기버섯',held_selection='actual/owned-balm')
  self.assertEqual(p.stages,stages)
  self.physical(other,'item/작은버섯','actual/other-mushroom')
  before=other.hp;self.e.use_item(other,'item/작은버섯',held_selection='actual/other-mushroom')
  self.assertEqual(other.hp,before-5)
  import chef_cooking as CHEF,trainer_feature_acquisition as A
  self.t.spec['edges'].append('edge/기본-요리');self.t.spec['items']['요리 세트']=1
  for uid in (CHEF.CLASS,CHEF.ACCENTUATED):A.acquire_static(self.e,self.t,uid,acquisition_request_id='actual/fungi-preserves/'+uid)
  self.physical(self.t,'item/큰버섯','actual/preserved-mushroom')
  M.appraise(self.e,self.t,instance_id='actual/preserved-mushroom')
  made=CHEF.cook(self.e,self.t,recipe='preserves',origin={'item':'item/큰버섯','instance_id':'actual/preserved-mushroom'},minutes=5,reason='actual Fungi Preserves')
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.t,initiative_count=20)
  used=CHEF.serve(self.e,self.t,batch_id=made['batch_id'],target=self.t,minutes=1,reason='actual protected preserved Mushroom')
  self.assertEqual(used['item_stock']['unit'],1);self.assertNotIn('독',self.t.conditions)
  self.e.end_of_turn(self.t);self.e.start_of_turn(other,initiative_count=10)
  used=CHEF.serve(self.e,self.t,batch_id=made['batch_id'],target=other,minutes=1,reason='actual unprotected second Preserves unit')
  self.assertEqual(used['item_stock']['unit'],2);self.assertIn('독',other.conditions)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_travel_stunts_and_weather_use_actual_studied_region_not_everywhere(self):
  import weather_state as WEATHER,turn as TURN
  self.book('travel')
  fact={'region':'Route 1','source':'gm/observation','reason':'actual location'}
  self.t.spec['crafting_location']=deepcopy(fact)
  self.assertEqual(len(B.stunts(self.e,self.t)),2)
  WEATHER.observe_natural(self.e,'actual regional sandstorm',treat_as='sandstorm',reason='natural regional hazard')
  hp=self.t.hp;TURN.weather_turn_start(self.e,self.t)
  self.assertEqual(self.t.hp,hp)
  self.t.spec['crafting_location']['region']='Route 2'
  TURN.weather_turn_start(self.e,self.t)
  self.assertLess(self.t.hp,hp)
  p=self.pokemon();p.spec['crafting_location']=deepcopy(fact)
  hp=p.hp;TURN.weather_turn_start(self.e,p);self.assertEqual(p.hp,hp)
  p.spec['crafting_location']['region']='Route 2'
  TURN.weather_turn_start(self.e,p);self.assertLess(p.hp,hp)

 def test_anarchist_repel_blind_once_per_scene_target_and_actual_hit_hp_loss(self):
  self.book('anarchist');p=self.pokemon()
  p.spec.pop('trainer_id');p.spec['wild']=True;p.side='wild'
  self.t.spec['items']['item/벌레회피스프레이']=2
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  before=p.hp
  self.e.use_item(self.t,'item/벌레회피스프레이',p,aim={'reachable':True,'reason':'actual spray exposure'},fixed_accuracy=20)
  self.assertEqual(before-p.hp,6);self.assertIn('실명',p.conditions)
  self.e.end_of_turn(self.t);self.e.start_of_turn(p,initiative_count=10);self.e.end_of_turn(p)
  self.assertNotIn('실명',p.conditions)
  self.e.end_round();self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  before=p.hp
  self.e.use_item(self.t,'item/벌레회피스프레이',p,aim={'reachable':True,'reason':'same actual target'},fixed_accuracy=20)
  self.assertEqual(before-p.hp,6);self.assertNotIn('실명',p.conditions)

 def test_anarchist_pester_actual_hit_loses_hp_but_miss_and_absent_book_do_not(self):
  self.book('anarchist');p=self.pokemon();self.t.spec['items']['item/오물탄-화상']=2
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  before=p.hp;out=self.e.use_item(self.t,'item/오물탄-화상',p,fixed_accuracy=1)
  self.assertFalse(out['hit']);self.assertEqual(p.hp,before)
  self.e.end_of_turn(self.t);self.e.end_round();self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  out=self.e.use_item(self.t,'item/오물탄-화상',p,fixed_accuracy=20)
  self.assertTrue(out['hit']);self.assertEqual(before-p.hp,6)

 def test_anarchist_actual_spray_miss_and_hit_keep_the_two_rank_conditions_distinct(self):
  for rank in (1,2):
   for physical in (False,True):
    with self.subTest(rank=rank,physical=physical):
     self.fresh();self.book('anarchist',rank);p=self.pokemon()
     source='item/벌레회피스프레이';self.t.spec['items'][source]=2
     def spray(roll,uid):
      if physical:
       W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual Repel bottle',kind='item_instance',item_rule_id=source,owner_id=self.t.entity_id)
       __import__('items').equip_held(self.e,self.t,source,source_instance_id=uid)
      return self.e.use_item(self.t,source,p,aim={'reachable':True,'reason':'actual spray attempt, not an invented hit'},fixed_accuracy=roll,**({'held_selection':uid} if physical else {}))
     self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
     before=p.hp;miss=spray(1,'actual-missed-repel')
     self.assertFalse(miss['hit']);self.assertIn('실명',p.conditions);self.assertEqual(p.hp,before)
     self.assertEqual(self.t.spec['items'][source],2 if physical else 1)
     if physical:self.assertIn('consumed',self.e._physical_objects['actual-missed-repel'])
     self.e.end_of_turn(self.t);self.e.start_of_turn(p,initiative_count=10);self.e.end_of_turn(p)
     self.assertNotIn('실명',p.conditions)
     self.e.end_round();self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
     hit=spray(20,'actual-hit-repel')
     self.assertTrue(hit['hit']);self.assertEqual(before-p.hp,6 if rank==2 else 0)
     self.assertNotIn('실명',p.conditions)
     self.assertEqual(self.t.spec['items'][source],2 if physical else 0)
     if physical:self.assertIn('consumed',self.e._physical_objects['actual-hit-repel'])

 def test_anarchist_actual_self_spray_is_application_not_a_rank_two_attack_hit(self):
  self.book('anarchist');p=self.pokemon();source='item/벌레회피스프레이'
  self.t.spec['items'][source]=2
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  before=(self.t.hp,deepcopy(self.t.budget),self.e.elapsed_seconds,self.e.rng.getstate())
  used=self.e.use_item(self.t,source,self.t,aim={'reason':'actual self application is not an attack'})
  self.assertEqual(used['mode'],'self');self.assertTrue(used['hit'])
  self.assertEqual((self.t.hp,self.t.budget,self.e.elapsed_seconds,self.e.rng.getstate()),before)
  self.assertIn('실명',self.t.conditions);self.assertEqual(self.t.spec['items'][source],1)
  self.e.end_of_turn(self.t);self.assertIn('실명',self.t.conditions)
  self.e.start_of_turn(p,initiative_count=10);self.e.end_of_turn(p);self.e.end_round()
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20);self.e.end_of_turn(self.t)
  self.assertNotIn('실명',self.t.conditions)
  self.e.use_item(self.t,source,self.t,aim={'reason':'same actual self target in the same Scene'})
  self.assertNotIn('실명',self.t.conditions);self.assertEqual(self.t.hp,before[0])

 def test_anarchist_outside_combat_self_application_survives_restore_until_actual_next_turn(self):
  self.book('anarchist');p=self.pokemon();source='item/벌레회피스프레이'
  self.t.spec['items'][source]=1
  before=(self.t.hp,self.e.elapsed_seconds,self.e.rng.getstate())
  had_budget=hasattr(self.t,'budget')
  if had_budget:budget_before=deepcopy(self.t.budget)
  used=self.e.use_item(self.t,source,self.t,aim={'reason':'actual self application before any encounter'})
  self.assertEqual(used['mode'],'self');self.assertIn('실명',self.t.conditions)
  self.assertFalse(self.e.encounter_active);self.assertIsNone(self.e.round_start_seconds)
  self.assertEqual((self.t.hp,self.e.elapsed_seconds,self.e.rng.getstate()),before)
  self.assertEqual(hasattr(self.t,'budget'),had_budget)
  if had_budget:self.assertEqual(self.t.budget,budget_before)
  self.assertTrue(self.e.validate_state()['valid'])
  self.t,p=self.restore(self.t,p)
  self.assertIn('실명',self.t.conditions);self.assertFalse(self.e.encounter_active)
  self.e.advance_time(10,[self.t,p]);self.assertIn('실명',self.t.conditions)
  self.e.start_round([self.t,p]);self.e.start_of_turn(p,initiative_count=20);self.e.end_of_turn(p)
  self.assertIn('실명',self.t.conditions)
  self.e.start_of_turn(self.t,initiative_count=10);self.e.end_of_turn(self.t)
  self.assertNotIn('실명',self.t.conditions);self.assertEqual(self.t.hp,before[0])

 def test_anarchist_native_spray_late_payment_failure_rolls_back_blind_and_scene_use(self):
  from unittest.mock import patch
  import consumption_execution as PAID
  for direct in (False,True):
   with self.subTest(direct=direct):
    self.fresh();self.book('anarchist');p=self.pokemon();source='item/벌레회피스프레이'
    self.t.spec['items'][source]=1
    self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
    options={'aim':{'reason':'actual late rejected spray',**({'reachable':True} if direct else {})},**({'fixed_accuracy':1} if direct else {})}
    protected=(self.t.hp,p.hp,self.t.injuries,p.injuries,deepcopy(p.spec),deepcopy(p.conditions),deepcopy(p.custom_conditions),deepcopy(B._state(self.t)),self.e.rng.getstate())
    with patch.object(PAID,'finish',side_effect=ValueError('actual late Repel payment failure')):
     if direct:
      # The native attack already paid and exposed its roll; only its late effect transaction rolls back.
      with self.assertRaisesRegex(ValueError,'actual late Repel payment failure'):
       self.e.use_item(self.t,source,p,**options)
     else:self.rejected(lambda:self.e.use_item(self.t,source,self.t,**options),'actual late Repel payment failure')
    self.assertEqual((self.t.hp,p.hp,self.t.injuries,p.injuries,p.spec,p.conditions,p.custom_conditions,B._state(self.t),self.e.rng.getstate()),protected)
    self.assertEqual(self.t.spec['items'][source],0 if direct else 1)
    self.assertEqual(self.t.budget['standard'],0 if direct else 1)
    self.assertFalse(self.t.spec.get('repel_uses'))
    self.assertFalse(any(r.get('event')=='anarchist_blind' for r in B._state(self.t)['events']))

 def test_book_assisted_breather_requires_another_known_ally(self):
  cases=[('party','party',False,True),('party','foe',False,False),
         (None,None,False,False),('party',None,False,False),
         (None,'party',False,False),('party','party',True,False)]
  for book in ('caretaker','combat_medic'):
   for reader_side,target_side,self_target,allowed in cases:
    with self.subTest(book=book,reader=reader_side,target=target_side,self_target=self_target):
     self.fresh();self.book(book,rank=1 if book=='caretaker' else 2);patient=self.pokemon()
     target=self.t if self_target else patient
     self.t.side,target.side=reader_side,target_side
     self.e.start_round([self.t,patient]);self.e.start_of_turn(self.t,initiative_count=20)
     self.e.change_stage(target,'atk',1)
     use=lambda:B.assisted_breather(self.e,self.t,target,book=book)
     if not allowed:
      self.rejected(use,'adjacent ally')
     else:
      self.assertTrue(use()['completed']);self.assertEqual(target.stages['atk'],0)
      self.assertEqual(self.t.budget['standard'],0)
      self.assertNotIn('넘어짐',target.conditions)

 def test_caretaker_deferred_drain_care_group_and_standard_breather_no_trip(self):
  self.book('caretaker');p=self.pokemon()
  B.care_for(self.e,self.t,[self.t,p],rest_id='actual/caretaker-rest',reason='actual patient group')
  self.assertEqual(B.care_healing(self.e,p,'actual/caretaker-rest',10),10)
  self.assertEqual(B.care_injury_bonus(self.e,p),0)
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  old=p.pos
  out=B.assisted_breather(self.e,self.t,p,book='caretaker')
  self.assertTrue(out['completed']);self.assertEqual(p.pos,old);self.assertNotIn('넘어짐',p.conditions)

 def test_combat_medic_sprint_native_swift_and_optional_full_action_interrupt(self):
  self.book('combat_medic');p=self.pokemon();p.hp=1;self.t.spec['items']['상처약']=1
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  self.rejected(lambda:B.swift_restorative(self.e,self.t,p,'상처약'),'actual Sprint')
  self.e.sprint(self.t,source_policy='ch07_turn')
  B.swift_restorative(self.e,self.t,p,'상처약')
  self.assertEqual((self.t.budget['swift'],self.t.spec['items']['상처약']),(0,0))

 def test_combat_medic_actual_full_interrupt_can_decline_and_pays_next_turn_when_accepted(self):
  self.book('combat_medic');p=self.pokemon();self.assertTrue(self.e.apply_status(p,'혼란'))
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  out=B.assisted_breather(self.e,self.t,p,book='combat_medic',accept=True,fixed=[6]*6)
  self.assertTrue(out['completed']);self.assertNotIn('혼란',p.conditions)
  self.assertNotIn('넘어짐',p.conditions)
  self.e.end_of_turn(self.t);self.e.start_of_turn(p,initiative_count=10)
  self.assertEqual((p.budget['standard'],p.budget['shift']),(0,0))

 def test_combat_medic_declined_interrupt_keeps_ally_resources_and_status(self):
  self.book('combat_medic');p=self.pokemon();self.assertTrue(self.e.apply_status(p,'마비'))
  self.e.start_round([self.t,p]);self.e.start_of_turn(self.t,initiative_count=20)
  before=deepcopy(getattr(p,'budget',None))
  out=B.assisted_breather(self.e,self.t,p,book='combat_medic',accept=False)
  self.assertFalse(out['completed']);self.assertEqual(getattr(p,'budget',None),before);self.assertIn('마비',p.conditions)

 def test_caretaker_actual_group_rest_double_hp_then_post_rest_drain_and_expiry(self):
  import downtime as D
  self.book('caretaker');p=self.pokemon();p.hp=1
  B.care_for(self.e,self.t,[self.t,p],rest_id='actual/group-rest',reason='actual next-day care')
  removed=self.t.spec['ap_removed']
  D.rest_many(self.e,[self.t,p],240,rest_id='actual/group-rest')
  self.assertEqual(self.t.spec['ap_removed'],1)
  self.assertEqual(B.care_injury_bonus(self.e,p),0)
  self.assertTrue(any(x.get('paid_after_rest') for x in self.t.spec[B.KEY]['events']))
  self.assertEqual(removed,1)
  self.t,p=self.restore(self.t,p)
  AP.extended_rest(self.t,request_id='actual/next-rest')
  self.assertEqual(B.care_injury_bonus(self.e,p),0)

 def test_caretaker_only_actual_shared_positive_extended_rest_admits_pending_or_paid_effect(self):
  import downtime as D,injury_recovery as I
  for mode in ('patient_only','zero','ordinary_time','short','direct_ap','outside_medical_ap'):
   with self.subTest(mode=mode):
    self.fresh();self.book('caretaker');p=self.pokemon();self.e.gm.set_injuries(p,value=2,reason='observed injuries')
    B.care_for(self.e,self.t,[p],rest_id='actual/scoped-rest',reason='actual future rest declaration')
    if mode=='patient_only':D.rest_many(self.e,[p],240,rest_id='actual/scoped-rest')
    elif mode=='zero':D.rest_many(self.e,[self.t,p],0,rest_id='actual/scoped-rest')
    elif mode=='ordinary_time':self.e.advance_time(14400,[self.t,p])
    elif mode=='short':D.rest_many(self.e,[self.t,p],30,rest_id='actual/scoped-rest')
    elif mode=='direct_ap':AP.extended_rest(self.t,request_id='actual/not-a-rest-producer')
    else:
     self.e.gm.set_injuries(self.t,value=2,reason='observed patient injury')
     out=self.e.recover_injury(self.t,source='trainer_ap',duration_minutes=1,reason='ordinary medical Extended Action')
     self.assertEqual(out['recovered'],1)
    self.assertEqual(p.spec[I.CLOCK]['accelerated_seconds'],0)
    self.assertEqual((B.care_injury_bonus(self.e,p),B.care_healing(self.e,p,'actual/scoped-rest',10)),(0,10))
    event=next(r for r in self.t.spec[B.KEY]['events'] if r['event']=='caretaker')
    self.assertFalse(event['paid_after_rest']);self.assertEqual(event['intervals'],[])
    self.assertTrue(self.e.validate_state()['valid'])

 def synthetic(self,actor):
  G.grant(actor,'capabilities','개선된 인조 근육','actual/synthetic','installed_upgrade',rule_id='C2CSV/item-data:178:5')

 def test_actual_care_and_synthetic_rates_are_additive_only_for_their_known_intersection(self):
  import downtime as D,injury_recovery as I
  for care,muscle in ((False,False),(False,True),(True,False),(True,True)):
   with self.subTest(care=care,synthetic=muscle):
    self.fresh()
    if care:self.book('caretaker')
    p=self.pokemon()
    if muscle:self.synthetic(p)
    self.e.gm.set_injuries(p,value=2,reason='actual no-new-injury window')
    if care:B.care_for(self.e,self.t,[p],rest_id='actual/rates',reason='actual shared four-hour rest')
    D.rest_many(self.e,[self.t,p],240,rest_id='actual/rates')
    clock=p.spec[I.CLOCK]
    self.assertEqual(clock['known_seconds'],14400)
    self.assertEqual(clock['accelerated_seconds'],14400*(care+muscle))
    self.assertEqual(B.clock_extra_bound(clock),14400 if care and muscle else 0)
    self.assertEqual(p.injuries,2)
    self.t,p=self.restore(self.t,p)
    before=p.spec[I.CLOCK]['accelerated_seconds']
    self.e.advance_time(3600,[p])
    self.assertEqual(p.spec[I.CLOCK]['accelerated_seconds']-before,3600*muscle)
    self.assertEqual(B.care_injury_bonus(self.e,p),0)
    self.assertTrue(self.e.validate_state()['valid'])

 def test_caretaker_historical_credit_survives_provider_loss_but_future_bonus_does_not(self):
  import downtime as D,injury_recovery as I
  _,studies=self.book('caretaker');p=self.pokemon();self.synthetic(p)
  self.e.gm.set_injuries(p,value=2,reason='actual injury before shared rest')
  B.care_for(self.e,self.t,[p],rest_id='actual/history',reason='actual care')
  D.rest_many(self.e,[self.t,p],240,rest_id='actual/history')
  historical=deepcopy(p.spec[I.CLOCK]['study_book_acceleration'])
  B.withdraw(self.e,self.t,studies[1]['source_id']);G.revoke(p,'actual/synthetic',engine=self.e)
  self.t,p=self.restore(self.t,p)
  D.rest_many(self.e,[self.t,p],60,rest_id='actual/history')
  self.assertEqual(p.spec[I.CLOCK]['accelerated_seconds'],28800)
  self.assertEqual(p.spec[I.CLOCK]['study_book_acceleration'],historical)
  self.assertTrue(self.e.validate_state()['valid'])

 def test_caretaker_and_synthetic_each_add_one_daily_injury_without_multiplying_healed_count(self):
  import downtime as D,injury_recovery as I
  for muscle in (False,True):
   with self.subTest(synthetic=muscle):
    self.fresh();p=self.pokemon()
    if muscle:self.synthetic(p)
    self.e.gm.set_injuries(p,value=6,reason='actual injuries needing ordinary treatment')
    D.pokemon_center(self.e,p)
    self.assertEqual(I.healed_today(p),3+muscle)
    self.book('caretaker');self.e.gm.set_injuries(p,delta=1,reason='new observed injury resets actual window')
    B.care_for(self.e,self.t,[p],rest_id='actual/daily-cap',reason='actual care at native daily cap')
    before=p.injuries
    D.rest_many(self.e,[self.t,p],480 if muscle else 720,rest_id='actual/daily-cap')
    self.assertEqual((I.healed_today(p),p.injuries),(4+muscle,before-1))
    evidence=p.spec['injury_healing_history'][-1]['eligibility']
    self.assertEqual(evidence['known_seconds']+evidence['accelerated_seconds'],86400)
    self.assertEqual(p.spec['injury_healing_history'][-1]['count'],1)
    self.assertEqual(self.e.recover_injury(p),0)
    self.t,p=self.restore(self.t,p)
    self.assertTrue(self.e.validate_state()['valid'])

 def test_caretaker_late_native_payment_failure_rolls_back_the_entire_shared_rest(self):
  import trainer_feature_acquisition as A,researcher_fields as R,downtime as D
  self.rules=Rules(ROOT,ruleset='core+errata');self.fresh()
  for uid in (R.BREADTH,R.BOOKWORM):A.acquire_static(self.e,self.t,uid,acquisition_request_id=uid,selection={'edition':'book',**({'edges':[{'id':edge,'choice':None} for edge in ('edge/몬스터볼','edge/메딕-훈련','edge/브리더')]} if uid==R.BREADTH else {})})
  self.book('caretaker',payment='study');p=self.pokemon();p.hp=1
  B.care_for(self.e,self.t,[p],rest_id='actual/late-failure',payment='ap',reason='actual post-rest AP payment')
  AP.spend(self.t,AP.available(self.t))
  self.rejected(lambda:D.rest_many(self.e,[self.t,p],240,rest_id='actual/late-failure'),'AP|available|insufficient')
  self.assertNotIn('rest_interval',p.spec)
  self.assertEqual(p.hp,1)

 def test_native_medical_ap_uses_synthetic_daily_cap_but_not_pending_outside_caretaker(self):
  import injury_recovery as I
  self.book('caretaker');self.synthetic(self.t)
  self.e.gm.set_injuries(self.t,value=6,reason='actual Trainer injuries')
  B.care_for(self.e,self.t,[self.t],rest_id='actual/not-yet-resting',reason='actual pending care')
  for _ in range(4):
   out=self.e.recover_injury(self.t,source='trainer_ap',duration_minutes=1,reason='actual native medical AP treatment')
   self.assertEqual(out['recovered'],1)
  self.assertEqual((I.healed_today(self.t),self.t.injuries),(4,2))
  self.assertGreaterEqual(AP.available(self.t),2)
  before=self.e.export_state()
  self.assertIs(self.e.recover_injury(self.t,source='trainer_ap',duration_minutes=1,reason='daily cap already spent'),False)
  self.assertEqual(self.e.export_state(),before)
  self.assertEqual(B.care_injury_bonus(self.e,self.t),0)

 def test_caretaker_actual_bandage_hp_adds_rate_instead_of_multiplying_two_doublings(self):
  import downtime as D,bandages as BANDAGES,arithmetic_policy as M
  p=self.trainer('bandaged-patient',(1,0));q=self.trainer('unbandaged-patient',(2,0))
  D.rest_many(self.e,[p,q],420,rest_id='actual/prior-seven-hours')
  self.book('caretaker');self.t.spec['items']['붕대']=1
  self.e.gm.set_hp(p,value=1,reason='actual observed low HP before dressing');self.e.gm.set_hp(q,value=1,reason='actual observed low HP')
  BANDAGES.apply(self.e,self.t,target=p,minutes=1,reason='actual native dressing')
  B.care_for(self.e,self.t,[p,q],rest_id='actual/bandage-care',reason='actual shared bandaged rest')
  D.rest_many(self.e,[self.t,p,q],240,rest_id='actual/bandage-care')
  rule=self.rules.mech('combat/resting')['rest_heal']
  expected=min(p.max_hp,1+(60//rule['per_minutes'])*M.product(p.base_max_hp,'3/16'))
  self.assertEqual(p.hp,expected)
  self.assertEqual(q.hp,min(q.max_hp,1+(60//rule['per_minutes'])*M.product(q.base_max_hp,'1/8')))
  self.assertTrue(self.e.validate_state()['valid'])

 def test_caretaker_acceleration_cannot_be_invented_by_loosening_the_generic_clock_bound(self):
  import downtime as D,injury_recovery as I
  self.book('caretaker');p=self.pokemon();self.synthetic(p)
  self.e.gm.set_injuries(p,value=2,reason='actual injury')
  B.care_for(self.e,self.t,[p],rest_id='actual/integrity',reason='actual shared rest')
  D.rest_many(self.e,[self.t,p],240,rest_id='actual/integrity')
  before=deepcopy(p.spec)
  changes=(lambda c:c[I.CLOCK].update(accelerated_seconds=43200),
   lambda c:c[I.CLOCK]['study_book_acceleration'][0].update(seconds=28800),
   lambda c:c[I.CLOCK].update(study_book_acceleration=[]))
  for change in changes:
   p.spec.clear();p.spec.update(deepcopy(before));change(p.spec)
   with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  p.spec.clear();p.spec.update(before)
  self.assertTrue(self.e.validate_state()['valid'])


import state_grants as G
