"""PTK equipment/crafting activities (ch09:381-412), native inventory and time.
Unknown site, recipe timing, and tied Poffin flavor choices stay explicit GM facts.
"""
import arithmetic_policy as M
from collections import Counter
from copy import deepcopy
import common_checks as C
import crafting_recipes as RECIPES_CORE
import skill_modifiers as SKILL

import crafting_resources as RESOURCES
SHARDS=RESOURCES.SHARDS
BERRIES={name:stat for stat,names in {
 '근사함':('버치열매','라즈열매','무화열매'),'아름다움':('유루열매','블리열매','위키열매'),
 '귀여움':('복슝열매','나나열매','마고열매'),'슬기로움':('복분열매','서배열매','아바열매'),
 '강인함':('배리열매','파인열매','파야열매')}.items() for name in names}
POFFIN_ALTERNATIVES={'메호키열매':('근사함','아름다움'),'자야열매':('귀여움','아름다움'),'슈박열매':('귀여움','슬기로움'),'두리열매':('슬기로움','강인함'),'루베열매':('근사함','강인함')}
# ch09:383-398 source prices; normalized equipment category matches inventory.csv.
KIT_PRICES={'화학 세트':1000,'요리 세트':1000,'다우징 로드':2000,'포핀 혼합기':500,'몬스터볼 공구함':500,'나무열매플랜터':2000}
RECIPES={'몬스터볼':('basic_balls','몬스터볼',100,'몬스터볼 공구함'),
 '슈퍼볼':('basic_balls','몬스터볼',175,'몬스터볼 공구함'),
 '초코바':('basic_cooking','음식',50,'요리 세트'),'이유식':('basic_cooking','음식',50,'요리 세트'),
 '벌레회피스프레이':('repel_crafter','스프레이',100,'화학 세트'),'실버스프레이':('repel_crafter','스프레이',150,'화학 세트')}
ADVANCED_BALLS=('다크볼','다이브볼','힐볼','럭셔리볼','네트볼','네스트볼','퀵볼','리피트볼','타이머볼')
RECIPES.update({name:('ball_crafter','몬스터볼',700,'몬스터볼 공구함') for name in ADVANCED_BALLS})

def _p():
 import pokemon_activities
 return pokemon_activities

def _selected(e,uid):
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected equipment variant needs its own crafting policy')

def _duration(e,minutes,reason):
 _p()._outside(e);C.integer(minutes,'GM activity duration minutes',1);_p()._text(reason,'GM duration decision')

CRAFTING_SOURCE=RECIPES_CORE.CRAFTING_SOURCE

def _day(actor):return actor.spec.get('frequency_state',{}).get('day',0)

def dowse(e,actor,*,outdoors,rock_or_sand=False,reroll_sixes=False,fixed=None):
 import state_grants as G
 return G.transition(e,actor,lambda se,sa:_dowse(se,sa,outdoors=outdoors,rock_or_sand=rock_or_sand,reroll_sixes=reroll_sixes,fixed=fixed))


def _dowse(e,actor,*,outdoors,rock_or_sand=False,reroll_sixes=False,fixed=None):
 """One 10-minute use; paths select individual sixes, e.g. {'0','0.1'}.
 A True decision repeats every six. Each six grants its shard before rerolling.
 """
 RESOURCES.validate(actor)
 P=_p();P._outside(e);P._tool(actor,'다우징 로드');_selected(e,'item/다우징-로드')
 if outdoors is not True or type(rock_or_sand) is not bool:raise ValueError('explicit outdoor site and rock/sand condition required')
 rank=SKILL.effective_rank(e.r,actor,'오컬트학');count=rank+int(rock_or_sand)
 import skill_stunts as STUNTS
 if STUNTS.for_dowsing(e,actor):count+=1
 count+=__import__('researcher_fields').dowsing_bonus(e,actor)
 record=actor.spec.get('dowsing',{})
 used=record.get('uses',0) if record.get('day')==_day(actor) else 0
 C.integer(used,'dowsing daily uses',0)
 if used>=M.ratio(rank,2):raise ValueError('daily Dowsing Rod allowance exhausted')
 import roll_pools as POOLS
 gained=Counter()
 def award(path,face):
  color=e.rng.choice(tuple(SHARDS)) if face>=4 else None
  if color:gained[color]+=1
  return {'shard':color}
 results=POOLS.recursive(e.rng,count,repeat=reroll_sixes,fixed=fixed,on_face=award)
 # The shared transition commits clock, rolls and inventory together.
 e.advance_time(600,[actor])
 wallet=actor.spec.setdefault('shards',{})
 for color,number in gained.items():wallet[color]=wallet.get(color,0)+number
 actor.spec['dowsing']={'day':_day(actor),'uses':used+1}
 return {'activity':'dowse','pool':count,'results':results,'gained':dict(gained),'remaining_uses':M.ratio(rank,2)-used-1}

