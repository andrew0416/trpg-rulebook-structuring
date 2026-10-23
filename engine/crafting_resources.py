"""Shared typed crafting balances and source-owned transformation receipts.
Scrap kinds are open names, not a closed list of craftable products. Quantity
resources and monetary material values retain separate units in every receipt.
"""
from copy import deepcopy
from dataclasses import dataclass
import common_checks as C
import equipment_item_contracts as EQUIPMENT

SOURCE='ch09-equipment/제작-키트'
SHARDS={'빨강':('불꽃','페어리','에스퍼'),'주황':('노말','격투','드래곤'),
 '노랑':('전기','바위','강철'),'초록':('벌레','풀','땅'),'파랑':('물','얼음','비행'),'보라':('독','악','고스트')}
EXAMPLE_KINDS=EQUIPMENT.SCRAP_EXAMPLE_KINDS
# ch09:415-419 and ch04:2043. Display/catalog categories are not scrap kinds.
SOURCE_ITEM_KINDS={
 'item/미끼':'음식','item/미끼-2':'음식',
 **dict.fromkeys(('item/벌레회피스프레이','item/실버스프레이','item/골드스프레이','item/오물탄','item/오물탄-1',
   'item/오물탄-격노','item/오물탄-독','item/오물탄-마비','item/오물탄-잠듦','item/오물탄-혼란','item/오물탄-화상'),'스프레이'),
 **dict.fromkeys(('item/콘테스트-장신구','item/콘테스트-옷','item/멋진-옷','item/고고고글','item/방진고글','item/겨울망토',
   'item/기합의머리띠','item/기합의띠','item/무사태평향로','item/행운의향로','item/만복향로'),'패션 도구')}


def _name(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' must be nonempty text')
 return value


def _wallet(spec,field):
 wallet=spec.get(field,{})
 if not isinstance(wallet,dict):raise ValueError(field+' must be a named resource balance')
 for key,value in wallet.items():
  _name(key,field+' resource kind');C.integer(value,field+' balance',0)
  if field=='crafting_scrap':EQUIPMENT.validate_scrap_balance_kind(key)
  if field=='shards' and key not in SHARDS:raise ValueError('unknown source shard color')
 return wallet


def validate(actor):
 for field in ('crafting_scrap','shards'):_wallet(actor.spec,field)
 if 'cooking_materials_value' in actor.spec:C.integer(actor.spec['cooking_materials_value'],'cooking material value',0)
 history=actor.spec.get('resource_transformations',[])
 if not isinstance(history,list):raise ValueError('resource transformation history must be a list')
 for index,record in enumerate(history,1):
  if not isinstance(record,dict) or record.get('id')!='transform-'+str(index):raise ValueError('resource transformation sequence is inconsistent')
  if record.get('operation') not in ('cook_poffins','dismantle','craft_item','craft_gem','harvest_berry','cook_chef_food'):raise ValueError('unsupported transformation operation')
  if record.get('actor_id')!=actor.entity_id:raise ValueError('transformation belongs to another actor')
  sources=record.get('sources')
  if not isinstance(sources,list) or not sources:raise ValueError('transformation needs its actual rule sources')
  for source in sources:_name(source,'transformation source')
  start=C.integer(record.get('started_at'),'transformation start',0)
  C.integer(record.get('completed_at'),'transformation completion',start)
  details=record.get('result')
  if not isinstance(details,dict) or details.get('activity')!=record['operation']:raise ValueError('transformation must retain its native result')
  if record['operation']=='harvest_berry':
   import cultivation_harvest as HARVEST
   HARVEST.validate_result(actor,record)
  if 'recipe_definition' in details:
   import crafting_recipes as RECIPES
   recipe=RECIPES.declaration(details['recipe_definition'])
   if (details.get('recipe_id')!=recipe['id'] or details.get('recipe_source')!=recipe['source']
       or details.get('item_id')!=recipe['output']['item_id'] or details.get('item')!=recipe['output']['key']):
    raise ValueError('transformation recipe and actual result disagree')
   C.integer(details.get('count'),'recipe product count',1)
  if details.get('classification_reason') is not None:_name(details['classification_reason'],'source-related material classification reason')
  changes=record.get('resources')
  if not isinstance(changes,list) or not changes and not details.get('product_instance_ids') and not (record['operation']=='harvest_berry' and details.get('count')==0):raise ValueError('transformation must retain actual input/output changes')
  seen=set()
  for change in changes:
   if not isinstance(change,dict):raise ValueError('resource change must be a record')
   field=change.get('field');key=change.get('key');unit='value' if field in ('crafting_scrap','money','cooking_materials_value') else 'count'
   if field not in ('crafting_scrap','money','cooking_materials_value','items','shards','poffin_batches','chef_batches') or change.get('unit')!=unit:raise ValueError('resource change uses the wrong unit')
   if field in ('money','cooking_materials_value'):
    if key is not None:raise ValueError('scalar material value has no sub-kind')
   else:_name(key,'changed resource kind')
   if (field,key) in seen:raise ValueError('resource change counted twice')
   seen.add((field,key))
   before=C.integer(change.get('before'),'resource balance before',0);after=C.integer(change.get('after'),'resource balance after',0)
   delta=C.integer(change.get('delta'),'resource change')
   if before==after or delta!=after-before:raise ValueError('resource receipt arithmetic is inconsistent')
 return history