def _inventory(actor,name,count):
 inv=actor.spec.get('items',{});names=(name,'item/'+name)+(('힘의 뿌리','item/힘의 뿌리') if name=='힘의뿌리' else ())
 key=next((k for k in names if type(inv.get(k)) is int and inv[k]>=count),None)
 if key is None:raise ValueError('insufficient owned items: '+name)
 return key

def _cook_poffins(e,actor,*,ingredients,minutes,reason,tie_choice=None):
 P=_p();_duration(e,minutes,reason);P._tool(actor,'포핀 혼합기');_selected(e,'item/포핀-혼합기')
 if not isinstance(ingredients,dict) or not ingredients:raise ValueError('owned Poffin berries required')
 selected={};total=0
 for name,number in ingredients.items():
  if name not in BERRIES and name not in POFFIN_ALTERNATIVES:raise ValueError('selected ingredient must be a sourced Poffin berry')
  C.integer(number,'berry count',1);key=_inventory(actor,name,number)
  effects,header=e.r.item_effects(name);price=header.get('price');C.integer(price,'source berry price',1)
  selected[name]=(key,number);total+=price*number
 if total>500:raise ValueError('Poffin ingredients must total exactly 500')
 materials=actor.spec.get('cooking_materials_value',0);C.integer(materials,'owned cooking materials value',0)
 remainder=500-total
 if materials<remainder:raise ValueError('insufficient cooking ingredient value')
 biggest=max(ingredients.values());dominant={stat for name,count in ingredients.items() if count==biggest for stat in ((BERRIES[name],) if name in BERRIES else POFFIN_ALTERNATIVES[name])}
 if len(dominant)>1:
  if tie_choice not in dominant:raise ValueError('GM must resolve equal dominant berry types')
  stat=tie_choice
 else:
  stat=next(iter(dominant))
  if tie_choice is not None and tie_choice!=stat:raise ValueError('GM tie choice cannot replace a unique dominant berry')
 serial=actor.spec.get('poffin_batch_serial',0)+1;batch_id='poffin-'+str(serial)
 e.advance_time(minutes*60,[actor])
 for key,number in selected.values():actor.spec['items'][key]-=number
 actor.spec['cooking_materials_value']=materials-remainder
 batch={'id':batch_id,'count':2,'contest_stat':stat,'ingredients':dict(ingredients),'value':500,'source':'item/포핀-혼합기','duration_reason':reason}
 actor.spec.setdefault('poffin_batches',{})[batch_id]=batch;actor.spec['poffin_batch_serial']=serial
 return {'activity':'cook_poffins','batch':deepcopy(batch)}

def feed_poffin(e,actor,*,batch_id,target,minutes,reason,accepted=True):
 _duration(e,minutes,reason);_p()._pokemon(target)
 if type(accepted) is not bool:raise ValueError('recipient acceptance must be explicit')
 if not accepted:return {'activity':'feed_poffin','status':'refused'}
 if target.fainted or target.dead or target.hp<=0:raise ValueError('conscious Poffin recipient required')
 batch=actor.spec.get('poffin_batches',{}).get(batch_id)
 if not isinstance(batch,dict) or type(batch.get('count')) is not int or batch['count']<1 or batch.get('contest_stat') not in BERRIES.values():raise ValueError('owned produced Poffin batch required')
 import poffin_state as POFFINS
 history=POFFINS.history(target);cap=POFFINS.consumption_limit(target,engine=e)
 has_grace=POFFINS.grace(target,engine=e)
 maximum=8 if has_grace else 6
 if cap<maximum and len(history)>=cap:raise ValueError('level Poffin allowance reached')
 e.advance_time(minutes*60,[actor,target]);batch['count']-=1
 if len(history)<cap:target.spec.setdefault('poffins',[]).append(batch['contest_stat']);effective=True
 else:effective=False
 target.spec.setdefault('poffin_consumption',[]).append({'batch_id':batch_id,'from_trainer':actor.spec['id'],'stat':batch['contest_stat'],'effective':effective,'benefit_source':POFFINS.GRACE if effective and has_grace and len(history)>=cap-2 else 'contest/poffins','owner_id':target.spec.get('trainer_id')})
 return {'activity':'feed_poffin','effective':effective,'contest_stat':batch['contest_stat']}

def _dismantle(e,actor,*,item,count=1,scrap_kind=None,scrap_reason=None,held_selection=None):
 _p()._outside(e);C.integer(count,'intact item count',1)
 effects,header=e.r.item_effects(item)
 if not header.get('id'):raise ValueError('actual selected intact item definition required')
 name=e.r.items_mech.get(header['id'],{}).get('name') or item.removeprefix('item/')
 inventory=actor.spec.get('items',{})
 stock=None
 if held_selection is not None:
  import item_stock as STOCK
  stock=STOCK.prepare(e,actor,header['id'],held_selection=held_selection,count=count)
  key=header['id']
 else:key=item if type(inventory.get(item)) is int and inventory[item]>=count else _inventory(actor,name,count)
 if any(x in actor.spec.get('damaged_items',[]) for x in (name,'item/'+name,header['id'],key)):raise ValueError('only intact inventory items can be dismantled')
 price=header.get('price',KIT_PRICES.get(name));category=RESOURCES.item_kind(header,declared=scrap_kind,reason=scrap_reason)
 C.integer(price,'source item price',1)
 if not category:raise ValueError('source crafting category required')
 _selected(e,header['id']);value=M.ratio(price*count,2)
 if stock is not None:stock=STOCK.debit(e,actor,stock)
 else:actor.spec['items'][key]-=count
 wallet=actor.spec.setdefault('crafting_scrap',{});wallet[category]=wallet.get(category,0)+value
 return {'activity':'dismantle','category':category,'value':value,'classification_reason':scrap_reason,**({'input_stock':stock} if stock else {})}

RESEARCH_SOURCE='ch04-trainer-classes/프로페셔널-클래스/연구원-연구-분야'
CHEF_SOURCE='ch04-trainer-classes/프로페셔널-클래스'
CHEF_CLASS='class/요리사'
RESTORATIVE_RECIPES={'해독제','마비치료제','화상치료제','얼음상태치료제','상처약'}
MEAL_RECIPES={'맛있는물':(3,40),'미네랄사이다':(4,65),'후르츠밀크':(5,125),'튼튼밀크':(6,250)}

def _researcher(e,actor,field):
 import researcher_features as RF
 return RF.researcher(e,actor,RF.field_id(field))

def _recipe_item(e,item):
 """A reviewed recipe binds its exact output; a same-name variant is not that recipe."""
 names=(*RECIPES,*RESTORATIVE_RECIPES,*MEAL_RECIPES)
 identities={name:'item/'+name.replace(' ','-') for name in names}
 # ch09:418 is the scrap category heading; inventory.csv:R3 is the product.
 identities['몬스터볼']='item/몬스터볼-2'
 name=next((name for name,uid in identities.items() if item in (name,uid)),None)
 if name is None:raise ValueError('source-reviewed recipe definition required')
 uid=identities[name]
 _selected(e,uid)
 if e.r.item_effects(uid)[1].get('id')!=uid:raise ValueError('selected recipe output changed')
 return name,uid