def item_kind(header,*,declared=None,reason=None):
 """Use established source relationships; preserve a reasoned open-kind ruling.
 A known item's category cannot be relabelled to bypass matching material cost.
 """
 known=SOURCE_ITEM_KINDS.get(header['id'])
 if known is None and header.get('category') in ('음식','약','몬스터볼'):known=header['category']
 return EQUIPMENT.scrap_kind(header,known=known,declared=declared,reason=reason)


@dataclass(frozen=True)
class ValueCost:
 kind:str
 total:int
 scrap:int
 money:int


def prepare_cost(actor,kind,total,scrap):
 validate(actor);EQUIPMENT.validate_scrap_balance_kind(kind)
 C.integer(total,'source recipe cost',0);C.integer(scrap,'selected scrap value',0,total)
 money=C.integer(actor.spec.get('money',0),'owned money',0)
 if actor.spec.get('crafting_scrap',{}).get(kind,0)<scrap or money<total-scrap:raise ValueError('insufficient matching scrap or money')
 return ValueCost(kind,total,scrap,total-scrap)


def pay_cost(actor,plan):
 if not isinstance(plan,ValueCost):raise ValueError('prepared material value cost required')
 checked=prepare_cost(actor,plan.kind,plan.total,plan.scrap)
 if checked!=plan:raise ValueError('material cost changed after admission')
 wallet=actor.spec.setdefault('crafting_scrap',{});wallet[plan.kind]=wallet.get(plan.kind,0)-plan.scrap
 actor.spec['money']=actor.spec.get('money',0)-plan.money


def snapshot(actor):
 validate(actor);values={}
 for field in ('crafting_scrap','shards','items'):
  for key,value in _wallet(actor.spec,field).items():values[(field,key)]=value
 for field in ('money','cooking_materials_value'):values[(field,None)]=C.integer(actor.spec.get(field,0),field,0)
 batches=actor.spec.get('poffin_batches',{})
 if not isinstance(batches,dict):raise ValueError('Poffin batches must be a mapping')
 for key,batch in batches.items():
  _name(key,'Poffin batch identity')
  if not isinstance(batch,dict):raise ValueError('Poffin batch must be a record')
  values[('poffin_batches',key)]=C.integer(batch.get('count'),'Poffin batch count',0)
 chef=actor.spec.get('chef_batches',{})
 if not isinstance(chef,dict):raise ValueError('Chef batches must be a mapping')
 for key,batch in chef.items():
  _name(key,'Chef batch identity')
  if not isinstance(batch,dict):raise ValueError('Chef batch must be a record')
  values[('chef_batches',key)]=C.integer(batch.get('count'),'Chef batch count',0)
 return values


def record(engine,actor,*,operation,sources,started_at,before,result):
 after=snapshot(actor);changes=[]
 for field,key in sorted(set(before)|set(after),key=lambda entry:(entry[0],entry[1] or '')):
  old=before.get((field,key),0);new=after.get((field,key),0)
  if old!=new:changes.append(dict(field=field,key=key,unit='value' if field in ('crafting_scrap','money','cooking_materials_value') else 'count',before=old,after=new,delta=new-old))
 history=actor.spec.setdefault('resource_transformations',[])
 receipt=dict(id='transform-'+str(len(history)+1),actor_id=actor.entity_id,operation=operation,sources=list(dict.fromkeys(sources)),started_at=started_at,completed_at=engine.elapsed_seconds,resources=changes,result=deepcopy(result))
 history.append(receipt);validate(actor)
 return deepcopy(receipt)