def _recipe(e,actor,item,*,item_id,inventory_key,seconds):
 P=_p()
 requirements=[]
 if item in RECIPES:
  feature,category,unit,tool=RECIPES[item]
  source,aliases,prerequisites=P.FEATURES[feature]
  requirements.append({'kind':'owned','fields':['edges' if source.startswith('edge/') else 'feats'],'names':[source,*aliases]})
  if feature=='ball_crafter':
   import source_context as SOURCE,hobbyist as H
   SOURCE.verified_source(e.r,{'file':'input/ch03-skills-edges-feats.md','sha256':H.GENERAL},label='printed Poké Ball Crafter recipes')
   if e.r.selection.units[source]['source']['lines']!=[892,895]:raise ValueError('exact nine Poké Ball Crafter recipes required')
   requirements.extend({'kind':'owned','fields':['edges'],'names':[parent]} for parent in ('edge/몬스터볼','edge/몬스터볼-수리'))
  if prerequisites:requirements.append({'kind':'any','conditions':[{'kind':'skill','skill':skill,'rank':rank,'effective':False} for skill,rank in prerequisites]})
 elif item in RESTORATIVE_RECIPES:
  _researcher(e,actor,'약사')
  import researcher_fields as RESEARCH
  RESEARCH.qualify(e,actor,RESEARCH.APOTHECARY)
  source=RESEARCH_SOURCE
  owned_names=['약사','Apothecary'] if any(x in ('약사','Apothecary') for x in actor.spec.get('feats',[])) else ['class/연구원']
  requirements.extend(({'kind':'owned','fields':['feats','classes'],'names':owned_names},{'kind':'skill','skill':'의학','rank':3,'effective':False}))
  category,unit,tool='약',100,'화학 세트'
 elif item in MEAL_RECIPES:
  source=CHEF_SOURCE
  minimum,unit=MEAL_RECIPES[item]
  requirements.extend(({'kind':'owned','fields':['classes','feats'],'names':[CHEF_CLASS,'요리사','Chef']},
    {'kind':'owned','fields':['edges'],'names':[P.FEATURES['basic_cooking'][0],*P.FEATURES['basic_cooking'][1]]},
    {'kind':'skill','skill':'직감','rank':3,'effective':False},
    {'kind':'skill','skill':'직감','rank':minimum,'effective':True}))
  category,tool='음식','요리 세트'
 else:raise ValueError('source-reviewed recipe required')
 tool_id='item/화학-세트-1' if tool=='화학 세트' else e.r.item_effects(tool)[1]['id']
 rows=[{'id':'permission','condition':{'kind':'all','conditions':requirements},'reason':'acquired recipe provider and actual skill prerequisite required'},
       {'id':'tool','condition':{'kind':'tool','item_id':tool_id,'names':[tool],'instance_id':None},'reason':'required equipment is not accessible: '+tool}]
 return {'id':'native:'+item_id,'source':source,'output':{'item_id':item_id,'key':inventory_key},
   'requirements':rows,'materials':[{'id':'cost','options':[{'kind':'value','category':category,'amount':unit,'scrap':True,'money':True}]}],'seconds':seconds}

def _craft_item(e,actor,*,item=None,recipe=None,count=1,scrap_value=0,minutes=None,reason,inputs=None):
 if recipe is not None:
  if item is not None or minutes is not None or scrap_value:raise ValueError('authored recipe uses its own timing and material selections')
  return RECIPES_CORE.perform(e,actor,recipe,count=count,inputs=inputs,reason=reason)
 if inputs is not None:raise ValueError('native recipe material selection uses scrap_value')
 _duration(e,minutes,reason)
 requested=item;item,item_id=_recipe_item(e,item)
 ambiguous=len([uid for uid in e.r.selection.names.get(item,()) if uid.startswith('item/')])>1
 inventory_key=item_id if requested==item_id or ambiguous else item
 recipe=_recipe(e,actor,item,item_id=item_id,inventory_key=inventory_key,seconds=minutes*60)
 return RECIPES_CORE.perform(e,actor,recipe,count=count,inputs={'cost':{'option':0,'scrap_value':scrap_value}},reason=reason)

def cook_poffins(e,actor,**options):
 import transformation_use as T
 return T.dispatch(e,actor,'cook_poffins',**options)

def dismantle(e,actor,**options):
 import transformation_use as T
 return T.dispatch(e,actor,'dismantle',**options)

def craft_item(e,actor,**options):
 import transformation_use as T
 return T.dispatch(e,actor,'craft_item',**options)

def craft_gem(e,actor,**options):
 import transformation_use as T
 return T.dispatch(e,actor,'craft_gem',**options)

ACTIVITIES={'dowse':dowse,'cook_poffins':cook_poffins,'feed_poffin':feed_poffin,'dismantle':dismantle,'craft_item':craft_item}


def _craft_gem(e,actor,*,color,gem_type,minutes,reason):
 _duration(e,minutes,reason)
 source,aliases,prerequisites=_p().FEATURES['gem_lore']
 if color not in SHARDS or gem_type not in SHARDS[color]:raise ValueError('gem type must correspond to the owned shard color')
 item=gem_type+'주얼'
 recipe={'id':'native:gem:'+gem_type,'source':source,'output':{'item_id':'item/'+item,'key':item},
  'requirements':[{'id':'permission','condition':{'kind':'all','conditions':[
    {'kind':'owned','fields':['edges'],'names':[source,*aliases]},
    {'kind':'any','conditions':[{'kind':'skill','skill':skill,'rank':rank,'effective':False} for skill,rank in prerequisites]}]},
    'reason':'acquired Gem Lore and actual skill prerequisite required'}],
  'materials':[{'id':'shard','options':[{'kind':'shard','color':color,'amount':1}]}],'seconds':minutes*60}
 return dict(RECIPES_CORE.perform(e,actor,recipe,reason=reason,operation='craft_gem'),color=color)

def _planter_policy(e,selection):
 import cultivation_state as PLANTS
 return PLANTS.variant(e.r,selection)


def _cultivation(e):
 import cultivation_state as PLANTS
 return PLANTS.policy(e.r,'cultivation')


def _top_tier(e,actor,required=True):
 P=_p();owned=actor.spec.get('feats',[])
 if '최상급 열매' not in owned and 'Top Tier Berries' not in owned and 'feat/최상급-열매' not in owned:
  if required:raise ValueError('actual acquired Top Tier Berries required')
  return 0
 _researcher(e,actor,'식물학');P._feature(e,actor,'green_thumb')
 return max(SKILL.effective_rank(e.r,actor,'일반 지식'),SKILL.effective_rank(e.r,actor,'생존'))

def _crop(e,actor,name):
 import cultivation_state as PLANTS
 data=_cultivation(e);crop=PLANTS.crop(e.r,name)
 if crop['kind']=='berry':
  if crop['tier']>1 and _top_tier(e,actor)<(3 if crop['tier']==2 else 5):raise ValueError('Top Tier Berries effective rank is insufficient')
 elif crop['kind']=='herb':
  if name not in data['herbs']:raise ValueError('cultivation acquisition source is unresolved for this plant')
  if _top_tier(e,actor)<data['herbs'][name]['rank']:raise ValueError('Top Tier herb/mushroom effective rank is insufficient')
 return crop


TIER1_BERRIES={'버치열매','유루열매','복슝열매','복분열매','배리열매','오랭열매','시몬열매','라즈열매','블리열매','나나열매','서배열매','파인열매'}

def plant_berry(e,actor,**options):
 return _plant_berry(e,actor,**options)


def _plant_berry(e,actor,*,berry,plant_id,planter_slot=None,planter_policy=None,soft_soil=False):
 import cultivation_growth as GROWTH
 return GROWTH.native_plant(e,actor,berry=berry,plant_id=plant_id,planter_slot=planter_slot,planter_policy=planter_policy,soft_soil=soft_soil)

def harvest_berry(e,actor,*,plant_id,environment_allows_growth=True,soil_quality=0,fixed=None,event_id=None):
 import cultivation_harvest as HARVEST
 return HARVEST.native_harvest(e,actor,plant_id=plant_id,environment_allows_growth=environment_allows_growth,soil_quality=soil_quality,fixed=fixed,event_id=event_id)


def _harvest_berry(e,actor,*,plant_id,environment_allows_growth=True,soil_quality=0,fixed=None):
 return harvest_berry(e,actor,plant_id=plant_id,environment_allows_growth=environment_allows_growth,soil_quality=soil_quality,fixed=fixed)

ACTIVITIES.update(craft_gem=craft_gem,plant_berry=plant_berry,harvest_berry=harvest_berry)
